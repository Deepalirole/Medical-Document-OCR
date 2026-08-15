from typing import Any

import httpx

from app.core.config import Settings
from app.core.errors import AppError


class SupabaseRestClient:
    """Minimal PostgREST client that forwards the caller JWT so RLS remains authoritative."""

    def __init__(self, settings: Settings, access_token: str) -> None:
        self.base_url = f"{settings.supabase_url.rstrip('/')}/rest/v1"
        self.headers = {
            "apikey": settings.supabase_publishable_key,
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json: Any = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Any:
        async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
            response = await client.request(
                method,
                f"{self.base_url}/{path}",
                headers={**self.headers, **(extra_headers or {})},
                params=params,
                json=json,
            )
        if response.status_code >= 400:
            raise AppError(
                "DATABASE_FAILED",
                f"The data service rejected the request: {response.text}",
                502,
                {"status": response.status_code, "body": response.text},
            )
        if not response.content:
            return None
        return response.json()


class SupabaseAdminClient(SupabaseRestClient):
    def __init__(self, settings: Settings) -> None:
        service_key = settings.supabase_service_role_key.get_secret_value()
        if not settings.supabase_url or not service_key:
            raise AppError(
                "SERVICE_NOT_CONFIGURED", "Supabase service access is not configured.", 503
            )
        self.base_url = f"{settings.supabase_url.rstrip('/')}/rest/v1"
        self.headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
        }
