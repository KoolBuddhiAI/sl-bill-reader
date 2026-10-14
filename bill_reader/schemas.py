"""Pydantic schemas exchanged with the LLM and the API.

`BillExtraction` is also the JSON schema the model is asked to fill (tool/JSON output).
Amounts are strings holding plain decimals ("2305000.00") so no precision is lost.
"""

import re
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, Field

FIELD_NAMES = (
    "supplier_name",
    "supplier_address",
    "supplier_tax_id",
    "bill_number",
    "bill_date",
    "currency",
    "subtotal",
    "discount",
    "vat_amount",
    "vat_rate",
    "sscl_amount",
    "total",
    "payment_method",
)
AMOUNT_FIELDS = ("subtotal", "discount", "vat_amount", "vat_rate", "sscl_amount", "total")
REQUIRED_FIELDS = ("supplier_name", "bill_date", "total")


class FieldValue(BaseModel):
    value: str | None = Field(None, description="Value as read. Amounts: plain decimal like 2305000.00. Dates: YYYY-MM-DD.")
    confidence: float = Field(0.0, ge=0, le=1, description="How sure you are this value is correct, 0-1.")
    bbox: list[float] | None = Field(
        None, description="Approximate location [x0,y0,x1,y1], normalised 0-1 relative to the page image."
    )
    page: int = Field(0, description="0-based page index the value was read from.")
    line_ids: list[int] | None = Field(None, description="OCR line ids the value came from (OCR+text mode only).")


class LineItemOut(BaseModel):
    description: str | None = Field(None, description="Item description in English (translate if needed).")
    description_original: str | None = Field(None, description="Description exactly as written, in its original script.")
    qty: str | None = None
    unit_price: str | None = None
    amount: str | None = None
    confidence: float = Field(0.0, ge=0, le=1)


class BillExtraction(BaseModel):
    doc_type: str = Field(
        "invoice", description="One of: tax_invoice, invoice, receipt, cash_bill, not_a_bill."
    )
    languages: list[str] = Field(default_factory=list, description="ISO 639-1 codes seen, e.g. ['si','en'].")
    document_count: int = Field(1, description="Number of separate bills visible in the input.")
    supplier_name: FieldValue = Field(default_factory=FieldValue, description="Supplier/vendor name in English (transliterate if needed).")
    supplier_address: FieldValue = Field(default_factory=FieldValue)
    supplier_tax_id: FieldValue = Field(default_factory=FieldValue, description="Supplier TIN / VAT / PAN number.")
    bill_number: FieldValue = Field(default_factory=FieldValue)
    bill_date: FieldValue = Field(default_factory=FieldValue)
    currency: FieldValue = Field(default_factory=FieldValue, description="ISO 4217 code, e.g. LKR, INR.")
    subtotal: FieldValue = Field(default_factory=FieldValue)
    discount: FieldValue = Field(default_factory=FieldValue)
    vat_amount: FieldValue = Field(default_factory=FieldValue)
    vat_rate: FieldValue = Field(default_factory=FieldValue, description="Percent, e.g. 18.")
    sscl_amount: FieldValue = Field(default_factory=FieldValue)
    total: FieldValue = Field(default_factory=FieldValue, description="Final amount payable for the bill.")
    payment_method: FieldValue = Field(default_factory=FieldValue)
    line_items: list[LineItemOut] = Field(default_factory=list)
    notes: str | None = Field(None, description="Anything the reviewer should know (ambiguities, multiple documents).")

    def field(self, name: str) -> FieldValue:
        return getattr(self, name)


class CategorySuggestion(BaseModel):
    account_code: str = Field(..., description="Account number from the chart of accounts, e.g. 6-1520.")
    confidence: float = Field(..., ge=0, le=1)
    reason: str = Field(..., description="One short sentence explaining the choice.")


_AMOUNT_RE = re.compile(r"-?\d[\d,\s]*(?:\.\d+)?")


def to_decimal(value: str | None) -> Decimal | None:
    """Parse a model/user supplied amount; tolerant of commas, currency symbols and spaces."""
    if value is None:
        return None
    match = _AMOUNT_RE.search(str(value))
    if not match:
        return None
    try:
        return Decimal(re.sub(r"[,\s]", "", match.group(0)))
    except InvalidOperation:
        return None
