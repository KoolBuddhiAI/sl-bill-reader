"""Vision mode: send the page images to any vision-capable model profile."""

from bill_reader.extract.base import ExtractionResult
from bill_reader.extract.prompts import EXTRACTION_SYSTEM, PDF_TEXT_HINT, VISION_USER
from bill_reader.llm import LLMClient
from bill_reader.preprocess import PreparedDocument
from bill_reader.schemas import BillExtraction


class VisionLLMExtractor:
    mode = "vision"

    def __init__(self, client: LLMClient):
        self.client = client
        self.name = f"{client.profile.name} (vision)"

    def extract(self, doc: PreparedDocument) -> ExtractionResult:
        user = VISION_USER
        if doc.text_layer.strip():
            user += PDF_TEXT_HINT.format(text=doc.text_layer[:8000])
        extraction, resp = self.client.complete_structured(
            EXTRACTION_SYSTEM, user, BillExtraction, images=doc.page_jpegs
        )
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
