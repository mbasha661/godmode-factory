"""Groq provider (free tier alternate). OpenAI-compatible chat completions."""
from __future__ import annotations

from typing import Any, Optional
import json
import asyncio
import re

import httpx

from ...errors import ErrorCategory
from .base import AIProvider, AIResponse, ProviderError

BASE = "https://api.groq.com/openai/v1"


class GroqProvider(AIProvider):
    name = "groq"

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise ProviderError(ErrorCategory.AUTH_FAILURE, "GROQ_API_KEY is not configured")
        self._key = api_key
        self.model = model

    async def generate(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        json_schema: Optional[dict[str, Any]] = None,
        max_output_tokens: int = 4096,
        timeout_s: float = 60.0,
    ) -> AIResponse:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_completion_tokens": min(max_output_tokens, 8192),
        }
        if self.model.startswith("openai/gpt-oss-"):
            body["reasoning_effort"] = "low"
        if json_schema is not None:
            def strict_schema(node):
                if isinstance(node, dict):
                    out = {k: strict_schema(v) for k,v in node.items()}
                    if out.get("type") == "object":
                        out["required"] = list(out.get("properties", {}))
                        out["additionalProperties"] = False
                    return out
                if isinstance(node, list): return [strict_schema(v) for v in node]
                return node
            body["response_format"] = {"type": "json_schema", "json_schema": {
                "name": "agent_output", "strict": True, "schema": strict_schema(json_schema)}}
            if not self.model.startswith("openai/gpt-oss-"):
                body["response_format"] = {"type": "json_object"}
                messages.insert(0, {"role": "system", "content": "Required output JSON schema: " + json.dumps(json_schema)})

        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                for attempt in range(3):
                    resp = await client.post(
                        f"{BASE}/chat/completions",
                        headers={"Authorization": f"Bearer {self._key}"}, json=body)
                    if resp.status_code != 429:
                        break
                    detail = resp.json().get("error", {}).get("message", "")
                    if "per minute" not in detail.lower() or attempt == 2:
                        break
                    match = re.search(r"try again in ([0-9.]+)s", detail)
                    delay = float(match.group(1)) if match else 30
                    if delay > 65:
                        break
                    await asyncio.sleep(delay + 1)
        except httpx.TimeoutException as exc:
            raise ProviderError(ErrorCategory.PROVIDER_UNAVAILABLE, f"groq timeout: {exc}", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(ErrorCategory.PROVIDER_UNAVAILABLE, f"groq network error: {exc}", retryable=True) from exc

        if resp.status_code == 429:
            detail = resp.json().get("error", {}).get("message", "")
            raise ProviderError(ErrorCategory.QUOTA_EXHAUSTED, f"groq rate limit (429): {detail[:350]}")
        if resp.status_code in (401, 403):
            raise ProviderError(ErrorCategory.AUTH_FAILURE, f"groq auth failed ({resp.status_code})")
        if resp.status_code == 503:
            raise ProviderError(ErrorCategory.PROVIDER_UNAVAILABLE, "groq overloaded (503)", retryable=True)
        if resp.status_code >= 400:
            raise ProviderError(ErrorCategory.PROVIDER_UNAVAILABLE, f"groq error {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(ErrorCategory.INVALID_MODEL_OUTPUT, f"unexpected groq payload: {exc}") from exc
        usage = data.get("usage", {})
        return AIResponse(
            text=text,
            provider=self.name,
            model=self.model,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            raw={"usage": usage},
        )
