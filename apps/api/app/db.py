"""Database access layer.

Two implementations behind one protocol:
- SupabaseDB: real PostgREST access using the service role key (server-side only).
  RLS stays enabled as defense-in-depth; every query also carries explicit
  ownership filters, so the service role can never leak another tenant's rows.
- MemoryDB: deterministic in-memory store for unit tests. Real logic, fake storage.
"""
from __future__ import annotations

from typing import Any, Optional
import httpx

from .config import Settings


class DatabaseError(Exception):
    pass


class MemoryDB:
    """In-memory implementation of the store used by unit tests."""

    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}

    async def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        self.tables.setdefault(table, []).append(dict(row))
        return dict(row)

    async def select(
        self,
        table: str,
        filters: Optional[dict[str, Any]] = None,
        order: Optional[str] = None,
        desc: bool = True,
        limit: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        rows = list(self.tables.get(table, []))
        for key, value in (filters or {}).items():
            rows = [r for r in rows if r.get(key) == value]
        if order:
            rows.sort(key=lambda r: (r.get(order) is None, r.get(order)), reverse=desc)
        if limit is not None:
            rows = rows[:limit]
        return [dict(r) for r in rows]

    async def select_one(self, table: str, filters: dict[str, Any]) -> Optional[dict[str, Any]]:
        rows = await self.select(table, filters, limit=1)
        return rows[0] if rows else None

    async def update(self, table: str, filters: dict[str, Any], patch: dict[str, Any]) -> list[dict[str, Any]]:
        updated = []
        for row in self.tables.get(table, []):
            if all(row.get(k) == v for k, v in filters.items()):
                row.update(patch)
                updated.append(dict(row))
        return updated

    async def delete(self, table: str, filters: dict[str, Any]) -> int:
        before = len(self.tables.get(table, []))
        self.tables[table] = [
            r for r in self.tables.get(table, [])
            if not all(r.get(k) == v for k, v in filters.items())
        ]
        return before - len(self.tables[table])


class SupabaseDB:
    """PostgREST-backed store. Server-side only; requires the service role key."""

    def __init__(self, settings: Settings) -> None:
        if not settings.supabase_configured:
            raise DatabaseError("Supabase is not configured")
        self._base = f"{settings.supabase_url}/rest/v1"
        self._headers = {
            "apikey": settings.supabase_service_role_key,
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.request(method, f"{self._base}/{path}", headers=self._headers, **kwargs)
        except httpx.HTTPError as exc:
            raise DatabaseError(f"database unreachable: {exc}") from exc
        if resp.status_code >= 400:
            raise DatabaseError(f"database error {resp.status_code}: {resp.text[:300]}")
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    @staticmethod
    def _params(filters: Optional[dict[str, Any]]) -> dict[str, str]:
        return {k: f"eq.{v}" for k, v in (filters or {}).items()}

    async def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        data = await self._request("POST", table, json=row)
        return data[0] if isinstance(data, list) else data

    async def select(
        self,
        table: str,
        filters: Optional[dict[str, Any]] = None,
        order: Optional[str] = None,
        desc: bool = True,
        limit: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        params = self._params(filters)
        if order:
            params["order"] = f"{order}.{'desc' if desc else 'asc'}"
        if limit is not None:
            params["limit"] = str(limit)
        data = await self._request("GET", table, params=params)
        return data or []

    async def select_one(self, table: str, filters: dict[str, Any]) -> Optional[dict[str, Any]]:
        rows = await self.select(table, filters, limit=1)
        return rows[0] if rows else None

    async def update(self, table: str, filters: dict[str, Any], patch: dict[str, Any]) -> list[dict[str, Any]]:
        data = await self._request("PATCH", table, params=self._params(filters), json=patch)
        return data or []

    async def delete(self, table: str, filters: dict[str, Any]) -> int:
        await self._request("DELETE", table, params=self._params(filters))
        return 1


_memory_db_singleton: MemoryDB | None = None


def get_db(settings: Settings) -> Any:
    """Factory: real Supabase store when configured, in-memory otherwise (dev/test).

    The in-memory fallback is a process-wide singleton so state persists across
    requests, matching the semantics of a real database.
    """
    global _memory_db_singleton
    if settings.supabase_configured:
        return SupabaseDB(settings)
    if _memory_db_singleton is None:
        _memory_db_singleton = MemoryDB()
    return _memory_db_singleton
