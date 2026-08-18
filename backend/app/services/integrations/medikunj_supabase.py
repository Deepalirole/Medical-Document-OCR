"""Production Medikunj HMIS/EMR transport over PostgREST.

Dispatch is idempotent through ``medimind_id_map``: the deterministic ``source_id`` produced
by :class:`~app.services.integrations.medikunj.MedikunjMapper` is looked up before any write,
so replaying an approved version never duplicates clinical rows.
"""

import asyncio
from typing import Any

import httpx

from app.core.errors import AppError
from app.services.integrations.base import HMISDispatchResult, HMISDocument

TRANSIENT_STATUSES = {429, 500, 502, 503, 504}
MAP_ENTITY_TYPE = "prescription"


class MedikunjSupabaseConnector:
    def __init__(
        self,
        base_url: str,
        service_key: str,
        branch_id: str = "",
        timeout_seconds: int = 30,
        retries: int = 2,
    ) -> None:
        self.base_url = f"{base_url.rstrip('/')}/rest/v1" if base_url else ""
        self.service_key = service_key
        self.branch_id = branch_id
        self.timeout_seconds = timeout_seconds
        self.retries = retries

    @property
    def name(self) -> str:
        return "medikunj_supabase"

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.service_key)

    def health(self) -> dict[str, str | bool]:
        return {
            "provider": self.name,
            "configured": self.configured,
            "branch_scoped": bool(self.branch_id),
            "status": "HMIS_READY" if self.configured else "HMIS_NOT_CONFIGURED",
        }

    async def dispatch(self, document: HMISDocument) -> HMISDispatchResult:
        if not self.configured:
            raise AppError(
                "HMIS_NOT_CONFIGURED",
                "The Medikunj destination has no base URL or service key configured.",
                503,
            )

        existing = await self._request(
            "GET",
            "medimind_id_map",
            params={
                "select": "target_id",
                "entity_type": f"eq.{MAP_ENTITY_TYPE}",
                "source_id": f"eq.{document.source_id}",
                "limit": "1",
            },
        )
        if existing:
            return HMISDispatchResult(
                connector=self.name,
                dispatched=False,
                idempotent=True,
                source_id=document.source_id,
                item_count=len(document.prescription_items),
                target_ids={"prescription": str(existing[0]["target_id"])},
            )

        patient_id = await self._resolve_patient(document)
        prescription_row = await self._insert(
            "prescriptions",
            {
                **document.prescription,
                "patient_id": patient_id,
                **({"branch_id": self.branch_id} if self.branch_id else {}),
            },
        )
        prescription_id = str(prescription_row["id"])

        if document.prescription_items:
            await self._insert(
                "prescription_items",
                [
                    {**item, "prescription_id": prescription_id, "source_id": document.source_id}
                    for item in document.prescription_items
                ],
            )

        await self._insert(
            "medimind_id_map",
            {
                "entity_type": MAP_ENTITY_TYPE,
                "source_id": document.source_id,
                "target_id": prescription_id,
                "source_data": document.source_data,
            },
        )
        return HMISDispatchResult(
            connector=self.name,
            dispatched=True,
            idempotent=False,
            source_id=document.source_id,
            item_count=len(document.prescription_items),
            target_ids={"prescription": prescription_id, "patient": patient_id},
        )

    async def _resolve_patient(self, document: HMISDocument) -> str:
        found = await self._request(
            "GET",
            "patients",
            params={
                "select": "id",
                "source_id": f"eq.{document.source_id}",
                "limit": "1",
            },
        )
        if found:
            return str(found[0]["id"])
        row = await self._insert(
            "patients",
            {
                **document.patient,
                **({"branch_id": self.branch_id} if self.branch_id else {}),
            },
        )
        return str(row["id"])

    async def _insert(self, table: str, payload: Any) -> Any:
        rows = await self._request(
            "POST",
            table,
            json=payload,
            extra_headers={"Prefer": "return=representation"},
        )
        if isinstance(payload, list):
            return rows
        if not rows:
            raise AppError(
                "HMIS_DISPATCH_FAILED",
                f"The Medikunj destination returned no row for {table}.",
                502,
            )
        return rows[0]

    async def _request(
        self,
        method: str,
        table: str,
        *,
        params: dict[str, str] | None = None,
        json: Any = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Any:
        headers = {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Content-Type": "application/json",
            **(extra_headers or {}),
        }
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout_seconds, trust_env=False
                ) as client:
                    response = await client.request(
                        method,
                        f"{self.base_url}/{table}",
                        headers=headers,
                        params=params,
                        json=json,
                    )
                if response.status_code in TRANSIENT_STATUSES and attempt < self.retries:
                    await asyncio.sleep(0.25 * (2**attempt))
                    continue
                if response.status_code >= 400:
                    raise AppError(
                        "HMIS_DISPATCH_FAILED",
                        "The Medikunj destination rejected the approved prescription.",
                        502,
                        {"status": response.status_code, "table": table},
                    )
                if not response.content:
                    return []
                return response.json()
            except AppError:
                raise
            except (httpx.HTTPError, ValueError) as error:
                last_error = error
                if attempt < self.retries:
                    await asyncio.sleep(0.25 * (2**attempt))
                    continue
        raise AppError(
            "HMIS_DISPATCH_FAILED",
            "The Medikunj destination could not be reached.",
            502,
            {"table": table},
        ) from last_error
