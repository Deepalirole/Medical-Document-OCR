"""Realtime processing progress over server-sent events."""

import asyncio
import time
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.dependencies import ProcessingRepoDep
from app.core.auth import AuthDep, RepoDep
from app.core.config import get_settings
from app.core.errors import AppError
from app.services.realtime.progress import progress_events

router = APIRouter(tags=["realtime"])


@router.get("/prescriptions/{prescription_id}/progress-stream")
async def progress_stream(
    prescription_id: UUID,
    auth: AuthDep,
    repository: RepoDep,
    processing_repository: ProcessingRepoDep,
) -> StreamingResponse:
    prescription = await repository.prescription_for_user(prescription_id)
    if not prescription:
        raise AppError("PRESCRIPTION_NOT_FOUND", "Prescription not found.", 404)
    organization_id = UUID(str(prescription["organization_id"]))
    await repository.assert_membership(auth.user_id, organization_id)
    settings = get_settings()

    async def fetch_state():
        return await processing_repository.get_prescription(prescription_id, organization_id)

    stream = progress_events(
        fetch_state,
        sleep=asyncio.sleep,
        clock=time.monotonic,
        poll_interval=settings.progress_poll_seconds,
        max_seconds=settings.progress_max_seconds,
    )
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
