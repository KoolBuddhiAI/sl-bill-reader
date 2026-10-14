"""Walk the configured profile chain until one extraction is confident enough (FR-11)."""

import logging
from collections.abc import Callable

from bill_reader.extract.base import ExtractionFailed, ExtractionResult, Extractor, OcrEngine
from bill_reader.extract.ocr_text import OcrTextLLMExtractor
from bill_reader.extract.vision import VisionLLMExtractor
from bill_reader.llm import LLMClient, LLMError, ModelProfile, make_client
from bill_reader.preprocess import PreparedDocument
from bill_reader.validate import validate

log = logging.getLogger(__name__)


class ExtractionOrchestrator:
    def __init__(
        self,
        chain: list[ModelProfile],
        *,
        ocr: OcrEngine | None = None,
        last_resort: Extractor | None = None,
        fallback_confidence: float = 0.5,
        home_currency: str = "LKR",
        client_factory: Callable[[ModelProfile], LLMClient] = make_client,
    ):
        self.chain = chain
        self.ocr = ocr if ocr is not None and ocr.is_available() else None
        self.last_resort = last_resort
        self.fallback_confidence = fallback_confidence
        self.home_currency = home_currency
        self.client_factory = client_factory

    def _extractor_for(self, profile: ModelProfile, ocr_cache: dict) -> Extractor:
        if not profile.has_key:
            raise LLMError(f"{profile.api_key_env} not set")
        client = self.client_factory(profile)
        if profile.supports_vision:
            return VisionLLMExtractor(client)
        if self.ocr is None:
            raise LLMError("text-only model needs OCR, but Surya is not installed")
        return OcrTextLLMExtractor(client, self.ocr, ocr_cache)

    def _finish(self, result: ExtractionResult) -> ExtractionResult:
        report = validate(result.extraction, self.home_currency)
        result.warnings = report.warnings
        result.overall_confidence = report.overall_confidence
        return result

    def run(self, doc: PreparedDocument) -> ExtractionResult:
        attempts: list[str] = []
        best: ExtractionResult | None = None
        ocr_cache: dict = {}
        for profile in self.chain:
            try:
                result = self._finish(self._extractor_for(profile, ocr_cache).extract(doc))
            except LLMError as exc:
                attempts.append(f"{profile.name}: {exc}")
                log.warning("extraction with %s failed: %s", profile.name, exc)
                continue
            if best is None or result.overall_confidence > best.overall_confidence:
                best = result
            if result.overall_confidence >= self.fallback_confidence or result.extraction.doc_type == "not_a_bill":
                break
            attempts.append(f"{profile.name}: low confidence {result.overall_confidence:.2f}")

        if best is None and self.last_resort is not None and self.ocr is not None:
            try:
                best = self._finish(self.last_resort.extract(doc))
            except Exception as exc:  # last resort must not crash the worker
                attempts.append(f"{self.last_resort.name}: {exc}")
        if best is None:
            raise ExtractionFailed(attempts)
        best.log = [a for a in attempts if not a.startswith(f"{best.profile}:")]
        return best
