from typing import Any

from pydantic import BaseModel


class HMISHealth(BaseModel):
    provider: str
    configured: bool
    status: str
    branch_scoped: bool = False


class HMISPreview(BaseModel):
    contract_version: str
    source_id: str
    prescription_id: str
    organization_id: str
    approved_version: int
    patient: dict[str, Any]
    prescription: dict[str, Any]
    prescription_items: list[dict[str, Any]]
    unmapped: list[str]


class HMISDispatchResponse(BaseModel):
    connector: str
    dispatched: bool
    idempotent: bool
    source_id: str
    item_count: int
    target_ids: dict[str, str]
