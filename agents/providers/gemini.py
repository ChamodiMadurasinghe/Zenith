import json
import re

from config import Config

try:
    import google.generativeai as genai
except ImportError:
    genai = None


def _model(model_name: str | None = None):
    if not genai:
        raise RuntimeError("google-generativeai not installed")
    api_key = Config.gemini_api_key()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set in .env")
    genai.configure(api_key=api_key)
    name = model_name or Config.gemini_vision_model()
    return genai.GenerativeModel(name)


def gemini_text(prompt: str, system: str = "", model: str | None = None) -> str:
    model_client = _model(model)
    full = f"{system}\n\n{prompt}" if system else prompt
    response = model_client.generate_content(full)
    try:
        return response.text or ""
    except ValueError as e:
        raise RuntimeError(f"Gemini returned no text: {e}") from e


def gemini_json(prompt: str, system: str = "", model: str | None = None) -> dict:
    text = gemini_text(
        prompt + "\n\nRespond with valid JSON only, no markdown fences.",
        system,
        model=model,
    )
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def gemini_vision_json(prompt: str, image_path: str, system: str = "", model: str | None = None) -> dict:
    if not genai:
        raise RuntimeError("google-generativeai not installed")
    model_client = _model(model)
    uploaded = genai.upload_file(image_path)
    full = f"{system}\n\n{prompt}" if system else prompt
    response = model_client.generate_content([full, uploaded])
    text = (response.text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)
