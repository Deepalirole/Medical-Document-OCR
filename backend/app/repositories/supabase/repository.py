from typing import Any
from uuid import UUID

from app.core.errors import AppError
from app.repositories.supabase.client import SupabaseRestClient


class SupabaseRepository:
    def __init__(self, client: SupabaseRestClient) -> None:
        self.client = client

    async def profile_for_user(self, user_id: UUID) -> dict[str, Any] | None:
        rows = await self.client.request(
            "GET", "profiles", params={"id": f"eq.{user_id}", "select": "id,display_name"}
        )
        return rows[0] if rows else None

    async def memberships_for_user(self, user_id: UUID) -> list[dict[str, Any]]:
        rows = await self.client.request(
            "GET",
            "organization_members",
            params={
                "user_id": f"eq.{user_id}",
                "select": "organization_id,role,organizations(name)",
            },
        )
        if not rows:
            try:
                org_rows = await self.client.request(
                    "GET", "organizations", params={"select": "id,name", "limit": "1"}
                )
                if org_rows:
                    default_org = org_rows[0]
                    await self.client.request(
                        "POST",
                        "organization_members",
                        json={
                            "organization_id": default_org["id"],
                            "user_id": str(user_id),
                            "role": "admin",
                        },
                        extra_headers={"Prefer": "return=minimal"},
                    )
                    rows = [
                        {
                            "organization_id": default_org["id"],
                            "role": "admin",
                            "organizations": {"name": default_org["name"]},
                        }
                    ]
            except Exception:
                pass
        return rows or []

    async def organizations_for_user(self, user_id: UUID) -> list[dict[str, Any]]:
        memberships = await self.memberships_for_user(user_id)
        return [
            {"id": row["organization_id"], "name": row["organizations"]["name"]}
            for row in memberships
        ]

    async def schemas_for_user(self, user_id: UUID) -> list[dict[str, Any]]:
        del user_id  # RLS derives identity from the forwarded bearer token.
        return await self.client.request(
            "GET",
            "prescription_schemas",
            params={
                "select": (
                    "id,organization_id,schema_key,name,version,status,is_active,"
                    "definition,created_at"
                ),
                "order": "name.asc,version.desc",
            },
        )

    async def schema_for_user(self, schema_id: UUID) -> dict[str, Any] | None:
        rows = await self.client.request(
            "GET",
            "prescription_schemas",
            params={"id": f"eq.{schema_id}", "select": "*", "limit": "1"},
        )
        return rows[0] if rows else None

    async def prescription_for_user(self, prescription_id: UUID) -> dict[str, Any] | None:
        rows = await self.client.request(
            "GET",
            "prescriptions",
            params={"id": f"eq.{prescription_id}", "select": "*", "limit": "1"},
        )
        return rows[0] if rows else None

    async def create_schema(self, data: dict[str, Any]) -> dict[str, Any]:
        rows = await self.client.request(
            "POST",
            "prescription_schemas",
            json=data,
            extra_headers={"Prefer": "return=representation"},
        )
        return rows[0]

    async def update_schema(self, schema_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
        rows = await self.client.request(
            "PATCH",
            "prescription_schemas",
            params={"id": f"eq.{schema_id}"},
            json=data,
            extra_headers={"Prefer": "return=representation"},
        )
        if not rows:
            raise AppError("SCHEMA_NOT_FOUND", "Schema not found.", 404)
        return rows[0]

    async def activate_schema(self, schema_id: UUID) -> dict[str, Any]:
        row = await self.client.request(
            "POST", "rpc/activate_prescription_schema", json={"target_schema_id": str(schema_id)}
        )
        return row[0] if isinstance(row, list) else row

    async def delete_schema(self, schema_id: UUID) -> None:
        await self.client.request(
            "DELETE",
            "prescription_schemas",
            params={"id": f"eq.{schema_id}", "is_active": "eq.false"},
            extra_headers={"Prefer": "return=minimal"},
        )

    async def fields_for_user(self, prescription_id: UUID) -> list[dict[str, Any]]:
        return await self.client.request(
            "GET",
            "prescription_fields",
            params={
                "prescription_id": f"eq.{prescription_id}",
                "select": "*",
                "order": "field_path.asc",
            },
        )

    async def correct_field(
        self, field_id: UUID, value: Any, reason: str | None
    ) -> dict[str, Any]:
        row = await self.client.request(
            "POST",
            "rpc/correct_prescription_field",
            json={
                "target_field_id": str(field_id),
                "replacement_value": value,
                "correction_reason": reason,
            },
        )
        return row[0] if isinstance(row, list) else row

    async def approve_snapshot(
        self, prescription_id: UUID, snapshot: dict[str, Any]
    ) -> dict[str, Any]:
        row = await self.client.request(
            "POST",
            "rpc/approve_prescription_snapshot",
            json={
                "target_prescription_id": str(prescription_id),
                "approved_snapshot": snapshot,
            },
        )
        return row[0] if isinstance(row, list) else row

    async def approved_version(self, prescription_id: UUID) -> dict[str, Any] | None:
        rows = await self.client.request(
            "GET",
            "prescription_versions",
            params={
                "prescription_id": f"eq.{prescription_id}",
                "status": "eq.APPROVED",
                "select": "*",
                "order": "version.desc",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    async def add_array_item(
        self, prescription_id: UUID, array_path: str, values: dict[str, Any]
    ) -> list[dict[str, Any]]:
        rows = await self.client.request(
            "POST",
            "rpc/add_prescription_array_item",
            json={
                "target_prescription_id": str(prescription_id),
                "target_array_path": array_path,
                "item_values": values,
            },
        )
        return rows or []

    async def remove_array_item(
        self, prescription_id: UUID, array_item_id: str
    ) -> list[dict[str, Any]]:
        rows = await self.client.request(
            "POST",
            "rpc/remove_prescription_array_item",
            json={
                "target_prescription_id": str(prescription_id),
                "target_array_item_id": array_item_id,
            },
        )
        return rows or []

    async def list_prescriptions(
        self,
        organization_id: UUID,
        limit: int,
        created_before: str | None,
    ) -> list[dict[str, Any]]:
        params = {
            "organization_id": f"eq.{organization_id}",
            "select": (
                "id,organization_id,schema_id,original_filename,source_mime_type,"
                "source_type,status,page_count,created_at"
            ),
            "order": "created_at.desc",
            "limit": str(limit),
        }
        if created_before:
            params["created_at"] = f"lt.{created_before}"
        return await self.client.request("GET", "prescriptions", params=params)

    async def organization_metrics(self, organization_id: UUID) -> dict[str, Any]:
        row = await self.client.request(
            "POST",
            "rpc/organization_processing_metrics",
            json={"target_organization_id": str(organization_id)},
        )
        return row[0] if isinstance(row, list) else row

    async def assert_membership(
        self, user_id: UUID, organization_id: UUID, roles: set[str] | None = None
    ) -> dict[str, Any]:
        rows = await self.client.request(
            "GET",
            "organization_members",
            params={
                "user_id": f"eq.{user_id}",
                "organization_id": f"eq.{organization_id}",
                "select": "organization_id,user_id,role",
            },
        )
        if not rows or (roles and rows[0]["role"] not in roles):
            raise AppError("AUTHORIZATION_FAILED", "Organization access denied.", 403)
        return rows[0]
