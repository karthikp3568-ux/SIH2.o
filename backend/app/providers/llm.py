"""LLM providers.

The system is designed so the LLM is *optional*. With LLM_PROVIDER=none (the
default) every user-visible output is produced by deterministic code:
rule-based profile extraction and template-rendered explanations built from
computed scores.

When an LLM is configured it is used only to:
  * assist profile extraction (its output is merged with, and overridden by,
    the deterministic extractor's high-confidence facts), and
  * rephrase already-computed explanation bullets into friendlier language.

It is never allowed to originate an opportunity, qualification, scheme or fact.
"""

from __future__ import annotations

import json
from functools import lru_cache

import httpx

from ..config import get_settings
from .base import LLMProvider, ProviderNotConfigured, ProviderStatus


class NullLLMProvider:
    """No LLM. Callers fall back to deterministic templates."""

    name = "none"
    available = False

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            kind="llm",
            configured=False,
            detail=(
                "No LLM configured. Profile extraction and explanations use "
                "deterministic rules and templates."
            ),
            is_offline_default=True,
        )

    def complete(self, system: str, user: str, max_tokens: int = 800) -> str:
        raise ProviderNotConfigured("No LLM provider is configured.")


class AnthropicLLMProvider:
    name = "anthropic"

    def __init__(self) -> None:
        settings = get_settings()
        self.api_key = settings.anthropic_api_key
        self.model = settings.llm_model or "claude-sonnet-5"

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            kind="llm",
            configured=self.available,
            detail=(
                f"Anthropic API, model {self.model}."
                if self.available
                else "ANTHROPIC_API_KEY is not set."
            ),
        )

    def complete(self, system: str, user: str, max_tokens: int = 800) -> str:
        if not self.available:
            raise ProviderNotConfigured("ANTHROPIC_API_KEY is not set.")
        try:
            response = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": max_tokens,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
                timeout=45.0,
            )
            response.raise_for_status()
            body = response.json()
            return "".join(
                block.get("text", "") for block in body.get("content", []) if isinstance(block, dict)
            )
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise ProviderNotConfigured(f"Anthropic request failed: {exc}") from exc


class OpenAICompatibleLLMProvider:
    name = "openai_compatible"

    def __init__(self) -> None:
        settings = get_settings()
        self.api_key = settings.openai_api_key
        self.base_url = settings.openai_base_url.rstrip("/")
        self.model = settings.llm_model

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            kind="llm",
            configured=self.available,
            detail=(
                f"OpenAI-compatible endpoint {self.base_url}, model {self.model}."
                if self.available
                else "OPENAI_API_KEY is not set."
            ),
        )

    def complete(self, system: str, user: str, max_tokens: int = 800) -> str:
        if not self.available:
            raise ProviderNotConfigured("OPENAI_API_KEY is not set.")
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "max_tokens": max_tokens,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=45.0,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
            raise ProviderNotConfigured(f"LLM request failed: {exc}") from exc


@lru_cache
def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    match settings.llm_provider:
        case "anthropic":
            return AnthropicLLMProvider()
        case "openai_compatible":
            return OpenAICompatibleLLMProvider()
        case _:
            return NullLLMProvider()


def complete_json(system: str, user: str, max_tokens: int = 800) -> dict | None:
    """Ask the LLM for JSON. Returns None on any failure - callers must cope."""
    provider = get_llm_provider()
    if not provider.available:
        return None
    try:
        raw = provider.complete(system, user, max_tokens)
    except ProviderNotConfigured:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None
