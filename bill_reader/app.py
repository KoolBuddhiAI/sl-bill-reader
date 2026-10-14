"""FastAPI application factory."""

from fastapi import FastAPI

from bill_reader import __version__
from bill_reader.config import Settings, get_settings
from bill_reader.db import make_engine


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Bill Reader", version=__version__)
    app.state.settings = settings
    app.state.engine = make_engine(settings)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok", "version": __version__}

    return app
