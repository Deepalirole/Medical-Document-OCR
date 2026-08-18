import asyncio
import json
from uuid import uuid4

from app.api.dependencies import get_processing_repository
from app.core.config import Settings
from app.services.realtime.progress import (
    STAGE_ORDER,
    build_event,
    progress_events,
    progress_fraction,
)
from app.tests.conftest import ORG_ID
from app.tests.test_p2_dynamic_review import PRESCRIPTION_ID


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    async def sleep(self, seconds):
        self.now += seconds


async def collect(states, **kwargs):
    queue = list(states)
    clock = FakeClock()

    async def fetch():
        return queue.pop(0) if len(queue) > 1 else queue[0]

    frames = []
    async for frame in progress_events(
        fetch, sleep=clock.sleep, clock=clock, poll_interval=1.0, **kwargs
    ):
        frames.append(frame)
    return frames


def parse(frames):
    parsed = []
    for frame in frames:
        if frame.startswith(":"):
            parsed.append(("heartbeat", None))
            continue
        lines = frame.strip().splitlines()
        event = lines[0].removeprefix("event: ")
        data = json.loads(lines[1].removeprefix("data: "))
        parsed.append((event, data))
    return parsed


def state(status, **extra):
    return {"id": str(PRESCRIPTION_ID), "status": status, "page_count": 2, **extra}


def test_progress_fraction_is_monotonic_across_the_pipeline():
    fractions = [progress_fraction(stage) for stage in STAGE_ORDER]
    assert fractions == sorted(fractions)
    assert fractions[0] > 0.0
    assert fractions[-1] == 1.0


def test_an_unknown_status_reports_zero_rather_than_guessing():
    assert progress_fraction("SOMETHING_ELSE") == 0.0


def test_failures_report_complete_progress_and_a_failed_event():
    event = build_event(state("LLM_FAILED", error_code="LLM_FAILED"))
    assert event.event == "failed"
    assert event.data["terminal"] is True
    assert event.data["progress"] == 1.0
    assert event.data["error_code"] == "LLM_FAILED"


def test_stream_emits_a_frame_per_status_change_then_done():
    frames = parse(
        asyncio.run(
            collect([state("RENDERING"), state("OCR_RUNNING"), state("REVIEW_REQUIRED")])
        )
    )
    assert [item[0] for item in frames] == ["progress", "progress", "progress", "done"]
    assert [item[1]["status"] for item in frames] == [
        "RENDERING",
        "OCR_RUNNING",
        "REVIEW_REQUIRED",
        "REVIEW_REQUIRED",
    ]
    assert frames[-1][1]["terminal"] is True


def test_an_unchanged_status_does_not_emit_duplicate_frames():
    frames = parse(
        asyncio.run(collect([state("OCR_RUNNING"), state("OCR_RUNNING"), state("COMPLETED")]))
    )
    statuses = [item[1]["status"] for item in frames if item[0] == "progress"]
    assert statuses == ["OCR_RUNNING", "COMPLETED"]


def test_a_terminal_status_ends_the_stream_immediately():
    frames = parse(asyncio.run(collect([state("APPROVED")])))
    assert [item[0] for item in frames] == ["progress", "done"]


def test_a_failure_status_is_terminal_too():
    frames = parse(asyncio.run(collect([state("OCR_FAILED", error_code="OCR_FAILED")])))
    assert frames[0][0] == "failed"
    assert frames[-1][0] == "done"


def test_a_stalled_pipeline_emits_heartbeats_then_times_out():
    frames = parse(
        asyncio.run(collect([state("OCR_RUNNING")], max_seconds=10.0, heartbeat_after=3.0))
    )
    kinds = [item[0] for item in frames]
    assert kinds[0] == "progress"
    assert "heartbeat" in kinds
    assert kinds[-1] == "timeout"
    assert frames[-1][1]["error_code"] == "PROGRESS_STREAM_TIMEOUT"


def test_a_vanished_prescription_ends_the_stream_with_an_error():
    frames = parse(asyncio.run(collect([None])))
    assert frames == [("error", {"error_code": "PRESCRIPTION_NOT_FOUND"})]


def test_frames_are_valid_sse():
    frame = build_event(state("RENDERING")).render()
    assert frame.startswith("event: progress\ndata: {")
    assert frame.endswith("\n\n")


# --- API -----------------------------------------------------------------------------


class FakeProcessingRepository:
    def __init__(self, states):
        self.states = list(states)

    async def get_prescription(self, prescription_id, organization_id):
        return self.states.pop(0) if len(self.states) > 1 else self.states[0]


def wire(repository, organization_id=ORG_ID):
    async def prescription_for_user(_id):
        return {"id": str(PRESCRIPTION_ID), "organization_id": str(organization_id)}

    repository.prescription_for_user = prescription_for_user


def test_stream_endpoint_returns_event_stream(client, repository):
    from app.main import app

    wire(repository)
    app.dependency_overrides[get_processing_repository] = lambda: FakeProcessingRepository(
        [state("RENDERING"), state("REVIEW_REQUIRED")]
    )
    try:
        response = client.get(f"/api/prescriptions/{PRESCRIPTION_ID}/progress-stream")
    finally:
        app.dependency_overrides.pop(get_processing_repository, None)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"].startswith("no-cache")
    body = response.text
    assert "event: progress" in body
    assert "event: done" in body
    assert "REVIEW_REQUIRED" in body


def test_stream_endpoint_enforces_membership(client, repository):
    wire(repository, organization_id=uuid4())
    response = client.get(f"/api/prescriptions/{PRESCRIPTION_ID}/progress-stream")
    assert response.status_code == 403


def test_stream_endpoint_is_404_for_an_unknown_prescription(client, repository):
    async def missing(_id):
        return None

    repository.prescription_for_user = missing
    response = client.get(f"/api/prescriptions/{PRESCRIPTION_ID}/progress-stream")
    assert response.status_code == 404


def test_progress_settings_have_bounded_defaults():
    settings = Settings()
    assert settings.progress_poll_seconds == 1.0
    assert settings.progress_max_seconds == 300.0
