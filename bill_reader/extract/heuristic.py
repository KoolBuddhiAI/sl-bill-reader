"""Last-resort extractor: regexes over OCR lines when every model in the chain failed.

Only fills supplier_name, bill_date and total, always with low confidence so a human
must confirm them.
"""

import re
from decimal import Decimal, InvalidOperation

from bill_reader.extract.base import ExtractionResult, OcrEngine, OcrLine
from bill_reader.preprocess import PreparedDocument
from bill_reader.schemas import BillExtraction, FieldValue
from bill_reader.validate import parse_date

TOTAL_KEYWORDS = ("total", "amount due", "එකතුව", "මුළු", "மொத்தம்")
_DATE_RE = re.compile(r"\d{1,4}\s*[/.-]\s*\d{1,2}\s*[/.-]\s*\d{2,4}")
# grouped thousands, a 2-decimal number, or a plain integer of at most 7 digits (not phone numbers)
_AMOUNT_RE = re.compile(r"(?<!\d)(?<!\d[.,])(\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+\.\d{1,2}|\d{1,7})(?![\d.,]*\d)")
_LETTER_RE = re.compile(r"[^\W\d_]")


def amounts(text: str) -> list[Decimal]:
    out = []
    for token in _AMOUNT_RE.findall(_DATE_RE.sub(" ", text)):
        try:
            out.append(Decimal(token.replace(",", "")))
        except InvalidOperation:
            continue
    return out


def _fv(value: str, line: OcrLine, confidence: float) -> FieldValue:
    return FieldValue(value=value, confidence=confidence, bbox=list(line.bbox), page=line.page, line_ids=[line.id])


def _find_total(lines: list[OcrLine]) -> FieldValue | None:
    keyed: list[tuple[Decimal, OcrLine]] = []
    for i, line in enumerate(lines):
        if any(k in line.text.lower() for k in TOTAL_KEYWORDS):
            candidates = [line] if amounts(line.text) else lines[i + 1 : i + 2]  # amount may sit on the next line
            keyed += [(a, c) for c in candidates for a in amounts(c.text)]
    if keyed:
        amount, line = max(keyed, key=lambda t: t[0])
        return _fv(f"{amount:.2f}", line, 0.4)
    every = [(a, line) for line in lines for a in amounts(line.text)]
    if every:
        amount, line = max(every, key=lambda t: t[0])
        return _fv(f"{amount:.2f}", line, 0.2)
    return None


def _find_date(lines: list[OcrLine]) -> FieldValue | None:
    for line in lines:
        for token in _DATE_RE.findall(line.text):
            parsed = parse_date(token)
            if parsed:
                return _fv(parsed.isoformat(), line, 0.4)
    return None


def _find_supplier(lines: list[OcrLine]) -> FieldValue | None:
    for line in lines:
        if line.text.strip() and _LETTER_RE.search(line.text):
            return _fv(line.text.strip(), line, 0.3)
    return None


class HeuristicExtractor:
    name = "heuristic"
    mode = "heuristic"

    def __init__(self, ocr: OcrEngine):
        self.ocr = ocr

    def extract(self, doc: PreparedDocument) -> ExtractionResult:
        lines = self.ocr.read(doc.pages)
        extraction = BillExtraction(notes="Heuristic extraction (no model available); check every field.")
        for name, finder in (("supplier_name", _find_supplier), ("bill_date", _find_date), ("total", _find_total)):
            value = finder(lines)
            if value is not None:
                setattr(extraction, name, value)
        return ExtractionResult(
            extraction=extraction,
            extractor=f"{self.name} (via {self.ocr.name})",
            profile=None,
            model_id=None,
            mode=self.mode,
        )
