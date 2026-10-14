"""Database tables. Monetary values are stored as decimal strings (never floats)."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlmodel import JSON, Column, Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BillStatus(str, Enum):
    processing = "processing"
    needs_review = "needs_review"
    approved = "approved"
    exported = "exported"
    failed = "failed"


class VoucherType(str, Enum):
    spend_money = "spend_money"
    purchase = "purchase"


class Bill(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    sha256: str = Field(index=True, unique=True)
    original_filename: str
    source: str = "upload"  # upload | inbox
    stored_path: str
    page_count: int = 0
    status: BillStatus = Field(default=BillStatus.processing, index=True)
    error: str | None = None

    # Extraction provenance
    extractor_used: str | None = None
    model_profile: str | None = None
    model_id: str | None = None
    extraction_mode: str | None = None  # vision | ocr+text | heuristic
    latency_ms: int | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None

    overall_confidence: float | None = None
    doc_type: str | None = None
    languages: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    currency: str | None = None
    exchange_rate: str | None = None  # Decimal as string; required when currency != home

    voucher_type: VoucherType = VoucherType.spend_money
    paying_account: str | None = None
    account_code: str | None = None
    account_confidence: float | None = None
    account_reason: str | None = None
    tax_code: str | None = None

    warnings: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    raw_extraction: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    export_batch_id: int | None = Field(default=None, foreign_key="exportbatch.id")

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class BillField(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    bill_id: int = Field(foreign_key="bill.id", index=True)
    name: str
    value: str | None = None
    extracted_value: str | None = None
    confidence: float = 0.0
    bbox: list[float] | None = Field(default=None, sa_column=Column(JSON))
    page: int = 0
    confirmed: bool = False  # user touched/confirmed this field in review


class LineItem(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    bill_id: int = Field(foreign_key="bill.id", index=True)
    idx: int
    description: str | None = None
    description_original: str | None = None
    qty: str | None = None
    unit_price: str | None = None
    amount: str | None = None
    confidence: float = 0.0


class AuditEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    bill_id: int = Field(foreign_key="bill.id", index=True)
    ts: datetime = Field(default_factory=utcnow)
    action: str  # extracted | corrected | approved | exported | reextracted
    details: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class SupplierHistory(SQLModel, table=True):
    normalised_name: str = Field(primary_key=True)
    display_name: str
    last_account_code: str
    last_tax_code: str | None = None
    times_used: int = 0
    updated_at: datetime = Field(default_factory=utcnow)


class Account(SQLModel, table=True):
    code: str = Field(primary_key=True)
    name: str
    type: str
    is_detail: bool = True


class ExportBatch(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=utcnow)
    file_path: str
    bill_count: int = 0
