import json
import pytest
from app.services.agents import AGENT_SPECS, execute_agent, AgentOutputError
from app.services.providers.base import AIResponse

ROLES = ["architect", "ui_designer", "db_engineer", "backend_dev",
         "frontend_dev", "test_repair", "devops"]

def test_all_seven_roles_have_system_and_schema():
    assert sorted(AGENT_SPECS) == sorted(ROLES)
    for role, spec in AGENT_SPECS.items():
        assert spec["system"] and spec["schema"]["type"] == "object"

class FakeProvider:
    name = "fake"
    model = "fake-1"
    def __init__(self, payload): self.payload = payload
    async def generate(self, prompt, *, system=None, json_schema=None, max_output_tokens=4096, timeout_s=60.0):
        self.seen = (prompt, system, json_schema)
        return AIResponse(text=self.payload, provider="fake", model="fake-1",
                          prompt_tokens=10, completion_tokens=20)

@pytest.mark.asyncio
async def test_execute_agent_valid_output():
    payload = json.dumps({"requirements": "r", "architecture": "a", "plan": ["1"],
                          "assumptions": [], "missing_requirements": [], "technologies": []})
    # extra keys allowed? additionalProperties False -> use exactly required+optional set
    out = await execute_agent("architect", {"goal": "x"}, FakeProvider(payload))
    assert out["architecture"] == "a"
    assert out["_prompt_tokens"] == 10 and out["_completion_tokens"] == 20

@pytest.mark.asyncio
async def test_non_json_raises():
    with pytest.raises(AgentOutputError, match="non-JSON"):
        await execute_agent("architect", {}, FakeProvider("not json"))

@pytest.mark.asyncio
async def test_schema_violation_raises():
    with pytest.raises(AgentOutputError, match="schema validation"):
        await execute_agent("architect", {}, FakeProvider(json.dumps({"requirements": 1})))

@pytest.mark.asyncio
async def test_unknown_role_raises():
    with pytest.raises(AgentOutputError, match="unknown agent role"):
        await execute_agent("nope", {}, FakeProvider("{}"))

@pytest.mark.asyncio
async def test_files_schema_enforced_for_dev_roles():
    bad = json.dumps({"files": [{"path": "a.py"}], "entrypoint": "a.py"})  # missing content
    with pytest.raises(AgentOutputError):
        await execute_agent("backend_dev", {}, FakeProvider(bad))
    good = json.dumps({"files": [{"path": "a.py", "content": "print(1)"}], "entrypoint": "a.py", "notes": "n"})
    out = await execute_agent("backend_dev", {}, FakeProvider(good))
    assert out["files"][0]["path"] == "a.py"
