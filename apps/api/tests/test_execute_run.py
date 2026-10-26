"""Regression: POST /runs/{id}/execute must be idempotent and must never leave
a created run orphaned in pending (the site-button bug, seen twice in proof
runs after redeploys)."""
import asyncio

from fastapi.testclient import TestClient

from app.auth import AuthUser, get_current_user
from app.main import create_app
from app.config import get_settings
from app.routers import runs as runs_router
from app.services.orchestrator import Orchestrator

USER = AuthUser(id="11111111-1111-1111-1111-111111111111", email="a@example.com")


def _client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_settings] = lambda: get_settings()
    return TestClient(app)


def _mk_run(client: TestClient) -> str:
    pid = client.post("/api/projects", json={"name": "P", "project_type": "web"}).json()["id"]
    return client.post(f"/api/projects/{pid}/runs").json()["run"]["id"]


def test_execute_flips_pending_to_running_and_second_execute_is_idempotent(monkeypatch):
    async def _stall(self, run_id):  # worker stays alive inside _EXECUTING
        await asyncio.sleep(30)

    monkeypatch.setattr(Orchestrator, "run_until_done", _stall)
    with _client() as client:  # portal stays open so the background worker keeps running
        run_id = _mk_run(client)

        r1 = client.post(f"/api/runs/{run_id}/execute")
        assert r1.status_code == 202, r1.text
        assert r1.json()["status"] == "executing"

        # the run must not still read pending after a successful execute
        assert client.get(f"/api/runs/{run_id}").json()["run"]["status"] == "running"

        r2 = client.post(f"/api/runs/{run_id}/execute")
        assert r2.status_code == 202, r2.text
        assert r2.json()["status"] == "already_executing"

    runs_router._EXECUTING.clear()  # don't leak into other tests


def test_execute_on_finished_run_conflicts():
    client = _client()
    run_id = _mk_run(client)
    r_cancel = client.post(f"/api/runs/{run_id}/cancel")
    assert r_cancel.status_code == 200, r_cancel.text
    r = client.post(f"/api/runs/{run_id}/execute")
    assert r.status_code == 409, r.text
