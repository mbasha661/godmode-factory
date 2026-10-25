"""Central configuration. All secrets arrive via environment variables only."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_storage_bucket: str = "artifacts"

    api_port: int = 8000
    api_cors_origins: str = "http://localhost:3000"

    ai_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    max_concurrent_ai_tasks: int = 1
    max_repair_attempts: int = 2
    seconds_between_agent_steps: float = 25.0
    max_tasks_per_run: int = 30
    max_prompt_chars: int = 12000
    max_workflow_duration_minutes: int = 30
    max_file_size_mb: int = 5
    max_test_retries: int = 1

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_anon_key and self.supabase_service_role_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
