from typing import Any

from pydantic import BaseModel


class FeedbackExampleModel(BaseModel):
    prescription_id: str
    schema_id: str
    schema_version: int
    approved_version: int
    field_path: str
    field_type: str
    proposed_value: Any = None
    approved_value: Any = None
    corrected: bool
    correction_count: int
    review_status: str
    confidence: float | None = None
    evidence: list[dict[str, Any]]


class FeedbackDatasetResponse(BaseModel):
    prescriptions_considered: int
    prescriptions_exported: int
    prescriptions_skipped_unapproved: int
    example_count: int
    corrected_count: int
    correction_rate: float
    examples: list[FeedbackExampleModel]
