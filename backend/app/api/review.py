from uuid import UUID

from fastapi import APIRouter, Response

from app.core.auth import RepoDep
from app.core.errors import AppError
from app.models.review import (
    ApprovedVersionResponse,
    BulkFieldCorrection,
    FieldCorrection,
    FieldResponse,
    FieldsResponse,
)
from app.services.approvals.workflow import ApprovalWorkflow
from app.services.export.excel import generate_excel_export
from app.services.extraction.mapper import build_structured_json
from app.services.schema.registry import SchemaRegistry
from app.services.validation.dynamic import DynamicValidator

router = APIRouter(prefix="/prescriptions/{prescription_id}", tags=["review"])


async def _prescription_and_fields(prescription_id: UUID, repository: RepoDep):
    prescription = await repository.prescription_for_user(prescription_id)
    if not prescription:
        raise AppError("PRESCRIPTION_NOT_FOUND", "Prescription not found.", 404)
    fields = await repository.fields_for_user(prescription_id)
    return prescription, fields


@router.get("/fields", response_model=FieldsResponse)
async def fields(prescription_id: UUID, repository: RepoDep) -> FieldsResponse:
    prescription, rows = await _prescription_and_fields(prescription_id, repository)
    schema = await repository.schema_for_user(UUID(prescription["schema_id"]))
    if not schema:
        raise AppError("SCHEMA_NOT_FOUND", "Pinned schema not found.", 404)
    return FieldsResponse(
        prescription_id=prescription_id,
        schema_definition=schema["definition"],
        structured_json=build_structured_json(rows),
        fields=[FieldResponse.model_validate(row) for row in rows],
    )


@router.patch("/fields/{field_id}", response_model=FieldResponse)
async def correct_field(
    prescription_id: UUID,
    field_id: UUID,
    payload: FieldCorrection,
    repository: RepoDep,
) -> FieldResponse:
    _, rows = await _prescription_and_fields(prescription_id, repository)
    if not any(UUID(row["id"]) == field_id for row in rows):
        raise AppError("FIELD_NOT_FOUND", "Field not found.", 404)
    return FieldResponse.model_validate(
        await repository.correct_field(field_id, payload.value, payload.reason)
    )


@router.patch("/fields", response_model=list[FieldResponse])
async def correct_fields(
    prescription_id: UUID,
    payload: BulkFieldCorrection,
    repository: RepoDep,
) -> list[FieldResponse]:
    _, rows = await _prescription_and_fields(prescription_id, repository)
    allowed = {UUID(row["id"]) for row in rows}
    if any(field_id not in allowed for field_id, _, _ in payload.updates):
        raise AppError("FIELD_NOT_FOUND", "One or more fields were not found.", 404)
    corrected = []
    for field_id, value, reason in payload.updates:
        corrected.append(await repository.correct_field(field_id, value, reason))
    for item in payload.add_items:
        corrected.extend(
            await repository.add_array_item(
                prescription_id, item.array_path, item.values
            )
        )
    for item_id in payload.remove_item_ids:
        corrected.extend(await repository.remove_array_item(prescription_id, item_id))
    return [FieldResponse.model_validate(row) for row in corrected]


@router.post("/approve", response_model=ApprovedVersionResponse)
async def approve(prescription_id: UUID, repository: RepoDep) -> ApprovedVersionResponse:
    prescription, rows = await _prescription_and_fields(prescription_id, repository)
    if not rows:
        raise AppError("FIELDS_NOT_READY", "No reviewable fields exist.", 409)
    await _assert_approval_stages_complete(prescription, prescription_id, repository)
    unresolved_or_null = [
        r for r in rows if r["review_status"] == "REVIEW_REQUIRED" or r["current_value"] is None
    ]
    if unresolved_or_null:
        for r in unresolved_or_null:
            val = "" if r["current_value"] is None else r["current_value"]
            await repository.correct_field(UUID(r["id"]), val, "Confirmed on approval")
        rows = await repository.fields_for_user(prescription_id)
    schema = await repository.schema_for_user(UUID(prescription["schema_id"]))
    if not schema:
        raise AppError("SCHEMA_NOT_FOUND", "Pinned schema not found.", 404)
    SchemaRegistry().validate(schema["definition"])
    snapshot = build_structured_json(rows)
    return ApprovedVersionResponse.model_validate(
        await repository.approve_snapshot(prescription_id, snapshot)
    )


async def _assert_approval_stages_complete(prescription, prescription_id: UUID, repository) -> None:
    """Refuse to cut the immutable version while approval stages are outstanding."""
    getter = getattr(repository, "approval_workflow", None)
    if getter is None:
        return
    organization_id = UUID(str(prescription["organization_id"]))
    workflow = ApprovalWorkflow.from_config(await getter(organization_id))
    if not workflow.is_multi_stage:
        return
    steps = await repository.approval_steps(prescription_id)
    progress = workflow.progress(steps)
    if not progress.can_finalize:
        raise AppError(
            "APPROVAL_STAGES_INCOMPLETE",
            "All approval stages must be signed off before the version is created.",
            409,
            {
                "next_stage": progress.next_stage.key if progress.next_stage else None,
                "completed_keys": progress.completed_keys,
            },
        )


@router.get("/json", response_model=dict)
async def final_json(prescription_id: UUID, repository: RepoDep) -> dict:
    prescription = await repository.prescription_for_user(prescription_id)
    if not prescription:
        raise AppError("PRESCRIPTION_NOT_FOUND", "Prescription not found.", 404)
    version = await repository.approved_version(prescription_id)
    if not version:
        raise AppError("NOT_APPROVED", "No approved prescription version exists.", 409)
    return version["structured_json"]


@router.get("/export/excel")
async def export_excel(prescription_id: UUID, repository: RepoDep) -> Response:
    prescription, rows = await _prescription_and_fields(prescription_id, repository)
    version = await repository.approved_version(prescription_id)
    structured = version["structured_json"] if version else build_structured_json(rows)
    filename = prescription.get("original_filename", "medical_document").rsplit(".", 1)[0]
    excel_bytes = generate_excel_export(
        structured_json=structured,
        document_name=prescription.get("original_filename", "Medical Document"),
        document_id=str(prescription_id),
    )
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}_export.xlsx"'},
    )


@router.get("/export/json")
async def export_json(prescription_id: UUID, repository: RepoDep) -> dict:
    prescription, rows = await _prescription_and_fields(prescription_id, repository)
    version = await repository.approved_version(prescription_id)
    structured = version["structured_json"] if version else build_structured_json(rows)
    return structured

