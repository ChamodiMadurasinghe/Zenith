"""Gemini provider — google-genai SDK (supports AI Studio AQ. and AIzaSy keys)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from config import Config

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None


def _api_key() -> str:
    key = Config.gemini_api_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set in .env")
    return key.strip()


def _model_name(model: str | None) -> str:
    return model or Config.gemini_vision_model()


def _parse_json_text(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    if not text:
        return {}
    return json.loads(text)


def _legacy_module():
    try:
        import google.generativeai as legacy_genai
    except ImportError:
        return None
    return legacy_genai


def _use_legacy_sdk(key: str) -> bool:
    """Legacy google-generativeai only accepts classic AIzaSy keys."""
    return key.startswith("AIza") and _legacy_module() is not None


def _legacy_model(model_name: str | None = None):
    legacy_genai = _legacy_module()
    if not legacy_genai:
        raise RuntimeError("google-generativeai not installed")
    legacy_genai.configure(api_key=_api_key())
    return legacy_genai.GenerativeModel(_model_name(model_name))


def _client() -> genai.Client:
    if genai is None:
        raise RuntimeError(
            "google-genai not installed. Run: pip install google-genai"
        )
    return genai.Client(api_key=_api_key())


def _generate_config(*, system: str = "", json_mode: bool = False):
    if types is None:
        return None
    kwargs: dict = {}
    if system:
        kwargs["system_instruction"] = system
    if json_mode:
        kwargs["response_mime_type"] = "application/json"
    return types.GenerateContentConfig(**kwargs) if kwargs else None


def gemini_text(prompt: str, system: str = "", model: str | None = None) -> str:
    key = _api_key()
    name = _model_name(model)

    if _use_legacy_sdk(key):
        model_client = _legacy_model(name)
        full = f"{system}\n\n{prompt}" if system else prompt
        response = model_client.generate_content(full)
        try:
            return response.text or ""
        except ValueError as e:
            raise RuntimeError(f"Gemini returned no text: {e}") from e

    client = _client()
    response = client.models.generate_content(
        model=name,
        contents=prompt,
        config=_generate_config(system=system),
    )
    return response.text or ""


def gemini_json(prompt: str, system: str = "", model: str | None = None) -> dict:
    text = gemini_text(
        prompt + "\n\nRespond with valid JSON only, no markdown fences.",
        system,
        model=model,
    )
    return _parse_json_text(text)


def gemini_vision_json(
    prompt: str,
    image_path: str,
    system: str = "",
    model: str | None = None,
) -> dict:
    key = _api_key()
    name = _model_name(model)
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    json_hint = "\n\nRespond with valid JSON only, no markdown fences."
    full_prompt = f"{prompt}{json_hint}"

    if _use_legacy_sdk(key):
        legacy_genai = _legacy_module()
        if not legacy_genai:
            raise RuntimeError("google-generativeai not installed")
        model_client = _legacy_model(name)
        uploaded = legacy_genai.upload_file(str(path))
        system_block = f"{system}\n\n" if system else ""
        response = model_client.generate_content([f"{system_block}{full_prompt}", uploaded])
        return _parse_json_text(response.text or "")

    from PIL import Image

    client = _client()
    image = Image.open(path)
    contents: list = [full_prompt, image]
    if system:
        config = _generate_config(system=system, json_mode=True)
    else:
        config = _generate_config(json_mode=True)

    response = client.models.generate_content(
        model=name,
        contents=contents,
        config=config,
    )
    return _parse_json_text(response.text or "")
