import copy
import json
from pathlib import Path

import pytest

from bill_reader.evaluate import evaluate, render_markdown, score_field, supplier_matches, write_reports
from bill_reader.llm import LLMError
from bill_reader.llm.base import FakeLLMClient

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "llm" / "sample-02-extraction.json").read_text())


def test_scoring_rules():
    truth = {"supplier_name": "Vat Company (Pvt) Ltd", "supplier_aliases": [], "total": "2719900.00",
             "bill_number": "T-10001", "bill_date": None, "expected_account_code": "5-1000", "currency": "LKR"}
    assert supplier_matches("VAT COMPANY PVT LTD.", truth)
    assert not supplier_matches("Saman Motors", truth)
    assert score_field("total", "2719900.4", truth) is True
    assert score_field("total", "2719000", truth) is False
    assert score_field("bill_number", "t 10001", truth) is True
    assert score_field("bill_date", "2026-01-04", truth) is None
    assert score_field("account_code", None, truth) is False


def test_evaluate_compares_profiles(settings, samples_dir, monkeypatch, tmp_path):
    monkeypatch.setenv("ZAI_API_KEY", "x")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "x")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def factory(profile):
        if profile.name == "glm-vision":
            return FakeLLMClient(profile, [copy.deepcopy(FIXTURE) for _ in range(5)])
        if profile.name == "deepseek-vision":
            return FakeLLMClient(profile, [LLMError("unsupported")] * 5)
        return FakeLLMClient(profile, [{"account_code": "5-1000", "confidence": 0.8, "reason": "r"}] * 20)

    reports = evaluate(settings, samples_dir, ["glm-vision", "deepseek-vision", "deepseek-text", "openai-vision"],
                       categorisation="deepseek-text", client_factory=factory)
    by_name = {r.profile: r for r in reports}
    glm = by_name["glm-vision"]
    assert len(glm.samples) == 5
    assert glm.accuracy("total") == (1, 5)  # the fixture is sample 02 for every image
    assert glm.accuracy("account_code") == (1, 5)
    assert all(not s.ok for s in by_name["deepseek-vision"].samples)
    assert "Surya" in by_name["deepseek-text"].skipped
    assert "OPENAI_API_KEY" in by_name["openai-vision"].skipped

    md = render_markdown(reports, "deepseek-text")
    assert "| glm-vision | glm-4.6v | vision | " in md and "skipped – no API key" in md
    json_path = write_reports(reports, "deepseek-text", tmp_path / "eval.md", tmp_path / "json")
    assert json.loads(json_path.read_text())[0]["profile"] == "glm-vision"
