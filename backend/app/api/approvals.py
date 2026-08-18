"""Multi-stage approval endpoints.

These routes record and report stage sign-offs. Cutting the immutable approved version stays
with ``POST /api/prescriptions/{id}/approve``, which now consults the same workflow.
"""

from uuid import UUID

from fastapi import APIRouter

from app.core.auth import AuthDep, RepoDep
from app.core.errors import AppError
from app.models.approvals import ApprovalStatusResponse, ApprovalStepRequest, ApprovalStepResponse
from app.services.approvals.workflow import ApprovalWorkflow

router = APIRouter(tags=["approvals"])


async def load_workflow(prescription_id: UUID, auth: AuthDep, repository: RepoDep):
    prescription = await repository.prescription_for_user(prescription_id)
    if not prescription:
        raise AppError("PRESCRIPTION_NOT_FOUND", "Prescription not found.", 404)
    organization_id = UUID(str(prescription["organization_id"]))
    membership = await repository.assert_membership(auth.user_id, organization_id)
    config = await repository.approval_workflow(organization_id)
    steps = await repository.approval_steps(prescription_id)
    return prescription, organization_id, membership, ApprovalWorkflow.from_config(config), steps


@router.get(
    "/prescriptions/{prescription_id}/approval-status",
    response_model=ApprovalStatusResponse,
)
async def approval_status(
    prescription_id: UUID, auth: AuthDep, repository: RepoDep
) -> ApprovalStatusResponse:
    _, _, _, workflow, steps = await load_workflow(prescription_id, auth, repository)
    payload = workflow.progress(steps).to_dict()
    return ApprovalStatusResponse.model_validate(
        {
            **payload,
            "prescription_id": str(prescription_id),
            "signed_steps": [
                {
                    "stage_key": str(step.get("stage_key", "")),
                    "stage_order": int(step.get("stage_order", 0) or 0),
                    "created_at": _optional_str(step.get("created_at")),
                }
                for step in steps
            ],
        }
    )


@router.post(
    "/prescriptions/{prescription_id}/approval-steps",
    response_model=ApprovalStatusResponse,
)
async def sign_approval_step(
    prescription_id: UUID,
    payload: ApprovalStepRequest,
    auth: AuthDep,
    repository: RepoDep,
) -> ApprovalStatusResponse:
    _, organization_id, membership, workflow, steps = await load_workflow(
        prescription_id, auth, repository
    )
    stage = workflow.assert_can_sign(
        payload.stage_key, str(auth.user_id), str(membership.get("role", "")), steps
    )
    await repository.record_approval_step(
        {
            "organization_id": str(organization_id),
            "prescription_id": str(prescription_id),
            "stage_key": stage.key,
            "stage_order": stage.order,
            "approved_by": str(auth.user_id),
            "notes": payload.notes,
        }
    )
    return await approval_status(prescription_id, auth, repository)


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


__all__ = ["router", "ApprovalStepResponse", "load_workflow"]
