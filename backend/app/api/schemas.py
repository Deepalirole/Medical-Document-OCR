from uuid import UUID

from fastapi import APIRouter, status

from app.core.auth import AuthDep, RepoDep
from app.core.errors import AppError
from app.models.domain import SchemaSummary
from app.models.review import SchemaCreate, SchemaUpdate
from app.services.schema.registry import SchemaRegistry

router = APIRouter(prefix="/prescription-schemas", tags=["schemas"])


@router.post("", response_model=SchemaSummary, status_code=status.HTTP_201_CREATED)
async def create_schema(
    payload: SchemaCreate, auth: AuthDep, repository: RepoDep
) -> SchemaSummary:
    await repository.assert_membership(auth.user_id, payload.organization_id, {"admin"})
    definition = SchemaRegistry().validate(payload.definition)
    row = await repository.create_schema(
        {
            **payload.model_dump(mode="json", exclude={"definition"}),
            "definition": definition,
            "status": "draft",
            "is_active": False,
            "created_by": str(auth.user_id),
        }
    )
    return SchemaSummary.model_validate(row)


@router.get("/{schema_id}", response_model=SchemaSummary)
async def schema_detail(schema_id: UUID, repository: RepoDep) -> SchemaSummary:
    row = await repository.schema_for_user(schema_id)
    if not row:
        raise AppError("SCHEMA_NOT_FOUND", "Schema not found.", 404)
    return SchemaSummary.model_validate(row)


@router.put("/{schema_id}", response_model=SchemaSummary)
async def update_schema(
    schema_id: UUID, payload: SchemaUpdate, auth: AuthDep, repository: RepoDep
) -> SchemaSummary:
    current = await repository.schema_for_user(schema_id)
    if not current:
        raise AppError("SCHEMA_NOT_FOUND", "Schema not found.", 404)
    organization_id = UUID(current["organization_id"])
    await repository.assert_membership(auth.user_id, organization_id, {"admin"})
    definition = SchemaRegistry().validate(payload.definition)
    if current["is_active"]:
        row = await repository.create_schema(
            {
                "organization_id": str(organization_id),
                "schema_key": current["schema_key"],
                "name": payload.name,
                "version": current["version"] + 1,
                "definition": definition,
                "status": "draft",
                "is_active": False,
                "created_by": str(auth.user_id),
            }
        )
    else:
        row = await repository.update_schema(
            schema_id, {"name": payload.name, "definition": definition}
        )
    return SchemaSummary.model_validate(row)


@router.post("/{schema_id}/activate", response_model=SchemaSummary)
async def activate_schema(schema_id: UUID, auth: AuthDep, repository: RepoDep) -> SchemaSummary:
    current = await repository.schema_for_user(schema_id)
    if not current:
        raise AppError("SCHEMA_NOT_FOUND", "Schema not found.", 404)
    await repository.assert_membership(auth.user_id, UUID(current["organization_id"]), {"admin"})
    return SchemaSummary.model_validate(await repository.activate_schema(schema_id))


@router.delete("/{schema_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schema(schema_id: UUID, auth: AuthDep, repository: RepoDep) -> None:
    current = await repository.schema_for_user(schema_id)
    if not current:
        raise AppError("SCHEMA_NOT_FOUND", "Schema not found.", 404)
    if current["is_active"]:
        raise AppError(
            "ACTIVE_SCHEMA_DELETE_FORBIDDEN",
            "Archive by activating a newer version.",
            409,
        )
    await repository.assert_membership(
        auth.user_id, UUID(current["organization_id"]), {"admin"}
    )
    await repository.delete_schema(schema_id)
