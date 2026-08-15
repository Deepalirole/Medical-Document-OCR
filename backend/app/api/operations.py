from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.dependencies import ProcessingRepoDep
from app.core.auth import AuthDep, RepoDep
from app.core.errors import AppError
from app.models.prescriptions import PrescriptionResponse

router = APIRouter(tags=["operations"])


@router.get("/prescriptions", response_model=list[PrescriptionResponse])
async def list_prescriptions(
    organization_id: UUID,
    auth: AuthDep,
    repository: RepoDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    created_before: Annotated[str | None, Query()] = None,
) -> list[PrescriptionResponse]:
    await repository.assert_membership(auth.user_id, organization_id)
    rows = await repository.list_prescriptions(organization_id, limit, created_before)
    return [PrescriptionResponse.model_validate({**row, "duplicate": False}) for row in rows]


@router.get("/organizations/{organization_id}/metrics", response_model=dict[str, Any])
async def metrics(
    organization_id: UUID, auth: AuthDep, repository: RepoDep
) -> dict[str, Any]:
    await repository.assert_membership(auth.user_id, organization_id)
    return await repository.organization_metrics(organization_id)


@router.get("/admin/diagnostics", response_model=list[dict[str, Any]])
async def diagnostics(
    organization_id: UUID,
    auth: AuthDep,
    repository: RepoDep,
    processing_repository: ProcessingRepoDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> list[dict[str, Any]]:
    await repository.assert_membership(auth.user_id, organization_id, {"admin"})
    return await processing_repository.diagnostics(organization_id, limit)


@router.get("/prescriptions/{prescription_id}/integration-payload", response_model=dict)
async def integration_payload(prescription_id: UUID, repository: RepoDep) -> dict:
    prescription = await repository.prescription_for_user(prescription_id)
    if not prescription:
        raise AppError("PRESCRIPTION_NOT_FOUND", "Prescription not found.", 404)
    version = await repository.approved_version(prescription_id)
    if not version:
        raise AppError("NOT_APPROVED", "Only approved prescriptions can be exported.", 409)
    return {
        "contract_version": "1.0",
        "prescription_id": str(prescription_id),
        "organization_id": prescription["organization_id"],
        "schema": {"id": version["schema_id"], "version": version["schema_version"]},
        "approved_version": version["version"],
        "approved_at": prescription["approved_at"],
        "data": version["structured_json"],
    }

