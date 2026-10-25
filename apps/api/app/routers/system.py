from datetime import datetime, timezone
from fastapi import APIRouter, Depends

from ..config import Settings, get_settings
from ..schemas import SystemStatus

router = APIRouter(tags=["system"])


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/api/system/status", response_model=SystemStatus)
async def system_status(settings: Settings = Depends(get_settings)):
    provider_key_present = (
        bool(settings.gemini_api_key) if settings.ai_provider == "gemini"
        else bool(settings.groq_api_key) if settings.ai_provider == "groq"
        else False
    )
    return SystemStatus(
        environment=settings.app_env,
        supabase_configured=settings.supabase_configured,
        ai_provider=settings.ai_provider,
        ai_provider_configured=provider_key_present,
        limits={
            "max_concurrent_ai_tasks": settings.max_concurrent_ai_tasks,
            "max_repair_attempts": settings.max_repair_attempts,
            "max_tasks_per_run": settings.max_tasks_per_run,
            "max_prompt_chars": settings.max_prompt_chars,
            "max_workflow_duration_minutes": settings.max_workflow_duration_minutes,
            "max_file_size_mb": settings.max_file_size_mb,
            "max_test_retries": settings.max_test_retries,
        },
        timestamp=datetime.now(timezone.utc),
    )
