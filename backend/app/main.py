from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.approvals import router as approvals_router
from app.api.assistance import router as assistance_router
from app.api.dependencies import build_worker_pool
from app.api.feedback import router as feedback_router
from app.api.foundation import router as foundation_router
from app.api.integrations import router as integrations_router
from app.api.operations import router as operations_router
from app.api.prescriptions import router as prescriptions_router
from app.api.realtime import router as realtime_router
from app.api.review import router as review_router
from app.api.schemas import router as schemas_router
from app.api.workers import router as workers_router
from app.core.config import get_settings
from app.core.errors import AppError, app_error_handler
from app.core.logging import RequestLoggingMiddleware, configure_logging


@asynccontextmanager
async def lifespan(_: FastAPI):
    current = get_settings()
    pool = build_worker_pool(current)
    if current.worker_pool_enabled:
        await pool.start()
    try:
        yield
    finally:
        await pool.stop()


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
app.include_router(integrations_router, prefix=settings.api_prefix)
app.include_router(assistance_router, prefix=settings.api_prefix)
app.include_router(feedback_router, prefix=settings.api_prefix)
app.include_router(approvals_router, prefix=settings.api_prefix)
app.include_router(workers_router, prefix=settings.api_prefix)
app.include_router(realtime_router, prefix=settings.api_prefix)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "prescription-ocr-api"}
