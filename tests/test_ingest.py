import time
from pathlib import Path

import pytest
from sqlmodel import Session, select

from bill_reader.ingest import ingest_bytes, ingest_path
from bill_reader.models import AuditEvent, Bill, BillStatus
from bill_reader.watcher import InboxWatcher


@pytest.fixture
def png_sample(samples_dir: Path) -> Path:
    return next((samples_dir / "bills").glob("02-*.png"))


def test_ingest_creates_bill_and_enqueues(session, settings, png_sample):
    queued = []
    res = ingest_bytes(session, settings, png_sample.read_bytes(), png_sample.name, enqueue=queued.append)
    assert res.error is None and res.bill_id is not None
    assert queued == [res.bill_id]
    bill = session.get(Bill, res.bill_id)
    assert bill.status == BillStatus.processing
    assert bill.page_count == 1
    stored = Path(bill.stored_path)
    assert stored == settings.documents_dir / bill.sha256 / "original.png"
    assert stored.read_bytes() == png_sample.read_bytes()
    events = session.exec(select(AuditEvent).where(AuditEvent.bill_id == bill.id)).all()
    assert [e.action for e in events] == ["ingested"]


def test_duplicate_detected(session, settings, png_sample):
    first = ingest_path(session, settings, png_sample)
    queued = []
    second = ingest_bytes(session, settings, png_sample.read_bytes(), "copy.png", enqueue=queued.append)
    assert second.bill_id is None and second.duplicate_of == first.bill_id
    assert queued == []
    assert len(session.exec(select(Bill)).all()) == 1


@pytest.mark.parametrize(
    "name,data,msg",
    [
        ("notes.txt", b"hello", "Unsupported file type"),
        ("fake.pdf", b"not a pdf", "not a valid PDF"),
        ("empty.png", b"", "empty"),
        ("broken.png", b"garbage bytes", "Could not read"),
    ],
)
def test_rejected_files(session, settings, name, data, msg):
    res = ingest_bytes(session, settings, data, name)
    assert res.bill_id is None and msg in res.error
    assert session.exec(select(Bill)).all() == []


def _watcher(engine, settings, **kw):
    def ingest_fn(path):
        with Session(engine) as s:
            return ingest_path(s, settings, path, source="inbox")

    return InboxWatcher(settings, ingest_fn, **kw)


def test_process_file_moves_to_processed_and_failed(engine, settings, png_sample):
    inbox = settings.inbox_dir
    inbox.mkdir(parents=True)
    w = _watcher(engine, settings)
    good = inbox / png_sample.name
    good.write_bytes(png_sample.read_bytes())
    assert w.process_file(good).bill_id is not None
    assert not good.exists() and (inbox / "processed" / good.name).exists()

    dup = inbox / png_sample.name
    dup.write_bytes(png_sample.read_bytes())
    assert w.process_file(dup).duplicate_of is not None
    assert len(list((inbox / "processed").iterdir())) == 2

    bad = inbox / "bad.txt"
    bad.write_text("x")
    assert w.process_file(bad).error
    assert (inbox / "failed" / "bad.txt").exists()


def test_should_handle_filters(settings):
    inbox = settings.inbox_dir
    (inbox / "processed").mkdir(parents=True)
    w = InboxWatcher(settings, lambda p: None)
    for name in (".hidden.png", "~lock.png", "x.png.part"):
        (inbox / name).write_bytes(b"x")
        assert not w.should_handle(inbox / name)
    (inbox / "processed" / "a.png").write_bytes(b"x")
    assert not w.should_handle(inbox / "processed" / "a.png")
    (inbox / "ok.png").write_bytes(b"x")
    assert w.should_handle(inbox / "ok.png")


def test_observer_ingests_existing_and_new_files(engine, settings, png_sample, samples_dir):
    inbox = settings.inbox_dir
    inbox.mkdir(parents=True)
    (inbox / "existing.png").write_bytes(png_sample.read_bytes())
    w = _watcher(engine, settings, stable_seconds=0.2, poll_seconds=0.05)
    w.start()
    try:
        other = next((samples_dir / "bills").glob("03-*.png"))
        (inbox / "new.png").write_bytes(other.read_bytes())
        deadline = time.monotonic() + 10
        processed = inbox / "processed"
        while time.monotonic() < deadline and len(list(processed.iterdir())) < 2:
            time.sleep(0.05)
    finally:
        w.stop()
    assert sorted(p.name for p in processed.iterdir()) == ["existing.png", "new.png"]
    with Session(engine) as s:
        bills = s.exec(select(Bill)).all()
    assert {b.source for b in bills} == {"inbox"} and len(bills) == 2
