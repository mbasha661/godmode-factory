import os
os.environ["SECONDS_BETWEEN_AGENT_STEPS"]="0"
"""Orchestrator tests over the real logic with the in-memory store."""
import pytest

from app.config import get_settings
from app.db import MemoryDB
from app.services.orchestrator import Orchestrator, ready_tasks, blocked_tasks
from app.services.providers.base import AIResponse, ProviderError
from app.errors import ErrorCategory


class FakeProvider:
    name = "fake"
    model = "m1"


def make_orch(executor):
    settings = get_settings()
    settings.seconds_between_agent_steps = 0
    return Orchestrator(MemoryDB(), settings, lambda: FakeProvider(), executor)


async def ok_executor(role, task_input, provider):
    return {"role": role, "done": True}


@pytest.mark.asyncio
async def test_run_creates_seven_tasks_with_dependencies():
    orch = make_orch(ok_executor)
    run = await orch.create_run("p1", "u1")
    tasks = await orch.db.select("tasks", {"run_id": run["id"]})
    deps = await orch.db.select("task_dependencies", {})
    assert len(tasks) == 7
    assert {t["agent_role"] for t in tasks} == {
        "architect", "ui_designer", "frontend_dev", "backend_dev",
        "db_engineer", "devops", "test_repair",
    }
    assert len(deps) == 10  # 0+1+1+2+3+2+1 dependency edges


@pytest.mark.asyncio
async def test_dependencies_gate_execution_order():
    orch = make_orch(ok_executor)
    run = await orch.create_run("p1", "u1")
    await orch.run_until_done(run["id"])
    tasks = await orch.db.select("tasks", {"run_id": run["id"]}, order="sequence", desc=False)
    assert all(t["status"] == "succeeded" for t in tasks)
    final = await orch.db.select_one("workflow_runs", {"id": run["id"]})
    assert final["status"] == "succeeded"
    events = await orch.db.select("execution_events", {"run_id": run["id"]})
    assert any(e["event_type"] == "run_succeeded" for e in events)


@pytest.mark.asyncio
async def test_architect_runs_first_and_devops_last():
    order = []
    async def recording(role, task_input, provider):
        order.append(role)
        return {}
    orch = make_orch(recording)
    run = await orch.create_run("p1", "u1")
    await orch.run_until_done(run["id"])
    assert order[0] == "architect"
    assert order[-1] == "devops"
    assert order.index("test_repair") > order.index("frontend_dev")


@pytest.mark.asyncio
async def test_failed_task_blocks_dependents_and_fails_run():
    async def failing(role, task_input, provider):
        if role == "db_engineer":
            raise ProviderError(ErrorCategory.TEST_FAILURE, "boom")
        return {}
    orch = make_orch(failing)
    run = await orch.create_run("p1", "u1")
    await orch.run_until_done(run["id"])
    tasks = {t["agent_role"]: t for t in await orch.db.select("tasks", {"run_id": run["id"]})}
    # db_engineer retried to max_attempts then failed
    assert tasks["db_engineer"]["status"] == "failed"
    assert tasks["db_engineer"]["attempts"] == tasks["db_engineer"]["max_attempts"]
    # dependents can never run
    assert tasks["backend_dev"]["status"] == "blocked"
    assert tasks["frontend_dev"]["status"] == "blocked"
    # architect is independent and did succeed
    assert tasks["architect"]["status"] == "succeeded"
    final = await orch.db.select_one("workflow_runs", {"id": run["id"]})
    assert final["status"] == "failed"


@pytest.mark.asyncio
async def test_quota_error_fails_immediately_without_retry():
    calls = []
    async def quota(role, task_input, provider):
        calls.append(role)
        raise ProviderError(ErrorCategory.QUOTA_EXHAUSTED, "quota")
    orch = make_orch(quota)
    run = await orch.create_run("p1", "u1")
    await orch.run_until_done(run["id"])
    assert calls == ["architect"]  # no retry, run stops
    task = (await orch.db.select("tasks", {"run_id": run["id"]}))[0]
    assert task["attempts"] == 1
    assert task["status"] == "failed"


@pytest.mark.asyncio
async def test_recovery_resets_stale_running_task():
    orch = make_orch(ok_executor)
    run = await orch.create_run("p1", "u1")
    tasks = await orch.db.select("tasks", {"run_id": run["id"]})
    # simulate crash mid-task
    await orch.db.update("tasks", {"id": tasks[0]["id"]}, {"status": "running"})
    n = await orch.recover_interrupted(run["id"])
    assert n == 1
    t = await orch.db.select_one("tasks", {"id": tasks[0]["id"]})
    assert t["status"] == "ready"
    # and the run can now complete
    await orch.run_until_done(run["id"])
    final = await orch.db.select_one("workflow_runs", {"id": run["id"]})
    assert final["status"] == "succeeded"


@pytest.mark.asyncio
async def test_cancel_stops_run():
    orch = make_orch(ok_executor)
    run = await orch.create_run("p1", "u1")
    await orch.cancel(run["id"])
    final = await orch.db.select_one("workflow_runs", {"id": run["id"]})
    assert final["status"] == "cancelled"
    tasks = await orch.db.select("tasks", {"run_id": run["id"]})
    assert all(t["status"] == "cancelled" for t in tasks)


def test_ready_tasks_pure():
    tasks = [
        {"id": "a", "status": "succeeded", "sequence": 0},
        {"id": "b", "status": "pending", "sequence": 1},
        {"id": "c", "status": "pending", "sequence": 2},
    ]
    deps = [{"task_id": "c", "depends_on_task_id": "b"}]
    ready = ready_tasks(tasks, deps)
    assert [t["id"] for t in ready] == ["b"]


def test_blocked_tasks_pure():
    tasks = [
        {"id": "a", "status": "failed", "sequence": 0},
        {"id": "b", "status": "pending", "sequence": 1},
    ]
    deps = [{"task_id": "b", "depends_on_task_id": "a"}]
    assert [t["id"] for t in blocked_tasks(tasks, deps)] == ["b"]
