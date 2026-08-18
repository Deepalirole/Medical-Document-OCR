"""Reviewer assistance endpoints.

Everything here is advisory. These routes read persisted evidence and return suggestions; none
of them mutate a prescription, activate a schema, or alter a reviewed value.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.dependencies import MedicineDictionaryDep, ProcessingRepoDep
from app.core.auth import AuthDep, RepoDep
from app.core.errors import AppError
from app.models.assistance import (
    MedicineFieldSuggestion,
    MedicineLookupResponse,
    PrescriptionMedicineSuggestions,
    PromptVersionModel,
    PromptVersionsResponse,
    SchemaSuggestionResponse,
)
from app.services.assistance.medicines import (
    field_matches_medicine_name,
    medicine_name_paths,
)
from app.services.llm.prompt_registry import LATEST_PROMPT_VERSION, list_prompts
from app.services.schema.detection import SchemaDetector

router = APIRouter(tags=["assistance"])


@router.get(
    "/prescriptions/{prescription_id}/schema-suggestions",
    response_model=SchemaSuggestionResponse,
)
async def schema_suggestions(
    prescription_id: UUID,
    auth: AuthDep,
    repository: RepoDep,
    processing_repository: ProcessingRepoDep,
) -> SchemaSuggestionResponse:
    prescription = await repository.prescription_for_user(prescription_id)
    if not prescription:
        raise AppError("PRESCRIPTION_NOT_FOUND", "Prescription not found.", 404)
    organization_id = UUID(str(prescription["organization_id"]))
    await repository.assert_membership(auth.user_id, organization_id)

    rows = await processing_repository.ocr_results(prescription_id, include_tokens=False)
    raw_text = " ".join(str(row.get("raw_text") or "") for row in rows).strip()

    schemas = [
        schema
        for schema in await repository.schemas_for_user(auth.user_id)
        if str(schema.get("organization_id", "")) == str(organization_id)
    ]
    report = SchemaDetector().detect(
        raw_text, schemas, active_schema_id=_optional_str(prescription.get("schema_id"))
    )
    return SchemaSuggestionResponse.model_validate(report.to_dict())


@router.get("/assistance/prompt-versions", response_model=PromptVersionsResponse)
async def prompt_versions(auth: AuthDep) -> PromptVersionsResponse:
    del auth
    return PromptVersionsResponse(
        latest=LATEST_PROMPT_VERSION,
        versions=[PromptVersionModel.model_validate(item) for item in list_prompts()],
    )


@router.get("/assistance/medicines", response_model=MedicineLookupResponse)
async def medicine_lookup(
    auth: AuthDep,
    dictionary: MedicineDictionaryDep,
    query: Annotated[str, Query(min_length=1, max_length=120)],
    limit: Annotated[int, Query(ge=1, le=25)] = 5,
) -> MedicineLookupResponse:
    del auth
    return MedicineLookupResponse.model_validate(dictionary.lookup(query, limit).to_dict())


@router.get(
    "/prescriptions/{prescription_id}/medicine-suggestions",
    response_model=PrescriptionMedicineSuggestions,
)
async def prescription_medicine_suggestions(
    prescription_id: UUID,
    auth: AuthDep,
    repository: RepoDep,
    dictionary: MedicineDictionaryDep,
    limit: Annotated[int, Query(ge=1, le=25)] = 5,
) -> PrescriptionMedicineSuggestions:
    prescription = await repository.prescription_for_user(prescription_id)
    if not prescription:
        raise AppError("PRESCRIPTION_NOT_FOUND", "Prescription not found.", 404)
    await repository.assert_membership(
        auth.user_id, UUID(str(prescription["organization_id"]))
    )

    schema_id = prescription.get("schema_id")
    schema = await repository.schema_for_user(UUID(str(schema_id))) if schema_id else None
    definition = (schema or {}).get("definition")
    name_paths = medicine_name_paths(definition) if isinstance(definition, dict) else set()

    suggestions: list[MedicineFieldSuggestion] = []
    unknown = 0
    for field in await repository.fields_for_user(prescription_id):
        path = str(field.get("field_path", ""))
        value = field.get("current_value")
        if not field_matches_medicine_name(path, name_paths) or not isinstance(value, str):
            continue
        lookup = dictionary.lookup(value, limit)
        if not lookup.known:
            unknown += 1
        suggestions.append(
            MedicineFieldSuggestion(
                field_id=str(field.get("id", "")),
                field_path=path,
                value=value,
                **lookup.to_dict(),
            )
        )
    return PrescriptionMedicineSuggestions(
        prescription_id=str(prescription_id),
        dictionary_size=len(dictionary),
        fields_examined=len(suggestions),
        unknown_medicines=unknown,
        requires_reviewer_confirmation=True,
        fields=suggestions,
    )


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)
