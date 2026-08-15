import asyncio
from io import BytesIO
from uuid import UUID, uuid4

import fitz
import pytest
from PIL import Image, ImageDraw

from app.core.errors import AppError
from app.services.htr.unconfigured import UnconfiguredHTREngine
from app.services.ingestion.files import FileValidator
from app.services.ingestion.renderer import DocumentRenderer
from app.services.ocr.base import BoundingBox, OCRDocumentResult, OCRToken
from app.services.ocr.normalizer import normalize_evidence
from app.services.preprocessing.image import ImagePreprocessor
from app.services.preprocessing.quality import ImageQualityAnalyzer
from app.services.processing.pipeline import PrescriptionProcessingService

ORG_ID = UUID("22222222-2222-4222-8222-222222222222")
PRESCRIPTION_ID = UUID("44444444-4444-4444-8444-444444444444")


def sample_png(width: int = 800, height: int = 1100) -> bytes:
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((80, 100), "Patient: Evidence Test", fill="black")
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def sample_pdf(page_count: int = 2) -> bytes:
    document = fitz.open()
    for number in range(page_count):
        page = document.new_page()
        page.insert_text((72, 72), f"Prescription page {number + 1}")
    content = document.tobytes()
    document.close()
    return content


def test_validates_image_and_rejects_mime_mismatch():
    validator = FileValidator(max_upload_mb=2, max_pdf_pages=4)
    result = validator.validate("scan.png", "image/png", sample_png())
    assert result.source_type == "image"
    assert result.page_count == 1
    assert len(result.sha256) == 64
    with pytest.raises(AppError) as error:
        validator.validate("scan.png", "application/pdf", sample_png())
    assert error.value.code == "FILE_MIME_MISMATCH"


def test_validates_and_renders_multipage_pdf_with_text_evidence():
    source = FileValidator(2, 4).validate("scan.pdf", "application/pdf", sample_pdf())
    pages = DocumentRenderer(dpi=100).render(source)
    assert len(pages) == 2
    assert pages[0].page_number == 1
    assert pages[0].supplemental_text == "Prescription page 1"
    assert pages[1].width > 0 and pages[1].height > 0


def test_rejects_corrupt_and_excess_page_files():
    validator = FileValidator(2, 1)
    with pytest.raises(AppError) as corrupt:
        validator.validate("bad.pdf", "application/pdf", b"not-a-pdf")
    assert corrupt.value.code == "FILE_CORRUPT"
    with pytest.raises(AppError) as pages:
        validator.validate("large.pdf", "application/pdf", sample_pdf(2))
    assert pages.value.code == "PDF_TOO_MANY_PAGES"


def test_quality_and_preprocessing_are_deterministic():
    content = sample_png(500, 700)
    analyzer = ImageQualityAnalyzer()
    report = analyzer.analyze(content)
    first = ImagePreprocessor().process(content, report)
    second = ImagePreprocessor().process(content, report)
    assert first.png_bytes == second.png_bytes
    assert first.operations == second.operations
    assert "grayscale" in first.operations
    assert report.width == 500


def test_normalizer_preserves_real_confidence_and_bbox():
    result = OCRDocumentResult(
        provider="test",
        provider_version="1",
        raw_text="Evidence",
        confidence=0.8,
        processing_ms=2,
        tokens=[OCRToken("Evidence", 0.8, BoundingBox(1, 2, 3, 4), 0)],
        metadata={},
    )
    evidence = normalize_evidence(result, PRESCRIPTION_ID, uuid4(), 1, "ocr")
    assert evidence[0]["confidence"] == 0.8
    assert evidence[0]["bbox"] == {"x1": 1, "y1": 2, "x2": 3, "y2": 4}


def test_unconfigured_htr_degrades_explicitly():
    engine = UnconfiguredHTREngine()
    assert engine.health()["status"] == "HTR_NOT_CONFIGURED"
    with pytest.raises(AppError) as error:
        engine.extract(sample_png())
    assert error.value.code == "HTR_NOT_CONFIGURED"


