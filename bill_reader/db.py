"""SQLite engine and session helpers."""

from collections.abc import Iterator

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine

from bill_reader.config import Settings


def make_engine(settings: Settings) -> Engine:
    settings.ensure_dirs()
    engine = create_engine(
        f"sqlite:///{settings.db_path}",
        connect_args={"check_same_thread": False},
    )
    from bill_reader import models  # noqa: F401  (register tables)

    SQLModel.metadata.create_all(engine)
    return engine


def session_scope(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session
