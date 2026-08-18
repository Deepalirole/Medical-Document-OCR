from pydantic import BaseModel


class JobStateResponse(BaseModel):
    prescription_id: str
    key: str
    state: str
    error_code: str | None = None
    attempts: int
    duration_ms: int | None = None


class WorkerPoolStatus(BaseModel):
    running: bool
    concurrency: int
    max_queue: int
    queued: int
    in_flight: int
    completed: int
    failed: int
    tracked_jobs: int
