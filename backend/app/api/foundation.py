from fastapi import APIRouter

from app.core.auth import AuthDep, RepoDep
from app.models.domain import CurrentUser, Membership, Organization, SchemaSummary

router = APIRouter(tags=["foundation"])


@router.get("/me", response_model=CurrentUser)
async def me(auth: AuthDep, repository: RepoDep) -> CurrentUser:
    profile = await repository.profile_for_user(auth.user_id)
    memberships = await repository.memberships_for_user(auth.user_id)
    return CurrentUser(
        id=auth.user_id,
        email=auth.email,
        display_name=profile.get("display_name") if profile else None,
        memberships=[
            Membership(
                organization_id=row["organization_id"],
                organization_name=row["organizations"]["name"],
                role=row["role"],
            )
            for row in memberships
        ],
    )


@router.get("/organizations", response_model=list[Organization])
async def organizations(auth: AuthDep, repository: RepoDep) -> list[Organization]:
    rows = await repository.organizations_for_user(auth.user_id)
    return [Organization.model_validate(row) for row in rows]


@router.get("/prescription-schemas", response_model=list[SchemaSummary])
async def schemas(auth: AuthDep, repository: RepoDep) -> list[SchemaSummary]:
    rows = await repository.schemas_for_user(auth.user_id)
    return [SchemaSummary.model_validate(row) for row in rows]
