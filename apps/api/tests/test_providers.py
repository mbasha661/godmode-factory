"""Provider adapter tests: real parsing/retry logic, mocked transport.
The live Gemini request evidence is scripts/verify_provider.py (real HTTP)."""
import pytest

from app.errors import ErrorCategory
from app.services.providers import generate_with_retry, parse_json_response
from app.services.providers.base import AIProvider, AIResponse, ProviderError


class FakeProvider(AIProvider):
    name = "fake"

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    async def generate(self, prompt, **kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.mark.asyncio
async def test_retry_succeeds_after_transient_503():
    p = FakeProvider([
        ProviderError(ErrorCategory.PROVIDER_UNAVAILABLE, "503", retryable=True),
        AIResponse(text="ok", provider="fake", model="m"),
    ])
    r = await generate_with_retry(p, "hi")
    assert r.text == "ok"
    assert p.calls == 2


@pytest.mark.asyncio
async def test_quota_error_is_never_retried():
    p = FakeProvider([ProviderError(ErrorCategory.QUOTA_EXHAUSTED, "429")])
    with pytest.raises(ProviderError) as ei:
        await generate_with_retry(p, "hi")
    assert ei.value.category == ErrorCategory.QUOTA_EXHAUSTED
    assert p.calls == 1


@pytest.mark.asyncio
async def test_auth_error_is_never_retried():
    p = FakeProvider([ProviderError(ErrorCategory.AUTH_FAILURE, "401")])
    with pytest.raises(ProviderError):
        await generate_with_retry(p, "hi")
    assert p.calls == 1


@pytest.mark.asyncio
async def test_retry_budget_is_capped():
    p = FakeProvider([
        ProviderError(ErrorCategory.PROVIDER_UNAVAILABLE, "503", retryable=True),
        ProviderError(ErrorCategory.PROVIDER_UNAVAILABLE, "503", retryable=True),
        ProviderError(ErrorCategory.PROVIDER_UNAVAILABLE, "503", retryable=True),
    ])
    with pytest.raises(ProviderError):
        await generate_with_retry(p, "hi", max_retries=2)
    assert p.calls == 3


def test_parse_json_response_valid():
    r = AIResponse(text='{"a": 1}', provider="x", model="y")
    assert parse_json_response(r) == {"a": 1}


def test_parse_json_response_rejects_non_json():
    r = AIResponse(text="not json", provider="x", model="y")
    with pytest.raises(ProviderError) as ei:
        parse_json_response(r)
    assert ei.value.category == ErrorCategory.INVALID_MODEL_OUTPUT


def test_parse_json_response_rejects_array():
    r = AIResponse(text="[1,2]", provider="x", model="y")
    with pytest.raises(ProviderError):
        parse_json_response(r)
