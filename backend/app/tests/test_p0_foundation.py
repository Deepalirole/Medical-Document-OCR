import asyncio
from uuid import UUID

from app.core.errors import AppError
from app.tests.conftest import ORG_ID, USER_ID, FakeRepository


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_current_user_includes_membership(client):
    response = client.get("/api/me")
    assert response.status_code == 200
    assert response.json()["memberships"][0]["organization_id"] == str(ORG_ID)


def test_organizations_are_membership_scoped(client):
    response = client.get("/api/organizations")
    assert response.status_code == 200
    assert response.json() == [{"id": str(ORG_ID), "name": "Safe Clinic"}]


def test_protected_endpoint_requires_authentication():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as anonymous:
        response = anonymous.get("/api/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_cross_org_is_denied(repository: FakeRepository):
    async def exercise() -> None:
        try:
            await repository.assert_membership(
                USER_ID, UUID("33333333-3333-4333-8333-333333333333")
            )
        except AppError as error:
            assert error.status_code == 403
            return
        raise AssertionError("Cross-organization access was accepted")

    asyncio.run(exercise())
