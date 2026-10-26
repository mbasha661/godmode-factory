"""Phase 6 backend - workflow run endpoints. Wires Orchestrator + execute_agent + provider."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends

from ..auth import AuthUser, get_current_user
from ..config import Settings, get_settings
from ..db import get_db
from ..errors import conflict, not_found
from ..services.agents import execute_agent
from ..services.orchestrator import Orchestrator, utcnow
from ..services.providers import build_provider

router = APIRouter(prefix="/api", tags=["runs"])


def _orchestrator(settings: Settings) -> Orchestrator:
    return Orchestrator(
        db=get_db(settings),
        settings=settings,
        provider_factory=lambda: build_provider(settings),
        agent_executor=execute_agent,
    )


async def _owned_run(run_id: str, user: AuthUser, settings: Settings) -> dict:
    db = get_db(settings)
    run = await db.select_one("workflow_runs", {"id": run_id})
    if not run:
        raise not_found("run not found")
    project = await db.select_one("projects", {"id": run["project_id"]})
    if not project or project["owner_id"] != user.id:
        raise not_found("run not found")
    return run


@router.post("/projects/{project_id}/runs", status_code=201)
async def create_run(project_id: str, user: AuthUser = Depends(get_current_user),
                     settings: Settings = Depends(get_settings)):
    db = get_db(settings)
    project = await db.select_one("projects", {"id": project_id})
    if not project or project["owner_id"] != user.id:
        raise not_found("project not found")
    orch = _orchestrator(settings)
    goal = project.get("description") or project["name"]
    run = await orch.create_run(project_id, user.id, goal=goal)
    tasks = await db.select("tasks", {"run_id": run["id"]}, order="sequence", desc=False)
    return {"run": run, "tasks": tasks}


@router.get("/runs/{run_id}")
async def get_run(run_id: str, user: AuthUser = Depends(get_current_user),
                  settings: Settings = Depends(get_settings)):
    await _owned_run(run_id, user, settings)
    db = get_db(settings)
    run = await db.select_one("workflow_runs", {"id": run_id})
    tasks = await db.select("tasks", {"run_id": run_id}, order="sequence", desc=False)
    events = await db.select("execution_events", {"run_id": run_id},
                             order="created_at", desc=True, limit=50)
    return {"run": run, "tasks": tasks, "events": events}


@router.post("/runs/{run_id}/step")
async def step_run(run_id: str, user: AuthUser = Depends(get_current_user),
                   settings: Settings = Depends(get_settings)):
    await _owned_run(run_id, user, settings)
    return await _orchestrator(settings).step(run_id)


# In-process set of run ids with a live worker. The execution model is an
# in-process asyncio worker, so the only authoritative concurrency guard is
# in-process too: a DB "running" status can be a zombie from a killed deploy.
_EXECUTING: set[str] = set()


@router.post("/runs/{run_id}/execute", status_code=202)
async def execute_run(run_id: str, user: AuthUser = Depends(get_current_user),
                      settings: Settings = Depends(get_settings)):
    """Run the workflow to completion in the background (in-process worker).

    Idempotent: finished runs are a conflict, a run with a live worker returns
    already_executing, and a stale (orphaned) pending/running run can always be
    (re)started - this is the recovery path when the client's first execute call
    failed after the run was created.
    """
    run = await _owned_run(run_id, user, settings)
    if run["status"] in ("succeeded", "failed", "cancelled"):
        raise conflict(f"run is already {run['status']}; create a new run")
    if run_id in _EXECUTING:
        return {"status": "already_executing", "run_id": run_id}
    db = get_db(settings)
    if run["status"] == "pending":
        now = utcnow()
        await db.update("workflow_runs", {"id": run_id},
                        {"status": "running", "started_at": now, "updated_at": now})

    _EXECUTING.add(run_id)

    async def _worker() -> None:
        try:
            await _orchestrator(settings).run_until_done(run_id)
        except Exception:
            pass  # failures are already recorded on the run/tasks/events honestly
        finally:
            _EXECUTING.discard(run_id)

    asyncio.create_task(_worker())
    return {"status": "executing", "run_id": run_id}


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str, user: AuthUser = Depends(get_current_user),
                     settings: Settings = Depends(get_settings)):
    await _owned_run(run_id, user, settings)
    return await _orchestrator(settings).cancel(run_id)


@router.post("/runs/{run_id}/pause")
async def pause_run(run_id: str, user: AuthUser = Depends(get_current_user),
                    settings: Settings = Depends(get_settings)):
    await _owned_run(run_id, user, settings)
    return await _orchestrator(settings).pause(run_id)


@router.post("/runs/{run_id}/resume")
async def resume_run(run_id: str, user: AuthUser = Depends(get_current_user),
                     settings: Settings = Depends(get_settings)):
    await _owned_run(run_id, user, settings)
    return await _orchestrator(settings).resume(run_id)
