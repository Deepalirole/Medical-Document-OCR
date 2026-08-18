"""Approved-only dispatch orchestration for the HMIS/EMR boundary.

The service reads the reviewer-approved immutable version, pins the schema that version was
approved against, maps it to destination records, and only then hands it to a connector.
OCR output, OpenRouter output, and unapproved current field values never reach this path.
"""

from typing import Any
from uuid import UUID

from app.core.errors import AppError
from app.repositories.base import Repository
from app.services.integrations.base import HMISConnector, HMISDispatchResult, HMISDocument
from app.services.integrations.medikunj import MedikunjMapper

CONTRACT_VERSION = "1.0"


class HMISDispatchService:
    def __init__(
        self,
        repository: Repository,
        connector: HMISConnector,
        mapper: MedikunjMapper | None = None,
    ) -> None:
        self.repository = repository
        self.connector = connector
        self.mapper = mapper or MedikunjMapper()

    async def build_document(self, prescription_id: UUID) -> HMISDocument:
        prescription = await self.repository.prescription_for_user(prescription_id)
        if not prescription:
            raise AppError("PRESCRIPTION_NOT_FOUND", "Prescription not found.", 404)
        version = await self.repository.approved_version(prescription_id)
        if not version:
            raise AppError(
                "NOT_APPROVED",
                "Only reviewer-approved prescriptions can be dispatched to an HMIS/EMR.",
                409,
            )
        payload = {
            "contract_version": CONTRACT_VERSION,
            "prescription_id": str(prescription_id),
            "organization_id": prescription["organization_id"],
            "schema": {"id": version["schema_id"], "version": version["schema_version"]},
            "approved_version": version["version"],
            "approved_at": prescription.get("approved_at"),
            "data": version["structured_json"],
        }
        definition = await self._pinned_definition(version)
        return self.mapper.map(payload, definition)

    async def dispatch(self, prescription_id: UUID) -> HMISDispatchResult:
        document = await self.build_document(prescription_id)
        return await self.connector.dispatch(document)

    async def _pinned_definition(self, version: dict[str, Any]) -> dict[str, Any] | None:
        schema_id = version.get("schema_id")
        if not schema_id:
            return None
        row = await self.repository.schema_for_user(UUID(str(schema_id)))
        if not row:
            return None
        definition = row.get("definition")
        return definition if isinstance(definition, dict) else None
