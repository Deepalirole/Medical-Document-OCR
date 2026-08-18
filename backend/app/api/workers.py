"""Asynchronous processing endpoints backed by the background worker pool.

The synchronous ``POST /api/prescriptions/{id}/process`` route is unchanged. These routes are
an additional entry point for callers that would rather not hold a request open for the whole
render/OCR/extract cycle.
"""

from uuid import UUID

from fastapi import APIRouter, Header, Response

from app.api.dependencies import (
    ExtractionServiceDep,
    ProcessingRepoDep,
    ProcessingServiceDep,
    StorageDep,
    WorkerPoolDep,
)
from app.core.auth import AuthDep, RepoDep
from app.core.config import get_settings
from app.core.errors import AppError
from app.models.workers import JobStateResponse, WorkerPoolStatus
from app.services.ingestion.files import FileValidator

router = APIRouter(tags=["workers"])


def job_key(prescription_id: UUID) -> str:
    return f"process:{prescription_id}"


@router.post("/prescriptions/{prescription_id}/process-async", response_model=JobStateResponse)
async def process_async(
    prescription_id: UUID,
    response: Response,
    auth: AuthDep,
    repository: RepoDep,
    processing_repository: ProcessingRepoDep,
    processing: ProcessingServiceDep,
    extraction: ExtractionServiceDep,
    storage: StorageDep,
    pool: WorkerPoolDep,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JobStateResponse:
    prescription = await repository.prescription_for_user(prescription_id)
    if not prescription:
        raise AppError("PRESCRIPTION_NOT_FOUND", "Prescription not found.", 404)
    await repository.assert_membership(
        auth.user_id, UUID(str(prescription["organization_id"]))
    )

    async def run() -> None:
        row = await processing_repository.get_prescription(
            prescription_id, UUID(str(prescription["organization_id"]))
        )
        target = row or prescription
        if not await processing_repository.ocr_results(prescription_id, include_tokens=False):
            pages = await processing_repository.pages(prescription_id)
            if pages:
                await processing.resume_ocr(target, pages, idempotency_key)
            else:
                settings = get_settings()
                content = await storage.download(
                    "prescription-source",
                    target["source_storage_path"],
                    str(target["organization_id"]),
                )
                source = FileValidator(
                    settings.max_upload_mb, settings.max_pdf_pages
                ).validate(
                    target["original_filename"], target["source_mime_type"], content
                )
                await processing.process(target, source, idempotency_key)
        await extraction.extract(target, idempotency_key)

    record = pool.submit(job_key(prescription_id), run)
    response.status_code = 202
    return JobStateResponse(prescription_id=str(prescription_id), **record.to_dict())


@router.get("/prescriptions/{prescription_id}/process-async", response_model=JobStateResponse)
async def process_async_status(
    prescription_id: UUID,
    auth: AuthDep,
    repository: RepoDep,
    pool: WorkerPoolDep,
) -> JobStateResponse:
    prescription = await repository.prescription_for_user(prescription_id)
    if not prescription:
        raise AppError("PRESCRIPTION_NOT_FOUND", "Prescription not found.", 404)
    await repository.assert_membership(
        auth.user_id, UUID(str(prescription["organization_id"]))
    )
    record = pool.get(job_key(prescription_id))
    if record is None:
        raise AppError("JOB_NOT_FOUND", "No background job exists for this prescription.", 404)
    return JobStateResponse(prescription_id=str(prescription_id), **record.to_dict())


@router.get("/admin/worker-pool", response_model=WorkerPoolStatus)
async def worker_pool_status(
    organization_id: UUID,
    auth: AuthDep,
    repository: RepoDep,
    pool: WorkerPoolDep,
) -> WorkerPoolStatus:
    await repository.assert_membership(auth.user_id, organization_id, {"admin"})
    return WorkerPoolStatus.model_validate(pool.status())
