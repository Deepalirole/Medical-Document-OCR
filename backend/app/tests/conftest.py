from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.core.auth import AuthContext, get_auth_context, get_repository
from app.main import app

USER_ID = UUID("11111111-1111-4111-8111-111111111111")
ORG_ID = UUID("22222222-2222-4222-8222-222222222222")


class FakeRepository:
    async def profile_for_user(self, user_id: UUID) -> dict[str, Any] | None:
        return {"id": str(user_id), "display_name": "Test Reviewer"}

    async def memberships_for_user(self, user_id: UUID) -> list[dict[str, Any]]:
        return [
            {
                "organization_id": str(ORG_ID),
                "user_id": str(user_id),
                "role": "reviewer",
                "organizations": {"name": "Safe Clinic"},
            }
        ]

    async def organizations_for_user(self, user_id: UUID) -> list[dict[str, Any]]:
        return [{"id": str(ORG_ID), "name": "Safe Clinic"}]

    async def schemas_for_user(self, user_id: UUID) -> list[dict[str, Any]]:
        return []

    async def schema_for_user(self, schema_id: UUID) -> dict[str, Any] | None:
        return None

    async def prescription_for_user(self, prescription_id: UUID) -> dict[str, Any] | None:
        return None

    async def create_schema(self, data: dict[str, Any]) -> dict[str, Any]:
        return data

    async def update_schema(self, schema_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
        return {"id": str(schema_id), **data}

    async def activate_schema(self, schema_id: UUID) -> dict[str, Any]:
        return {"id": str(schema_id), "is_active": True}

    async def delete_schema(self, schema_id: UUID) -> None:
        return None

    async def fields_for_user(self, prescription_id: UUID) -> list[dict[str, Any]]:
        return []

    async def correct_field(self, field_id: UUID, value: Any, reason: str | None):
        return {"id": str(field_id), "current_value": value, "reason": reason}

    async def approve_snapshot(self, prescription_id: UUID, snapshot: dict[str, Any]):
        return {"prescription_id": str(prescription_id), "structured_json": snapshot}

    async def approved_version(self, prescription_id: UUID):
        return None

    async def add_array_item(self, prescription_id: UUID, array_path: str, values):
        return []

    async def remove_array_item(self, prescription_id: UUID, array_item_id: str):
        return []

    async def list_prescriptions(
        self, organization_id: UUID, limit: int, created_before: str | None
    ):
        return []

    async def organization_metrics(self, organization_id: UUID):
        return {"processed_count": 0}

    async def assert_membership(
        self, user_id: UUID, organization_id: UUID, roles: set[str] | None = None
    ) -> dict[str, Any]:
        if organization_id != ORG_ID or (roles and "reviewer" not in roles):
            from app.core.errors import AppError

            raise AppError("AUTHORIZATION_FAILED", "Organization access denied.", 403)
        return {
            "user_id": str(user_id),
            "organization_id": str(organization_id),
            "role": "reviewer",
        }


@pytest.fixture
def repository() -> FakeRepository:
    return FakeRepository()


@pytest.fixture
def client(repository: FakeRepository) -> AsyncIterator[TestClient]:
    async def auth_override() -> AuthContext:
        return AuthContext(USER_ID, "reviewer@example.test", "test-token")

    app.dependency_overrides[get_auth_context] = auth_override
    app.dependency_overrides[get_repository] = lambda: repository
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
