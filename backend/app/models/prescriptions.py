from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class PrescriptionResponse(BaseModel):
    id: UUID
    organization_id: UUID
    schema_id: UUID
    original_filename: str
    source_mime_type: str
    source_type: str
    status: str
    page_count: int
    created_at: datetime | None = None
    duplicate: bool = False


class PageResponse(BaseModel):
    id: UUID
    page_number: int
    width: int
    height: int
    quality_metadata: dict[str, Any]
    preprocessing_applied: list[str]
    status: str
    preview_url: str | None = None


class PrescriptionDetail(PrescriptionResponse):
    pages: list[PageResponse] = Field(default_factory=list)


class ProcessingJobResponse(BaseModel):
    id: UUID
    stage: str
    status: str
    attempt: int
    processing_ms: int | None = None
    error_code: str | None = None
    safe_error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProcessingStatusResponse(BaseModel):
    prescription_id: UUID
    status: str
    jobs: list[ProcessingJobResponse]


class OCRTokenResponse(BaseModel):
    text: str
    confidence: float | None = None
    bbox: dict[str, int] | None = None
    sequence_index: int
    source: str


class OCRResultResponse(BaseModel):
    id: UUID
    page_id: UUID
    provider: str
    provider_version: str | None = None
    raw_text: str
    confidence: float | None = None
    processing_ms: int
    metadata: dict[str, Any]
    tokens: list[OCRTokenResponse]


class OCRResponse(BaseModel):
    prescription_id: UUID
    results: list[OCRResultResponse]

