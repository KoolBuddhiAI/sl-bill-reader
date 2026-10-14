from decimal import Decimal

from fastapi.testclient import TestClient

from bill_reader.app import create_app
from bill_reader.models import Bill, BillStatus
from bill_reader.schemas import BillExtraction, to_decimal


def test_healthz(settings):
    client = TestClient(create_app(settings))
    assert client.get("/healthz").json()["status"] == "ok"


def test_bill_roundtrip(session):
    bill = Bill(sha256="abc", original_filename="x.png", stored_path="/tmp/x.png", languages=["si"])
    session.add(bill)
    session.commit()
    session.refresh(bill)
    assert bill.status == BillStatus.processing
    assert bill.languages == ["si"]


def test_extraction_schema_defaults():
    ex = BillExtraction.model_validate({"total": {"value": "510.00", "confidence": 0.9}})
    assert ex.total.value == "510.00"
    assert ex.supplier_name.value is None
    assert "supplier_name" in BillExtraction.model_json_schema()["properties"]


def test_to_decimal_handles_lakh_grouping():
    assert to_decimal("2,30,5000.00") == Decimal("2305000.00")
    assert to_decimal("Rs. 44,800/-") == Decimal("44800")
    assert to_decimal(None) is None
    assert to_decimal("n/a") is None
