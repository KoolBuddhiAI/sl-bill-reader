import copy
import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bill_reader.app import create_app
from bill_reader.llm import LLMError, load_models_config
from bill_reader.llm.base import FakeLLMClient

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "llm" / "sample-02-extraction.json").read_text())
CATEGORY = {"account_code": "5-1000", "confidence": 0.8, "reason": "Goods for resale"}


@pytest.fixture(autouse=True)
def _keys(monkeypatch):
    for var in ("ZAI_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.setenv(var, "test")


def make_client(extraction=None, category=None):
    """client_factory returning fakes: extraction profiles get the fixture, categorisation gets CATEGORY."""
    def factory(profile):
        if profile.supports_vision:
            return FakeLLMClient(profile, [extraction if extraction is not None else copy.deepcopy(FIXTURE)])
        return FakeLLMClient(profile, [category or CATEGORY])
    return factory


@pytest.fixture
def client(settings):
    app = create_app(settings, worker_threads=0, client_factory=make_client(), ocr=None)
    with TestClient(app) as c:
        yield c


def upload(client, samples_dir, name="02-vat-company-en-printed-tax-invoice.png"):
    data = (samples_dir / "bills" / name).read_bytes()
    return client.post("/api/bills", files=[("files", (name, data, "image/png"))]).json()["results"][0]


def test_upload_extract_review_approve_export(client, samples_dir):
    r = upload(client, samples_dir)
    bill_id = r["bill_id"]
    assert r["error"] is None

    dup = upload(client, samples_dir)
    assert dup["duplicate_of"] == bill_id

    bill = client.get(f"/api/bills/{bill_id}").json()
    assert bill["status"] == "needs_review"
    assert bill["fields"]["total"]["value"] == "2719900.00"
    assert bill["fields"]["total"]["level"] == "high"
    assert bill["account_code"] == "5-1000" and bill["tax_code"] == "VAT"
    assert bill["voucher_type"] == "spend_money" and bill["paying_account"] == "1-1110"
    default_profile = load_models_config(client.app.state.settings).extraction
    assert bill["extraction"]["profile"] == default_profile and bill["extraction"]["mode"] == "vision"
    assert client.get(f"/api/bills/{bill_id}/pages/0").headers["content-type"] == "image/jpeg"

    # correct a value; audit keeps original vs corrected
    patched = client.patch(f"/api/bills/{bill_id}", json={"fields": {"bill_number": "T-10001A"}}).json()
    change = [a for a in patched["audit"] if a["action"] == "corrected"][0]["details"]["changes"][0]
    assert change == {"field": "bill_number", "old": "T-10001", "new": "T-10001A", "extracted": "T-10001"}

    assert client.post(f"/api/bills/{bill_id}/approve").json()["status"] == "approved"

    resp = client.post("/api/exports")
    assert resp.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(resp.content)).namelist()
    assert names == ["SpendMoney.txt"]
    assert client.get(f"/api/bills/{bill_id}").json()["status"] == "exported"
    assert client.post("/api/exports").status_code == 204
    assert len(client.get("/api/exports").json()) == 1


def test_supplier_history_reused(client, samples_dir):
    first = upload(client, samples_dir)["bill_id"]
    client.patch(f"/api/bills/{first}", json={"account_code": "6-3310"})
    client.post(f"/api/bills/{first}/approve")
    second = upload(client, samples_dir, "03-malindu-spice-hut-si-thermal.png")["bill_id"]  # same fixture supplier
    bill = client.get(f"/api/bills/{second}").json()
    assert bill["account_code"] == "6-3310" and "Previously used" in bill["account_reason"]


def test_foreign_currency_requires_rate_and_low_confidence_requires_confirmation(settings, samples_dir):
    ex = copy.deepcopy(FIXTURE)
    ex["currency"] = {"value": "INR", "confidence": 0.9}
    ex["bill_date"]["confidence"] = 0.6
    app = create_app(settings, worker_threads=0, client_factory=make_client(extraction=ex), ocr=None)
    with TestClient(app) as c:
        bill_id = upload(c, samples_dir)["bill_id"]
        bill = c.get(f"/api/bills/{bill_id}").json()
        assert bill["needs_exchange_rate"] and bill["fields"]["bill_date"]["level"] == "medium"
        resp = c.post(f"/api/bills/{bill_id}/approve")
        assert resp.status_code == 422
        problems = resp.json()["detail"]["problems"]
        assert any("exchange rate" in p for p in problems) and any("bill_date" in p for p in problems)
        ok = c.post(f"/api/bills/{bill_id}/approve", json={"exchange_rate": "3.45", "confirmed": ["bill_date"]})
        assert ok.status_code == 200 and ok.json()["status"] == "approved"


def test_failed_extraction_marks_bill_failed(settings, samples_dir):
    def factory(profile):
        return FakeLLMClient(profile, [LLMError("quota exceeded")])

    app = create_app(settings, worker_threads=0, client_factory=factory, ocr=None)
    with TestClient(app) as c:
        bill_id = upload(c, samples_dir)["bill_id"]
        bill = c.get(f"/api/bills/{bill_id}").json()
        assert bill["status"] == "failed" and "quota exceeded" in bill["error"]


def test_reextract_with_other_profile_and_models_api(client, samples_dir):
    bill_id = upload(client, samples_dir)["bill_id"]
    assert client.post(f"/api/bills/{bill_id}/reextract?profile=nope").status_code == 422
    client.post(f"/api/bills/{bill_id}/reextract?profile=deepseek-vision")
    bill = client.get(f"/api/bills/{bill_id}").json()
    assert bill["extraction"]["profile"] == "deepseek-vision" and bill["status"] == "needs_review"

    models = client.put("/api/models/active", json={"extraction": "glm-vision-flash"}).json()
    assert models["extraction"] == "glm-vision-flash"
    assert client.put("/api/models/active", json={"extraction": "nope"}).status_code == 422


def test_accounts_search_import_and_delete(client, samples_dir):
    hits = client.get("/api/accounts", params={"q": "meals"}).json()
    assert hits[0]["code"] == "6-3110"
    csv = b"Account Number,Account Name,Account Type,Header/Detail\n6-5000,Sundry,Expense,D\n"
    assert client.post("/api/accounts/import", files={"file": ("a.csv", csv, "text/csv")}).json() == {"imported": 1}
    bill_id = upload(client, samples_dir)["bill_id"]
    assert client.delete(f"/api/bills/{bill_id}").status_code == 204
    assert client.get(f"/api/bills/{bill_id}").status_code == 404
