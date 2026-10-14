"""Expense categorisation: chart of accounts, supplier history, LLM suggestion, tax code rule."""

import csv
import io
import re
from decimal import Decimal
from pathlib import Path

from sqlmodel import Session, delete, select

from bill_reader.config import Settings
from bill_reader.llm import LLMClient, LLMError
from bill_reader.models import Account, SupplierHistory, utcnow
from bill_reader.schemas import BillExtraction, CategorySuggestion, to_decimal

FALLBACK_ACCOUNT = "6-9999"
SELECTABLE_TYPES = {"expense", "cost of sales", "other expense", "asset"}

_HEADER_ALIASES = {
    "code": ("account number", "account no", "account code", "number"),
    "name": ("account name", "name"),
    "type": ("account type", "type"),
    "header": ("header/detail", "header", "detail", "header or detail"),
}


def _column(fieldnames: list[str], key: str) -> str | None:
    lookup = {f.strip().lower(): f for f in fieldnames if f}
    for alias in _HEADER_ALIASES[key]:
        if alias in lookup:
            return lookup[alias]
    return None


def load_chart_csv(session: Session, path_or_bytes: str | Path | bytes) -> int:
    """Replace the Account table with a MYOB accounts export (CSV). Returns rows loaded."""
    if isinstance(path_or_bytes, bytes):
        text = path_or_bytes.decode("utf-8-sig")
    else:
        text = Path(path_or_bytes).read_text(encoding="utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    fields = reader.fieldnames or []
    cols = {k: _column(fields, k) for k in _HEADER_ALIASES}
    if not cols["code"] or not cols["name"] or not cols["type"]:
        raise ValueError(f"Chart CSV needs Account Number, Account Name and Account Type columns; got {fields}")

    accounts: dict[str, Account] = {}
    for row in reader:
        code = (row.get(cols["code"]) or "").strip()
        if not code:
            continue
        flag = (row.get(cols["header"]) or "D").strip().lower() if cols["header"] else "d"
        accounts[code] = Account(
            code=code,
            name=(row.get(cols["name"]) or "").strip(),
            type=(row.get(cols["type"]) or "").strip(),
            is_detail=flag not in ("h", "header", "y", "yes", "true"),
        )
    session.exec(delete(Account))
    session.add_all(accounts.values())
    session.commit()
    return len(accounts)


def ensure_chart(session: Session, settings: Settings) -> int:
    """Load the sample chart when no accounts exist yet. Returns rows loaded (0 if already present)."""
    if session.exec(select(Account).limit(1)).first() is not None:
        return 0
    return load_chart_csv(session, settings.config_dir / "chart_of_accounts.sample.csv")


def selectable_accounts(session: Session) -> list[Account]:
    """Detail accounts a bill can be posted to (expense, cost of sales, other expense, asset)."""
    rows = session.exec(select(Account).where(Account.is_detail == True).order_by(Account.code)).all()
    return [a for a in rows if a.type.strip().lower() in SELECTABLE_TYPES]


def normalise_supplier(name: str) -> str:
    """Key for supplier history: lowercase, no company suffixes or punctuation, single spaces."""
    s = (name or "").lower()
    s = re.sub(r"\(\s*pvt\s*\)", " pvt ", s)
    s = re.sub(r"\b(?:pvt\.?\s*ltd|private\s+limited|limited|ltd|pvt)\b\.?", " ", s)
    s = re.sub(r"(?:&|\band)\s*co\b\.?", " ", s)
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def propose_tax_code(extraction_or_vat_amount: BillExtraction | str | Decimal | None) -> str:
    """'VAT' when the bill shows VAT, otherwise 'N-T' (SSCL is folded into the expense, A5)."""
    value = extraction_or_vat_amount
    if isinstance(value, BillExtraction):
        value = value.vat_amount.value
    amount = value if isinstance(value, Decimal) else to_decimal(value)
    return "VAT" if amount is not None and amount > 0 else "N-T"


SYSTEM_PROMPT = """You are a bookkeeper for a small business in Sri Lanka that uses MYOB AccountRight.
Choose the ONE account from the chart of accounts that a supplier bill should be posted to.
Rules:
- Use only an account code from the list given; never invent codes.
- Bills are usually expenses. Use an Asset account only for durable equipment, furniture or vehicles
  (capital items), Cost of Sales for goods bought for resale or freight inwards.
- VAT and SSCL are handled separately; categorise the underlying purchase.
- Typical Sri Lankan suppliers: CEB/LECO (electricity), Dialog/SLT/Mobitel (telephone & internet),
  fuel stations such as Ceypetco/Lanka IOC (fuel), restaurants/hotels (meals or travel).
- If nothing fits, use 6-9999 with low confidence.
Give a confidence between 0 and 1 and one short sentence of reasoning."""


def record_approval(session: Session, supplier_name: str, account_code: str, tax_code: str | None) -> SupplierHistory | None:
    """Remember the approved account/tax code for this supplier (upsert, times_used += 1)."""
    key = normalise_supplier(supplier_name)
    if not key:
        return None
    hist = session.get(SupplierHistory, key)
    if hist is None:
        hist = SupplierHistory(normalised_name=key, display_name=supplier_name.strip(), last_account_code=account_code)
    hist.display_name = supplier_name.strip()
    hist.last_account_code = account_code
    hist.last_tax_code = tax_code
    hist.times_used += 1
    hist.updated_at = utcnow()
    session.add(hist)
    session.commit()
    return hist


class Categoriser:
    def __init__(self, session: Session, client: LLMClient | None):
        self.session = session
        self.client = client

    def suggest(self, supplier_name: str, line_items: list[str], doc_hint: str = "") -> CategorySuggestion:
        hist = self.session.get(SupplierHistory, normalise_supplier(supplier_name)) if supplier_name else None
        if hist is not None:
            return CategorySuggestion(
                account_code=hist.last_account_code,
                confidence=0.95,
                reason=f"Previously used for this supplier ({hist.times_used} times)",
            )
        if self.client is None:
            return self._fallback("No categorisation model configured")

        accounts = selectable_accounts(self.session)
        valid = {a.code for a in accounts}
        chart = "\n".join(f"{a.code} | {a.name} | {a.type}" for a in accounts)
        items = "\n".join(f"- {li}" for li in line_items if li) or "(none)"
        user_text = (
            f"Supplier: {supplier_name or '(unknown)'}\n"
            + (f"Document: {doc_hint}\n" if doc_hint else "")
            + f"Line items (English):\n{items}\n\nChart of accounts (code | name | type):\n{chart}"
        )
        try:
            out, _ = self.client.complete_structured(SYSTEM_PROMPT, user_text, CategorySuggestion)
            if out.account_code.strip() in valid:
                return out.model_copy(update={"account_code": out.account_code.strip()})
            retry_text = (
                f"{user_text}\n\nYour previous answer used account code {out.account_code!r}, which is not in the "
                "list. Choose a code from the chart of accounts above."
            )
            out, _ = self.client.complete_structured(SYSTEM_PROMPT, retry_text, CategorySuggestion)
        except LLMError as exc:
            return self._fallback(f"Categorisation model failed: {exc}")
        if out.account_code.strip() in valid:
            return out.model_copy(update={"account_code": out.account_code.strip()})
        return self._fallback("Model suggested an unknown account")

    @staticmethod
    def _fallback(reason: str) -> CategorySuggestion:
        return CategorySuggestion(account_code=FALLBACK_ACCOUNT, confidence=0.0, reason=reason[:500])
