"""LLM client abstraction supporting Ollama, vLLM, and llama.cpp."""
from __future__ import annotations

import json
from typing import Any

import httpx

from packages.core.logging import get_logger

logger = get_logger(__name__)


class LLMClient:
    """Unified LLM client for Ollama, vLLM (OpenAI-compatible), and llama.cpp."""

    def __init__(self, backend: str, base_url: str, model_name: str) -> None:
        self.backend = backend
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name

    async def complete(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str:
        """Send a prompt and return the completion string."""
        if self.backend == "ollama":
            return await self._ollama_complete(prompt, system, temperature, max_tokens)
        else:
            # vLLM and llama.cpp both expose an OpenAI-compatible /v1/chat/completions
            return await self._openai_compat_complete(
                prompt, system, temperature, max_tokens
            )

    async def _ollama_complete(
        self, prompt: str, system: str, temperature: float, max_tokens: int
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["message"]["content"]

    async def _openai_compat_complete(
        self, prompt: str, system: str, temperature: float, max_tokens: int
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/v1/chat/completions", json=payload
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def complete_json(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> dict:
        """
        Complete and parse JSON response.
        Raises ValueError if the output cannot be parsed as JSON.
        """
        raw = await self.complete(prompt, system=system, temperature=temperature, max_tokens=max_tokens)
        # strip markdown code fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw.rsplit("```", 1)[0]
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("llm_json_parse_failed", raw=raw[:500], error=str(exc))
            raise ValueError(f"LLM did not return valid JSON: {exc}") from exc
