import json
from pathlib import Path

import pytest
from PIL import Image

from bill_reader.extract.base import ExtractionFailed, ExtractionResult, OcrLine
from bill_reader.extract.ocr_text import OcrTextLLMExtractor
from bill_reader.extract.orchestrator import ExtractionOrchestrator
from bill_reader.extract.vision import VisionLLMExtractor
from bill_reader.llm import LLMError
from bill_reader.llm.base import FakeLLMClient
from bill_reader.llm.profiles import ModelProfile
from bill_reader.preprocess import PreparedDocument
from bill_reader.schemas import BillExtraction

SAMPLE02 = json.loads((Path(__file__).parent / "fixtures" / "llm" / "sample-02-extraction.json").read_text())


def profile(name: str, vision: bool = True, key_env: str = "TEST_KEY") -> ModelProfile:
    return ModelProfile(name=name, provider="openai_compatible", model=f"{name}-model", api_key_env=key_env,
                        supports_vision=vision)


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("TEST_KEY", "k")
    monkeypatch.delenv("MISSING_KEY", raising=False)


def doc(text_layer: str = "") -> PreparedDocument:
    return PreparedDocument(pages=[Image.new("RGB", (10, 10))], page_jpegs=[b"\xff\xd8page"], text_layer=text_layer)


class FakeOcr:
    name = "fake-ocr"

    def __init__(self, available=True):
        self.available = available
        self.calls = 0

    def is_available(self):
        return self.available

    def read(self, pages):
        self.calls += 1
        return [OcrLine(0, "SAMAN MOTORS", [0.1, 0.1, 0.5, 0.15]), OcrLine(1, "එකතුව 44800", [0.6, 0.8, 0.9, 0.85])]


def factory(responses: dict[str, list]):
    clients = {}

    def make(p: ModelProfile):
        clients[p.name] = FakeLLMClient(p, responses.get(p.name, []))
        return clients[p.name]

    make.clients = clients
    return make


def test_vision_extractor_sends_images_and_pdf_text():
    client = FakeLLMClient(profile("v"), [SAMPLE02])
    result = VisionLLMExtractor(client).extract(doc("TAX INVOICE T-10001"))
    assert result.extraction.bill_number.value == "T-10001"
    assert result.mode == "vision" and result.profile == "v" and result.tokens_in == 100
    assert client.calls[0]["images"] == 1 and "T-10001" in client.calls[0]["user_text"]


def test_ocr_text_extractor_maps_line_ids_to_boxes():
    reply = {"supplier_name": {"value": "Saman Motors", "confidence": 0.8, "line_ids": [0]},
             "total": {"value": "44800", "confidence": 0.8, "line_ids": [1]}}
    client = FakeLLMClient(profile("t", vision=False), [reply])
    result = OcrTextLLMExtractor(client, FakeOcr()).extract(doc())
    assert result.mode == "ocr+text"
    assert result.extraction.total.bbox == [0.6, 0.8, 0.9, 0.85]
    assert "[1] (p0) එකතුව 44800" in client.calls[0]["user_text"] and client.calls[0]["images"] == 0


def test_orchestrator_uses_first_confident_profile():
    make = factory({"a": [SAMPLE02]})
    result = ExtractionOrchestrator([profile("a"), profile("b")], client_factory=make).run(doc())
    assert result.profile == "a" and result.overall_confidence >= 0.9 and result.warnings == []
    assert "b" not in make.clients


def test_orchestrator_falls_back_on_error_and_missing_key():
    make = factory({"a": [LLMError("boom")], "c": [SAMPLE02]})
    chain = [profile("a"), profile("b", key_env="MISSING_KEY"), profile("c")]
    result = ExtractionOrchestrator(chain, client_factory=make).run(doc())
    assert result.profile == "c"
    assert result.log[0].startswith("a: boom") and "MISSING_KEY not set" in result.log[1]


def test_orchestrator_low_confidence_tries_next_and_keeps_best():
    weak = {"supplier_name": {"value": "X", "confidence": 0.3}, "bill_date": {"value": "2026-01-01", "confidence": 0.3},
            "total": {"value": "10", "confidence": 0.3}}
    make = factory({"a": [weak], "b": [LLMError("down")]})
    result = ExtractionOrchestrator([profile("a"), profile("b")], client_factory=make).run(doc())
    assert result.profile == "a" and result.overall_confidence == 0.3
    assert make.clients["b"]  # second profile was tried


def test_text_only_profile_needs_ocr():
    make = factory({"t": [SAMPLE02]})
    with pytest.raises(ExtractionFailed, match="Surya is not installed"):
        ExtractionOrchestrator([profile("t", vision=False)], client_factory=make).run(doc())
    ocr = FakeOcr()
    make = factory({"t": [SAMPLE02]})
    result = ExtractionOrchestrator([profile("t", vision=False)], ocr=ocr, client_factory=make).run(doc())
    assert result.mode == "ocr+text" and ocr.calls == 1


def test_last_resort_used_when_no_llm_works():
    class Heuristic:
        name, mode = "heuristic", "heuristic"

        def extract(self, d):
            ex = BillExtraction.model_validate({"total": {"value": "44800", "confidence": 0.3}})
            return ExtractionResult(extraction=ex, extractor="heuristic", profile=None, model_id=None, mode="heuristic")

    make = factory({"a": [LLMError("down")]})
    result = ExtractionOrchestrator([profile("a")], ocr=FakeOcr(), last_resort=Heuristic(),
                                    client_factory=make).run(doc())
    assert result.mode == "heuristic" and result.log == ["a: down"]


def test_all_fail_raises_with_reasons():
    make = factory({"a": [LLMError("down")]})
    with pytest.raises(ExtractionFailed) as err:
        ExtractionOrchestrator([profile("a")], client_factory=make).run(doc())
    assert err.value.log == ["a: down"]
