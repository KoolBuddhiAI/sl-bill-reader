"""Background pipeline: preprocess → extract (profile chain) → validate → categorise → persist."""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session, delete, select

from bill_reader.categorise import Categoriser, ensure_chart, propose_tax_code
from bill_reader.config import Settings
from bill_reader.extract.base import ExtractionFailed, Extractor, OcrEngine
from bill_reader.extract.orchestrator import ExtractionOrchestrator
from bill_reader.llm import LLMClient, LLMError, ModelProfile, load_models_config, make_client
from bill_reader.models import AuditEvent, Bill, BillField, BillStatus, LineItem, utcnow
from bill_reader.preprocess import prepare
from bill_reader.schemas import FIELD_NAMES

log = logging.getLogger(__name__)


def default_ocr() -> tuple[OcrEngine | None, Extractor | None]:
    """Surya engine + heuristic last resort when the optional [surya] extra is installed."""
    try:
        from bill_reader.extract.heuristic import HeuristicExtractor
        from bill_reader.ocr.surya import SuryaOcrEngine
    except ImportError:
        return None, None
    engine = SuryaOcrEngine()
    if not engine.is_available():
        return None, None
    return engine, HeuristicExtractor(engine)


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        engine: Engine,
        *,
        client_factory: Callable[[ModelProfile], LLMClient] = make_client,
        ocr: OcrEngine | None = None,
        last_resort: Extractor | None = None,
    ):
        self.settings = settings
        self.engine = engine
        self.client_factory = client_factory
        self.ocr = ocr
        self.last_resort = last_resort

    def _categoriser_client(self, profile: ModelProfile) -> LLMClient | None:
        if not profile.has_key:
            return None
        try:
            return self.client_factory(profile)
        except LLMError:
            return None

    def process(self, bill_id: int, profile: str | None = None) -> None:
        with Session(self.engine) as session:
            bill = session.get(Bill, bill_id)
            if bill is None:
                return
            try:
                self._process(session, bill, profile)
            except ExtractionFailed as exc:
                self._fail(session, bill, "Extraction failed – " + "; ".join(exc.log or [str(exc)]))
            except Exception as exc:  # keep the worker alive; surface the reason on the bill
                log.exception("processing bill %s failed", bill_id)
                self._fail(session, bill, f"{type(exc).__name__}: {exc}")

    def _fail(self, session: Session, bill: Bill, error: str) -> None:
        session.rollback()
        bill.status, bill.error, bill.updated_at = BillStatus.failed, error, utcnow()
        session.add(bill)
        session.add(AuditEvent(bill_id=bill.id, action="failed", details={"error": error}))
        session.commit()

    def _process(self, session: Session, bill: Bill, profile_name: str | None) -> None:
        settings = self.settings
        doc = prepare(Path(bill.stored_path), settings, sha=bill.sha256)
        models = load_models_config(settings)
        chain = [models.get(profile_name)] if profile_name else models.extraction_chain()
        result = ExtractionOrchestrator(
            chain,
            ocr=self.ocr,
            last_resort=self.last_resort,
            fallback_confidence=settings.fallback_confidence,
            home_currency=settings.home_currency,
            client_factory=self.client_factory,
        ).run(doc)
        ex = result.extraction

        session.exec(delete(BillField).where(BillField.bill_id == bill.id))
        session.exec(delete(LineItem).where(LineItem.bill_id == bill.id))
        for name in FIELD_NAMES:
            fv = ex.field(name)
            session.add(
                BillField(bill_id=bill.id, name=name, value=fv.value, extracted_value=fv.value,
                          confidence=fv.confidence, bbox=fv.bbox, page=fv.page)
            )
        for idx, item in enumerate(ex.line_items):
            session.add(LineItem(bill_id=bill.id, idx=idx, **item.model_dump()))

        bill.extractor_used = result.extractor
        bill.model_profile, bill.model_id, bill.extraction_mode = result.profile, result.model_id, result.mode
        bill.latency_ms, bill.tokens_in, bill.tokens_out = result.latency_ms, result.tokens_in, result.tokens_out
        bill.overall_confidence = result.overall_confidence
        bill.doc_type, bill.languages, bill.currency = ex.doc_type, ex.languages, ex.currency.value
        bill.warnings = result.warnings + (["Earlier attempts: " + "; ".join(result.log)] if result.log else [])
        bill.raw_extraction = ex.model_dump()
        bill.paying_account = bill.paying_account or settings.default_paying_account
        bill.tax_code = propose_tax_code(ex)

        ensure_chart(session, settings)
        suggestion = Categoriser(session, self._categoriser_client(models.get(models.categorisation))).suggest(
            ex.supplier_name.value or "",
            [i.description or i.description_original or "" for i in ex.line_items],
            doc_hint=ex.doc_type,
        )
        bill.account_code, bill.account_confidence = suggestion.account_code, suggestion.confidence
        bill.account_reason = suggestion.reason

        if ex.doc_type == "not_a_bill":
            bill.status, bill.error = BillStatus.failed, "This does not look like a bill."
        else:
            bill.status, bill.error = BillStatus.needs_review, None
        bill.updated_at = utcnow()
        session.add(bill)
        session.add(
            AuditEvent(
                bill_id=bill.id,
                action="extracted",
                details={"extractor": result.extractor, "model": result.model_id, "mode": result.mode,
                         "confidence": result.overall_confidence, "earlier_attempts": result.log},
            )
        )
        session.commit()


class Worker:
    """Runs the pipeline on a thread pool; threads=0 runs inline (tests)."""

    def __init__(self, pipeline: Pipeline, threads: int = 2):
        self.pipeline = pipeline
        self.executor = ThreadPoolExecutor(max_workers=threads, thread_name_prefix="bill-worker") if threads else None

    def enqueue(self, bill_id: int, profile: str | None = None) -> None:
        if self.executor is None:
            self.pipeline.process(bill_id, profile)
        else:
            self.executor.submit(self.pipeline.process, bill_id, profile)

    def requeue_stuck(self) -> int:
        """Bills left in `processing` by a previous run are queued again."""
        with Session(self.pipeline.engine) as session:
            ids = session.exec(select(Bill.id).where(Bill.status == BillStatus.processing)).all()
        for bill_id in ids:
            self.enqueue(bill_id)
        return len(ids)

    def shutdown(self) -> None:
        if self.executor is not None:
            self.executor.shutdown(wait=False, cancel_futures=True)
