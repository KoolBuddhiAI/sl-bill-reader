"""Watch the inbox folder; ingest files once their size is stable, then move them aside."""

import logging
import shutil
import threading
import time
from collections.abc import Callable
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from bill_reader.config import Settings
from bill_reader.ingest import IngestResult

log = logging.getLogger(__name__)

PROCESSED = "processed"
FAILED = "failed"


class _Handler(FileSystemEventHandler):
    def __init__(self, watcher: "InboxWatcher") -> None:
        self.watcher = watcher

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self.watcher.notify(Path(event.src_path))

    def on_modified(self, event: FileSystemEvent) -> None:
        self.on_created(event)

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self.watcher.notify(Path(event.dest_path))


class InboxWatcher:
    def __init__(
        self,
        settings: Settings,
        ingest_fn: Callable[[Path], IngestResult],
        stable_seconds: float = 2.0,
        poll_seconds: float = 0.5,
    ) -> None:
        self.inbox = Path(settings.inbox_dir)
        self.ingest_fn = ingest_fn
        self.stable_seconds = stable_seconds
        self.poll_seconds = poll_seconds
        # path -> (last seen size, monotonic time size last changed)
        self._pending: dict[Path, tuple[int, float]] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._observer: Observer | None = None
        self._thread: threading.Thread | None = None

    def should_handle(self, path: Path) -> bool:
        """Only regular, non-hidden, non-temp files directly in the inbox."""
        if path.parent.resolve() != self.inbox.resolve():
            return False
        name = path.name
        if name.startswith((".", "~")) or name.endswith((".tmp", ".part", ".crdownload", ".swp")):
            return False
        return path.is_file()

    def notify(self, path: Path) -> None:
        if self.should_handle(path):
            with self._lock:
                self._pending.setdefault(path, (-1, time.monotonic()))

    def start(self) -> None:
        for sub in (PROCESSED, FAILED):
            (self.inbox / sub).mkdir(parents=True, exist_ok=True)
        self._stop.clear()
        for p in sorted(self.inbox.iterdir()):
            self.notify(p)
        self._observer = Observer()
        self._observer.schedule(_Handler(self), str(self.inbox), recursive=False)
        self._observer.start()
        self._thread = threading.Thread(target=self._run, name="inbox-watcher", daemon=True)
        self._thread.start()
        log.info("Watching inbox %s", self.inbox)

    def stop(self) -> None:
        self._stop.set()
        if self._observer is not None:
            self._observer.stop()
            self._observer.join()
            self._observer = None
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def _run(self) -> None:
        while not self._stop.wait(self.poll_seconds):
            for path in self._ready_paths():
                self.process_file(path)

    def _ready_paths(self) -> list[Path]:
        now = time.monotonic()
        ready = []
        with self._lock:
            for path, (size, since) in list(self._pending.items()):
                try:
                    current = path.stat().st_size
                except FileNotFoundError:
                    del self._pending[path]
                    continue
                if current != size:
                    self._pending[path] = (current, now)
                elif now - since >= self.stable_seconds:
                    del self._pending[path]
                    ready.append(path)
        return ready

    def process_file(self, path: Path) -> IngestResult:
        """Ingest one file and move it to processed/ (incl. duplicates) or failed/."""
        try:
            result = self.ingest_fn(path)
        except Exception as exc:
            log.exception("Ingest of %s crashed", path)
            result = IngestResult(error=str(exc))
        if result.error:
            log.warning("Inbox file %s failed: %s", path.name, result.error)
            dest = FAILED
        else:
            if result.duplicate_of is not None:
                log.info("Inbox file %s is a duplicate of bill %s", path.name, result.duplicate_of)
            dest = PROCESSED
        self._move(path, self.inbox / dest)
        return result

    @staticmethod
    def _move(path: Path, folder: Path) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / path.name
        n = 1
        while target.exists():
            target = folder / f"{path.stem}-{n}{path.suffix}"
            n += 1
        shutil.move(str(path), target)
        return target
