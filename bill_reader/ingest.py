"""Ingest a bill file: type check, SHA-256 dedupe, store the original, create the Bill, enqueue."""

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pypdfium2 import PdfiumError
from sqlmodel import Session, select

from bill_reader.config import Settings
from bill_reader.models import AuditEvent, Bill, BillStatus
from bill_reader.preprocess import page_count

log = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".heic", ".heif", ".webp"}


@dataclass
class IngestResult:
    bill_id: int | None = None
    duplicate_of: int | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.bill_id is not None


def ingest_bytes(
    session: Session,
    settings: Settings,
    data: bytes,
    filename: str,
    source: str = "upload",
    enqueue: Callable[[int], None] | None = None,
) -> IngestResult:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(e.lstrip(".").upper() for e in ALLOWED_EXTENSIONS))
        return IngestResult(error=f"Unsupported file type '{ext or filename}'. Allowed: {allowed}.")
    if not data:
        return IngestResult(error=f"'{filename}' is empty.")
    if ext == ".pdf" and not data.startswith(b"%PDF-"):
        return IngestResult(error=f"'{filename}' is not a valid PDF file.")

    sha = hashlib.sha256(data).hexdigest()
    existing = session.exec(select(Bill).where(Bill.sha256 == sha)).first()
    if existing is not None:
        return IngestResult(duplicate_of=existing.id)

    doc_dir = settings.documents_dir / sha
    doc_dir.mkdir(parents=True, exist_ok=True)
    stored = doc_dir / f"original{ext}"
    stored.write_bytes(data)
    try:
        pages = page_count(stored)
    except (OSError, PdfiumError) as exc:  # undecodable / corrupt file
        stored.unlink(missing_ok=True)
        return IngestResult(error=f"Could not read '{filename}': {exc}")

    bill = Bill(
        sha256=sha,
        original_filename=Path(filename).name,
        source=source,
        stored_path=str(stored),
        page_count=pages,
        status=BillStatus.processing,
    )
    session.add(bill)
    session.flush()
    session.add(
        AuditEvent(bill_id=bill.id, action="ingested", details={"filename": bill.original_filename, "source": source})
    )
    session.commit()
    log.info("Ingested %s as bill %s (%s)", filename, bill.id, source)
    if enqueue is not None:
        enqueue(bill.id)
    return IngestResult(bill_id=bill.id)


def ingest_path(
    session: Session,
    settings: Settings,
    path: Path,
    source: str = "inbox",
    enqueue: Callable[[int], None] | None = None,
) -> IngestResult:
    return ingest_bytes(session, settings, Path(path).read_bytes(), Path(path).name, source=source, enqueue=enqueue)
