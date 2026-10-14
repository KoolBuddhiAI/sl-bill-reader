"""Extractor protocol and shared result types."""

from dataclasses import dataclass, field
from typing import Any, Protocol

from PIL import Image

from bill_reader.preprocess import PreparedDocument
from bill_reader.schemas import BillExtraction


class ExtractionFailed(RuntimeError):
    """Every extractor in the chain failed; `log` explains why per profile."""

    def __init__(self, log: list[str]):
        super().__init__("; ".join(log) or "no extractor available")
        self.log = log


@dataclass
class OcrLine:
    id: int
    text: str
    bbox: list[float]  # normalised [x0, y0, x1, y1]
    page: int = 0
    confidence: float = 1.0


class OcrEngine(Protocol):
    name: str

    def is_available(self) -> bool: ...

    def read(self, pages: list[Image.Image]) -> list[OcrLine]: ...


@dataclass
class ExtractionResult:
    extraction: BillExtraction
    extractor: str  # e.g. "glm-vision (vision)"
    profile: str | None
    model_id: str | None
    mode: str  # vision | ocr+text | heuristic
    latency_ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    overall_confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)
    log: list[str] = field(default_factory=list)  # what happened with earlier profiles in the chain
    raw: list[Any] = field(default_factory=list)


class Extractor(Protocol):
    name: str
    mode: str

    def extract(self, doc: PreparedDocument) -> ExtractionResult: ...
