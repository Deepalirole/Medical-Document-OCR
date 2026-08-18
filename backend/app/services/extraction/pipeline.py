import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.core.errors import AppError
from app.repositories.processing import ProcessingRepository
from app.services.extraction.mapper import DynamicFieldMapper
from app.services.llm.base import LLMProvider
from app.services.schema.registry import SchemaRegistry
from app.services.validation.dynamic import DynamicValidator


class ExtractionService:
    def __init__(self, repository: ProcessingRepository, provider: LLMProvider) -> None:
        self.repository = repository
        self.provider = provider
        self.registry = SchemaRegistry()
        self.mapper = DynamicFieldMapper()
        self.validator = DynamicValidator()

    async def extract(
        self, prescription: dict[str, Any], idempotency_key: str | None = None
    ) -> dict[str, Any]:
        prescription_id = UUID(prescription["id"])
        organization_id = UUID(prescription["organization_id"])
        schema_id = UUID(prescription["schema_id"])
        existing_fields = await self.repository.fields(prescription_id)
        if existing_fields and prescription.get("status") not in {"UPLOADED", "LLM_FAILED", "OCR_FAILED"}:
            return {
                "prescription_id": str(prescription_id),
                "status": prescription.get("status", "REVIEW_REQUIRED"),
                "warnings": [],
                "idempotent": True,
            }
        if existing_fields:
            await self.repository.delete_fields(prescription_id)
        schema = await self.repository.schema(schema_id)
        if not schema:
            raise AppError("SCHEMA_NOT_FOUND", "Pinned prescription schema not found.", 404)
        definition = self.registry.validate(schema["definition"])
        json_schema = self.registry.to_json_schema(definition)
        results = await self.repository.ocr_results(prescription_id)
        raw_text, evidence = self._evidence(results)
        input_hash = hashlib.sha256(
            json.dumps(
                {"schema": definition, "evidence": evidence},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        job = await self.repository.create_job(
            {
                "organization_id": str(organization_id),
                "prescription_id": str(prescription_id),
                "stage": "EXTRACTION_RUNNING",
                "status": "RUNNING",
                "attempt": 1,
                "idempotency_key": (
                    f"{idempotency_key}:extraction" if idempotency_key else f"extraction:{uuid4()}"
                ),
                "metadata": {"provider": self.provider.name, "schema_id": str(schema_id)},
            }
        )
        try:
            extraction = await self.provider.extract(
                raw_text, evidence, definition, json_schema
            )
            validation = self.validator.validate(definition, extraction.structured_output)
            fields = self.mapper.map(definition, extraction.structured_output, evidence)
            await self.repository.create_extraction_run(
                {
                    "organization_id": str(organization_id),
                    "prescription_id": str(prescription_id),
                    "schema_id": str(schema_id),
                    "provider": extraction.provider,
                    "model": extraction.model,
                    "input_hash": input_hash,
                    "raw_response": extraction.raw_response,
                    "structured_output": extraction.structured_output,
                    "status": "REVIEW_REQUIRED" if not validation.valid else "COMPLETED",
                    "processing_ms": extraction.processing_ms,
                    **self._prompt_identity(),
                }
            )
            await self._persist_fields(organization_id, prescription_id, schema_id, fields)
            await self.repository.finish_job(
                UUID(job["id"]),
                {
                    "status": "COMPLETED",
                    "completed_at": datetime.now(UTC).isoformat(),
                    "processing_ms": extraction.processing_ms,
                    "metadata": {
                        "provider": extraction.provider,
                        "model": extraction.model,
                        "warning_count": len(validation.warnings),
                    },
                },
            )
            await self.repository.update_prescription(
                prescription_id, {"status": "REVIEW_REQUIRED"}
            )
            return {
                "prescription_id": str(prescription_id),
                "status": "REVIEW_REQUIRED",
                "warnings": validation.warnings,
            }
        except AppError as error:
            empty_output: dict[str, Any] = {}
            fields = self.mapper.map(definition, empty_output, evidence)
            await self.repository.create_extraction_run(
                {
                    "organization_id": str(organization_id),
                    "prescription_id": str(prescription_id),
                    "schema_id": str(schema_id),
                    "provider": self.provider.name,
                    "model": str(self.provider.health().get("model", "unconfigured")),
                    "input_hash": input_hash,
                    "raw_response": None,
                    "structured_output": None,
                    "status": "FAILED",
                    "processing_ms": 0,
                    "error_code": error.code,
                    **self._prompt_identity(),
                }
            )
            await self._persist_fields(organization_id, prescription_id, schema_id, fields)
            await self.repository.finish_job(
                UUID(job["id"]),
                {
                    "status": "FAILED",
                    "completed_at": datetime.now(UTC).isoformat(),
                    "error_code": error.code,
                    "safe_error_message": error.message,
                },
            )
            await self.repository.update_prescription(prescription_id, {"status": "LLM_FAILED"})
            return {
                "prescription_id": str(prescription_id),
                "status": "LLM_FAILED",
                "warnings": [{"path": "", "code": error.code}],
            }

    def _prompt_identity(self) -> dict[str, Any]:
        """Pin the exact prompt an extraction ran under, when the provider exposes one.

        Providers that carry no versioned prompt record nulls rather than a guess, so the
        column never claims a lineage that does not exist.
        """
        return {
            "prompt_version": getattr(self.provider, "prompt_version", None),
            "prompt_sha256": getattr(self.provider, "prompt_sha256", None),
        }

    async def _persist_fields(
        self, organization_id: UUID, prescription_id: UUID, schema_id: UUID, fields
    ) -> None:
        await self.repository.create_fields(
            [
                {
                    "organization_id": str(organization_id),
                    "prescription_id": str(prescription_id),
                    "schema_id": str(schema_id),
                    **field.as_dict(),
                }
                for field in fields
            ]
        )

    @staticmethod
    def _evidence(results: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
        raw_parts: list[str] = []
        evidence: list[dict[str, Any]] = []
        for result in results:
            raw_text = result.get("raw_text", "")
            if raw_text:
                raw_parts.append(raw_text)
                evidence.append(
                    {
                        "text": raw_text,
                        "page_id": result["page_id"],
                        "source": "ocr_result",
                        "engine": result["provider"],
                        "confidence": result.get("confidence"),
                        "bbox": None,
                    }
                )
            for token in result.get("ocr_tokens", []):
                evidence.append(
                    {
                        "text": token["text"],
                        "page_id": token["page_id"],
                        "source": token["source"],
                        "engine": result["provider"],
                        "confidence": token.get("confidence"),
                        "bbox": token.get("bbox"),
                    }
                )
        return "\n\n".join(raw_parts), evidence
