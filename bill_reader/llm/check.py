"""`bill-reader models list|check`: show profiles and probe the ones that have an API key."""

import io

from pydantic import BaseModel
from PIL import Image, ImageDraw

from bill_reader.config import Settings
from bill_reader.llm import LLMError, load_models_config, make_client


class _Probe(BaseModel):
    text: str


def _probe_image(text: str = "4931") -> bytes:
    img = Image.new("RGB", (320, 120), "white")
    ImageDraw.Draw(img).text((40, 30), text, fill="black", font_size=48)
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


def list_profiles(settings: Settings) -> list[dict]:
    cfg = load_models_config(settings)
    return [
        {
            "name": p.name,
            "provider": p.provider,
            "model": p.model,
            "mode": p.mode,
            "key": p.api_key_env + (" ✓" if p.has_key else " (not set)"),
            "role": ", ".join(
                r
                for r, active in (
                    ("extraction", p.name == cfg.extraction),
                    ("categorisation", p.name == cfg.categorisation),
                    ("fallback", p.name in cfg.fallback_chain),
                )
                if active
            ),
        }
        for p in cfg.profiles.values()
    ]


def check_profile(settings: Settings, name: str) -> dict:
    """Text probe for every profile; image probe for vision profiles. Never includes the key."""
    profile = load_models_config(settings).get(name)
    result = {"name": name, "model": profile.model, "text": "skipped", "vision": "n/a"}
    if not profile.has_key:
        result["text"] = f"skipped – {profile.api_key_env} not set"
        return result
    try:
        client = make_client(profile)
        out, resp = client.complete_structured("Reply in JSON.", "Return text = 'ok'.", _Probe)
        result["text"] = f"ok ({resp.strategy}, {resp.latency_ms} ms)"
        if profile.supports_vision:
            out, resp = client.complete_structured(
                "Read the image.", "What number is written in the image? Put only the digits in text.", _Probe,
                images=[_probe_image()],
            )
            result["vision"] = "ok" if "4931" in out.text else f"unexpected answer {out.text!r}"
    except LLMError as exc:
        msg = str(exc)
        result["vision" if result["text"].startswith("ok") else "text"] = f"error: {msg[:200]}"
    return result
