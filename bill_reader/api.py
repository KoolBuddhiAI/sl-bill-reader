"""JSON API (the HTML pages in web.py use the same helpers)."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlmodel import Session, col, delete, select

from bill_reader.categorise import ensure_chart, load_chart_csv, record_approval, selectable_accounts
from bill_reader.config import Settings
from bill_reader.export.myob_file import MyobFileSink
from bill_reader.ingest import ingest_bytes
from bill_reader.llm.check import list_profiles
from bill_reader.llm.profiles import load_models_config, save_active_profiles
from bill_reader.models import (
    Account,
    AuditEvent,
    Bill,
    BillField,
    BillStatus,
    ExportBatch,
    LineItem,
    VoucherType,
    utcnow,
)
from bill_reader.preprocess import page_image_path, prepare
from bill_reader.schemas import FIELD_NAMES, REQUIRED_FIELDS, to_decimal

router = APIRouter(prefix="/api")


# ---------- dependencies ----------

def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_session(request: Request):
    with Session(request.app.state.engine) as session:
        yield session


def get_bill(bill_id: int, session: Session = Depends(get_session)) -> Bill:
    bill = session.get(Bill, bill_id)
    if bill is None:
        raise HTTPException(404, "Bill not found")
    return bill


# ---------- helpers shared with web.py ----------

def confidence_level(conf: float | None, settings: Settings) -> str:
    if conf is None:
        return "none"
    if conf >= settings.confidence_high:
        return "high"
    return "medium" if conf >= settings.confidence_low else "low"


def bill_fields(session: Session, bill_id: int) -> dict[str, BillField]:
    rows = session.exec(select(BillField).where(BillField.bill_id == bill_id)).all()
    return {r.name: r for r in rows}


def bill_summary(session: Session, bill: Bill, settings: Settings) -> dict[str, Any]:
    fields = bill_fields(session, bill.id)
    value = lambda n: fields[n].value if n in fields else None  # noqa: E731
    return {
        "id": bill.id,
        "filename": bill.original_filename,
        "status": bill.status.value,
        "supplier_name": value("supplier_name"),
        "bill_date": value("bill_date"),
        "total": value("total"),
        "currency": bill.currency,
        "overall_confidence": bill.overall_confidence,
        "confidence_level": confidence_level(bill.overall_confidence, settings),
        "voucher_type": bill.voucher_type.value,
        "account_code": bill.account_code,
        "model_profile": bill.model_profile,
        "error": bill.error,
        "created_at": bill.created_at.isoformat(),
    }


def bill_detail(session: Session, bill: Bill, settings: Settings) -> dict[str, Any]:
    fields = bill_fields(session, bill.id)
    items = session.exec(select(LineItem).where(LineItem.bill_id == bill.id).order_by(LineItem.idx)).all()
    audit = session.exec(select(AuditEvent).where(AuditEvent.bill_id == bill.id).order_by(AuditEvent.ts)).all()
    account = session.get(Account, bill.account_code) if bill.account_code else None
    detail = bill_summary(session, bill, settings)
    detail.update(
        {
            "page_count": bill.page_count,
            "fields": {
                name: {
                    "value": f.value,
                    "extracted_value": f.extracted_value,
                    "confidence": f.confidence,
                    "level": "confirmed" if f.confirmed else confidence_level(f.confidence, settings),
                    "confirmed": f.confirmed,
                    "bbox": f.bbox,
                    "page": f.page,
                }
                for name in FIELD_NAMES
                if (f := fields.get(name)) is not None
            },
            "line_items": [i.model_dump(exclude={"id", "bill_id"}) for i in items],
            "warnings": bill.warnings,
            "doc_type": bill.doc_type,
            "languages": bill.languages,
            "exchange_rate": bill.exchange_rate,
            "home_currency": settings.home_currency,
            "needs_exchange_rate": bool(bill.currency) and bill.currency != settings.home_currency,
            "paying_account": bill.paying_account,
            "account_name": account.name if account else None,
            "account_confidence": bill.account_confidence,
            "account_level": confidence_level(bill.account_confidence, settings),
            "account_reason": bill.account_reason,
            "tax_code": bill.tax_code,
            "extraction": {
                "extractor": bill.extractor_used,
                "profile": bill.model_profile,
                "model": bill.model_id,
                "mode": bill.extraction_mode,
                "latency_ms": bill.latency_ms,
                "tokens_in": bill.tokens_in,
                "tokens_out": bill.tokens_out,
            },
            "audit": [{"ts": a.ts.isoformat(), "action": a.action, "details": a.details} for a in audit],
        }
    )
    return detail


class LineItemIn(BaseModel):
    description: str | None = None
    description_original: str | None = None
    qty: str | None = None
    unit_price: str | None = None
    amount: str | None = None


class BillPatch(BaseModel):
    fields: dict[str, str | None] = {}
    confirmed: list[str] = []  # fields the reviewer checked without changing
    line_items: list[LineItemIn] | None = None
    account_code: str | None = None
    tax_code: str | None = None
    voucher_type: VoucherType | None = None
    paying_account: str | None = None
    exchange_rate: str | None = None


def apply_patch(session: Session, bill: Bill, patch: BillPatch) -> None:
    if bill.status in (BillStatus.exported, BillStatus.processing):
        raise HTTPException(409, f"Bill is {bill.status.value} and cannot be edited")
    fields = bill_fields(session, bill.id)
    changes: list[dict[str, Any]] = []
    for name, new in patch.fields.items():
        if name not in FIELD_NAMES:
            raise HTTPException(422, f"Unknown field {name!r}")
        new = (new or "").strip() or None
        f = fields.get(name) or BillField(bill_id=bill.id, name=name)
        if new != f.value:
            changes.append({"field": name, "old": f.value, "new": new, "extracted": f.extracted_value})
            f.value = new
        f.confirmed = True
        session.add(f)
        if name == "currency" and new:
            bill.currency = new.upper()
    for name in patch.confirmed:
        if name in fields:
            fields[name].confirmed = True
            session.add(fields[name])
    if patch.line_items is not None:
        session.exec(delete(LineItem).where(LineItem.bill_id == bill.id))
        for idx, item in enumerate(patch.line_items):
            session.add(LineItem(bill_id=bill.id, idx=idx, confidence=1.0, **item.model_dump()))
        changes.append({"field": "line_items", "new": len(patch.line_items)})
    for attr in ("account_code", "tax_code", "voucher_type", "paying_account", "exchange_rate"):
        new = getattr(patch, attr)
        if new is not None and new != getattr(bill, attr):
            old = getattr(bill, attr)
            changes.append({"field": attr, "old": getattr(old, "value", old), "new": getattr(new, "value", new)})
            setattr(bill, attr, new)
    if patch.account_code is not None and session.get(Account, patch.account_code) is None:
        raise HTTPException(422, f"Unknown account {patch.account_code}")
    if changes:
        session.add(AuditEvent(bill_id=bill.id, action="corrected", details={"changes": changes}))
    bill.updated_at = utcnow()
    session.add(bill)


def approval_problems(session: Session, bill: Bill, settings: Settings) -> list[str]:
    fields = bill_fields(session, bill.id)
    problems = []
    for name in REQUIRED_FIELDS:
        f = fields.get(name)
        if f is None or not f.value:
            problems.append(f"{name} is required")
        elif f.confidence < settings.confidence_high and not f.confirmed:
            problems.append(f"{name} has low confidence – check and confirm it")
    if fields.get("total") and to_decimal(fields["total"].value) is None:
        problems.append("total is not a number")
    if not bill.account_code:
        problems.append("account code is required")
    if bill.currency and bill.currency != settings.home_currency:
        rate = to_decimal(bill.exchange_rate)
        if rate is None or rate <= 0:
            problems.append(f"exchange rate {bill.currency}→{settings.home_currency} is required")
    return problems


# ---------- bills ----------

@router.post("/bills")
async def upload_bills(
    request: Request,
    files: list[UploadFile] = File(...),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    results = []
    for upload in files:
        r = ingest_bytes(session, settings, await upload.read(), upload.filename or "upload",
                         enqueue=request.app.state.worker.enqueue)
        results.append({"filename": upload.filename, "bill_id": r.bill_id, "duplicate_of": r.duplicate_of,
                        "error": r.error})
    return {"results": results}


@router.get("/bills")
def list_bills(status: BillStatus | None = None, session: Session = Depends(get_session),
               settings: Settings = Depends(get_settings)):
    query = select(Bill).order_by(col(Bill.id).desc())
    if status is not None:
        query = query.where(Bill.status == status)
    return [bill_summary(session, b, settings) for b in session.exec(query).all()]


@router.get("/bills/{bill_id}")
def get_bill_detail(bill: Bill = Depends(get_bill), session: Session = Depends(get_session),
                    settings: Settings = Depends(get_settings)):
    return bill_detail(session, bill, settings)


@router.get("/bills/{bill_id}/pages/{n}")
def get_page(n: int, bill: Bill = Depends(get_bill), settings: Settings = Depends(get_settings)):
    if not 0 <= n < max(bill.page_count, 1):
        raise HTTPException(404, "No such page")
    path = page_image_path(settings, bill.sha256, n)
    if not path.exists():
        prepare(Path(bill.stored_path), settings, sha=bill.sha256)
    return FileResponse(path, media_type="image/jpeg")


@router.patch("/bills/{bill_id}")
def patch_bill(patch: BillPatch, bill: Bill = Depends(get_bill), session: Session = Depends(get_session),
               settings: Settings = Depends(get_settings)):
    apply_patch(session, bill, patch)
    session.commit()
    return bill_detail(session, bill, settings)


@router.post("/bills/{bill_id}/approve")
def approve_bill(patch: BillPatch | None = None, bill: Bill = Depends(get_bill),
                 session: Session = Depends(get_session), settings: Settings = Depends(get_settings)):
    if patch is not None:
        apply_patch(session, bill, patch)
    if bill.status not in (BillStatus.needs_review, BillStatus.approved):
        raise HTTPException(409, f"Bill is {bill.status.value}")
    problems = approval_problems(session, bill, settings)
    if problems:
        session.commit()  # keep the reviewer's edits
        raise HTTPException(422, {"problems": problems})
    bill.status = BillStatus.approved
    session.add(AuditEvent(bill_id=bill.id, action="approved", details={"account_code": bill.account_code}))
    session.add(bill)
    session.commit()
    record_approval(session, bill_fields(session, bill.id)["supplier_name"].value, bill.account_code, bill.tax_code)
    return bill_detail(session, bill, settings)


@router.post("/bills/{bill_id}/reextract")
def reextract(request: Request, profile: str | None = None, bill: Bill = Depends(get_bill),
              session: Session = Depends(get_session), settings: Settings = Depends(get_settings)):
    if bill.status == BillStatus.exported:
        raise HTTPException(409, "Exported bills cannot be re-extracted")
    if profile:
        try:
            load_models_config(settings).get(profile)
        except KeyError as exc:
            raise HTTPException(422, str(exc)) from None
    bill.status, bill.error = BillStatus.processing, None
    session.add(bill)
    session.add(AuditEvent(bill_id=bill.id, action="reextracted", details={"profile": profile}))
    session.commit()
    request.app.state.worker.enqueue(bill.id, profile)
    return {"status": "queued", "profile": profile}


@router.delete("/bills/{bill_id}", status_code=204)
def delete_bill(bill: Bill = Depends(get_bill), session: Session = Depends(get_session)):
    for table in (BillField, LineItem, AuditEvent):
        session.exec(delete(table).where(table.bill_id == bill.id))
    session.delete(bill)
    session.commit()
    return Response(status_code=204)


# ---------- accounts ----------

@router.get("/accounts")
def search_accounts(q: str = "", session: Session = Depends(get_session), settings: Settings = Depends(get_settings)):
    ensure_chart(session, settings)
    accounts = selectable_accounts(session)
    if q:
        needle = q.lower()
        accounts = [a for a in accounts if needle in a.code.lower() or needle in a.name.lower()]
    return [{"code": a.code, "name": a.name, "type": a.type} for a in accounts]


@router.post("/accounts/import")
async def import_accounts(file: UploadFile = File(...), session: Session = Depends(get_session)):
    try:
        count = load_chart_csv(session, await file.read())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return {"imported": count}


# ---------- models ----------

class ActiveModels(BaseModel):
    extraction: str | None = None
    categorisation: str | None = None


@router.get("/models")
def get_models(settings: Settings = Depends(get_settings)):
    cfg = load_models_config(settings)
    return {"extraction": cfg.extraction, "categorisation": cfg.categorisation,
            "fallback_chain": cfg.fallback_chain, "profiles": list_profiles(settings)}


@router.put("/models/active")
def set_active_models(body: ActiveModels, settings: Settings = Depends(get_settings)):
    try:
        save_active_profiles(settings, body.extraction, body.categorisation)
    except KeyError as exc:
        raise HTTPException(422, str(exc)) from None
    return get_models(settings)


# ---------- exports ----------

@router.post("/exports")
def create_export(session: Session = Depends(get_session), settings: Settings = Depends(get_settings)):
    bills = session.exec(select(Bill).where(Bill.status == BillStatus.approved)).all()
    try:
        result = MyobFileSink(settings).export(session, list(bills))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    if result is None:
        return Response(status_code=204)
    return FileResponse(result.file_path, media_type="application/zip", filename=Path(result.file_path).name)


@router.get("/exports")
def list_exports(session: Session = Depends(get_session)):
    batches = session.exec(select(ExportBatch).order_by(col(ExportBatch.id).desc())).all()
    return [{"id": b.id, "created_at": b.created_at.isoformat(), "bill_count": b.bill_count,
             "file": Path(b.file_path).name} for b in batches]


@router.get("/exports/{batch_id}")
def download_export(batch_id: int, session: Session = Depends(get_session)):
    batch = session.get(ExportBatch, batch_id)
    if batch is None or not Path(batch.file_path).exists():
        raise HTTPException(404, "Export not found")
    return FileResponse(batch.file_path, media_type="application/zip", filename=Path(batch.file_path).name)
