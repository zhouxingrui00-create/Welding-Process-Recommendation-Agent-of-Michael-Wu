"""Compatibility imports. New callers should use services.llm.router.LLMRouter."""
from dataclasses import replace
from services.llm.base import LLMResponse
from services.llm.config import load_model_config
from services.llm.router import LLMRouter


class OllamaService(LLMRouter):
    """Legacy local-only entry point, implemented through the shared router."""

    def __init__(self) -> None:
        super().__init__(replace(load_model_config(), provider="ollama"))


__all__ = ["LLMResponse", "LLMRouter", "OllamaService"]
