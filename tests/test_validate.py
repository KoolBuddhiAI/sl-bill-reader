import json
from datetime import date
from pathlib import Path

from bill_reader.schemas import BillExtraction
from bill_reader.validate import parse_date, validate

FIXTURES = Path(__file__).parent / "fixtures" / "llm"


def sample02() -> BillExtraction:
    return BillExtraction.model_validate(json.loads((FIXTURES / "sample-02-extraction.json").read_text()))


def test_sample02_normalises_and_passes_checks():
    ex = sample02()
    report = validate(ex, "LKR", today=date(2026, 10, 14))
    assert report.warnings == []
    assert (ex.subtotal.value, ex.vat_amount.value, ex.total.value) == ("2305000.00", "414900.00", "2719900.00")
    assert ex.bill_date.value == "2026-01-04"
    assert report.overall_confidence == 0.93


def test_wrong_total_penalises_total_and_subtotal():
    ex = sample02()
    ex.total.value = "2,719,000.00"
    report = validate(ex, today=date(2026, 10, 14))
    assert any("total is 2719000.00" in w for w in report.warnings)
    assert ex.total.confidence < 0.95 * 0.61


def test_receipt_cash_tendered_trap_detected_by_line_sum():
    ex = BillExtraction.model_validate({
        "supplier_name": {"value": "Malindu Spice Hut", "confidence": 0.9},
        "bill_date": {"value": "2026-08-13", "confidence": 0.9},
        "currency": {"value": "LKR", "confidence": 0.9},
        "total": {"value": "1000.00", "confidence": 0.9},
        "line_items": [{"amount": "170.00"}, {"amount": "340.00"}],
    })
    report = validate(ex, today=date(2026, 10, 14))
    assert any("line items add up to 510.00" in w for w in report.warnings)
    assert report.overall_confidence < 0.6


def test_missing_required_fields_and_future_date():
    ex = BillExtraction.model_validate({"bill_date": {"value": "2027-01-01", "confidence": 0.9}})
    report = validate(ex, today=date(2026, 10, 14))
    assert "supplier_name: missing" in report.warnings and "total: missing" in report.warnings
    assert any("future" in w for w in report.warnings)
    assert report.overall_confidence == 0.0


def test_currency_symbol_and_default():
    ex = BillExtraction.model_validate({"currency": {"value": "Rs.", "confidence": 0.9}})
    validate(ex, "LKR")
    assert ex.currency.value == "LKR" and ex.currency.confidence == 0.7
    ex = BillExtraction.model_validate({"currency": {"value": "inr", "confidence": 0.9}})
    validate(ex, "LKR")
    assert ex.currency.value == "INR"


def test_not_a_bill_has_zero_confidence():
    ex = sample02()
    ex.doc_type = "not_a_bill"
    assert validate(ex).overall_confidence == 0.0


def test_parse_date_formats():
    assert parse_date("28/10/2024") == date(2024, 10, 28)
    assert parse_date("27/1/16") == date(2016, 1, 27)
    assert parse_date("26/9/6") is None
