"""FastAPI application factory: wires the database, worker, inbox watcher and routes."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from sqlmodel import Session

from bill_reader import __version__
from bill_reader.config import Settings, get_settings
from bill_reader.db import make_engine
from bill_reader.ingest import IngestResult, ingest_path
from bill_reader.watcher import InboxWatcher
from bill_reader.worker import Pipeline, Worker, default_ocr

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, *, worker_threads: int | None = None, **pipeline_kwargs) -> FastAPI:
    """pipeline_kwargs (client_factory, ocr, last_resort) let tests swap in fakes."""
    settings = settings or get_settings()
    engine = make_engine(settings)
    if not pipeline_kwargs:
        ocr, last_resort = default_ocr()
        pipeline_kwargs = {"ocr": ocr, "last_resort": last_resort}
    pipeline = Pipeline(settings, engine, **pipeline_kwargs)
    worker = Worker(pipeline, settings.worker_threads if worker_threads is None else worker_threads)

    def ingest_inbox_file(path: Path) -> IngestResult:
        with Session(engine) as session:
            return ingest_path(session, settings, path, source="inbox", enqueue=worker.enqueue)

    watcher = InboxWatcher(settings, ingest_inbox_file) if settings.watch_inbox else None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        requeued = worker.requeue_stuck()
        if requeued:
            log.info("re-queued %d bills left in processing", requeued)
        if watcher is not None:
            Path(settings.inbox_dir).mkdir(parents=True, exist_ok=True)
            watcher.start()
        yield
        if watcher is not None:
            watcher.stop()
        worker.shutdown()

    app = FastAPI(title="Bill Reader", version=__version__, lifespan=lifespan)
    app.state.settings, app.state.engine, app.state.worker, app.state.pipeline = settings, engine, worker, pipeline

    from bill_reader.api import router as api_router

    app.include_router(api_router)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok", "version": __version__, "ocr": pipeline.ocr.name if pipeline.ocr else None}

    return app
