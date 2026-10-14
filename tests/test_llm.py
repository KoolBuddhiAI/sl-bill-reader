import json

import httpx
import pytest
from pydantic import BaseModel

from bill_reader.llm import LLMError, load_models_config, make_client
from bill_reader.llm.base import FakeLLMClient, inline_schema, parse_json_text
from bill_reader.llm.profiles import ModelProfile
from bill_reader.schemas import BillExtraction


class Out(BaseModel):
    total: str


def profile(**kw) -> ModelProfile:
    base = dict(name="p", provider="openai_compatible", model="m", api_key_env="TEST_KEY", base_url="https://x.test/v1")
    base.update(kw)
    return ModelProfile(**base)


def test_models_yaml_loads_and_env_override(settings, monkeypatch):
    cfg = load_models_config(settings)
    assert cfg.extraction in cfg.profiles
    assert {"glm-vision", "deepseek-vision", "deepseek-text"} <= set(cfg.profiles)
    assert cfg.extraction_chain()[0].name == cfg.extraction
    settings.extraction_profile = "deepseek-vision"
    assert load_models_config(settings).extraction == "deepseek-vision"
    settings.extraction_profile = "nope"
    with pytest.raises(KeyError):
        load_models_config(settings)


def test_has_key_reads_named_env(monkeypatch):
    p = profile()
    monkeypatch.delenv("TEST_KEY", raising=False)
    assert not p.has_key
    monkeypatch.setenv("TEST_KEY", "k")
    assert p.has_key and p.api_key == "k"


def test_inline_schema_has_no_refs():
    assert "$ref" not in json.dumps(inline_schema(BillExtraction))


def test_parse_json_text_fenced():
    assert parse_json_text('Sure!\n```json\n{"total": "1"}\n```') == {"total": "1"}


def test_fake_client_repairs_once_then_fails():
    client = FakeLLMClient(profile(), [{"wrong": 1}, {"total": "5"}])
    out, resp = client.complete_structured("s", "u", Out)
    assert out.total == "5" and resp.attempts == 2 and "invalid" in client.calls[1]["user_text"]
    with pytest.raises(LLMError):
        FakeLLMClient(profile(), [{"x": 1}, {"y": 2}]).complete_structured("s", "u", Out)


def test_images_rejected_for_text_only_profile():
    with pytest.raises(LLMError):
        FakeLLMClient(profile(supports_vision=False), []).complete_structured("s", "u", Out, images=[b"x"])


def _completion(message: dict) -> dict:
    return {
        "id": "c1", "object": "chat.completion", "created": 0, "model": "m-2026",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", **message}}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
    }


def _openai_client(p, reply: dict, seen: list):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=_completion(reply))

    return make_client(p, http_client=httpx.Client(transport=httpx.MockTransport(handler)), api_key="k")


def test_openai_compat_tools_strategy_with_image():
    seen: list = []
    reply = {"content": None, "tool_calls": [{"id": "t", "type": "function",
             "function": {"name": "submit_result", "arguments": '{"total": "510.00"}'}}]}
    client = _openai_client(profile(supports_vision=True, extra_body={"thinking": {"type": "disabled"}}), reply, seen)
    out, resp = client.complete_structured("sys", "read", Out, images=[b"\xff\xd8jpeg"])
    assert out.total == "510.00"
    assert (resp.tokens_in, resp.tokens_out, resp.model_id, resp.strategy) == (11, 7, "m-2026", "tools")
    body = seen[0]
    assert body["tool_choice"]["function"]["name"] == "submit_result"
    assert body["messages"][1]["content"][0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert body["thinking"] == {"type": "disabled"}


def test_openai_compat_json_mode_parses_content():
    seen: list = []
    client = _openai_client(profile(supports_tools=False, supports_json_mode=True), {"content": '{"total": "7"}'}, seen)
    out, resp = client.complete_structured("sys", "u", Out)
    assert out.total == "7" and resp.strategy == "json_mode"
    assert seen[0]["response_format"] == {"type": "json_object"}
    assert "JSON schema" in seen[0]["messages"][0]["content"]


def test_openai_compat_http_error_becomes_llmerror():
    def handler(request):
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    client = make_client(profile(), http_client=httpx.Client(transport=httpx.MockTransport(handler)), api_key="k")
    with pytest.raises(LLMError):
        client.complete_structured("s", "u", Out)


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("TEST_KEY", raising=False)
    with pytest.raises(LLMError, match="TEST_KEY"):
        make_client(profile())


def test_anthropic_forced_tool():
    # Recent anthropic SDKs are built on httpx2 (older ones on httpx).
    transport_lib = pytest.importorskip("httpx2")
    seen: list = []

    def handler(request):
        seen.append(json.loads(request.content))
        return transport_lib.Response(200, json={
            "id": "m", "type": "message", "role": "assistant", "model": "claude-x", "stop_reason": "tool_use",
            "content": [{"type": "tool_use", "id": "t", "name": "submit_result", "input": {"total": "340"}}],
            "usage": {"input_tokens": 5, "output_tokens": 3},
        })

    p = profile(provider="anthropic", base_url=None, supports_vision=True)
    http_client = transport_lib.Client(transport=transport_lib.MockTransport(handler))
    client = make_client(p, http_client=http_client, api_key="k")
    out, resp = client.complete_structured("s", "u", Out, images=[b"\x89PNG\r\n\x1a\nxx"])
    assert out.total == "340" and resp.tokens_in == 5
    assert seen[0]["tool_choice"] == {"type": "tool", "name": "submit_result"}
    assert seen[0]["messages"][0]["content"][0]["source"]["media_type"] == "image/png"

