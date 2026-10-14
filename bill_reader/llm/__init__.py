"""Provider-agnostic LLM access: model profiles from config/models.yaml plus adapters."""

from bill_reader.llm.base import LLMClient, LLMError, LLMResponse
from bill_reader.llm.profiles import ModelProfile, ModelsConfig, load_models_config


def make_client(profile: ModelProfile, **kwargs) -> LLMClient:
    """Build the adapter for a profile. kwargs are passed to the adapter (e.g. http_client for tests)."""
    if profile.provider == "anthropic":
        from bill_reader.llm.anthropic_client import AnthropicClient

        return AnthropicClient(profile, **kwargs)
    if profile.provider == "openai_compatible":
        from bill_reader.llm.openai_compat import OpenAICompatibleClient

        return OpenAICompatibleClient(profile, **kwargs)
    raise LLMError(f"Unknown provider {profile.provider!r} in profile {profile.name!r}")


__all__ = [
    "LLMClient",
    "LLMError",
    "LLMResponse",
    "ModelProfile",
    "ModelsConfig",
    "load_models_config",
    "make_client",
]
