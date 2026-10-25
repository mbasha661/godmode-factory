"""Phase 5 - Seven specialized agent roles.

Each role has a system prompt, a strict JSON output schema, and a validator.
execute_agent() is the orchestrator's agent_executor hook: it calls the AI
provider with the role's system prompt and schema, parses the reply, and
validates it. Invalid output raises AgentOutputError (recorded honestly by
the orchestrator as a task failure; never silently patched).
"""
from __future__ import annotations

import json
from typing import Any

import jsonschema

from ..providers import generate_with_retry
from ..providers.base import AIProvider


class AgentOutputError(Exception):
    """Agent returned malformed or schema-invalid output."""


def _schema(props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": required,
            "additionalProperties": False}


S = {"type": "string"}
SA = {"type": "array", "items": S}
FILE = _schema({"path": S, "content": S}, ["path", "content"])
FILES = {"type": "array", "items": FILE}

# File-generating roles need a large output budget; truncated JSON fails honestly otherwise.
ROLE_MAX_OUTPUT_TOKENS: dict[str, int] = {
    "backend_dev": 32768, "frontend_dev": 32768, "test_repair": 32768,
}

AGENT_SPECS: dict[str, dict[str, Any]] = {
    "architect": {
        "system": (
            "You are the GOD MODE AI ARCHITECT. Interpret the user request, write a "
            "requirements document, list assumptions and missing requirements, design "
            "the system architecture, choose technologies, and produce an ordered "
            "implementation plan. Be concrete and buildable on a free tier."),
        "schema": _schema({
            "requirements": S, "assumptions": SA, "missing_requirements": SA,
            "architecture": S, "technologies": SA, "plan": SA},
            ["requirements", "architecture", "plan"]),
    },
    "ui_designer": {
        "system": (
            "You are the GOD MODE AI UI DESIGNER. Given the architecture, define the "
            "user flows, page/component structure, and visual direction. Output a "
            "component tree and per-page wireframe descriptions."),
        "schema": _schema({
            "user_flows": SA, "pages": SA, "component_tree": S, "visual_direction": S},
            ["user_flows", "pages", "component_tree"]),
    },
    "db_engineer": {
        "system": (
            "You are the GOD MODE AI DB ENGINEER. Given the architecture, design the "
            "database schema and write runnable SQL migrations (PostgreSQL/Supabase), "
            "including constraints, indexes and row-level-security policies."),
        "schema": _schema({
            "tables": SA, "migrations": FILES, "rls_notes": S},
            ["tables", "migrations"]),
    },
    "backend_dev": {
        "system": (
            "You are the GOD MODE AI BACKEND DEVELOPER. Keep the implementation minimal (few small files). Implement the backend per the "
            "architecture and DB schema. Output complete runnable files only - no "
            "placeholders, no TODO stubs."),
        "schema": _schema({
            "files": FILES, "entrypoint": S, "notes": S},
            ["files", "entrypoint"]),
    },
    "frontend_dev": {
        "system": (
            "You are the GOD MODE AI FRONTEND DEVELOPER. Keep the implementation minimal (few small files). Implement the frontend per "
            "the design and backend API. Output complete runnable files only - no "
            "placeholders."),
        "schema": _schema({
            "files": FILES, "entrypoint": S, "notes": S},
            ["files", "entrypoint"]),
    },
    "test_repair": {
        "system": (
            "You are the GOD MODE AI TEST & REPAIR agent. Write real tests for the "
            "generated code, run them mentally against the implementation, and fix "
            "failures by outputting corrected files. Never claim tests pass without "
            "evidence; list exactly what you verified."),
        "schema": _schema({
            "test_files": FILES, "fixed_files": FILES,
            "verified": SA, "unverified": SA},
            ["test_files", "verified"]),
    },
    "devops": {
        "system": (
            "You are the GOD MODE AI DEVOPS agent. Prepare deployment: configuration, "
            "environment variable list, build/run commands, and a deployment checklist "
            "for free-tier hosting. Flag anything that cannot be done free."),
        "schema": _schema({
            "env_vars": SA, "commands": SA, "checklist": SA, "blockers": SA},
            ["env_vars", "commands", "checklist"]),
    },
}


async def execute_agent(role: str, task_input: dict[str, Any], provider: AIProvider) -> dict[str, Any]:
    spec = AGENT_SPECS.get(role)
    if spec is None:
        raise AgentOutputError(f"unknown agent role: {role}")
    prompt = (
        f"Task input (JSON):\n{json.dumps(task_input, indent=2)[:12000]}\n\n"
        "Respond with a single JSON object matching the required schema. No prose outside the JSON."
    )
    response = await generate_with_retry(
        provider, prompt, system=spec["system"], json_schema=spec["schema"],
        max_output_tokens=ROLE_MAX_OUTPUT_TOKENS.get(role, 8192), max_retries=3)
    try:
        output = json.loads(response.text)
    except json.JSONDecodeError as exc:
        raise AgentOutputError(f"{role} returned non-JSON output: {exc}") from exc
    try:
        jsonschema.validate(output, spec["schema"])
    except jsonschema.ValidationError as exc:
        raise AgentOutputError(f"{role} output failed schema validation: {exc.message}") from exc
    output["_prompt_tokens"] = response.prompt_tokens
    output["_completion_tokens"] = response.completion_tokens
    return output
