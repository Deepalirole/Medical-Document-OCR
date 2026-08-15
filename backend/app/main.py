from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.foundation import router as foundation_router
from app.api.operations import router as operations_router
from app.api.prescriptions import router as prescriptions_router
from app.api.review import router as review_router
from app.api.schemas import router as schemas_router
from app.core.config import get_settings
from app.core.errors import AppError, app_error_handler
from app.core.logging import RequestLoggingMiddleware, configure_logging


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_settings()
    yield


settings = get_settings()
configure_logging()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Organization-Id", "Idempotency-Key"],
)
app.add_exception_handler(AppError, app_error_handler)
app.include_router(foundation_router, prefix=settings.api_prefix)
app.include_router(prescriptions_router, prefix=settings.api_prefix)
app.include_router(schemas_router, prefix=settings.api_prefix)
app.include_router(review_router, prefix=settings.api_prefix)
app.include_router(operations_router, prefix=settings.api_prefix)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "prescription-ocr-api"}
