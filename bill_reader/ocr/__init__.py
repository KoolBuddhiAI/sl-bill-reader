"""Local OCR engines (optional heavy dependencies, imported lazily)."""

from bill_reader.ocr.surya import SuryaOcrEngine

__all__ = ["SuryaOcrEngine"]
