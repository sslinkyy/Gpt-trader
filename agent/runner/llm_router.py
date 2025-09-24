"""Provider-agnostic LLM router."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict

from agent.schemas.config import LLMConfigSchema, LLMProviderSchema

LOGGER = logging.getLogger(__name__)


@dataclass
class LLMRequest:
    prompt: str
    temperature: float | None = None


class LLMRouter:
    """Route prompts to the active provider (API-first)."""

    def __init__(self, config: LLMConfigSchema) -> None:
        self._config = config
        self._active = config.active_provider

    def set_active_provider(self, name: str) -> None:
        if name not in self._config.providers:
            raise KeyError(f"LLM provider '{name}' not registered")
        self._active = name
        LOGGER.info("LLM active provider set to %s", name)

    def active_provider(self) -> LLMProviderSchema:
        return self._config.providers[self._active]

    def invoke(self, request: LLMRequest) -> str:
        provider = self.active_provider()
        if provider.type == "api":
            return self._invoke_api(provider, request)
        return self._invoke_ui(provider, request)

    def _invoke_api(self, provider: LLMProviderSchema, request: LLMRequest) -> str:
        LOGGER.info(
            "[demo] Would call API provider %s model=%s temperature=%s",
            provider.provider,
            provider.model,
            request.temperature,
        )
        return "(api response stub)"

    def _invoke_ui(self, provider: LLMProviderSchema, request: LLMRequest) -> str:
        LOGGER.info(
            "[demo] Would automate UI provider %s via app %s",
            provider.provider,
            provider.app,
        )
        return "(ui response stub)"


__all__ = ["LLMRouter", "LLMRequest"]
