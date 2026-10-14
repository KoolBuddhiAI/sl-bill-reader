"""OCR+text mode: OCR the pages locally, then let any (text-only) model interpret the lines."""

from bill_reader.extract.base import ExtractionResult, OcrEngine, OcrLine
from bill_reader.extract.prompts import EXTRACTION_SYSTEM, OCR_USER
from bill_reader.llm import LLMClient
from bill_reader.preprocess import PreparedDocument
from bill_reader.schemas import FIELD_NAMES, BillExtraction


def format_lines(lines: list[OcrLine]) -> str:
    return "\n".join(f"[{line.id}] (p{line.page}) {line.text}" for line in lines)


def boxes_from_line_ids(extraction: BillExtraction, lines: list[OcrLine]) -> None:
    """Replace model-reported line ids with the union box of those OCR lines."""
    by_id = {line.id: line for line in lines}
    for name in FIELD_NAMES:
        fv = extraction.field(name)
        hits = [by_id[i] for i in (fv.line_ids or []) if i in by_id]
        if hits:
            fv.page = hits[0].page
            same_page = [h for h in hits if h.page == fv.page]
            fv.bbox = [
                min(h.bbox[0] for h in same_page),
                min(h.bbox[1] for h in same_page),
                max(h.bbox[2] for h in same_page),
                max(h.bbox[3] for h in same_page),
            ]


class OcrTextLLMExtractor:
    mode = "ocr+text"

    def __init__(self, client: LLMClient, ocr: OcrEngine, lines_cache: dict | None = None):
        self.client = client
        self.ocr = ocr
        self.name = f"{client.profile.name} (ocr+text via {ocr.name})"
        self._cache = lines_cache if lines_cache is not None else {}

    def ocr_lines(self, doc: PreparedDocument) -> list[OcrLine]:
        key = id(doc)
        if key not in self._cache:
            self._cache[key] = self.ocr.read(doc.pages)
        return self._cache[key]

    def extract(self, doc: PreparedDocument) -> ExtractionResult:
        lines = self.ocr_lines(doc)
        extraction, resp = self.client.complete_structured(
            EXTRACTION_SYSTEM, OCR_USER.format(lines=format_lines(lines)), BillExtraction
        )
        boxes_from_line_ids(extraction, lines)
        return ExtractionResult(
            extraction=extraction,
            extractor=self.name,
            profile=resp.profile,
            model_id=resp.model_id,
            mode=self.mode,
            latency_ms=resp.latency_ms,
            tokens_in=resp.tokens_in,
            tokens_out=resp.tokens_out,
            raw=resp.raw,
        )
