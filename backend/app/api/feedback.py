"""Feedback dataset export.

Admin-only and approved-only: the export is built from immutable approved snapshots, so an
in-flight review can never leak into an evaluation artefact.
"""

from collections import defaultdict
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from app.core.auth import AuthDep, RepoDep
from app.models.feedback import FeedbackDatasetResponse
from app.services.feedback.dataset import FeedbackDatasetBuilder

router = APIRouter(tags=["feedback"])


async def _build(
    organization_id: UUID,
    auth: AuthDep,
    repository: RepoDep,
    limit: int,
    include_evidence: bool,
):
    await repository.assert_membership(auth.user_id, organization_id, {"admin"})
    prescriptions = await repository.list_prescriptions(organization_id, limit, None)

    approved: dict[str, dict[str, Any]] = {}
    fields: dict[str, list[dict[str, Any]]] = {}
    for prescription in prescriptions:
        prescription_id = UUID(str(prescription["id"]))
        version = await repository.approved_version(prescription_id)
        if not version:
            continue
        approved[str(prescription_id)] = version
        fields[str(prescription_id)] = await repository.fields_for_user(prescription_id)

    corrections_by_field: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rows = await repository.corrections_for_prescriptions(
        [UUID(key) for key in approved]
    )
    for row in rows:
        corrections_by_field[str(row.get("prescription_field_id", ""))].append(row)

    return FeedbackDatasetBuilder(include_evidence).build(
        prescriptions, approved, fields, dict(corrections_by_field)
    )


@router.get(
    "/organizations/{organization_id}/feedback-dataset",
    response_model=FeedbackDatasetResponse,
)
async def feedback_dataset(
    organization_id: UUID,
    auth: AuthDep,
    repository: RepoDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    include_evidence: Annotated[bool, Query()] = True,
) -> FeedbackDatasetResponse:
    dataset = await _build(organization_id, auth, repository, limit, include_evidence)
    return FeedbackDatasetResponse.model_validate(dataset.to_dict())


@router.get(
    "/organizations/{organization_id}/feedback-dataset.jsonl",
    response_class=PlainTextResponse,
)
async def feedback_dataset_jsonl(
    organization_id: UUID,
    auth: AuthDep,
    repository: RepoDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    include_evidence: Annotated[bool, Query()] = True,
) -> PlainTextResponse:
    dataset = await _build(organization_id, auth, repository, limit, include_evidence)
    return PlainTextResponse(dataset.to_jsonl(), media_type="application/x-ndjson")
