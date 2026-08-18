"""Bounded background worker pool.

Processing a prescription is slow (render, preprocess, OCR, LLM), so this pool lets the upload
request return immediately while the work continues behind it.

Three properties are deliberate:

* **Bounded.** The queue has a fixed size and rejects work with ``WORKER_POOL_SATURATED``
  rather than growing without limit. Silent unbounded buffering turns a traffic spike into an
  out-of-memory kill, which loses every queued job instead of the one that overflowed.
* **Idempotent by key.** Re-submitting a key that is queued or running returns the existing
  state instead of duplicating the work, matching the idempotency guarantees the synchronous
  pipeline already provides.
* **Failure is recorded, never swallowed.** A crashing job marks its entry FAILED with the
  error code and lets the worker continue.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.core.errors import AppError

JobFactory = Callable[[], Awaitable[Any]]


class JobState(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class JobRecord:
    key: str
    state: JobState = JobState.QUEUED
    submitted_at: float = field(default_factory=time.monotonic)
    started_at: float | None = None
    finished_at: float | None = None
    error_code: str | None = None
    attempts: int = 0

    @property
    def active(self) -> bool:
        return self.state in {JobState.QUEUED, JobState.RUNNING}

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "state": str(self.state),
            "error_code": self.error_code,
            "attempts": self.attempts,
            "duration_ms": (
                int((self.finished_at - self.started_at) * 1000)
                if self.started_at and self.finished_at
                else None
            ),
        }


class BackgroundWorkerPool:
    def __init__(self, concurrency: int = 2, max_queue: int = 64, history: int = 500) -> None:
        self.concurrency = max(1, concurrency)
        self.max_queue = max(1, max_queue)
        self.history = max(1, history)
        self._queue: asyncio.Queue[tuple[str, JobFactory]] | None = None
        self._workers: list[asyncio.Task] = []
        self._jobs: dict[str, JobRecord] = {}
        self._completed = 0
        self._failed = 0

    @property
    def running(self) -> bool:
        return bool(self._workers)

    async def start(self) -> None:
        if self._workers:
            return
        self._queue = asyncio.Queue(maxsize=self.max_queue)
        self._workers = [
            asyncio.create_task(self._worker(index), name=f"prescription-worker-{index}")
            for index in range(self.concurrency)
        ]

    async def stop(self, drain: bool = False) -> None:
        if not self._workers:
            return
        if drain and self._queue is not None:
            await self._queue.join()
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []
        self._queue = None

    def submit(self, key: str, factory: JobFactory) -> JobRecord:
        if self._queue is None:
            raise AppError(
                "WORKER_POOL_NOT_RUNNING",
                "The background worker pool is not running.",
                503,
            )
        existing = self._jobs.get(key)
        if existing is not None and existing.active:
            return existing
        record = JobRecord(key=key)
        try:
            self._queue.put_nowait((key, factory))
        except asyncio.QueueFull as error:
            raise AppError(
                "WORKER_POOL_SATURATED",
                "The background worker pool is at capacity; retry shortly.",
                503,
                {"max_queue": self.max_queue},
            ) from error
        self._jobs[key] = record
        self._trim_history()
        return record

    def get(self, key: str) -> JobRecord | None:
        return self._jobs.get(key)

    def status(self) -> dict[str, Any]:
        queued = sum(1 for job in self._jobs.values() if job.state is JobState.QUEUED)
        running = sum(1 for job in self._jobs.values() if job.state is JobState.RUNNING)
        return {
            "running": self.running,
            "concurrency": self.concurrency,
            "max_queue": self.max_queue,
            "queued": queued,
            "in_flight": running,
            "completed": self._completed,
            "failed": self._failed,
            "tracked_jobs": len(self._jobs),
        }

    async def _worker(self, index: int) -> None:
        del index
        assert self._queue is not None
        queue = self._queue
        while True:
            key, factory = await queue.get()
            record = self._jobs.get(key)
            try:
                if record is not None:
                    record.state = JobState.RUNNING
                    record.started_at = time.monotonic()
                    record.attempts += 1
                await factory()
                if record is not None:
                    record.state = JobState.COMPLETED
                self._completed += 1
            except asyncio.CancelledError:
                if record is not None and record.state is JobState.RUNNING:
                    record.state = JobState.QUEUED
                    record.started_at = None
                queue.task_done()
                raise
            except AppError as error:
                self._fail(record, error.code)
            except Exception as error:  # noqa: BLE001 - a crashing job must not kill the worker
                self._fail(record, type(error).__name__)
            finally:
                if record is not None and record.state is not JobState.QUEUED:
                    record.finished_at = time.monotonic()
            queue.task_done()

    def _fail(self, record: JobRecord | None, error_code: str) -> None:
        if record is not None:
            record.state = JobState.FAILED
            record.error_code = error_code
        self._failed += 1

    def _trim_history(self) -> None:
        """Keep the job table bounded by discarding the oldest finished entries."""
        if len(self._jobs) <= self.history:
            return
        finished = sorted(
            (job for job in self._jobs.values() if not job.active),
            key=lambda job: job.finished_at or job.submitted_at,
        )
        for job in finished[: len(self._jobs) - self.history]:
            self._jobs.pop(job.key, None)
