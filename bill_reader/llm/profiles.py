"""Model profiles loaded from config/models.yaml."""

import json
import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from bill_reader.config import Settings


class ModelProfile(BaseModel):
    name: str = ""
    provider: Literal["openai_compatible", "anthropic"]
    model: str
    api_key_env: str
    base_url: str | None = None
    supports_vision: bool = False
    supports_tools: bool = True
    supports_json_mode: bool = False
    tool_choice: Literal["named", "required", "auto"] = "named"
    extra_body: dict[str, Any] = Field(default_factory=dict)
    max_tokens: int = 4096
    timeout_s: float = 90.0
    price_in_per_m: float | None = None
    price_out_per_m: float | None = None

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env) or None

    @property
    def has_key(self) -> bool:
        return self.api_key is not None

    @property
    def mode(self) -> str:
        return "vision" if self.supports_vision else "ocr+text"

    def estimate_cost(self, tokens_in: int, tokens_out: int) -> float | None:
        if self.price_in_per_m is None or self.price_out_per_m is None:
            return None
        return (tokens_in * self.price_in_per_m + tokens_out * self.price_out_per_m) / 1_000_000


class ModelsConfig(BaseModel):
    profiles: dict[str, ModelProfile]
    extraction: str
    categorisation: str
    fallback_chain: list[str] = Field(default_factory=list)

    def get(self, name: str) -> ModelProfile:
        try:
            return self.profiles[name]
        except KeyError:
            raise KeyError(f"Unknown model profile {name!r}; known: {', '.join(self.profiles)}") from None

    def extraction_chain(self) -> list[ModelProfile]:
        """Active extraction profile first, then the fallback chain (deduplicated)."""
        names = [self.extraction] + [n for n in self.fallback_chain if n != self.extraction]
        return [self.get(n) for n in names]


def active_overrides_path(settings: Settings) -> Path:
    return settings.data_dir / "active_models.json"


def save_active_profiles(settings: Settings, extraction: str | None, categorisation: str | None) -> None:
    """Persist the profiles chosen on the Settings page (they win over env vars and models.yaml)."""
    path = active_overrides_path(settings)
    current = json.loads(path.read_text()) if path.exists() else {}
    current.update({k: v for k, v in {"extraction": extraction, "categorisation": categorisation}.items() if v})
    load_models_config(settings, overrides=current)  # validate names before saving
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current))


def load_models_config(
    settings: Settings, path: Path | None = None, overrides: dict[str, str] | None = None
) -> ModelsConfig:
    """Selection precedence: Settings page (data/active_models.json) > BILL_READER_* env > models.yaml."""
    path = path or settings.config_dir / "models.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if overrides is None:
        override_file = active_overrides_path(settings)
        overrides = json.loads(override_file.read_text()) if override_file.exists() else {}
    profiles = {
        name: ModelProfile(name=name, **spec) for name, spec in (raw.get("profiles") or {}).items()
    }
    config = ModelsConfig(
        profiles=profiles,
        extraction=overrides.get("extraction") or settings.extraction_profile or raw.get("extraction", ""),
        categorisation=overrides.get("categorisation")
        or settings.categorisation_profile
        or raw.get("categorisation", ""),
        fallback_chain=raw.get("fallback_chain") or [],
    )
    for name in [config.extraction, config.categorisation, *config.fallback_chain]:
        config.get(name)  # fail fast on typos
    return config
