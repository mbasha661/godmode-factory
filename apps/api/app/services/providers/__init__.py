"""Provider factory + resilience wrapper: timeouts, capped exponential backoff.

Retry policy (spec sections 5-6):
- Only retryable transient failures are retried (timeouts, 503s).
- Auth and quota failures are never retried.
- Backoff: 1s, 2s, 4s ... capped; at most `max_retries` attempts total.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from ...config import Settings
from ...errors import ErrorCategory
from .base import AIProvider, AIResponse, ProviderError
from .gemini import GeminiProvider
from .groq import GroqProvider


def build_provider(settings: Settings) -> AIProvider:
    if settings.ai_provider == "gemini":
        return GeminiProvider(settings.gemini_api_key, settings.gemini_model)
    if settings.ai_provider == "groq":
        return GroqProvider(settings.groq_api_key, settings.groq_model)
    raise ProviderError(ErrorCategory.PROVIDER_UNAVAILABLE, f"unknown provider {settings.ai_provider!r}")


async def generate_with_retry(
    provider: AIProvider,
    prompt: str,
    *,
    system: Optional[str] = None,
    json_schema: Optional[dict[str, Any]] = None,
    max_output_tokens: int = 4096,
    timeout_s: float = 60.0,
    max_retries: int = 2,
) -> AIResponse:
    attempt = 0
    while True:
        try:
            return await provider.generate(
                prompt,
                system=system,
                json_schema=json_schema,
                max_output_tokens=max_output_tokens,
                timeout_s=timeout_s,
            )
        except ProviderError as exc:
            if not exc.retryable or attempt >= max_retries:
                raise
            await asyncio.sleep(min(2 ** attempt, 8))
            attempt += 1


def parse_json_response(response: AIResponse) -> dict[str, Any]:
    """Parse and minimally validate a structured model response."""
    try:
        data = json.loads(response.text)
    except json.JSONDecodeError as exc:
        raise ProviderError(
            ErrorCategory.INVALID_MODEL_OUTPUT,
            f"model did not return valid JSON: {exc}",
        ) from exc
    if not isinstance(data, dict):
        raise ProviderError(ErrorCategory.INVALID_MODEL_OUTPUT, "model JSON is not an object")
    return data
