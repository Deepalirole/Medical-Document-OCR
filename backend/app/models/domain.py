from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Role(StrEnum):
    ADMIN = "admin"
    REVIEWER = "reviewer"


class ReviewStatus(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class ProcessingState(StrEnum):
    UPLOADED = "UPLOADED"
    VALIDATING_FILE = "VALIDATING_FILE"
    REGISTERING_DOCUMENT = "REGISTERING_DOCUMENT"
    ROUTING_FILE = "ROUTING_FILE"
    RENDERING = "RENDERING"
    ANALYZING_IMAGE = "ANALYZING_IMAGE"
    PREPROCESSING = "PREPROCESSING"
    OCR_READY = "OCR_READY"
    OCR_RUNNING = "OCR_RUNNING"
    HTR_RUNNING = "HTR_RUNNING"
    EXTRACTION_RUNNING = "EXTRACTION_RUNNING"
    FIELD_MAPPING = "FIELD_MAPPING"
    VALIDATING = "VALIDATING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    APPROVED = "APPROVED"
    COMPLETED = "COMPLETED"


class Organization(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str


class Membership(BaseModel):
    organization_id: UUID
    organization_name: str
    role: Role


class CurrentUser(BaseModel):
    id: UUID
    email: str | None = None
    display_name: str | None = None
    memberships: list[Membership] = Field(default_factory=list)


class SchemaSummary(BaseModel):
    id: UUID
    organization_id: UUID
    schema_key: str
    name: str
    version: int
    status: str
    is_active: bool
    definition: dict[str, Any]
    created_at: datetime | None = None

