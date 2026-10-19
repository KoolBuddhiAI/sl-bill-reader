"""Run the extraction pipeline on the sample set once per model profile and compare against ground truth."""

import json
import re
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from difflib import SequenceMatcher
from pathlib import Path

from sqlmodel import Session

from bill_reader.categorise import Categoriser, ensure_chart, normalise_supplier
from bill_reader.config import Settings
from bill_reader.db import make_engine
from bill_reader.extract.base import ExtractionFailed, OcrEngine
from bill_reader.extract.orchestrator import ExtractionOrchestrator
from bill_reader.llm import LLMClient, ModelProfile, load_models_config, make_client
from bill_reader.preprocess import prepare
from bill_reader.schemas import BillExtraction, to_decimal

SCORED_FIELDS = ("supplier_name", "bill_number", "bill_date", "total", "vat_amount", "currency", "account_code")


def supplier_matches(predicted: str | None, truth: dict) -> bool:
    if not predicted:
        return False
    p = normalise_supplier(predicted)
    for candidate in [truth["supplier_name"], *truth.get("supplier_aliases", [])]:
        t = normalise_supplier(candidate)
        if p == t or (len(t) >= 4 and (t in p or p in t)) or SequenceMatcher(None, p, t).ratio() >= 0.8:
            return True
    return False


def _alnum(value: str | None) -> str:
    return re.sub(r"[^0-9a-z]", "", (value or "").lower())


def score_field(name: str, predicted: str | None, truth: dict) -> bool | None:
    """True/False, or None when the ground truth has no value for this field (not scored)."""
    if name == "supplier_name":
        return supplier_matches(predicted, truth)
    expected = truth.get("expected_account_code") if name == "account_code" else truth.get(name)
    if expected in (None, ""):
        return None
    if name in ("total", "vat_amount"):
        p, t = to_decimal(predicted), Decimal(str(expected))
        return p is not None and abs(p - t) <= Decimal("1.00")
    if name == "bill_number":
        return _alnum(predicted) == _alnum(expected)
    return (predicted or "").strip().upper() == str(expected).strip().upper()


@dataclass
class SampleResult:
    file: str
    ok: bool
    error: str | None = None
    mode: str | None = None
    model_id: str | None = None
    latency_ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    overall_confidence: float = 0.0
    predicted: dict[str, str | None] = field(default_factory=dict)
    expected: dict[str, str | None] = field(default_factory=dict)
    scores: dict[str, bool | None] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    raw: list = field(default_factory=list)


@dataclass
class ProfileReport:
    profile: str
    model: str
    mode: str
    skipped: str | None = None
    samples: list[SampleResult] = field(default_factory=list)
    est_cost_usd: float | None = None

    def accuracy(self, name: str) -> tuple[int, int]:
        scored = [s.scores.get(name) for s in self.samples if s.scores.get(name) is not None]
        return sum(1 for v in scored if v), len(scored)

    @property
    def mean_latency_ms(self) -> int:
        done = [s.latency_ms for s in self.samples if s.ok]
        return int(sum(done) / len(done)) if done else 0


def load_ground_truth(samples_dir: Path) -> list[tuple[Path, dict]]:
    out = []
    for gt_path in sorted((samples_dir / "ground_truth").glob("*.json")):
        truth = json.loads(gt_path.read_text(encoding="utf-8"))
        out.append((samples_dir / "bills" / truth["file"], truth))
    return out


def evaluate(
    settings: Settings,
    samples_dir: Path,
    profile_names: list[str] | None = None,
    *,
    categorisation: str | None = None,
    client_factory: Callable[[ModelProfile], LLMClient] = make_client,
    ocr: OcrEngine | None = None,
    progress: Callable[[str], None] = lambda msg: None,
) -> list[ProfileReport]:
    models = load_models_config(settings)
    names = profile_names or [n for n, p in models.profiles.items() if p.has_key]
    cat_profile = models.get(categorisation or models.categorisation)
    cat_client = client_factory(cat_profile) if cat_profile.has_key else None
    cases = load_ground_truth(samples_dir)
    reports = []

    with tempfile.TemporaryDirectory() as tmp:
        scratch = Settings(data_dir=Path(tmp), config_dir=settings.config_dir, _env_file=None)
        engine = make_engine(scratch)  # fresh DB: no supplier history leaks between samples
        with Session(engine) as session:
            ensure_chart(session, scratch)
            categoriser = Categoriser(session, cat_client)
            docs = {path: prepare(path, settings) for path, _ in cases}

            for name in names:
                profile = models.get(name)
                report = ProfileReport(profile=name, model=profile.model, mode=profile.mode)
                reports.append(report)
                if not profile.has_key:
                    report.skipped = f"no API key ({profile.api_key_env})"
                    continue
                if not profile.supports_vision and (ocr is None or not ocr.is_available()):
                    report.skipped = "text-only model needs OCR (Surya not installed)"
                    continue
                orchestrator = ExtractionOrchestrator(
                    [profile], ocr=ocr, fallback_confidence=0.0, home_currency=settings.home_currency,
                    client_factory=client_factory,
                )
                for path, truth in cases:
                    progress(f"{name}: {path.name}")
                    report.samples.append(_run_sample(orchestrator, categoriser, docs[path], path, truth))
                tokens_in = sum(s.tokens_in for s in report.samples)
                tokens_out = sum(s.tokens_out for s in report.samples)
                report.est_cost_usd = profile.estimate_cost(tokens_in, tokens_out)
    return reports


