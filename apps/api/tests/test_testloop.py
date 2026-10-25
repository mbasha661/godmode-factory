import os
os.environ["SECONDS_BETWEEN_AGENT_STEPS"]="0"
import json
import pytest
from app.services.orchestrator import Orchestrator
from app.db import MemoryDB
from app.config import get_settings
from app.services.providers.base import AIResponse

class FakeProvider:
    name = "fake"; model = "fake-1"

def make_executor(agent_outputs):
    async def _exec(role, task_input, provider):
        return agent_outputs[role]
    return _exec

BACKEND_OUT = {"files": [{"path": "app/calc.py", "content": "def add(a,b):\n    return a+b\n"}],
               "entrypoint": "app/calc.py", "notes": "n"}

@pytest.mark.asyncio
async def test_real_tests_run_and_pass():
    settings = get_settings()
    settings.seconds_between_agent_steps = 0
    orch = Orchestrator(MemoryDB(), settings, lambda: FakeProvider(), make_executor({
        "architect": {"requirements": "r", "architecture": "a", "plan": ["1"]},
        "ui_designer": {"user_flows": ["f"], "pages": ["p"], "component_tree": "t"},
        "db_engineer": {"tables": ["t"], "migrations": []},
        "backend_dev": BACKEND_OUT,
        "frontend_dev": {"files": [], "entrypoint": "x"},
        "test_repair": {"test_files": [{"path": "tests/test_calc.py",
            "content": "import sys; sys.path.insert(0,'app')\nfrom calc import add\n\ndef test_add():\n    assert add(1,2)==3\n"}],
            "verified": ["add"], "unverified": []},
        "devops": {"env_vars": [], "commands": [], "checklist": []},
    }))
    db = orch.db
    pid = "p1"
    await db.insert("projects", {"id": pid, "owner_id": "u1", "name": "x"})
    run = await orch.create_run(pid, "u1", goal="calc app")
    final = await orch.run_until_done(run["id"])
    assert final["status"] == "succeeded"
    tasks = await db.select("tasks", {"run_id": run["id"]})
    tr = [t for t in tasks if t["agent_role"] == "test_repair"][0]
    er = tr["output"]["executor_result"]
    assert er["ran"] is True and er["tests_passed"] is True
    assert "1 passed" in er["stdout_tail"]

@pytest.mark.asyncio
async def test_real_tests_fail_honestly():
    settings = get_settings()
    settings.seconds_between_agent_steps = 0
    orch = Orchestrator(MemoryDB(), settings, lambda: FakeProvider(), make_executor({
        "architect": {"requirements": "r", "architecture": "a", "plan": ["1"]},
        "ui_designer": {"user_flows": ["f"], "pages": ["p"], "component_tree": "t"},
        "db_engineer": {"tables": ["t"], "migrations": []},
        "backend_dev": {"files": [{"path": "app/calc.py", "content": "def add(a,b):\n    return a-b\n"}],
                        "entrypoint": "app/calc.py"},
        "frontend_dev": {"files": [], "entrypoint": "x"},
        "test_repair": {"test_files": [{"path": "tests/test_calc.py",
            "content": "import sys; sys.path.insert(0,'app')\nfrom calc import add\n\ndef test_add():\n    assert add(1,2)==3\n"}],
            "verified": [], "unverified": []},
        "devops": {"env_vars": [], "commands": [], "checklist": []},
    }))
    db = orch.db
    await db.insert("projects", {"id": "p2", "owner_id": "u1", "name": "x"})
    run = await orch.create_run("p2", "u1", goal="calc app")
    final = await orch.run_until_done(run["id"])
    tasks = await db.select("tasks", {"run_id": run["id"]})
    tr = [t for t in tasks if t["agent_role"] == "test_repair"][0]
    # attempts exhausted (max_attempts = 1 + max_repair_attempts) -> failed, run failed
    assert tr["status"] == "failed"
    assert "real test run failed" in (tr["error_summary"] or "")
    assert final["status"] == "failed"
