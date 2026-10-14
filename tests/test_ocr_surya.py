import sys
import types
from types import SimpleNamespace

import pytest
from PIL import Image

from bill_reader.extract.base import OcrLine
from bill_reader.extract.heuristic import HeuristicExtractor
from bill_reader.ocr import SuryaOcrEngine
from bill_reader.ocr import surya as surya_mod
from bill_reader.preprocess import PreparedDocument


class FakeOcr:
    name = "fake-ocr"

    def __init__(self, texts):
        self.lines = [OcrLine(i, t, [0.1, i / 20, 0.9, (i + 1) / 20]) for i, t in enumerate(texts)]

    def is_available(self):
        return True

    def read(self, pages):
        return self.lines


def doc() -> PreparedDocument:
    return PreparedDocument(pages=[Image.new("RGB", (10, 10))], page_jpegs=[b""])


def test_heuristic_picks_sinhala_total_over_cash_and_change():
    ocr = FakeOcr(["", "1234", "සමන් මෝටර්ස් SAMAN MOTORS", "Tel 0112345678", "දිනය 12/03/2024",
                   "Item A 40,000.00", "එකතුව 44,800.00", "Cash 50,000.00", "Change 5,200.00"])
    result = HeuristicExtractor(ocr).extract(doc())
    ex = result.extraction
    assert ex.total.value == "44800.00" and ex.total.line_ids == [6]
    assert ex.total.bbox == ocr.lines[6].bbox
    assert ex.bill_date.value == "2024-03-12"
    assert ex.supplier_name.value == "සමන් මෝටර්ස් SAMAN MOTORS"
    assert all(ex.field(n).confidence <= 0.4 for n in ("total", "bill_date", "supplier_name"))
    assert (result.mode, result.profile, result.model_id) == ("heuristic", None, None)


def test_heuristic_total_on_next_line_and_largest_fallback():
    ex = HeuristicExtractor(FakeOcr(["Shop", "Grand Total", "Rs. 1,250.00", "Cash 2,000"])).extract(doc()).extraction
    assert ex.total.value == "1250.00"
    ex = HeuristicExtractor(FakeOcr(["Shop", "Tea 120.00", "Bun 80.00", "Tel 0771234567"])).extract(doc()).extraction
    assert ex.total.value == "120.00" and ex.total.confidence <= 0.4
    assert ex.bill_date.value is None


def test_surya_unavailable(monkeypatch):
    monkeypatch.setattr(surya_mod.importlib.util, "find_spec", lambda name: None)
    assert SuryaOcrEngine().is_available() is False


def block(order, bbox, html, conf=0.9, skipped=False):
    return SimpleNamespace(reading_order=order, bbox=bbox, html=html, confidence=conf, skipped=skipped, error=False)


@pytest.fixture
def fake_surya(monkeypatch):
    calls = []

    class Manager:
        pass

    class Predictor:
        def __init__(self, manager):
            calls.append("init")

        def __call__(self, images, full_page=None):
            assert full_page is True
            return [
                SimpleNamespace(blocks=[
                    block(1, [0, 100, 200, 300], "<p>Total<br/>44,800.00</p>", 0.8),
                    block(0, [20, 0, 180, 50], "<h1>SAMAN &amp; SONS</h1>"),
                    block(2, [0, 0, 1, 1], "", skipped=True),
                ]),
                SimpleNamespace(blocks=[block(0, [50, 50, 100, 100], "<table><tr><td>Tea</td><td>120</td></tr></table>")]),
            ]

    surya = types.ModuleType("surya")
    inference = types.ModuleType("surya.inference")
    inference.SuryaInferenceManager = Manager
    recognition = types.ModuleType("surya.recognition")
    recognition.RecognitionPredictor = Predictor
    monkeypatch.setitem(sys.modules, "surya", surya)
    monkeypatch.setitem(sys.modules, "surya.inference", inference)
    monkeypatch.setitem(sys.modules, "surya.recognition", recognition)
    return calls


def test_surya_read_orders_and_normalises(fake_surya):
    engine = SuryaOcrEngine()
    pages = [Image.new("RGB", (200, 400)), Image.new("RGB", (100, 100))]
    lines = engine.read(pages)
    assert [(l.id, l.page, l.text) for l in lines] == [
        (0, 0, "SAMAN & SONS"), (1, 0, "Total"), (2, 0, "44,800.00"), (3, 1, "Tea 120"),
    ]
    assert lines[0].bbox == [0.1, 0.0, 0.9, 0.125]
    assert lines[1].bbox == [0.0, 0.25, 1.0, 0.5] and lines[2].bbox == [0.0, 0.5, 1.0, 0.75]
    assert lines[3].bbox == [0.5, 0.5, 1.0, 1.0]
    assert lines[1].confidence == 0.8
    engine.read(pages)
    assert fake_surya == ["init"]  # predictor loaded once
