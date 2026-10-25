"""Provider-independent AI adapter. Spec section 2 (AI model provider).

All providers return a common AIResponse; failures are typed so the
orchestrator can distinguish quota exhaustion from transient errors.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ...errors import ErrorCategory


class ProviderError(Exception):
    def __init__(self, category: ErrorCategory, message: str, retryable: bool = False):
        super().__init__(message)
        self.category = category
        self.retryable = retryable


@dataclass
class AIResponse:
    text: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


class AIProvider:
    name: str = "base"

    async def generate(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        json_schema: Optional[dict[str, Any]] = None,
        max_output_tokens: int = 4096,
        timeout_s: float = 60.0,
    ) -> AIResponse:
        raise NotImplementedError
