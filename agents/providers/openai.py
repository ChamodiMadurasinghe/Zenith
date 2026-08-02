import json
import re

from config import Config

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


def _client():
    if OpenAI is None:
        raise RuntimeError("openai package not installed — run: pip install openai")
    api_key = Config.openai_api_key()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set in .env")
    return OpenAI(api_key=api_key)


def openai_text(prompt: str, system: str = "", model: str | None = None) -> str:
    client = _client()
    model_name = Config.resolve_openai_model(model, Config.openai_chat_model())
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    response = client.chat.completions.create(model=model_name, messages=messages)
    return response.choices[0].message.content or ""


def openai_json(prompt: str, system: str = "", model: str | None = None) -> dict:
    text = openai_text(
        prompt + "\n\nRespond with valid JSON only, no markdown fences.",
        system,
        model=Config.resolve_openai_model(model, Config.openai_chat_model()),
    )
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)
