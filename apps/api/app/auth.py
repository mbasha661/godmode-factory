"""Supabase JWT auth. Validates the bearer token against Supabase GoTrue.

The token is never trusted from claims alone: /auth/v1/user is the authority.
"""
from dataclasses import dataclass
import httpx
from fastapi import Depends, Request

from .config import Settings, get_settings
from .errors import unauthorized, api_error


@dataclass
class AuthUser:
    id: str
    email: str


async def get_current_user(
    request: Request, settings: Settings = Depends(get_settings)
) -> AuthUser:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise unauthorized("missing bearer token")
    token = header.split(None, 1)[1].strip()
    if not token:
        raise unauthorized("empty bearer token")
    if not settings.supabase_configured:
        raise api_error(503, "auth_unavailable", "authentication backend is not configured")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{settings.supabase_url}/auth/v1/user",
                headers={"Authorization": f"Bearer {token}", "apikey": settings.supabase_anon_key},
            )
    except httpx.HTTPError:
        raise api_error(503, "auth_unavailable", "authentication backend unreachable")
    if resp.status_code != 200:
        raise unauthorized("invalid or expired token")
    data = resp.json()
    user_id = data.get("id")
    if not user_id:
        raise unauthorized("invalid token payload")
    return AuthUser(id=user_id, email=data.get("email", ""))
