"""Request/response schemas. Validation enforced here, server-side."""
from datetime import datetime
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field

ProjectType = Literal["web", "mobile", "api", "fullstack"]
RunStatus = Literal["pending", "running", "paused", "succeeded", "failed", "cancelled", "awaiting_approval"]
TaskStatus = Literal["pending", "ready", "running", "succeeded", "failed", "blocked", "cancelled"]
AgentRole = Literal["architect", "ui_designer", "frontend_dev", "backend_dev", "db_engineer", "devops", "test_repair"]


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=12000)
    project_type: ProjectType = "fullstack"


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=12000)
    status: Optional[Literal["draft", "active", "archived"]] = None


class ProjectOut(BaseModel):
    id: str
    owner_id: str
    name: str
    description: str
    project_type: str
    status: str
    created_at: datetime
    updated_at: datetime


class RunCreate(BaseModel):
    max_duration_minutes: Optional[int] = Field(default=None, ge=1, le=120)


class RunOut(BaseModel):
    id: str
    project_id: str
    status: str
    current_task_id: Optional[str] = None
    error_summary: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime


class TaskOut(BaseModel):
    id: str
    run_id: str
    agent_role: str
    title: str
    kind: str
    status: str
    sequence: int
    attempts: int
    error_summary: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class EventOut(BaseModel):
    id: int
    run_id: Optional[str] = None
    task_id: Optional[str] = None
    agent_role: Optional[str] = None
    level: str
    event_type: str
    message: str
    data: dict[str, Any] = {}
    created_at: datetime


class ApprovalDecision(BaseModel):
    comment: Optional[str] = Field(default=None, max_length=2000)


class SystemStatus(BaseModel):
    environment: str
    supabase_configured: bool
    ai_provider: str
    ai_provider_configured: bool
    limits: dict[str, int]
    timestamp: datetime
