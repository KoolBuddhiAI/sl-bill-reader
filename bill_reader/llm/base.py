"""LLM client protocol and the shared structured-output loop (validate + one repair retry)."""

import json
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from bill_reader.llm.profiles import ModelProfile

T = TypeVar("T", bound=BaseModel)

TOOL_NAME = "submit_result"


class LLMError(RuntimeError):
    """Provider call failed or never produced valid structured output."""


@dataclass
class LLMResponse:
    profile: str
    model_id: str
    strategy: str  # tools | json_mode | prompt_json
    latency_ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    attempts: int = 1
    raw: list[Any] = field(default_factory=list)  # raw payloads per attempt (for fixtures/debugging)


@dataclass
class RawResult:
    """What an adapter returns from one provider call."""

    data: Any  # dict (tool/json) or str (text to parse)
    tokens_in: int = 0
    tokens_out: int = 0
    model_id: str | None = None


def inline_schema(model: type[BaseModel]) -> dict:
    """JSON schema with $refs inlined; several OpenAI-compatible providers reject $ref/$defs."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return resolve(defs[node["$ref"].split("/")[-1]])
            return {k: resolve(v) for k, v in node.items()}
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    return resolve(schema)


def parse_json_text(text: str) -> dict:
    """Extract the first JSON object from model text (tolerates ```json fences and prose)."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in model output")
    return json.loads(text[start : end + 1])


class LLMClient(ABC):
    """Adapters implement `_call`; callers use `complete_structured`."""

    def __init__(self, profile: ModelProfile):
        self.profile = profile

    @property
    def strategy(self) -> str:
        if self.profile.supports_tools:
            return "tools"
        if self.profile.supports_json_mode:
            return "json_mode"
        return "prompt_json"

    @abstractmethod
    def _call(
        self, system: str, user_text: str, schema: dict, images: list[bytes], strategy: str
    ) -> RawResult: ...

    def complete_structured(
        self,
        system: str,
        user_text: str,
        output_model: type[T],
        images: list[bytes] | None = None,
    ) -> tuple[T, LLMResponse]:
        images = images or []
        if images and not self.profile.supports_vision:
            raise LLMError(f"Profile {self.profile.name!r} does not support images")
        schema = inline_schema(output_model)
        strategy = self.strategy
        if strategy != "tools":
            system = (
                f"{system}\n\nRespond with ONLY a JSON object (no prose) that matches this JSON schema:\n"
                f"{json.dumps(schema, ensure_ascii=False)}"
            )
        resp = LLMResponse(profile=self.profile.name, model_id=self.profile.model, strategy=strategy, attempts=0)
        started = time.monotonic()
        prompt = user_text
        last_error = ""
        for _ in range(2):  # first try + one repair retry
            resp.attempts += 1
            try:
                raw = self._call(system, prompt, schema, images, strategy)
            except LLMError:
                raise
            except Exception as exc:  # provider SDK errors: auth, timeout, 4xx/5xx
                raise LLMError(f"{self.profile.name}: {type(exc).__name__}: {exc}") from exc
            resp.tokens_in += raw.tokens_in
            resp.tokens_out += raw.tokens_out
            resp.model_id = raw.model_id or resp.model_id
            resp.raw.append(raw.data)
            try:
                data = raw.data if isinstance(raw.data, dict) else parse_json_text(str(raw.data))
                result = output_model.model_validate(data)
                resp.latency_ms = int((time.monotonic() - started) * 1000)
                return result, resp
            except (ValueError, ValidationError) as exc:
                last_error = str(exc)[:2000]
                prompt = (
                    f"{user_text}\n\nYour previous answer was invalid: {last_error}\n"
                    "Return a corrected answer that matches the schema exactly."
                )
        raise LLMError(f"{self.profile.name}: invalid structured output after retry: {last_error}")


class FakeLLMClient(LLMClient):
    """Deterministic client for tests: returns queued payloads (dict, str or Exception) in order."""

    def __init__(self, profile: ModelProfile, responses: list[Any]):
        super().__init__(profile)
        self.responses = list(responses)
        self.calls: list[dict] = []

    def _call(self, system, user_text, schema, images, strategy) -> RawResult:
        self.calls.append({"system": system, "user_text": user_text, "images": len(images), "strategy": strategy})
        if not self.responses:
            raise LLMError("FakeLLMClient: no more responses queued")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return RawResult(data=item, tokens_in=100, tokens_out=50)
