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
    openrouter_prompt_version: str = ""

    ocr_provider: Literal[
        "tesseract", "paddleocr", "google_vision", "azure_document_intelligence"
    ] = "tesseract"
    tesseract_cmd: str = ""
    paddleocr_language: str = "en"
    paddleocr_angle_classification: bool = True
    cloud_ocr_timeout_seconds: int = Field(default=30, ge=5, le=180)
    cloud_ocr_retries: int = Field(default=2, ge=0, le=4)
    google_vision_api_key: SecretStr = SecretStr("")
    google_vision_language_hints: str = ""
    azure_ocr_endpoint: str = ""
    azure_ocr_api_key: SecretStr = SecretStr("")
    azure_ocr_model: str = "prebuilt-read"
    progress_poll_seconds: float = Field(default=1.0, ge=0.1, le=10.0)
    progress_max_seconds: float = Field(default=300.0, ge=10.0, le=1800.0)

    worker_pool_enabled: bool = True
    worker_pool_concurrency: int = Field(default=2, ge=1, le=32)
    worker_pool_max_queue: int = Field(default=64, ge=1, le=1000)

    medicine_dictionary_path: str = ""
    medicine_suggestion_limit: int = Field(default=5, ge=1, le=25)
    medicine_min_similarity: float = Field(default=0.72, ge=0.0, le=1.0)

    htr_provider: Literal["", "trocr"] = ""
    htr_model: str = ""
    htr_max_new_tokens: int = Field(default=128, ge=16, le=1024)

    hmis_provider: Literal["", "medikunj_supabase"] = ""
    hmis_base_url: str = ""
    hmis_service_key: SecretStr = SecretStr("")
    hmis_branch_id: str = ""
    hmis_timeout_seconds: int = Field(default=30, ge=5, le=180)
    hmis_retries: int = Field(default=2, ge=0, le=4)

    emr_provider: Literal["", "fhir"] = ""
    emr_base_url: str = ""
    emr_api_key: SecretStr = SecretStr("")
    emr_timeout_seconds: int = Field(default=30, ge=5, le=180)
    emr_retries: int = Field(default=2, ge=0, le=4)

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

    @property
    def emr_configured(self) -> bool:
        return bool(self.emr_provider and self.emr_base_url)

    @property
    def hmis_configured(self) -> bool:
        return bool(
            self.hmis_provider and self.hmis_base_url and self.hmis_service_key.get_secret_value()
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
