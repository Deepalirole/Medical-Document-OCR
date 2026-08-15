from typing import Annotated

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.repositories.processing import ProcessingRepository
from app.repositories.supabase.client import SupabaseAdminClient
from app.repositories.supabase.processing import SupabaseProcessingRepository
from app.services.extraction.pipeline import ExtractionService
from app.services.htr.base import HTREngine
from app.services.htr.unconfigured import UnconfiguredHTREngine
from app.services.ingestion.renderer import DocumentRenderer
from app.services.llm.base import LLMProvider
from app.services.llm.openrouter import OpenRouterProvider
from app.services.ocr.base import OCREngine
from app.services.ocr.tesseract import TesseractEngine
from app.services.preprocessing.image import ImagePreprocessor
from app.services.preprocessing.quality import ImageQualityAnalyzer
from app.services.processing.pipeline import PrescriptionProcessingService
from app.services.storage.supabase import SupabaseStorage


def get_processing_repository(settings: Settings = Depends(get_settings)) -> ProcessingRepository:
    return SupabaseProcessingRepository(SupabaseAdminClient(settings))


def get_storage(settings: Settings = Depends(get_settings)) -> SupabaseStorage:
    return SupabaseStorage(settings)


def get_ocr_engine(settings: Settings = Depends(get_settings)) -> OCREngine:
    return TesseractEngine(settings.tesseract_cmd)


def get_htr_engine() -> HTREngine:
    return UnconfiguredHTREngine()


def get_llm_provider(settings: Settings = Depends(get_settings)) -> LLMProvider:
    return OpenRouterProvider(
        settings.openrouter_api_key.get_secret_value(),
        settings.openrouter_model,
        settings.openrouter_timeout_seconds,
        settings.openrouter_max_tokens,
        settings.openrouter_retries,
    )


def get_extraction_service(
    repository: ProcessingRepository = Depends(get_processing_repository),
    provider: LLMProvider = Depends(get_llm_provider),
) -> ExtractionService:
    return ExtractionService(repository, provider)


def get_processing_service(
    repository: ProcessingRepository = Depends(get_processing_repository),
    storage: SupabaseStorage = Depends(get_storage),
    ocr: OCREngine = Depends(get_ocr_engine),
    htr: HTREngine = Depends(get_htr_engine),
) -> PrescriptionProcessingService:
    return PrescriptionProcessingService(
        repository,
        storage,
        DocumentRenderer(),
        ImageQualityAnalyzer(),
        ImagePreprocessor(),
        ocr,
        htr,
    )


ProcessingRepoDep = Annotated[ProcessingRepository, Depends(get_processing_repository)]
StorageDep = Annotated[SupabaseStorage, Depends(get_storage)]
ProcessingServiceDep = Annotated[PrescriptionProcessingService, Depends(get_processing_service)]
ExtractionServiceDep = Annotated[ExtractionService, Depends(get_extraction_service)]
