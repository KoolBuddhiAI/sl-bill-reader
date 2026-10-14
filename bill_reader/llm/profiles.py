"""Model profiles loaded from config/models.yaml."""

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


def load_models_config(settings: Settings, path: Path | None = None) -> ModelsConfig:
    path = path or settings.config_dir / "models.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    profiles = {
        name: ModelProfile(name=name, **spec) for name, spec in (raw.get("profiles") or {}).items()
    }
    config = ModelsConfig(
        profiles=profiles,
        extraction=settings.extraction_profile or raw.get("extraction", ""),
        categorisation=settings.categorisation_profile or raw.get("categorisation", ""),
        fallback_chain=raw.get("fallback_chain") or [],
    )
    for name in [config.extraction, config.categorisation, *config.fallback_chain]:
        config.get(name)  # fail fast on typos
    return config
