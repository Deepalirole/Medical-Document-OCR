import asyncio
from uuid import uuid4

import pytest

from app.api.dependencies import get_worker_pool
from app.core.config import Settings
from app.core.errors import AppError
from app.services.workers.pool import BackgroundWorkerPool, JobState
from app.tests.conftest import ORG_ID
from app.tests.test_p2_dynamic_review import PRESCRIPTION_ID


async def drain(pool, timeout=2.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        status = pool.status()
        if status["queued"] == 0 and status["in_flight"] == 0:
            return
        await asyncio.sleep(0.005)
    raise AssertionError(f"pool did not drain: {pool.status()}")


def test_submitting_before_start_is_refused():
    pool = BackgroundWorkerPool()
    with pytest.raises(AppError) as error:
        pool.submit("k", lambda: asyncio.sleep(0))
    assert error.value.code == "WORKER_POOL_NOT_RUNNING"


def test_jobs_run_in_the_background_and_complete():
    async def scenario():
        pool = BackgroundWorkerPool(concurrency=2)
        await pool.start()
        done: list[str] = []

        async def job(name):
            await asyncio.sleep(0)
            done.append(name)

        record = pool.submit("a", lambda: job("a"))
        pool.submit("b", lambda: job("b"))
        assert record.state is JobState.QUEUED
        await drain(pool)
        await pool.stop()
        return done, pool.status()

    done, status = asyncio.run(scenario())
    assert sorted(done) == ["a", "b"]
    assert status["completed"] == 2
    assert status["failed"] == 0


def test_resubmitting_an_active_key_is_idempotent():
    async def scenario():
        pool = BackgroundWorkerPool(concurrency=1)
        await pool.start()
        runs: list[int] = []
        gate = asyncio.Event()

        async def job():
            await gate.wait()
            runs.append(1)

        first = pool.submit("same", job)
        second = pool.submit("same", job)
        assert first is second
        gate.set()
        await drain(pool)
        await pool.stop()
        return runs, pool.status()

    runs, status = asyncio.run(scenario())
    assert runs == [1]
    assert status["completed"] == 1


def test_a_finished_key_can_be_resubmitted():
    async def scenario():
        pool = BackgroundWorkerPool(concurrency=1)
        await pool.start()
        runs: list[int] = []

        async def job():
            runs.append(1)

        pool.submit("k", job)
        await drain(pool)
        pool.submit("k", job)
        await drain(pool)
        await pool.stop()
        return runs

    assert asyncio.run(scenario()) == [1, 1]


def test_the_queue_is_bounded_and_rejects_overflow():
    async def scenario():
        pool = BackgroundWorkerPool(concurrency=1, max_queue=2)
        await pool.start()
        gate = asyncio.Event()

        async def job():
            await gate.wait()

        accepted = 0
        rejected = None
        for index in range(10):
            try:
                pool.submit(f"k{index}", job)
                accepted += 1
            except AppError as error:
                rejected = error
                break
        gate.set()
        await pool.stop()
        return accepted, rejected

    accepted, rejected = asyncio.run(scenario())
    assert rejected is not None
    assert rejected.code == "WORKER_POOL_SATURATED"
    assert rejected.status_code == 503
    assert rejected.details["max_queue"] == 2
    assert accepted <= 3


def test_a_failing_job_is_recorded_and_the_worker_survives():
    async def scenario():
        pool = BackgroundWorkerPool(concurrency=1)
        await pool.start()

        async def boom():
            raise AppError("OCR_FAILED", "bad page", 502)

        async def crash():
            raise RuntimeError("unexpected")

        async def fine():
            return None

        pool.submit("bad", boom)
        pool.submit("worse", crash)
        pool.submit("good", fine)
        await drain(pool)
        states = {key: pool.get(key).to_dict() for key in ("bad", "worse", "good")}
        status = pool.status()
        await pool.stop()
        return states, status

    states, status = asyncio.run(scenario())
    assert states["bad"]["state"] == "FAILED"
    assert states["bad"]["error_code"] == "OCR_FAILED"
    assert states["worse"]["error_code"] == "RuntimeError"
    assert states["good"]["state"] == "COMPLETED"
    assert status["failed"] == 2
    assert status["completed"] == 1


def test_status_reports_capacity_and_counters():
    async def scenario():
        pool = BackgroundWorkerPool(concurrency=3, max_queue=7)
        await pool.start()
        status = pool.status()
        await pool.stop()
        return status

    status = asyncio.run(scenario())
    assert status["concurrency"] == 3
    assert status["max_queue"] == 7
    assert status["running"] is True


def test_stopping_an_unstarted_pool_is_safe():
    asyncio.run(BackgroundWorkerPool().stop())


def test_history_is_bounded():
    async def scenario():
        pool = BackgroundWorkerPool(concurrency=1, max_queue=200, history=5)
        await pool.start()

        async def job():
            return None

        for index in range(40):
            pool.submit(f"k{index}", job)
            await drain(pool)
        await pool.stop()
        return pool.status()

    assert asyncio.run(scenario())["tracked_jobs"] <= 6


def test_drain_on_stop_waits_for_queued_work():
    async def scenario():
        pool = BackgroundWorkerPool(concurrency=1)
        await pool.start()
        done: list[int] = []

        async def job():
            await asyncio.sleep(0.01)
            done.append(1)

        for index in range(5):
            pool.submit(f"k{index}", job)
        await pool.stop(drain=True)
        return done

    assert len(asyncio.run(scenario())) == 5


# --- API -----------------------------------------------------------------------------


class StubPool:
    def __init__(self, record=None, saturated=False):
        self.record = record
        self.saturated = saturated
        self.submitted: list[str] = []

    def submit(self, key, factory):
        if self.saturated:
            raise AppError("WORKER_POOL_SATURATED", "full", 503, {"max_queue": 1})
        self.submitted.append(key)
        return _Record(key)

    def get(self, key):
        return self.record

    def status(self):
        return {
            "running": True,
            "concurrency": 2,
            "max_queue": 64,
            "queued": 1,
            "in_flight": 0,
            "completed": 3,
            "failed": 1,
            "tracked_jobs": 4,
        }


class _Record:
    def __init__(self, key, state="QUEUED"):
        self.key = key
        self.state = state

    def to_dict(self):
        return {
            "key": self.key,
            "state": self.state,
            "error_code": None,
            "attempts": 0,
            "duration_ms": None,
        }


def use_pool(pool):
    from app.main import app

    app.dependency_overrides[get_worker_pool] = lambda: pool


def clear_pool():
    from app.main import app

    app.dependency_overrides.pop(get_worker_pool, None)


def wire(repository, organization_id=ORG_ID):
    async def prescription_for_user(_id):
        return {"id": str(PRESCRIPTION_ID), "organization_id": str(organization_id)}

    repository.prescription_for_user = prescription_for_user


def test_async_process_returns_202_and_enqueues(client, repository):
    wire(repository)
    pool = StubPool()
    use_pool(pool)
    try:
        response = client.post(f"/api/prescriptions/{PRESCRIPTION_ID}/process-async")
    finally:
        clear_pool()
    assert response.status_code == 202
    assert response.json()["state"] == "QUEUED"
    assert pool.submitted == [f"process:{PRESCRIPTION_ID}"]


def test_async_process_surfaces_saturation(client, repository):
    wire(repository)
    use_pool(StubPool(saturated=True))
    try:
        response = client.post(f"/api/prescriptions/{PRESCRIPTION_ID}/process-async")
    finally:
        clear_pool()
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "WORKER_POOL_SATURATED"


def test_async_process_enforces_membership(client, repository):
    wire(repository, organization_id=uuid4())
    use_pool(StubPool())
    try:
        response = client.post(f"/api/prescriptions/{PRESCRIPTION_ID}/process-async")
    finally:
        clear_pool()
    assert response.status_code == 403


def test_job_status_is_404_when_nothing_was_queued(client, repository):
    wire(repository)
    use_pool(StubPool(record=None))
    try:
        response = client.get(f"/api/prescriptions/{PRESCRIPTION_ID}/process-async")
    finally:
        clear_pool()
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "JOB_NOT_FOUND"


def test_job_status_reports_a_tracked_job(client, repository):
    wire(repository)
    use_pool(StubPool(record=_Record("process:x", "RUNNING")))
    try:
        response = client.get(f"/api/prescriptions/{PRESCRIPTION_ID}/process-async")
    finally:
        clear_pool()
    assert response.json()["state"] == "RUNNING"


def test_pool_status_endpoint_requires_admin(client, repository):
    use_pool(StubPool())
    try:
        denied = client.get("/api/admin/worker-pool", params={"organization_id": str(ORG_ID)})
    finally:
        clear_pool()
    assert denied.status_code == 403


def test_pool_status_endpoint_reports_counters_for_an_admin(client, repository):
    async def assert_membership(user_id, organization_id, roles=None):
        return {"role": "admin"}

    repository.assert_membership = assert_membership
    use_pool(StubPool())
    try:
        response = client.get("/api/admin/worker-pool", params={"organization_id": str(ORG_ID)})
    finally:
        clear_pool()
    assert response.status_code == 200
    assert response.json()["completed"] == 3
    assert response.json()["failed"] == 1


def test_pool_settings_have_safe_defaults():
    settings = Settings()
    assert settings.worker_pool_enabled is True
    assert settings.worker_pool_concurrency == 2
    assert settings.worker_pool_max_queue == 64
