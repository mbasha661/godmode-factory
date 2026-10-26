"""Central orchestrator (spec section 3 + 8).

- Plans a run as a dependency-aware DAG over the seven agent roles.
- Persists every state transition; a process restart loses nothing (recovery
  resets stale 'running' tasks to 'ready' and continues).
- Enforces: dependencies before execution, one active AI task at a time
  (MAX_CONCURRENT_AI_TASKS=1), bounded retries, run duration budget.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from uuid import uuid4

from ..config import Settings
from ..errors import ErrorCategory
from .execution import Executor, _failure_summary
from .providers.base import AIProvider, AIResponse, ProviderError

TASK_SUCCEEDED = "succeeded"
TERMINAL_RUN_STATES = {"succeeded", "failed", "cancelled"}

# The seven-agent pipeline DAG: role -> (kind, depends_on roles)
PIPELINE: list[tuple[str, str, list[str]]] = [
    ("architect", "spec", []),
    ("ui_designer", "design", ["architect"]),
    ("db_engineer", "migrate", ["architect"]),
    ("backend_dev", "generate", ["architect", "db_engineer"]),
    ("frontend_dev", "generate", ["architect", "ui_designer", "backend_dev"]),
    ("test_repair", "test", ["backend_dev", "frontend_dev"]),
    ("devops", "deploy_prep", ["test_repair"]),
]



def parse_ts(value: str) -> datetime:
    """Parse Postgres/ISO timestamps tolerant of arbitrary fractional precision."""
    text = str(value).replace("Z", "+00:00")
    if "." in text:
        head, rest = text.split(".", 1)
        frac = ""
        i = 0
        while i < len(rest) and rest[i].isdigit():
            frac += rest[i]; i += 1
        frac = (frac + "000000")[:6]
        text = f"{head}.{frac}{rest[i:]}"
    return datetime.fromisoformat(text)

def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def ready_tasks(tasks: list[dict], deps: list[dict]) -> list[dict]:
    """Tasks that may run now: status 'ready' or 'pending', all deps succeeded."""
    by_id = {t["id"]: t for t in tasks}
    dep_map: dict[str, list[str]] = {}
    for d in deps:
        dep_map.setdefault(d["task_id"], []).append(d["depends_on_task_id"])
    out = []
    for t in tasks:
        if t["status"] not in ("pending", "ready"):
            continue
        required = dep_map.get(t["id"], [])
        if all(by_id[r]["status"] == TASK_SUCCEEDED for r in required):
            out.append(t)
    return sorted(out, key=lambda t: t["sequence"])


def blocked_tasks(tasks: list[dict], deps: list[dict]) -> list[dict]:
    """Pending tasks that can never run: a dependency failed or was cancelled."""
    by_id = {t["id"]: t for t in tasks}
    dep_map: dict[str, list[str]] = {}
    for d in deps:
        dep_map.setdefault(d["task_id"], []).append(d["depends_on_task_id"])
    out = []
    for t in tasks:
        if t["status"] not in ("pending", "ready"):
            continue
        required = dep_map.get(t["id"], [])
        if any(by_id[r]["status"] in ("failed", "cancelled", "blocked") for r in required):
            out.append(t)
    return out


class Orchestrator:
    def __init__(
        self,
        db: Any,
        settings: Settings,
        provider_factory: Callable[[], AIProvider],
        agent_executor: Optional[Callable[[str, dict, AIProvider], Any]] = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self._provider_factory = provider_factory
        # agent_executor(role, task_input, provider) -> dict output. Injected for tests.
        self._agent_executor = agent_executor

    async def _event(self, run_id: str, project_id: str, event_type: str,
                     message: str, task_id: Optional[str] = None,
                     agent_role: Optional[str] = None, level: str = "info",
                     data: Optional[dict] = None) -> None:
        await self.db.insert("execution_events", {
            "run_id": run_id, "project_id": project_id, "task_id": task_id,
            "agent_role": agent_role, "level": level, "event_type": event_type,
            "message": message, "data": data or {}, "created_at": utcnow(),
        })

    async def create_run(self, project_id: str, user_id: str,
                         specification_id: Optional[str] = None, goal: str = "") -> dict:
        now = utcnow()
        run = await self.db.insert("workflow_runs", {
            "id": str(uuid4()), "project_id": project_id,
            "specification_id": specification_id, "status": "pending",
            "max_duration_minutes": self.settings.max_workflow_duration_minutes,
            "created_by": user_id, "created_at": now, "updated_at": now,
        })
        tasks = []
        for seq, (role, kind, _) in enumerate(PIPELINE[: self.settings.max_tasks_per_run]):
            task = await self.db.insert("tasks", {
                "id": str(uuid4()), "run_id": run["id"], "project_id": project_id,
                "agent_role": role, "title": f"{kind}: {role}", "kind": kind,
                "status": "pending", "sequence": seq, "attempts": 0,
                "input": ({"goal": goal} if role == "architect" and goal else {}),
                "max_attempts": 1 + self.settings.max_repair_attempts,
                "created_at": now, "updated_at": now,
            })
            tasks.append(task)
        role_to_task = {t["agent_role"]: t for t in tasks}
        for role, _, dep_roles in PIPELINE[: len(tasks)]:
            for dep_role in dep_roles:
                if dep_role in role_to_task:
                    await self.db.insert("task_dependencies", {
                        "task_id": role_to_task[role]["id"],
                        "depends_on_task_id": role_to_task[dep_role]["id"],
                    })
        await self._event(run["id"], project_id, "run_created",
                          f"run created with {len(tasks)} tasks")
        return run

    async def _load(self, run_id: str):
        run = await self.db.select_one("workflow_runs", {"id": run_id})
        tasks = await self.db.select("tasks", {"run_id": run_id}, order="sequence", desc=False)
        deps = []
        for t in tasks:
            # MemoryDB has no join support; Supabase path queries the table directly
            rows = await self.db.select("task_dependencies", {"task_id": t["id"]})
            deps.extend(rows)
        return run, tasks, deps

    async def _execute_task(self, run: dict, task: dict) -> None:
        provider = self._provider_factory()
        agent_run = await self.db.insert("agent_runs", {
            "id": str(uuid4()), "task_id": task["id"], "run_id": run["id"],
            "agent_role": task["agent_role"], "provider": getattr(provider, "name", None),
            "model": getattr(provider, "model", None), "attempt": task["attempts"] + 1,
            "status": "running", "created_at": utcnow(),
        })
        started = datetime.now(timezone.utc)
        try:
            if self._agent_executor is not None:
                output = await self._agent_executor(task["agent_role"], task["input"], provider)
                if task["agent_role"] == "test_repair":
                    output = await self._run_real_tests(run, output)
            else:
                output = {"note": "no agent executor wired (Phase 5)"}
            duration = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
            await self.db.update("agent_runs", {"id": agent_run["id"]}, {
                "status": "succeeded", "output": output,
                "prompt_tokens": output.pop("_prompt_tokens", 0),
                "completion_tokens": output.pop("_completion_tokens", 0),
                "duration_ms": duration,
            })
            await self.db.update("tasks", {"id": task["id"]}, {
                "status": "succeeded", "output": output,
                "attempts": task["attempts"] + 1,
                "finished_at": utcnow(), "updated_at": utcnow(),
            })
            await self._event(run["id"], run["project_id"], "task_succeeded",
                              f"{task['agent_role']} succeeded", task["id"], task["agent_role"])
        except ProviderError as exc:
            await self._fail_task(run, task, agent_run, exc.category.value, str(exc))
        except Exception as exc:  # noqa: BLE001 - recorded, never hidden
            await self._fail_task(run, task, agent_run, "code_execution_failure", str(exc)[:500])

    async def _run_real_tests(self, run: dict, output: dict) -> dict:
        """Phase 7: actually execute generated code + tests in the restricted worker.

        Combines dev-task files with the agent's test files (fixed files override),
        runs real pytest, records the true result. Failing tests raise so the task
        is honestly marked failed/retried with the real output attached.
        """
        tasks = await self.db.select("tasks", {"run_id": run["id"]})
        files: dict[str, str] = {}
        for t in tasks:
            if t["status"] == "succeeded" and t.get("output"):
                for f in (t["output"].get("files") or []):
                    if isinstance(f, dict) and f.get("path") and f.get("content") is not None:
                        files[f["path"]] = f["content"]
        for key in ("test_files", "fixed_files"):
            for f in (output.get(key) or []):
                files[f["path"]] = f["content"]
        has_pytest = any(p.endswith(".py") and "test" in p for p in files)
        if not has_pytest:
            output["executor_result"] = {
                "ran": False,
                "note": "no python test files to execute; nothing claimed as verified by execution",
            }
            return output
        result = await asyncio.to_thread(Executor().run_tests, files)
        output["executor_result"] = {
            "ran": True, "exit_code": result.exit_code, "timed_out": result.timed_out,
            "duration_ms": result.duration_ms,
            "stdout_tail": result.stdout[-2000:], "stderr_tail": result.stderr[-2000:],
            "tests_passed": result.exit_code == 0,
        }
        await self._event(run["id"], run["project_id"], "tests_executed",
                          f"real pytest run: exit {result.exit_code}", level="info")
        if result.exit_code != 0:
            raise RuntimeError(
                f"real test run failed (exit {result.exit_code}): "
                + _failure_summary(result.stdout, result.stderr))
        return output

    async def _fail_task(self, run: dict, task: dict, agent_run: dict,
                         category: str, message: str) -> None:
        attempts = task["attempts"] + 1
        final = attempts >= task["max_attempts"] or category in (
            ErrorCategory.QUOTA_EXHAUSTED.value, ErrorCategory.AUTH_FAILURE.value,
        )
        await self.db.update("agent_runs", {"id": agent_run["id"]}, {
            "status": "failed", "error_category": category, "error_summary": message[:500],
        })
        await self.db.update("tasks", {"id": task["id"]}, {
            "status": "failed" if final else "ready",
            "attempts": attempts, "error_summary": message[:500], "updated_at": utcnow(),
        })
        await self._event(run["id"], run["project_id"],
                          "task_failed" if final else "task_retry",
                          f"{task['agent_role']}: {message[:200]}",
                          task["id"], task["agent_role"], level="error",
                          data={"category": category, "attempt": attempts, "final": final})

    async def step(self, run_id: str) -> dict:
        """Run the next eligible task, if any. Returns the current run row."""
        run, tasks, deps = await self._load(run_id)
        if run["status"] in TERMINAL_RUN_STATES or run["status"] == "paused":
            return run

        # run duration budget
        if run.get("started_at"):
            started = parse_ts(run["started_at"])
            elapsed = (datetime.now(timezone.utc) - started).total_seconds() / 60
            if elapsed > run["max_duration_minutes"]:
                await self.db.update("workflow_runs", {"id": run_id}, {
                    "status": "failed", "error_summary": "workflow duration budget exceeded",
                    "finished_at": utcnow(), "updated_at": utcnow(),
                })
                await self._event(run_id, run["project_id"], "run_failed",
                                  "duration budget exceeded", level="error")
                return await self.db.select_one("workflow_runs", {"id": run_id})

        # mark never-runnable tasks blocked
        for t in blocked_tasks(tasks, deps):
            await self.db.update("tasks", {"id": t["id"]}, {"status": "blocked", "updated_at": utcnow()})
            tasks = await self.db.select("tasks", {"run_id": run_id}, order="sequence", desc=False)

        eligible = [t for t in ready_tasks(tasks, deps) if t["status"] != "blocked"]
        if not eligible:
            # nothing to run: terminal assessment
            if all(t["status"] in ("succeeded", "blocked", "failed", "cancelled") for t in tasks):
                any_failed = any(t["status"] in ("blocked", "failed", "cancelled") for t in tasks)
                final = "failed" if any_failed else "succeeded"
                await self.db.update("workflow_runs", {"id": run_id}, {
                    "status": final, "finished_at": utcnow(), "updated_at": utcnow(),
                })
                await self._event(run_id, run["project_id"], f"run_{final}",
                                  f"run {final}", level="info" if final == "succeeded" else "error")
            return await self.db.select_one("workflow_runs", {"id": run_id})

        if run["status"] == "pending":
            await self.db.update("workflow_runs", {"id": run_id}, {
                "status": "running", "started_at": utcnow(), "updated_at": utcnow(),
            })

        # Free-tier pacing: space out provider calls to stay under RPM quota.
        if run["status"] == "running" and self.settings.seconds_between_agent_steps > 0:
            await asyncio.sleep(self.settings.seconds_between_agent_steps)

        task = eligible[0]  # MAX_CONCURRENT_AI_TASKS=1: strictly sequential
        # Propagate goal + upstream outputs so each agent sees real context.
        goal = (task.get("input") or {}).get("goal") or next(
            ((t.get("input") or {}).get("goal") for t in tasks
             if t["agent_role"] == "architect" and (t.get("input") or {}).get("goal")), "")
        upstream = {}
        for t in tasks:
            if t["status"] == "succeeded" and t.get("output"):
                out = {k: v for k, v in t["output"].items() if not k.startswith("_")}
                upstream[t["agent_role"]] = json.dumps(out)[:6000]
        task_input = {"goal": goal, "upstream_outputs": upstream}
        if task.get("attempts") and task.get("error_summary"):
            task_input["previous_failure"] = task["error_summary"]
        await self.db.update("tasks", {"id": task["id"]}, {
            "status": "running", "started_at": utcnow(), "input": task_input,
            "updated_at": utcnow(),
        })
        task["input"] = task_input
        await self.db.update("workflow_runs", {"id": run_id}, {
            "current_task_id": task["id"], "updated_at": utcnow(),
        })
        await self._event(run_id, run["project_id"], "task_started",
                          f"{task['agent_role']} started", task["id"], task["agent_role"])
        await self._execute_task(run, task)
        return await self.db.select_one("workflow_runs", {"id": run_id})

    async def run_until_done(self, run_id: str, max_steps: int = 100) -> dict:
        for _ in range(max_steps):
            run = await self.step(run_id)
            if run["status"] in TERMINAL_RUN_STATES or run["status"] == "paused":
                return run
        return await self.db.select_one("workflow_runs", {"id": run_id})

    async def cancel(self, run_id: str) -> dict:
        await self.db.update("workflow_runs", {"id": run_id}, {
            "status": "cancelled", "finished_at": utcnow(), "updated_at": utcnow(),
        })
        for t in await self.db.select("tasks", {"run_id": run_id}):
            if t["status"] in ("pending", "ready", "running"):
                await self.db.update("tasks", {"id": t["id"]},
                                     {"status": "cancelled", "updated_at": utcnow()})
        run = await self.db.select_one("workflow_runs", {"id": run_id})
        await self._event(run_id, run["project_id"], "run_cancelled", "run cancelled by user")
        return run

    async def pause(self, run_id: str) -> dict:
        await self.db.update("workflow_runs", {"id": run_id},
                             {"status": "paused", "updated_at": utcnow()})
        return await self.db.select_one("workflow_runs", {"id": run_id})

    async def resume(self, run_id: str) -> dict:
        await self.db.update("workflow_runs", {"id": run_id},
                             {"status": "running", "updated_at": utcnow()})
        return await self.db.select_one("workflow_runs", {"id": run_id})

    async def recover_interrupted(self, run_id: str) -> int:
        """After a process restart: stale 'running' tasks go back to 'ready'.
        Returns how many tasks were recovered."""
        recovered = 0
        for t in await self.db.select("tasks", {"run_id": run_id}):
            if t["status"] == "running":
                await self.db.update("tasks", {"id": t["id"]}, {
                    "status": "ready",
                    "error_summary": "recovered after process restart",
                    "updated_at": utcnow(),
                })
                recovered += 1
        if recovered:
            run = await self.db.select_one("workflow_runs", {"id": run_id})
            await self._event(run_id, run["project_id"], "run_recovered",
                              f"{recovered} task(s) recovered after restart", level="warning")
        return recovered
