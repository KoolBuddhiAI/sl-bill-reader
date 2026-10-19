"""Application settings, read from environment variables (prefix BILL_READER_) and `.env`."""

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BILL_READER_", env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    inbox_dir: Path = Path("inbox")
    config_dir: Path = Path("config")

    home_currency: str = "LKR"
    default_paying_account: str = "1-1110"

    # Active model profiles; None means "use the selection in config/models.yaml".
    extraction_profile: str | None = None
    categorisation_profile: str | None = None

    # Overall confidence below this triggers the next profile in the fallback chain.
    fallback_confidence: float = 0.5
    # Field colouring thresholds (green >= high, amber >= low, red below).
    confidence_high: float = 0.85
    confidence_low: float = 0.6

    max_image_px: int = 2000
    pdf_dpi: int = 200
    worker_threads: int = 2
    watch_inbox: bool = True

    @property
    def db_path(self) -> Path:
        return self.data_dir / "bill_reader.db"

    @property
    def documents_dir(self) -> Path:
        return self.data_dir / "documents"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.documents_dir, self.exports_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    # Model profiles read their API keys (ZAI_API_KEY, DEEPSEEK_API_KEY, ...) from os.environ,
    # so export `.env` into the process environment; real environment variables still win.
    load_dotenv(".env", override=False)
    return Settings()
