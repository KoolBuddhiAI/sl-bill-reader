"""Adapter for the Anthropic Messages API (forced tool use for structured output)."""

import base64

from bill_reader.llm.base import TOOL_NAME, LLMClient, LLMError, RawResult
from bill_reader.llm.profiles import ModelProfile


class AnthropicClient(LLMClient):
    def __init__(self, profile: ModelProfile, http_client=None, api_key: str | None = None):
        super().__init__(profile)
        from anthropic import Anthropic

        key = api_key or profile.api_key
        if not key:
            raise LLMError(f"No API key: set {profile.api_key_env} for profile {profile.name!r}")
        kwargs = {"api_key": key, "timeout": profile.timeout_s, "max_retries": 1, "http_client": http_client}
        if profile.base_url:
            kwargs["base_url"] = profile.base_url
        self.client = Anthropic(**kwargs)

    def _call(self, system, user_text, schema, images, strategy) -> RawResult:
        content: list[dict] = []
        for img in images:
            media = "image/png" if img[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
            content.append(
                {"type": "image", "source": {"type": "base64", "media_type": media, "data": base64.b64encode(img).decode()}}
            )
        content.append({"type": "text", "text": user_text})
        kwargs: dict = {
            "model": self.profile.model,
            "system": system,
            "max_tokens": self.profile.max_tokens,
            "messages": [{"role": "user", "content": content}],
        }
        if strategy == "tools":
            kwargs["tools"] = [{"name": TOOL_NAME, "description": "Submit the result.", "input_schema": schema}]
            kwargs["tool_choice"] = {"type": "tool", "name": TOOL_NAME}
        message = self.client.messages.create(**kwargs)
        data: dict | str = ""
        for block in message.content:
            if block.type == "tool_use":
                data = block.input
                break
            if block.type == "text":
                data = block.text
        return RawResult(
            data=data,
            tokens_in=message.usage.input_tokens,
            tokens_out=message.usage.output_tokens,
            model_id=message.model,
        )
