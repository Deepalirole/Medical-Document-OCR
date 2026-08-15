from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, File, Form, Header, Query, UploadFile, status

from app.api.dependencies import (
    ExtractionServiceDep,
    ProcessingRepoDep,
    ProcessingServiceDep,
    StorageDep,
)
from app.core.auth import AuthDep, RepoDep
from app.core.config import get_settings
from app.core.errors import AppError
from app.models.prescriptions import (
    OCRResponse,
    OCRResultResponse,
    OCRTokenResponse,
    PageResponse,
    PrescriptionDetail,
    PrescriptionResponse,
    ProcessingJobResponse,
    ProcessingStatusResponse,
)
from app.services.ingestion.files import FileValidator
from app.services.ingestion.pipeline import PrescriptionRegistrationService

router = APIRouter(prefix="/prescriptions", tags=["prescriptions"])


async def require_prescription(prescription_id: UUID, repository: RepoDep) -> dict:
    prescription = await repository.prescription_for_user(prescription_id)
    if not prescription:
        raise AppError("PRESCRIPTION_NOT_FOUND", "Prescription not found.", 404)
    return prescription


@router.post("", response_model=PrescriptionResponse, status_code=status.HTTP_201_CREATED)
async def upload_prescription(
    auth: AuthDep,
    user_repository: RepoDep,
    processing_repository: ProcessingRepoDep,
    storage: StorageDep,
    organization_id: Annotated[UUID, Form()],
    schema_id: Annotated[UUID, Form()],
    file: Annotated[UploadFile, File()],
) -> PrescriptionResponse:
    await user_repository.assert_membership(auth.user_id, organization_id)
    schema = await user_repository.schema_for_user(schema_id)
    if not schema or UUID(schema["organization_id"]) != organization_id:
        raise AppError("SCHEMA_NOT_FOUND", "The selected organization schema was not found.", 404)

    settings = get_settings()
    content = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    source = FileValidator(settings.max_upload_mb, settings.max_pdf_pages).validate(
        file.filename or "upload", file.content_type, content
    )
    registered = await PrescriptionRegistrationService(
        processing_repository, storage
    ).register(source, organization_id, schema_id, auth.user_id)
    return PrescriptionResponse.model_validate(registered)


@router.post("/{prescription_id}/process")
async def process_prescription(
    prescription_id: UUID,
    user_repository: RepoDep,
    storage: StorageDep,
    processing: ProcessingServiceDep,
    extraction: ExtractionServiceDep,
    processing_repository: ProcessingRepoDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    prescription = await require_prescription(prescription_id, user_repository)
    if await processing_repository.fields(prescription_id):
        return {
            "prescription_id": str(prescription_id),
            "status": prescription["status"],
            "idempotent": True,
        }
    ocr_rows = await processing_repository.ocr_results(prescription_id, include_tokens=False)
    if not ocr_rows:
        pages = await processing_repository.pages(prescription_id)
        if pages:
            await processing.resume_ocr(prescription, pages, idempotency_key)
        else:
            organization_id = str(prescription["organization_id"])
            content = await storage.download(
                "prescription-source", prescription["source_storage_path"], organization_id
            )
            settings = get_settings()
            source = FileValidator(settings.max_upload_mb, settings.max_pdf_pages).validate(
                prescription["original_filename"], prescription["source_mime_type"], content
            )
            await processing.process(prescription, source, idempotency_key)
    return await extraction.extract(prescription, idempotency_key)


@router.get("/{prescription_id}", response_model=PrescriptionDetail)
async def prescription_detail(
    prescription_id: UUID,
    user_repository: RepoDep,
    processing_repository: ProcessingRepoDep,
    storage: StorageDep,
) -> PrescriptionDetail:
    prescription = await require_prescription(prescription_id, user_repository)
    organization_id = str(prescription["organization_id"])
    page_rows = await processing_repository.pages(prescription_id)
    pages: list[PageResponse] = []
    for row in page_rows:
        path = row.get("processed_image_path") or row["original_image_path"]
        preview_url = await storage.create_signed_url("prescription-derived", path, organization_id)
        pages.append(PageResponse.model_validate({**row, "preview_url": preview_url}))
    return PrescriptionDetail.model_validate({**prescription, "pages": pages})


@router.get("/{prescription_id}/status", response_model=ProcessingStatusResponse)
async def prescription_status(
    prescription_id: UUID,
    user_repository: RepoDep,
    processing_repository: ProcessingRepoDep,
) -> ProcessingStatusResponse:
    prescription = await require_prescription(prescription_id, user_repository)
    jobs = await processing_repository.jobs(prescription_id)
    return ProcessingStatusResponse(
        prescription_id=prescription_id,
        status=prescription["status"],
        jobs=[ProcessingJobResponse.model_validate(job) for job in jobs],
    )


@router.get("/{prescription_id}/ocr", response_model=OCRResponse)
async def prescription_ocr(
    prescription_id: UUID,
    user_repository: RepoDep,
    processing_repository: ProcessingRepoDep,
    include_tokens: Annotated[bool, Query()] = False,
) -> OCRResponse:
    await require_prescription(prescription_id, user_repository)
    rows = await processing_repository.ocr_results(
        prescription_id, include_tokens=include_tokens
    )
    results = []
    for row in rows:
        tokens = [
            OCRTokenResponse.model_validate(token) for token in row.pop("ocr_tokens", [])
        ]
        results.append(OCRResultResponse.model_validate({**row, "tokens": tokens}))
    return OCRResponse(prescription_id=prescription_id, results=results)
