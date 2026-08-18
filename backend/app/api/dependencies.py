from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.repositories.processing import ProcessingRepository
from app.repositories.supabase.client import SupabaseAdminClient
from app.repositories.supabase.processing import SupabaseProcessingRepository
from app.services.assistance.medicines import MedicineDictionary
from app.services.extraction.pipeline import ExtractionService
from app.services.htr.base import HTREngine
from app.services.htr.trocr import TrOCREngine
from app.services.htr.unconfigured import UnconfiguredHTREngine
from app.services.ingestion.renderer import DocumentRenderer
from app.services.integrations.base import HMISConnector
from app.services.integrations.fhir import FHIREMRConnector
from app.services.integrations.medikunj_supabase import MedikunjSupabaseConnector
from app.services.integrations.unconfigured import UnconfiguredHMISConnector
from app.services.llm.base import LLMProvider
from app.services.llm.openrouter import OpenRouterProvider
from app.services.ocr.base import OCREngine
from app.services.ocr.cloud import (
    AzureDocumentIntelligenceOCREngine,
    GoogleVisionOCREngine,
)
from app.services.ocr.paddle import PaddleOCREngine
from app.services.ocr.tesseract import TesseractEngine
from app.services.preprocessing.image import ImagePreprocessor
from app.services.preprocessing.quality import ImageQualityAnalyzer
from app.services.processing.pipeline import PrescriptionProcessingService
from app.services.storage.supabase import SupabaseStorage
from app.services.workers.pool import BackgroundWorkerPool


def get_processing_repository(settings: Settings = Depends(get_settings)) -> ProcessingRepository:
    return SupabaseProcessingRepository(SupabaseAdminClient(settings))


def get_storage(settings: Settings = Depends(get_settings)) -> SupabaseStorage:
    return SupabaseStorage(settings)


def get_ocr_engine(settings: Settings = Depends(get_settings)) -> OCREngine:
    if settings.ocr_provider == "paddleocr":
        return PaddleOCREngine(
            settings.paddleocr_language,
            settings.paddleocr_angle_classification,
        )
    if settings.ocr_provider == "google_vision":
        return GoogleVisionOCREngine(
            settings.google_vision_api_key.get_secret_value(),
            settings.google_vision_language_hints,
            settings.cloud_ocr_timeout_seconds,
            settings.cloud_ocr_retries,
        )
    if settings.ocr_provider == "azure_document_intelligence":
        return AzureDocumentIntelligenceOCREngine(
            settings.azure_ocr_endpoint,
            settings.azure_ocr_api_key.get_secret_value(),
            settings.azure_ocr_model,
            settings.cloud_ocr_timeout_seconds,
            settings.cloud_ocr_retries,
        )
    return TesseractEngine(settings.tesseract_cmd)


def get_htr_engine(settings: Settings = Depends(get_settings)) -> HTREngine:
    if settings.htr_provider == "trocr":
        return TrOCREngine(settings.htr_model, settings.htr_max_new_tokens)
    return UnconfiguredHTREngine()


def get_hmis_connector(settings: Settings = Depends(get_settings)) -> HMISConnector:
    if settings.hmis_provider == "medikunj_supabase":
        return MedikunjSupabaseConnector(
            settings.hmis_base_url,
            settings.hmis_service_key.get_secret_value(),
            settings.hmis_branch_id,
            settings.hmis_timeout_seconds,
            settings.hmis_retries,
        )
    return UnconfiguredHMISConnector()


def get_emr_connector(settings: Settings = Depends(get_settings)) -> HMISConnector:
    """The EMR destination. An unset provider yields an inert, explicitly unconfigured FHIR
    connector rather than a silently disabled one."""
    if settings.emr_provider == "fhir":
        return FHIREMRConnector(
            settings.emr_base_url,
            settings.emr_api_key.get_secret_value(),
            settings.emr_timeout_seconds,
            settings.emr_retries,
        )
    return FHIREMRConnector("")


def get_llm_provider(settings: Settings = Depends(get_settings)) -> LLMProvider:
    return OpenRouterProvider(
        settings.openrouter_api_key.get_secret_value(),
        settings.openrouter_model,
        settings.openrouter_timeout_seconds,
        settings.openrouter_max_tokens,
        settings.openrouter_retries,
        settings.openrouter_prompt_version or None,
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


_worker_pool: BackgroundWorkerPool | None = None


def build_worker_pool(settings: Settings) -> BackgroundWorkerPool:
    """Create the process-wide pool. Called once from the application lifespan."""
    global _worker_pool
    _worker_pool = BackgroundWorkerPool(
        settings.worker_pool_concurrency, settings.worker_pool_max_queue
    )
    return _worker_pool


def get_worker_pool() -> BackgroundWorkerPool:
    if _worker_pool is None:
        raise AppError(
            "WORKER_POOL_NOT_RUNNING", "The background worker pool is not running.", 503
        )
    return _worker_pool


@lru_cache(maxsize=4)
def _medicine_dictionary(extra_path: str) -> MedicineDictionary:
    return MedicineDictionary(extra_path=extra_path)


def get_medicine_dictionary(settings: Settings = Depends(get_settings)) -> MedicineDictionary:
    return _medicine_dictionary(settings.medicine_dictionary_path)


EMRConnectorDep = Annotated[HMISConnector, Depends(get_emr_connector)]
HMISConnectorDep = Annotated[HMISConnector, Depends(get_hmis_connector)]
MedicineDictionaryDep = Annotated[MedicineDictionary, Depends(get_medicine_dictionary)]
WorkerPoolDep = Annotated[BackgroundWorkerPool, Depends(get_worker_pool)]
ProcessingRepoDep = Annotated[ProcessingRepository, Depends(get_processing_repository)]
StorageDep = Annotated[SupabaseStorage, Depends(get_storage)]
ProcessingServiceDep = Annotated[PrescriptionProcessingService, Depends(get_processing_service)]
ExtractionServiceDep = Annotated[ExtractionService, Depends(get_extraction_service)]
