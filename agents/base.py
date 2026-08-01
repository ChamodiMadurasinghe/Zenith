"""Facade for agent LLM calls — routes to Gemini (vision) or OpenAI (text)."""

from agents.providers.gemini import gemini_json, gemini_text, gemini_vision_json
from agents.providers.openai import openai_json, openai_text
from config import Config


def generate_text(prompt: str, system: str = "", *, provider: str = "openai", model: str | None = None) -> str:
    if provider == "gemini":
        return gemini_text(prompt, system, model=model or Config.gemini_vision_model())
    return openai_text(prompt, system, model=model or Config.openai_chat_model())


def generate_json(prompt: str, system: str = "", *, provider: str = "openai", model: str | None = None) -> dict:
    if provider == "gemini":
        return gemini_json(prompt, system, model=model or Config.gemini_vision_model())
    return openai_json(prompt, system, model=model or Config.openai_chat_model())


def generate_with_image(prompt: str, image_path: str, system: str = "") -> dict:
    return gemini_vision_json(prompt, image_path, system, model=Config.gemini_vision_model())
