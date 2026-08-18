"""Server-sent progress events for a processing prescription.

The reviewer UI otherwise polls ``GET /prescriptions/{id}``; this turns that into a push
stream. The generator is deliberately independent of FastAPI so the event sequence can be
tested directly.

Bounded by construction: the stream stops at a terminal status, stops at ``max_seconds``, and
emits a heartbeat comment when nothing changes so an idle connection is not culled by a proxy
that cannot distinguish "slow" from "dead".
"""

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

StateFetcher = Callable[[], Awaitable[dict[str, Any]]]
Sleeper = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]

# Ordered pipeline stages. Progress is the index of the current stage, so the client gets a
# monotonic fraction without the server inventing a percentage.
STAGE_ORDER = [
    "UPLOADED",
    "VALIDATING_FILE",
    "REGISTERING_DOCUMENT",
    "ROUTING_FILE",
    "RENDERING",
    "ANALYZING_IMAGE",
    "PREPROCESSING",
    "OCR_READY",
    "OCR_RUNNING",
    "HTR_RUNNING",
    "EXTRACTION_RUNNING",
    "FIELD_MAPPING",
    "VALIDATING",
    "REVIEW_REQUIRED",
    "APPROVED",
    "COMPLETED",
]

TERMINAL_STATUSES = {
    "REVIEW_REQUIRED",
    "APPROVED",
    "COMPLETED",
    "LLM_FAILED",
    "OCR_FAILED",
    "FAILED",
}
FAILURE_STATUSES = {"LLM_FAILED", "OCR_FAILED", "FAILED"}


@dataclass(frozen=True)
class ProgressEvent:
    event: str
    data: dict[str, Any]

    def render(self) -> str:
        payload = json.dumps(self.data, ensure_ascii=False, sort_keys=True)
        return f"event: {self.event}\ndata: {payload}\n\n"


def progress_fraction(status: str) -> float:
    if status in FAILURE_STATUSES:
        return 1.0
    try:
        index = STAGE_ORDER.index(status)
    except ValueError:
        return 0.0
    return round((index + 1) / len(STAGE_ORDER), 4)


def build_event(state: dict[str, Any]) -> ProgressEvent:
    status = str(state.get("status", ""))
    return ProgressEvent(
        event="failed" if status in FAILURE_STATUSES else "progress",
        data={
            "prescription_id": str(state.get("id", "")),
            "status": status,
            "progress": progress_fraction(status),
            "terminal": status in TERMINAL_STATUSES,
            "page_count": state.get("page_count"),
            "error_code": state.get("error_code"),
        },
    )


async def progress_events(
    fetch_state: StateFetcher,
    *,
    sleep: Sleeper,
    clock: Clock,
    poll_interval: float = 1.0,
    max_seconds: float = 300.0,
    heartbeat_after: float = 15.0,
) -> AsyncIterator[str]:
    """Yield SSE frames until the prescription reaches a terminal status or time runs out."""
    started = clock()
    last_status: str | None = None
    last_emit = started

    while True:
        state = await fetch_state()
        if state is None:
            yield ProgressEvent("error", {"error_code": "PRESCRIPTION_NOT_FOUND"}).render()
            return

        event = build_event(state)
        status = event.data["status"]
        if status != last_status:
            yield event.render()
            last_status = status
            last_emit = clock()

        if event.data["terminal"]:
            yield ProgressEvent("done", {**event.data}).render()
            return

        now = clock()
        if now - started >= max_seconds:
            yield ProgressEvent(
                "timeout",
                {**event.data, "error_code": "PROGRESS_STREAM_TIMEOUT"},
            ).render()
            return
        if now - last_emit >= heartbeat_after:
            yield ": heartbeat\n\n"
            last_emit = now

        await sleep(poll_interval)