def _run_sample(orchestrator, categoriser, doc, path: Path, truth: dict) -> SampleResult:
    expected = {n: (truth.get("expected_account_code") if n == "account_code" else truth.get(n)) for n in SCORED_FIELDS}
    try:
        result = orchestrator.run(doc)
    except ExtractionFailed as exc:
        return SampleResult(file=path.name, ok=False, error=str(exc), expected=expected,
                            scores={n: score_field(n, None, truth) for n in SCORED_FIELDS})
    ex: BillExtraction = result.extraction
    suggestion = categoriser.suggest(
        ex.supplier_name.value or "", [i.description or i.description_original or "" for i in ex.line_items],
        doc_hint=ex.doc_type,
    )
    predicted = {n: ex.field(n).value for n in SCORED_FIELDS if n != "account_code"}
    predicted["account_code"] = suggestion.account_code
    return SampleResult(
        file=path.name, ok=True, mode=result.mode, model_id=result.model_id, latency_ms=result.latency_ms,
        tokens_in=result.tokens_in, tokens_out=result.tokens_out, overall_confidence=result.overall_confidence,
        predicted=predicted, expected=expected, scores={n: score_field(n, predicted[n], truth) for n in SCORED_FIELDS},
        warnings=result.warnings, raw=result.raw,
    )


def _short(error: str | None, limit: int = 140) -> str:
    """First line of an error, trimmed so one failure doesn't swamp the markdown table."""
    line = (error or "").strip().splitlines()[0] if error else ""
    return line if len(line) <= limit else line[: limit - 1] + "…"


def render_markdown(reports: list[ProfileReport], categorisation: str) -> str:
    ran = [r for r in reports if not r.skipped]
    lines = [
        "# Model comparison on the sample bills",
        "",
        f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC} by `bill-reader eval`. "
        f"Account codes suggested by the `{categorisation}` profile in every run.",
        "",
        "## Accuracy per field",
        "",
        "| Profile | Model | Mode | " + " | ".join(SCORED_FIELDS) + " | Mean latency | Tokens in/out | Est. cost |",
        "|" + "---|" * (len(SCORED_FIELDS) + 6),
    ]
    for r in ran:
        cells = []
        for name in SCORED_FIELDS:
            ok, n = r.accuracy(name)
            cells.append(f"{ok}/{n}" if n else "–")
        tin, tout = sum(s.tokens_in for s in r.samples), sum(s.tokens_out for s in r.samples)
        cost = f"${r.est_cost_usd:.4f}" if r.est_cost_usd is not None else "–"
        lines.append(f"| {r.profile} | {r.model} | {r.mode} | " + " | ".join(cells)
                     + f" | {r.mean_latency_ms} ms | {tin}/{tout} | {cost} |")
    for r in reports:
        if r.skipped:
            lines.append(f"| {r.profile} | {r.model} | {r.mode} | skipped – {r.skipped} |")

    if ran:
        lines += ["", "## Total read per sample", "", "| Sample | Expected | " + " | ".join(r.profile for r in ran) + " |",
                  "|" + "---|" * (len(ran) + 2)]
        for i, sample in enumerate(ran[0].samples):
            cells = []
            for r in ran:
                s = r.samples[i]
                mark = "✅" if s.scores.get("total") else "❌"
                cells.append(f"{mark} {s.predicted.get('total') or _short(s.error) or '–'}")
            lines.append(f"| {sample.file} | {sample.expected.get('total')} {sample.expected.get('currency') or ''} | "
                         + " | ".join(cells) + " |")
        lines += ["", "## Misses", ""]
        for r in ran:
            for s in r.samples:
                misses = [f"{n}: got `{s.predicted.get(n)}`, expected `{s.expected.get(n)}`"
                          for n, v in s.scores.items() if v is False]
                if s.error:
                    misses = [f"failed: {_short(s.error)}"]
                if misses:
                    lines.append(f"- **{r.profile}** · {s.file}: " + "; ".join(misses))
    return "\n".join(lines) + "\n"


def write_reports(reports: list[ProfileReport], categorisation: str, md_path: Path, json_dir: Path) -> Path:
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(reports, categorisation), encoding="utf-8")
    json_dir.mkdir(parents=True, exist_ok=True)
    json_path = json_dir / f"eval-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    json_path.write_text(json.dumps([asdict(r) for r in reports], indent=2, ensure_ascii=False, default=str),
                         encoding="utf-8")
    return json_path
