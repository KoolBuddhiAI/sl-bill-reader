"""Normalise extracted values and run consistency checks that adjust field confidence (FR-12)."""

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from bill_reader.schemas import AMOUNT_FIELDS, REQUIRED_FIELDS, BillExtraction, to_decimal

TOLERANCE = Decimal("1.00")
PENALTY = 0.6

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y", "%d.%m.%y")
_CURRENCY_ALIASES = {"RS": None, "RS.": None, "RS/-": None, "රු": "LKR", "ரூ": None, "₹": "INR", "SLR": "LKR", "SLRS": "LKR"}


@dataclass
class ValidationReport:
    warnings: list[str] = field(default_factory=list)
    overall_confidence: float = 0.0


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    text = re.sub(r"\s+", "", value)
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _fmt(amount: Decimal) -> str:
    return f"{amount:.2f}"


def validate(ex: BillExtraction, home_currency: str = "LKR", today: date | None = None) -> ValidationReport:
    """Normalise values in place, apply confidence penalties and return warnings + overall confidence."""
    today = today or date.today()
    report = ValidationReport()
    warn = report.warnings.append

    def penalise(*names: str) -> None:
        for name in names:
            ex.field(name).confidence = round(ex.field(name).confidence * PENALTY, 3)

    # --- normalise amounts ---
    amounts: dict[str, Decimal | None] = {}
    for name in AMOUNT_FIELDS:
        fv = ex.field(name)
        amounts[name] = to_decimal(fv.value)
        if fv.value is not None and amounts[name] is None:
            warn(f"{name}: could not read '{fv.value}' as a number")
            fv.confidence = 0.0
        elif amounts[name] is not None and name != "vat_rate":
            fv.value = _fmt(amounts[name])
    for item in ex.line_items:
        for attr in ("qty", "unit_price", "amount"):
            parsed = to_decimal(getattr(item, attr))
            if parsed is not None:
                setattr(item, attr, str(parsed))

    # --- currency ---
    cur = ex.currency
    if cur.value:
        code = cur.value.strip().upper()
        if code in _CURRENCY_ALIASES or len(code) != 3 or not code.isalpha():
            resolved = _CURRENCY_ALIASES.get(code) or home_currency
            warn(f"currency: '{cur.value}' interpreted as {resolved}")
            cur.value, cur.confidence = resolved, min(cur.confidence, 0.7)
        else:
            cur.value = code
    else:
        cur.value, cur.confidence = home_currency, 0.5
        warn(f"currency: not stated, assumed {home_currency}")

    # --- date ---
    bd = ex.bill_date
    if bd.value:
        parsed = parse_date(bd.value)
        if parsed is None:
            warn(f"bill_date: '{bd.value}' is not a valid date")
            bd.confidence = min(bd.confidence, 0.3)
        else:
            bd.value = parsed.isoformat()
            if parsed > today:
                warn(f"bill_date: {parsed.isoformat()} is in the future")
                penalise("bill_date")

    total, subtotal = amounts["total"], amounts["subtotal"]
    discount = amounts["discount"] or Decimal(0)
    vat, sscl = amounts["vat_amount"] or Decimal(0), amounts["sscl_amount"] or Decimal(0)

    # --- line items vs subtotal (or total when there is no subtotal/tax/discount) ---
    line_amounts = [to_decimal(i.amount) for i in ex.line_items]
    if line_amounts and all(a is not None for a in line_amounts):
        lines_sum = sum(line_amounts, Decimal(0))
        target_name = "subtotal" if subtotal is not None else "total"
        target = subtotal if subtotal is not None else (
            total - vat - sscl + discount if total is not None else None
        )
        if target is not None and abs(lines_sum - target) > TOLERANCE:
            warn(f"line items add up to {_fmt(lines_sum)} but {target_name} implies {_fmt(target)}")
            # The total is derived from the subtotal, so it is just as suspect (a misread digit in a
            # handwritten subtotal/total otherwise keeps a high-confidence total).
            penalise(*{target_name, "total"})

    # --- subtotal - discount + VAT + SSCL = total ---
    if subtotal is not None and total is not None:
        expected = subtotal - discount + vat + sscl
        if abs(expected - total) > TOLERANCE:
            warn(f"subtotal − discount + VAT + SSCL = {_fmt(expected)} but total is {_fmt(total)}")
            penalise("subtotal", "total")

    # --- VAT ≈ rate × taxable amount ---
    rate = amounts["vat_rate"]
    if rate is not None and vat and subtotal is not None:
        expected_vat = ((subtotal - discount) * rate / 100).quantize(Decimal("0.01"))
        if abs(expected_vat - vat) > max(TOLERANCE, expected_vat * Decimal("0.005")):
            warn(f"VAT {_fmt(vat)} does not match {rate}% of {_fmt(subtotal - discount)} ({_fmt(expected_vat)})")
            penalise("vat_amount")

    if total is not None and total <= 0:
        warn("total must be greater than zero")
        ex.total.confidence = 0.0

    # --- document-level checks ---
    if ex.doc_type == "not_a_bill":
        warn("this does not look like a bill")
    if ex.document_count > 1:
        warn(f"{ex.document_count} bills detected in one file; only the first is captured")

    for name in REQUIRED_FIELDS:
        if not ex.field(name).value:
            warn(f"{name}: missing")
            ex.field(name).confidence = 0.0

    report.overall_confidence = (
        0.0 if ex.doc_type == "not_a_bill" else min(ex.field(n).confidence for n in REQUIRED_FIELDS)
    )
    return report
