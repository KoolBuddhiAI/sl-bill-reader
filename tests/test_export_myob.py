import zipfile
from pathlib import Path

import pytest
from sqlmodel import select

from bill_reader.export import MyobFileSink, build_voucher, load_formats, render_file
from bill_reader.models import (
    AuditEvent,
    Bill,
    BillField,
    BillStatus,
    ExportBatch,
    VoucherType,
)

FIXTURES = Path(__file__).parent / "fixtures" / "export"


def _add_bill(session, sha, fields, **kw):
    bill = Bill(
        sha256=sha, original_filename=f"{sha}.png", stored_path=f"/x/{sha}", **kw
    )
    session.add(bill)
    session.flush()
    for name, value in fields.items():
        session.add(BillField(bill_id=bill.id, name=name, value=value))
    session.commit()
    return bill


def _spend_money_bill(session):
    # Like sample 02: LKR tax invoice with 18% VAT.
    return _add_bill(
        session,
        "s02",
        {
            "supplier_name": "Vat Company (Pvt) Ltd",
            "bill_number": "T-10001",
            "bill_date": "2026-01-04",
            "subtotal": "2305000.00",
            "vat_amount": "414900.00",
            "total": "2719900.00",
            "currency": "LKR",
        },
        status=BillStatus.approved,
        currency="LKR",
        account_code="5-1000",
        tax_code="VAT",
        voucher_type=VoucherType.spend_money,
    )


def _purchase_bill(session, rate="0.28"):
    # Like sample 04: INR bill, converted at a user-entered rate.
    return _add_bill(
        session,
        "s04",
        {
            "supplier_name": "Samsuddin Siddiqui",
            "bill_number": "287",
            "bill_date": "2024-10-28",
            "total": "7226.00",
            "currency": "INR",
        },
        status=BillStatus.approved,
        currency="INR",
        exchange_rate=rate,
        account_code="6-2310",
        tax_code="N-T",
        voucher_type=VoucherType.purchase,
    )


def _read_bytes(path: str) -> bytes:
    return Path(path).read_bytes()


def test_export_matches_golden_files(session, settings):
    b1 = _spend_money_bill(session)
    b2 = _purchase_bill(session)
    _add_bill(session, "pending", {"total": "1.00"}, status=BillStatus.needs_review)

    bills = session.exec(select(Bill)).all()
    result = MyobFileSink(settings).export(session, list(bills))

    assert result is not None
    assert result.bill_count == 2
    assert set(result.files) == {"SpendMoney.txt", "Purchases.txt"}
    assert (
        _read_bytes(result.files["SpendMoney.txt"])
        == (FIXTURES / "SpendMoney.txt").read_bytes()
    )
    assert (
        _read_bytes(result.files["Purchases.txt"])
        == (FIXTURES / "Purchases.txt").read_bytes()
    )

    with zipfile.ZipFile(result.file_path) as zf:
        assert sorted(zf.namelist()) == ["Purchases.txt", "SpendMoney.txt"]
        assert zf.read("SpendMoney.txt") == (FIXTURES / "SpendMoney.txt").read_bytes()

    batch = session.get(ExportBatch, result.batch_id)
    assert batch.file_path == result.file_path and batch.bill_count == 2
    for b in (b1, b2):
        session.refresh(b)
        assert b.status == BillStatus.exported
        assert b.export_batch_id == result.batch_id
    events = session.exec(
        select(AuditEvent).where(AuditEvent.action == "exported")
    ).all()
    assert sorted(e.bill_id for e in events) == sorted([b1.id, b2.id])


def test_second_export_returns_none(session, settings):
    _spend_money_bill(session)
    sink = MyobFileSink(settings)
    assert sink.export(session, list(session.exec(select(Bill)).all())) is not None
    assert sink.export(session, list(session.exec(select(Bill)).all())) is None


def test_single_type_export_zip_has_one_file(session, settings):
    _spend_money_bill(session)
    result = MyobFileSink(settings).export(
        session, list(session.exec(select(Bill)).all())
    )
    with zipfile.ZipFile(result.file_path) as zf:
        assert zf.namelist() == ["SpendMoney.txt"]


def test_missing_exchange_rate_raises(session, settings):
    bill = _purchase_bill(session, rate=None)
    fields = {
        "supplier_name": "X",
        "bill_number": "1",
        "bill_date": "2024-10-28",
        "total": "100",
    }
    with pytest.raises(ValueError, match="exchange rate"):
        build_voucher(bill, fields, settings)
    with pytest.raises(ValueError):
        MyobFileSink(settings).export(session, [bill])
    session.refresh(bill)
    assert bill.status == BillStatus.approved


def test_build_voucher_converts_currency(settings):
    bill = Bill(
        sha256="x",
        original_filename="x",
        stored_path="x",
        currency="INR",
        exchange_rate="3.555",
        account_code="6-2310",
        tax_code="VAT",
    )
    v = build_voucher(
        bill,
        {
            "supplier_name": "S",
            "bill_number": "9",
            "total": "1,000.50",
            "vat_amount": "10.01",
        },
        settings,
    )
    assert v["amount_inc_tax"] == "3556.78"  # 3556.7775 -> half up
    assert v["vat_amount"] == "35.59"  # 35.58555
    assert v["amount_ex_tax"] == "3521.19"
    assert v["memo"] == "S 9 | Orig INR 1,000.50 @ 3.555"
    assert v["paying_account"] == settings.default_paying_account


def test_render_file_layout(settings):
    fmt = load_formats(settings)["spend_money"]
    text = render_file(fmt, [{"bill_date": "2026-01-04", "memo": "a\tb"}, {}])
    lines = text.split("\r\n")
    assert len(lines) == 5 and lines[-1] == "" and lines[2] == ""
    assert lines[1].split("\t")[2] == "04/01/2026"
    assert "a b" in lines[1]
    assert len(lines[1].split("\t")) == len(fmt["columns"])
