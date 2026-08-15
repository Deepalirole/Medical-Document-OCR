from pathlib import PurePosixPath

import httpx

from app.core.config import Settings
from app.core.errors import AppError


class SupabaseStorage:
    ALLOWED_BUCKETS = {"prescription-source", "prescription-derived"}

    def __init__(self, settings: Settings) -> None:
        service_key = settings.supabase_service_role_key.get_secret_value()
        if not settings.supabase_url or not service_key:
            raise AppError("SERVICE_NOT_CONFIGURED", "Private storage is not configured.", 503)
        self.base_url = f"{settings.supabase_url.rstrip('/')}/storage/v1"
        self.headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}
        self.signed_url_ttl = settings.signed_url_ttl_seconds

    @classmethod
    def validate_object_path(cls, bucket: str, path: str, organization_id: str) -> str:
        if bucket not in cls.ALLOWED_BUCKETS:
            raise AppError("STORAGE_PATH_INVALID", "Unknown private storage bucket.", 400)
        normalized = str(PurePosixPath(path))
        parts = PurePosixPath(normalized).parts
        if not parts or parts[0] != organization_id or ".." in parts or normalized.startswith("/"):
            raise AppError("STORAGE_PATH_INVALID", "Storage path is outside the organization.", 400)
        return normalized

    async def upload(
        self,
        bucket: str,
        path: str,
        content: bytes,
        content_type: str,
        organization_id: str,
        upsert: bool = False,
    ) -> None:
        safe_path = self.validate_object_path(bucket, path, organization_id)
        headers = {
            **self.headers,
            "Content-Type": content_type,
            "x-upsert": "true" if upsert else "false",
        }
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            response = await client.post(
                f"{self.base_url}/object/{bucket}/{safe_path}", headers=headers, content=content
            )
        if response.status_code not in {200, 201}:
            raise AppError("STORAGE_FAILED", "The private source could not be stored.", 502)

    async def create_signed_url(
        self, bucket: str, path: str, organization_id: str
    ) -> str:
        safe_path = self.validate_object_path(bucket, path, organization_id)
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            response = await client.post(
                f"{self.base_url}/object/sign/{bucket}/{safe_path}",
                headers={**self.headers, "Content-Type": "application/json"},
                json={"expiresIn": self.signed_url_ttl},
            )
        if response.status_code != 200:
            raise AppError("STORAGE_FAILED", "A private preview link could not be created.", 502)
        signed_url = response.json().get("signedURL")
        if not signed_url:
            raise AppError("STORAGE_FAILED", "Storage returned an invalid preview link.", 502)
        if signed_url.startswith("http"):
            return signed_url
        return f"{self.base_url}{signed_url}"

    async def download(self, bucket: str, path: str, organization_id: str) -> bytes:
        safe_path = self.validate_object_path(bucket, path, organization_id)
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            response = await client.get(
                f"{self.base_url}/object/{bucket}/{safe_path}", headers=self.headers
            )
        if response.status_code != 200:
            raise AppError("STORAGE_FAILED", "The private source could not be loaded.", 502)
        return response.content
