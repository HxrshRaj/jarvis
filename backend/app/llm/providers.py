"""Provider-agnostic LLM interface. API keys come from environment settings only."""
from __future__ import annotations

from typing import Protocol

import httpx

from app.config import get_settings


class LLMError(Exception):
    pass


class LLMProvider(Protocol):
    name: str
    is_real: bool

    def complete(self, system: str, user: str, *, json_mode: bool = False) -> str: ...


class MockProvider:
    """Offline stand-in. It is NOT an AI model and says so; it never fabricates answers."""

    name = "mock"
    is_real = False

    def complete(self, system: str, user: str, *, json_mode: bool = False) -> str:
        if json_mode:
            raise LLMError("mock provider cannot produce plans")
        return (
            "No language-model provider is configured, so I can't answer open-ended questions yet. "
            "I can still run tool-based tasks (list/read/search files, statistics, task history, tests). "
            "Set JARVIS_LLM_PROVIDER=openai_compat and JARVIS_LLM_API_KEY to enable real conversations."
        )


class OpenAICompatProvider:
    """Any OpenAI-compatible /chat/completions endpoint (OpenAI, Ollama, vLLM, LM Studio...)."""

    name = "openai_compat"
    is_real = True

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float):
        self.base_url, self.api_key, self.model, self.timeout = base_url.rstrip("/"), api_key, model, timeout

    def complete(self, system: str, user: str, *, json_mode: bool = False) -> str:
        body: dict = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            r = httpx.post(f"{self.base_url}/chat/completions", json=body, headers=headers, timeout=self.timeout)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"] or ""
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            # Never include headers/keys in the message.
            raise LLMError(f"provider request failed: {type(e).__name__}") from e


_override: LLMProvider | None = None


def set_provider_override(p: LLMProvider | None) -> None:  # used by tests
    global _override
    _override = p


def get_provider() -> LLMProvider:
    if _override is not None:
        return _override
    s = get_settings()
    if s.llm_provider == "openai_compat":
        return OpenAICompatProvider(s.llm_base_url, s.llm_api_key, s.llm_model, s.llm_timeout_seconds)
    return MockProvider()
