import time
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.core.errors import AppError
from app.repositories.processing import ProcessingRepository
from app.services.htr.base import HTREngine
from app.services.ingestion.files import ValidatedFile
from app.services.ingestion.renderer import DocumentRenderer
from app.services.ocr.base import OCREngine, OCRToken
from app.services.preprocessing.image import ImagePreprocessor
from app.services.preprocessing.quality import ImageQualityAnalyzer
from app.services.storage.supabase import SupabaseStorage


class PrescriptionProcessingService:
    def __init__(
        self,
        repository: ProcessingRepository,
        storage: SupabaseStorage,
        renderer: DocumentRenderer,
        quality: ImageQualityAnalyzer,
        preprocessor: ImagePreprocessor,
        ocr: OCREngine,
        htr: HTREngine,
    ) -> None:
        self.repository = repository
        self.storage = storage
        self.renderer = renderer
        self.quality = quality
        self.preprocessor = preprocessor
        self.ocr = ocr
        self.htr = htr

    async def process(
        self,
        prescription: dict[str, Any],
        source: ValidatedFile,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        prescription_id = UUID(prescription["id"])
        organization_id = UUID(prescription["organization_id"])
        job = await self._start_job(
            organization_id,
            prescription_id,
            "DOCUMENT_PROCESSING",
            f"{idempotency_key}:document" if idempotency_key else f"document:{uuid4()}",
        )
        started = time.perf_counter()
        try:
            existing_pages_list = await self.repository.pages(prescription_id)
            existing_pages = {p["page_number"]: p for p in existing_pages_list}
            pages = self.renderer.render(source)
            for rendered in pages:
                await self._process_page(
                    organization_id,
                    prescription_id,
                    rendered,
                    existing_pages.get(rendered.page_number),
                )
            elapsed = int((time.perf_counter() - started) * 1000)
            await self.repository.update_prescription(
                prescription_id, {"status": "REVIEW_REQUIRED", "page_count": len(pages)}
            )
            await self.repository.finish_job(
                UUID(job["id"]),
                {
                    "status": "COMPLETED",
                    "completed_at": datetime.now(UTC).isoformat(),
                    "processing_ms": elapsed,
                    "metadata": {
                        "page_count": len(pages),
                        "ocr_provider": self.ocr.name,
                        "htr_provider": self.htr.name,
                    },
                },
            )
            return {"prescription_id": str(prescription_id), "status": "REVIEW_REQUIRED"}
        except AppError as error:
            await self._fail_job(UUID(job["id"]), prescription_id, error)
            raise
        except Exception as error:
            wrapped = AppError("PROCESSING_FAILED", "Document processing failed safely.", 500)
            await self._fail_job(UUID(job["id"]), prescription_id, wrapped)
            raise wrapped from error

    async def resume_ocr(
        self,
        prescription: dict[str, Any],
        pages: list[dict[str, Any]],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        prescription_id = UUID(prescription["id"])
        organization_id = UUID(prescription["organization_id"])
        job = await self._start_job(
            organization_id,
            prescription_id,
            "OCR_RETRY",
            f"{idempotency_key}:ocr-retry" if idempotency_key else f"ocr-retry:{uuid4()}",
        )
        started = time.perf_counter()
        try:
            for page in pages:
                path = page.get("processed_image_path") or page["original_image_path"]
                content = await self.storage.download(
                    "prescription-derived", path, str(organization_id)
                )
                result = self.ocr.extract(content)
                await self._persist_result(
                    organization_id,
                    prescription_id,
                    UUID(page["id"]),
                    result.provider,
                    result.provider_version,
                    result.raw_text,
                    result.confidence,
                    result.processing_ms,
                    result.tokens,
                    result.metadata,
                )
            elapsed = int((time.perf_counter() - started) * 1000)
            await self.repository.update_prescription(
                prescription_id, {"status": "REVIEW_REQUIRED"}
            )
            await self.repository.finish_job(
                UUID(job["id"]),
                {
                    "status": "COMPLETED",
                    "completed_at": datetime.now(UTC).isoformat(),
                    "processing_ms": elapsed,
                },
            )
            return {"prescription_id": str(prescription_id), "status": "OCR_READY"}
        except AppError as error:
            await self._fail_job(UUID(job["id"]), prescription_id, error)
            raise

    async def _process_page(
        self,
        organization_id: UUID,
        prescription_id: UUID,
        rendered,
        existing_page: dict[str, Any] | None = None,
    ) -> None:
        quality = self.quality.analyze(rendered.png_bytes)
        try:
            processed = self.preprocessor.process(rendered.png_bytes, quality)
        except ValueError:
            processed = None

        base = f"{organization_id}/{prescription_id}/pages/page-{rendered.page_number:03d}"
        original_path = f"{base}-original.png"
        await self.storage.upload(
            "prescription-derived",
            original_path,
            rendered.png_bytes,
            "image/png",
            str(organization_id),
            upsert=True,
        )
        processed_path = None
        ocr_input = rendered.png_bytes
        operations: list[str] = []
        if processed:
            processed_path = f"{base}-processed.png"
            ocr_input = processed.png_bytes
            operations = processed.operations
            await self.storage.upload(
                "prescription-derived",
                processed_path,
                processed.png_bytes,
                "image/png",
                str(organization_id),
                upsert=True,
            )

        page_data = {
            "organization_id": str(organization_id),
            "prescription_id": str(prescription_id),
            "page_number": rendered.page_number,
            "original_image_path": original_path,
            "processed_image_path": processed_path,
            "width": rendered.width,
            "height": rendered.height,
            "quality_metadata": quality.as_dict(),
            "preprocessing_applied": operations,
            "status": "OCR_RUNNING",
        }
        if existing_page:
            page_id = UUID(existing_page["id"])
            await self.repository.update_page(page_id, page_data)
        else:
            page = await self.repository.create_page(page_data)
            page_id = UUID(page["id"])
        if rendered.supplemental_text:
            supplemental_tokens = [
                OCRToken(token, None, None, index)
                for index, token in enumerate(rendered.supplemental_text.split())
            ]
            await self._persist_result(
                organization_id,
                prescription_id,
                page_id,
                "pdf_text",
                None,
                rendered.supplemental_text,
                None,
                0,
                supplemental_tokens,
                {"supplemental": True},
            )

        ocr_result = self.ocr.extract(ocr_input)
        await self._persist_result(
            organization_id,
            prescription_id,
            page_id,
            ocr_result.provider,
            ocr_result.provider_version,
            ocr_result.raw_text,
            ocr_result.confidence,
            ocr_result.processing_ms,
            ocr_result.tokens,
            ocr_result.metadata,
        )
        # HTR is optional. Health state is persisted in OCR metadata without crashing printed OCR.
        htr_health = self.htr.health()
        await self.repository.update_prescription(
            prescription_id,
            {"status": "REVIEW_REQUIRED" if not htr_health.get("configured") else "HTR_RUNNING"},
        )

    async def _persist_result(
        self,
        organization_id: UUID,
        prescription_id: UUID,
        page_id: UUID,
        provider: str,
        provider_version: str | None,
        raw_text: str,
        confidence: float | None,
        processing_ms: int,
        tokens: list[OCRToken],
        metadata: dict[str, Any],
    ) -> None:
        await self.repository.create_ocr_result(
            {
                "organization_id": str(organization_id),
                "prescription_id": str(prescription_id),
                "page_id": str(page_id),
                "provider": provider,
                "provider_version": provider_version,
                "raw_text": raw_text,
                "confidence": confidence,
                "processing_ms": processing_ms,
                "metadata": metadata,
            },
            [
                {
                    "organization_id": str(organization_id),
                    "prescription_id": str(prescription_id),
                    "page_id": str(page_id),
                    "text": token.text,
                    "confidence": token.confidence,
                    "bbox": asdict(token.bbox) if token.bbox else None,
                    "sequence_index": token.sequence_index,
                    "source": "pdf_text" if provider == "pdf_text" else "ocr",
                }
                for token in tokens
            ],
        )

    async def _start_job(
        self,
        organization_id: UUID,
        prescription_id: UUID,
        stage: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        return await self.repository.create_job(
            {
                "organization_id": str(organization_id),
                "prescription_id": str(prescription_id),
                "stage": stage,
                "status": "RUNNING",
                "attempt": 1,
                "idempotency_key": idempotency_key,
                "metadata": {
                    "ocr_provider": self.ocr.name,
                    "htr_provider": self.htr.name,
                },
            }
        )

    async def _fail_job(
        self, job_id: UUID, prescription_id: UUID, error: AppError
    ) -> None:
        await self.repository.finish_job(
            job_id,
            {
                "status": "FAILED",
                "completed_at": datetime.now(UTC).isoformat(),
                "error_code": error.code,
                "safe_error_message": error.message,
            },
        )
        await self.repository.update_prescription(prescription_id, {"status": error.code})
