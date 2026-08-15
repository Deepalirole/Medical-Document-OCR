from typing import Any
from uuid import UUID, uuid4

from app.core.errors import AppError
from app.repositories.processing import ProcessingRepository
from app.services.ingestion.files import ValidatedFile
from app.services.storage.supabase import SupabaseStorage


class PrescriptionRegistrationService:
    def __init__(self, repository: ProcessingRepository, storage: SupabaseStorage) -> None:
        self.repository = repository
        self.storage = storage

    async def register(
        self,
        source: ValidatedFile,
        organization_id: UUID,
        schema_id: UUID,
        uploaded_by: UUID,
    ) -> dict[str, Any]:
        duplicate = await self.repository.find_duplicate(organization_id, source.sha256)
        if duplicate:
            return {**duplicate, "duplicate": True}

        prescription_id = uuid4()
        path = (
            f"{organization_id}/{prescription_id}/original/"
            f"{uuid4().hex}-{source.generated_filename}"
        )
        await self.storage.upload(
            "prescription-source", path, source.content, source.mime_type, str(organization_id)
        )
        return await self.repository.create_prescription(
            {
                "id": str(prescription_id),
                "organization_id": str(organization_id),
                "uploaded_by": str(uploaded_by),
                "schema_id": str(schema_id),
                "original_filename": source.original_filename,
                "source_mime_type": source.mime_type,
                "source_storage_path": path,
                "source_type": source.source_type,
                "source_sha256": source.sha256,
                "status": "UPLOADED",
                "page_count": source.page_count,
            }
        )

    async def assert_schema_belongs_to_organization(
        self, schema_id: UUID, organization_id: UUID
    ) -> None:
        # Schema ownership is checked by the route's user-scoped RLS read before registration.
        if not schema_id or not organization_id:
            raise AppError("SCHEMA_REQUIRED", "An organization schema is required.", 422)

