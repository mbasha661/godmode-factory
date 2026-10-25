"""Live provider smoke test: makes ONE real Gemini request.
Run from apps/api: .venv/bin/python ../../scripts/verify_provider.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "apps", "api"))

from app.config import get_settings
from app.services.providers import build_provider, generate_with_retry, parse_json_response


async def main():
    settings = get_settings()
    provider = build_provider(settings)
    resp = await generate_with_retry(
        provider,
        'Reply with a JSON object: {"pong": true}',
        json_schema={"type": "object", "properties": {"pong": {"type": "boolean"}}},
        max_output_tokens=400,
    )
    data = parse_json_response(resp)
    assert data.get("pong") is True, data
    print(f"LIVE OK provider={resp.provider} model={resp.model} "
          f"prompt_tokens={resp.prompt_tokens} completion_tokens={resp.completion_tokens}")


if __name__ == "__main__":
    asyncio.run(main())
