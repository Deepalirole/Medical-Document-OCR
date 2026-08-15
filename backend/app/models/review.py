from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class SchemaCreate(BaseModel):
    organization_id: UUID
    schema_key: str
    name: str
    version: int = Field(default=1, ge=1)
    definition: dict[str, Any]


class SchemaUpdate(BaseModel):
    name: str
    definition: dict[str, Any]


class FieldResponse(BaseModel):
    id: UUID
    prescription_id: UUID
    schema_id: UUID
    field_path: str
    field_type: str
    array_item_id: str | None = None
    original_value: Any = None
    current_value: Any = None
    review_status: str
    confidence: float | None = None
    evidence: list[dict[str, Any]] | None = None
    validation: dict[str, Any]


class FieldsResponse(BaseModel):
    prescription_id: UUID
    schema_definition: dict[str, Any]
    structured_json: dict[str, Any]
    fields: list[FieldResponse]


class FieldCorrection(BaseModel):
    value: Any = None
    reason: str | None = Field(default=None, max_length=500)


class BulkFieldCorrection(BaseModel):
    updates: list[tuple[UUID, Any, str | None]] = Field(default_factory=list, max_length=200)
    add_items: list["ArrayItemAdd"] = Field(default_factory=list, max_length=20)
    remove_item_ids: list[str] = Field(default_factory=list, max_length=20)


class ArrayItemAdd(BaseModel):
    array_path: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    values: dict[str, Any]


class ApprovedVersionResponse(BaseModel):
    id: UUID
    prescription_id: UUID
    schema_id: UUID
    schema_version: int
    version: int
    structured_json: dict[str, Any]
    status: str
