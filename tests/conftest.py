from pathlib import Path

import pytest
from sqlmodel import Session

from bill_reader.config import Settings
from bill_reader.db import make_engine

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        inbox_dir=tmp_path / "inbox",
        config_dir=REPO_ROOT / "config",
        watch_inbox=False,
        _env_file=None,
    )


@pytest.fixture
def engine(settings: Settings):
    return make_engine(settings)


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


@pytest.fixture
def samples_dir() -> Path:
    return REPO_ROOT / "samples"
