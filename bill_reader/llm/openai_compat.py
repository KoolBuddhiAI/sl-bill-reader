"""Adapter for OpenAI-compatible chat completions APIs (Z.ai GLM, DeepSeek, OpenAI, OpenRouter...)."""

import base64
import json

from openai import OpenAI

from bill_reader.llm.base import TOOL_NAME, LLMClient, LLMError, RawResult
from bill_reader.llm.profiles import ModelProfile


def image_data_uri(jpeg: bytes) -> str:
    mime = "image/png" if jpeg[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(jpeg).decode()}"


class OpenAICompatibleClient(LLMClient):
    def __init__(self, profile: ModelProfile, http_client=None, api_key: str | None = None):
        super().__init__(profile)
        key = api_key or profile.api_key
        if not key:
            raise LLMError(f"No API key: set {profile.api_key_env} for profile {profile.name!r}")
        self.client = OpenAI(
            api_key=key,
            base_url=profile.base_url,
            timeout=profile.timeout_s,
            max_retries=1,
            http_client=http_client,
        )

    def _call(self, system, user_text, schema, images, strategy) -> RawResult:
        content: list[dict] | str = user_text
        if images:
            content = [{"type": "image_url", "image_url": {"url": image_data_uri(img)}} for img in images]
            content.append({"type": "text", "text": user_text})
        kwargs: dict = {
            "model": self.profile.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
            "max_tokens": self.profile.max_tokens,
            "temperature": 0,
        }
        if self.profile.extra_body:
            kwargs["extra_body"] = self.profile.extra_body
        if strategy == "tools":
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {"name": TOOL_NAME, "description": "Submit the result.", "parameters": schema},
                }
            ]
            kwargs["tool_choice"] = (
                {"type": "function", "function": {"name": TOOL_NAME}}
                if self.profile.tool_choice == "named"
                else self.profile.tool_choice
            )
        elif strategy == "json_mode":
            kwargs["response_format"] = {"type": "json_object"}

        completion = self.client.chat.completions.create(**kwargs)
        message = completion.choices[0].message
        data: dict | str = message.content or ""
        if message.tool_calls:
            args = message.tool_calls[0].function.arguments
            data = json.loads(args) if isinstance(args, str) else args
        usage = completion.usage
        return RawResult(
            data=data,
            tokens_in=getattr(usage, "prompt_tokens", 0) or 0,
            tokens_out=getattr(usage, "completion_tokens", 0) or 0,
            model_id=completion.model,
        )
