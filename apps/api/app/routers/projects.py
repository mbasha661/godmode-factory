"""Project CRUD. Ownership enforced on every query, in addition to RLS."""
from datetime import datetime, timezone
from uuid import uuid4
from fastapi import APIRouter, Depends

from ..auth import AuthUser, get_current_user
from ..config import Settings, get_settings
from ..db import get_db
from ..errors import not_found
from ..schemas import ProjectCreate, ProjectOut, ProjectUpdate

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _out(row: dict) -> ProjectOut:
    return ProjectOut(**{k: row[k] for k in (
        "id", "owner_id", "name", "description", "project_type", "status", "created_at", "updated_at"
    )})


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(
    body: ProjectCreate,
    user: AuthUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    db = get_db(settings)
    now = datetime.now(timezone.utc).isoformat()
    row = await db.insert("projects", {
        "id": str(uuid4()),
        "owner_id": user.id,
        "name": body.name,
        "description": body.description,
        "project_type": body.project_type,
        "status": "draft",
        "created_by": user.id,
        "created_at": now,
        "updated_at": now,
    })
    return _out(row)


@router.get("", response_model=list[ProjectOut])
async def list_projects(
    user: AuthUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    db = get_db(settings)
    rows = await db.select("projects", {"owner_id": user.id}, order="created_at", desc=True)
    return [_out(r) for r in rows if r.get("status") != "deleted"]


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: str,
    user: AuthUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    db = get_db(settings)
    row = await db.select_one("projects", {"id": project_id, "owner_id": user.id})
    if not row or row.get("status") == "deleted":
        raise not_found("project")
    return _out(row)


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    user: AuthUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    db = get_db(settings)
    row = await db.select_one("projects", {"id": project_id, "owner_id": user.id})
    if not row or row.get("status") == "deleted":
        raise not_found("project")
    patch = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    patch["updated_at"] = datetime.now(timezone.utc).isoformat()
    updated = await db.update("projects", {"id": project_id, "owner_id": user.id}, patch)
    if not updated:
        raise not_found("project")
    return _out(updated[0])


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: str,
    user: AuthUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    db = get_db(settings)
    row = await db.select_one("projects", {"id": project_id, "owner_id": user.id})
    if not row:
        raise not_found("project")
    # soft delete only - spec forbids silent destructive deletes of user data
    await db.update("projects", {"id": project_id, "owner_id": user.id}, {
        "status": "deleted", "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return None
