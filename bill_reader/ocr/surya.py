"""Surya OCR adapter (surya-ocr 0.22.x, optional `[surya]` extra).

Surya 0.22 is a VLM: `RecognitionPredictor(SuryaInferenceManager())(images, full_page=True)`
returns one `PageOCRResult` per page whose `blocks` (in reading order) carry a pixel
`bbox`, an HTML body and a `confidence`. Blocks are split into text lines here.
"""

import html
import importlib.util
import re
import threading

from PIL import Image

from bill_reader.extract.base import OcrLine

_BREAK_RE = re.compile(r"<br\s*/?>|</(?:p|div|tr|li|h[1-6])>", re.I)
_CELL_RE = re.compile(r"</t[dh]>", re.I)
_TAG_RE = re.compile(r"<[^>]+>")


def html_to_lines(body: str) -> list[str]:
    text = _CELL_RE.sub(" ", _BREAK_RE.sub("\n", body or ""))
    text = html.unescape(_TAG_RE.sub("", text))
    return [" ".join(part.split()) for part in text.splitlines() if part.strip()]


class SuryaOcrEngine:
    name = "surya"

    def __init__(self):
        self._predictor = None
        self._lock = threading.Lock()

    def is_available(self) -> bool:
        return importlib.util.find_spec("surya") is not None

    def _load(self):
        with self._lock:
            if self._predictor is None:
                from surya.inference import SuryaInferenceManager
                from surya.recognition import RecognitionPredictor

                self._predictor = RecognitionPredictor(SuryaInferenceManager())
        return self._predictor

    def read(self, pages: list[Image.Image]) -> list[OcrLine]:
        if not pages:
            return []
        results = self._load()(pages, full_page=True)
        lines: list[OcrLine] = []
        for page_no, (img, page) in enumerate(zip(pages, results)):
            w, h = img.size
            blocks = sorted(page.blocks, key=lambda b: b.reading_order)
            for block in blocks:
                if block.skipped or block.error:
                    continue
                texts = html_to_lines(block.html)
                x0, y0, x1, y1 = block.bbox
                step = (y1 - y0) / max(len(texts), 1)  # spread multi-line blocks evenly
                for i, text in enumerate(texts):
                    top, bottom = y0 + i * step, y0 + (i + 1) * step
                    lines.append(OcrLine(
                        id=len(lines),
                        text=text,
                        bbox=[_clip(x0 / w), _clip(top / h), _clip(x1 / w), _clip(bottom / h)],
                        page=page_no,
                        confidence=float(block.confidence if block.confidence is not None else 1.0),
                    ))
        return lines


def _clip(v: float) -> float:
    return min(max(v, 0.0), 1.0)
