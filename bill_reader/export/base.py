"""Export sink protocol. Iteration 2 adds an API-posting sink behind the same interface."""

from dataclasses import dataclass, field
from typing import Protocol

from sqlmodel import Session

from bill_reader.models import Bill


@dataclass
class ExportResult:
    batch_id: int
    file_path: str
    bill_count: int
    files: dict[str, str] = field(default_factory=dict)  # file name -> path on disk


class VoucherSink(Protocol):
    def export(self, session: Session, bills: list[Bill]) -> ExportResult | None: ...