class FakeOCR:
    name = "test-ocr"

    def health(self):
        return {"configured": True}

    def extract(self, png_bytes: bytes) -> OCRDocumentResult:
        assert png_bytes
        return OCRDocumentResult(
            provider=self.name,
            provider_version="1",
            raw_text="Patient Evidence",
            confidence=0.75,
            processing_ms=3,
            tokens=[OCRToken("Patient", 0.75, None, 0), OCRToken("Evidence", 0.75, None, 1)],
            metadata={},
        )


class FakeStorage:
    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}

    async def upload(self, bucket, path, content, content_type, organization_id, upsert=False):
        assert path.startswith(organization_id)
        assert content_type == "image/png"
        self.objects[(bucket, path)] = content

    async def download(self, bucket, path, organization_id):
        assert path.startswith(organization_id)
        return self.objects[(bucket, path)]


class FakeProcessingRepository:
    def __init__(self):
        self.pages_data = []
        self.jobs_data = []
        self.ocr_data = []
        self.prescription_updates = []

    async def create_job(self, data):
        row = {**data, "id": str(uuid4())}
        self.jobs_data.append(row)
        return row

    async def finish_job(self, job_id, data):
        self.jobs_data[-1].update(data)

    async def update_prescription(self, prescription_id, data):
        self.prescription_updates.append(data)

    async def create_page(self, data):
        row = {**data, "id": str(uuid4())}
        self.pages_data.append(row)
        return row

    async def update_page(self, page_id, data):
        for p in self.pages_data:
            if p["id"] == str(page_id):
                p.update(data)

    async def pages(self, prescription_id):
        return [p for p in self.pages_data if p.get("prescription_id") == str(prescription_id)]

    async def create_ocr_result(self, result, tokens):
        row = {**result, "id": str(uuid4()), "tokens": tokens}
        self.ocr_data.append(row)
        return row


def test_processing_pipeline_preserves_lineage_and_raw_ocr():
    repository = FakeProcessingRepository()
    storage = FakeStorage()
    service = PrescriptionProcessingService(
        repository,
        storage,
        DocumentRenderer(dpi=100),
        ImageQualityAnalyzer(),
        ImagePreprocessor(),
        FakeOCR(),
        UnconfiguredHTREngine(),
    )
    source = FileValidator(2, 4).validate("scan.png", "image/png", sample_png())
    prescription = {"id": str(PRESCRIPTION_ID), "organization_id": str(ORG_ID)}
    result = asyncio.run(service.process(prescription, source))
    assert result["status"] == "REVIEW_REQUIRED"
    assert repository.pages_data[0]["page_number"] == 1
    assert repository.ocr_data[0]["raw_text"] == "Patient Evidence"
    assert repository.ocr_data[0]["tokens"][0]["confidence"] == 0.75
    assert repository.jobs_data[0]["status"] == "COMPLETED"
    assert len(storage.objects) == 2


def test_resume_ocr_restores_prescription_to_review_required():
    repository = FakeProcessingRepository()
    storage = FakeStorage()
    path = f"{ORG_ID}/{PRESCRIPTION_ID}/pages/page-001-processed.png"
    storage.objects[("prescription-derived", path)] = sample_png()
    service = PrescriptionProcessingService(
        repository,
        storage,
        DocumentRenderer(dpi=100),
        ImageQualityAnalyzer(),
        ImagePreprocessor(),
        FakeOCR(),
        UnconfiguredHTREngine(),
    )
    prescription = {"id": str(PRESCRIPTION_ID), "organization_id": str(ORG_ID)}
    pages = [{"id": str(uuid4()), "processed_image_path": path, "original_image_path": path}]

    result = asyncio.run(service.resume_ocr(prescription, pages))

    assert result["status"] == "OCR_READY"
    assert repository.prescription_updates[-1] == {"status": "REVIEW_REQUIRED"}
    assert repository.jobs_data[-1]["status"] == "COMPLETED"
