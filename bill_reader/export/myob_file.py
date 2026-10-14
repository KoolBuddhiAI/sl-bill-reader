"""MYOB AccountRight tab-delimited import files, driven by config/myob_import_formats.yaml."""

import zipfile
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import yaml
from sqlmodel import Session, select

from bill_reader.config import Settings
from bill_reader.export.base import ExportResult
from bill_reader.models import (
    AuditEvent,
    Bill,
    BillField,
    BillStatus,
    ExportBatch,
    VoucherType,
    utcnow,
)
from bill_reader.schemas import to_decimal

FORMAT_FOR_VOUCHER = {
    VoucherType.spend_money: "spend_money",
    VoucherType.purchase: "purchase_service",
}
CENT = Decimal("0.01")


def load_formats(settings: Settings) -> dict[str, Any]:
    with open(settings.config_dir / "myob_import_formats.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _money(value: Decimal) -> str:
    """2 dp, ROUND_HALF_UP, '.' separator, no thousands separators (NFR-5)."""
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def build_voucher(
    bill: Bill, fields: dict[str, str | None], settings: Settings
) -> dict[str, str]:
    """Map a bill to the export source values named in the YAML (amounts in home currency).

    SSCL is not separated: it is already inside the total (assumption A5).
    `bill_date` stays ISO (YYYY-MM-DD) here; `render_file` applies the format's date_format.
    """
    supplier = (fields.get("supplier_name") or "").strip()
    bill_no = (fields.get("bill_number") or "").strip()
    currency = (
        bill.currency or fields.get("currency") or settings.home_currency
    ).upper()

    total = to_decimal(fields.get("total"))
    if total is None:
        raise ValueError(f"bill {bill.id}: total is missing")
    vat = to_decimal(fields.get("vat_amount")) or Decimal(0)

    memo = f"{supplier} {bill_no}".strip()
    if currency != settings.home_currency.upper():
        rate = to_decimal(bill.exchange_rate)
        if rate is None or rate <= 0:
            raise ValueError(
                f"bill {bill.id}: currency {currency} needs an exchange rate"
            )
        memo += f" | Orig {currency} {total.quantize(CENT, rounding=ROUND_HALF_UP):,} @ {rate.normalize():f}"
    else:
        rate = Decimal(1)

    inc = (total * rate).quantize(CENT, rounding=ROUND_HALF_UP)
    vat_home = (vat * rate).quantize(CENT, rounding=ROUND_HALF_UP)

    return {
        "paying_account": bill.paying_account or settings.default_paying_account,
        "bill_number": bill_no,
        "bill_date": fields.get("bill_date") or "",
        "supplier_name": supplier,
        "memo": memo,
        "account_code": bill.account_code or "",
        "amount_inc_tax": _money(inc),
        "amount_ex_tax": _money(inc - vat_home),
        "vat_amount": _money(vat_home),
        "tax_code": bill.tax_code or "",
        "description": (fields.get("description") or memo).strip(),
        "inclusive": "X",
    }


def _clean(value: str) -> str:
    # Tabs/newlines would break the record layout.
    return " ".join(str(value).split())


def render_file(fmt: dict[str, Any], vouchers: list[dict[str, str]]) -> str:
    """Tab-delimited, CRLF, one header row, blank line between records (MYOB multi-line convention)."""
    columns = fmt["columns"]
    date_format = fmt.get("date_format")
    lines = ["\t".join(c["header"] for c in columns)]
    for i, voucher in enumerate(vouchers):
        if i:
            lines.append("")
        cells = []
        for col in columns:
            if "const" in col:
                value = col["const"] or ""
            else:
                value = voucher.get(col["source"], "")
                if col["source"] == "bill_date" and value and date_format:
                    value = date.fromisoformat(value).strftime(date_format)
            cells.append(_clean(value))
        lines.append("\t".join(cells))
    return "\r\n".join(lines) + "\r\n"


class MyobFileSink:
    def __init__(self, settings: Settings):
        self.settings = settings

    def export(self, session: Session, bills: list[Bill]) -> ExportResult | None:
        bills = [b for b in bills if b.status == BillStatus.approved]
        if not bills:
            return None
        formats = load_formats(self.settings)

        # Build every voucher first so a bad bill (e.g. missing rate) aborts before any state changes.
        grouped: dict[str, list[dict[str, str]]] = {}
        for bill in bills:
            rows = session.exec(
                select(BillField).where(BillField.bill_id == bill.id)
            ).all()
            fields = {r.name: r.value for r in rows}
            fmt_name = FORMAT_FOR_VOUCHER[VoucherType(bill.voucher_type)]
            grouped.setdefault(fmt_name, []).append(
                build_voucher(bill, fields, self.settings)
            )

        batch = ExportBatch(file_path="", bill_count=len(bills))
        session.add(batch)
        session.flush()
        out_dir = self.settings.exports_dir / f"batch-{batch.id}"
        out_dir.mkdir(parents=True, exist_ok=True)

        files: dict[str, str] = {}
        for fmt_name in ("spend_money", "purchase_service"):
            if fmt_name not in grouped:
                continue
            fmt = formats[fmt_name]
            path = out_dir / fmt["file_name"]
            # newline="" keeps our explicit CRLFs untouched.
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(render_file(fmt, grouped[fmt_name]))
            files[fmt["file_name"]] = str(path)

        zip_path = out_dir / f"myob-export-batch-{batch.id}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, path in files.items():
                zf.write(path, arcname=name)
        batch.file_path = str(zip_path)

        now = utcnow()
        for bill in bills:
            bill.status = BillStatus.exported
            bill.export_batch_id = batch.id
            bill.updated_at = now
            session.add(bill)
            session.add(
                AuditEvent(
                    bill_id=bill.id, action="exported", details={"batch_id": batch.id}
                )
            )
        session.add(batch)
        session.commit()
        return ExportResult(
            batch_id=batch.id,
            file_path=str(zip_path),
            bill_count=len(bills),
            files=files,
        )
