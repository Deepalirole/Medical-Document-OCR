from typing import Any
from uuid import UUID

from app.core.errors import AppError
from app.repositories.supabase.client import SupabaseAdminClient


class SupabaseProcessingRepository:
    def __init__(self, client: SupabaseAdminClient) -> None:
        self.client = client

    async def _insert(self, table: str, data: dict[str, Any]) -> dict[str, Any]:
        rows = await self.client.request(
            "POST", table, json=data, extra_headers={"Prefer": "return=representation"}
        )
        return rows[0]

    async def find_duplicate(self, organization_id: UUID, sha256: str) -> dict[str, Any] | None:
        rows = await self.client.request(
            "GET",
            "prescriptions",
            params={
                "organization_id": f"eq.{organization_id}",
                "source_sha256": f"eq.{sha256}",
                "select": "*",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    async def create_prescription(self, data: dict[str, Any]) -> dict[str, Any]:
        return await self._insert("prescriptions", data)

    async def update_prescription(self, prescription_id: UUID, data: dict[str, Any]) -> None:
        await self.client.request(
            "PATCH",
            "prescriptions",
            params={"id": f"eq.{prescription_id}"},
            json=data,
            extra_headers={"Prefer": "return=minimal"},
        )

    async def get_prescription(
        self, prescription_id: UUID, organization_id: UUID
    ) -> dict[str, Any] | None:
        rows = await self.client.request(
            "GET",
            "prescriptions",
            params={
                "id": f"eq.{prescription_id}",
                "organization_id": f"eq.{organization_id}",
                "select": "*",
            },
        )
        return rows[0] if rows else None

    async def create_page(self, data: dict[str, Any]) -> dict[str, Any]:
        return await self._insert("prescription_pages", data)

    async def update_page(self, page_id: UUID, data: dict[str, Any]) -> None:
        await self.client.request(
            "PATCH",
            "prescription_pages",
            params={"id": f"eq.{page_id}"},
            json=data,
        )

    async def pages(self, prescription_id: UUID) -> list[dict[str, Any]]:
        return await self.client.request(
            "GET",
            "prescription_pages",
            params={
                "prescription_id": f"eq.{prescription_id}",
                "select": "*",
                "order": "page_number",
            },
        )

    async def create_job(self, data: dict[str, Any]) -> dict[str, Any]:
        return await self._insert("processing_jobs", data)

    async def finish_job(self, job_id: UUID, data: dict[str, Any]) -> None:
        await self.client.request(
            "PATCH",
            "processing_jobs",
            params={"id": f"eq.{job_id}"},
            json=data,
            extra_headers={"Prefer": "return=minimal"},
        )

    async def jobs(self, prescription_id: UUID) -> list[dict[str, Any]]:
        return await self.client.request(
            "GET",
            "processing_jobs",
            params={
                "prescription_id": f"eq.{prescription_id}",
                "select": "*",
                "order": "created_at.asc",
            },
        )

    async def create_ocr_result(
        self, result: dict[str, Any], tokens: list[dict[str, Any]]
    ) -> dict[str, Any]:
        created = await self._insert("ocr_results", result)
        if tokens:
            for token in tokens:
                token["ocr_result_id"] = created["id"]
            await self.client.request(
                "POST", "ocr_tokens", json=tokens, extra_headers={"Prefer": "return=minimal"}
            )
        return created

    async def ocr_results(
        self, prescription_id: UUID, include_tokens: bool = True
    ) -> list[dict[str, Any]]:
        selection = "*,ocr_tokens(*)" if include_tokens else "*"
        return await self.client.request(
            "GET",
            "ocr_results",
            params={
                "prescription_id": f"eq.{prescription_id}",
                "select": selection,
                "order": "created_at.asc",
            },
        )

    async def schema(self, schema_id: UUID) -> dict[str, Any] | None:
        rows = await self.client.request(
            "GET",
            "prescription_schemas",
            params={"id": f"eq.{schema_id}", "select": "*", "limit": "1"},
        )
        return rows[0] if rows else None

    async def create_extraction_run(self, data: dict[str, Any]) -> dict[str, Any]:
        try:
            return await self._insert("extraction_runs", data)
        except AppError as err:
            if "prompt_sha256" in err.message or "prompt_version" in err.message or "PGRST204" in err.message:
                fallback_data = {
                    k: v for k, v in data.items() if k not in ("prompt_version", "prompt_sha256")
                }
                return await self._insert("extraction_runs", fallback_data)
            raise

    async def create_fields(self, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not fields:
            return []
        return await self.client.request(
            "POST",
            "prescription_fields",
            json=fields,
            extra_headers={"Prefer": "return=representation"},
        )

    async def delete_fields(self, prescription_id: UUID) -> None:
        await self.client.request(
            "DELETE",
            "prescription_fields",
            params={"prescription_id": f"eq.{prescription_id}"},
            extra_headers={"Prefer": "return=minimal"},
        )

    async def fields(self, prescription_id: UUID) -> list[dict[str, Any]]:
        return await self.client.request(
            "GET",
            "prescription_fields",
            params={
                "prescription_id": f"eq.{prescription_id}",
                "select": "*",
                "order": "field_path.asc",
            },
        )

    async def diagnostics(
        self, organization_id: UUID, limit: int
    ) -> list[dict[str, Any]]:
        return await self.client.request(
            "GET",
            "processing_jobs",
            params={
                "organization_id": f"eq.{organization_id}",
                "select": (
                    "id,prescription_id,stage,status,attempt,started_at,completed_at,"
                    "processing_ms,error_code,safe_error_message,metadata"
                ),
                "order": "created_at.desc",
                "limit": str(limit),
            },
        )
