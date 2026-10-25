"""Gemini API provider (free tier). Key lives only in server-side settings."""
from __future__ import annotations

from typing import Any, Optional

import httpx

from ...errors import ErrorCategory
from .base import AIProvider, AIResponse, ProviderError

def _sanitize_schema(node):
    """Gemini responseSchema accepts only an OpenAPI subset; strip the rest."""
    if isinstance(node, dict):
        return {k: _sanitize_schema(v) for k, v in node.items()
                if k not in ("additionalProperties", "$schema")}
    if isinstance(node, list):
        return [_sanitize_schema(v) for v in node]
    return node



BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider(AIProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise ProviderError(ErrorCategory.AUTH_FAILURE, "GEMINI_API_KEY is not configured")
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
        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_output_tokens},
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if json_schema is not None:
            body["generationConfig"]["responseMimeType"] = "application/json"
            body["generationConfig"]["responseSchema"] = _sanitize_schema(json_schema)

        url = f"{BASE}/models/{self.model}:generateContent"
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                resp = await client.post(url, params={"key": self._key}, json=body)
        except httpx.TimeoutException as exc:
            raise ProviderError(ErrorCategory.PROVIDER_UNAVAILABLE, f"gemini timeout: {exc}", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(ErrorCategory.PROVIDER_UNAVAILABLE, f"gemini network error: {exc}", retryable=True) from exc

        if resp.status_code == 429:
            raise ProviderError(ErrorCategory.QUOTA_EXHAUSTED, "gemini quota exhausted (429)")
        if resp.status_code in (401, 403):
            raise ProviderError(ErrorCategory.AUTH_FAILURE, f"gemini auth failed ({resp.status_code})")
        if resp.status_code == 503:
            raise ProviderError(ErrorCategory.PROVIDER_UNAVAILABLE, "gemini overloaded (503)", retryable=True)
        if resp.status_code >= 400:
            raise ProviderError(ErrorCategory.PROVIDER_UNAVAILABLE, f"gemini error {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        try:
            text = "".join(
                part.get("text", "")
                for part in data["candidates"][0]["content"]["parts"]
                if "text" in part
            )
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(ErrorCategory.INVALID_MODEL_OUTPUT, f"unexpected gemini payload: {exc}") from exc
        usage = data.get("usageMetadata", {})
        return AIResponse(
            text=text,
            provider=self.name,
            model=self.model,
            prompt_tokens=usage.get("promptTokenCount", 0),
            completion_tokens=usage.get("candidatesTokenCount", 0),
            raw={"usageMetadata": usage},
        )
