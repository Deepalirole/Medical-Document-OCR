from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Prescription Evidence Studio"
    app_env: Literal["development", "test", "production"] = "development"
    api_prefix: str = "/api"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    supabase_url: str = ""
    supabase_publishable_key: str = ""
    supabase_service_role_key: SecretStr = SecretStr("")
    supabase_jwt_audience: str = "authenticated"

    openrouter_api_key: SecretStr = SecretStr("")
    openrouter_model: str = "openai/gpt-4o-mini"
    openrouter_timeout_seconds: int = Field(default=60, ge=5, le=180)
    openrouter_max_tokens: int = Field(default=4000, ge=256, le=16000)
    openrouter_retries: int = Field(default=2, ge=0, le=4)

    tesseract_cmd: str = ""
    htr_provider: str = ""
    htr_model: str = ""
    max_upload_mb: int = Field(default=15, ge=1, le=100)
    max_pdf_pages: int = Field(default=25, ge=1, le=250)
    signed_url_ttl_seconds: int = Field(default=300, ge=60, le=3600)

    @field_validator("cors_origins")
    @classmethod
    def reject_wildcard_in_production(cls, value: str, info):
        if info.data.get("app_env") == "production" and "*" in value:
            raise ValueError("Wildcard CORS is forbidden in production")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_publishable_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
