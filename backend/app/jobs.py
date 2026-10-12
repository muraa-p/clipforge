"""A dead-simple in-process background job manager.

Long tasks (downloading, transcribing, rendering) run in worker threads so the
HTTP API stays responsive. The frontend polls ``GET /api/jobs/{id}``.
"""

from __future__ import annotations

import threading
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

from .store import new_id
from .config import MAX_CONCURRENT_JOBS, MAX_QUEUED_JOBS

MAX_FINISHED_JOBS = 200


@dataclass
class Job:
    id: str
    kind: str
    status: str = "queued"  # queued | running | done | error
    progress: float = 0.0  # 0..100
    message: str = ""
    result: Any = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "progress": round(self.progress, 1),
            "message": self.message,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class JobManager:
    def __init__(self, max_concurrent: int = MAX_CONCURRENT_JOBS) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        # Bounded concurrency: jobs beyond the cap stay "queued" until a slot frees.
        self._slots = threading.Semaphore(max(1, max_concurrent))
        self._max_queued = MAX_QUEUED_JOBS

    def create(self, kind: str) -> Job:
        job = Job(id=new_id(), kind=kind)
        with self._lock:
            self._jobs[job.id] = job
            self._prune_locked()
        return job

    def pending_count(self) -> int:
        with self._lock:
            return sum(
                1 for j in self._jobs.values() if j.status in ("queued", "running")
            )

    def has_capacity(self) -> bool:
        """False when too much work is already queued/running (public safety)."""
        return self.pending_count() < self._max_queued

    def _prune_locked(self) -> None:
        """Drop the oldest finished jobs so memory can't grow without bound."""
        finished = [j for j in self._jobs.values() if j.status in ("done", "error")]
        if len(finished) <= MAX_FINISHED_JOBS:
            return
        finished.sort(key=lambda j: j.updated_at)
        for stale in finished[: len(finished) - MAX_FINISHED_JOBS]:
            self._jobs.pop(stale.id, None)

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def all(self) -> list[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def update(self, job: Job, **fields: Any) -> None:
        for key, value in fields.items():
            setattr(job, key, value)
        job.updated_at = time.time()

    def reporter(self, job: Job) -> Callable[..., None]:
        """Return a ``(progress, message)`` callback for use inside services."""

        def report(progress: float | None = None, message: str | None = None) -> None:
            if progress is not None:
                job.progress = max(0.0, min(100.0, float(progress)))
            if message is not None:
                job.message = message
            job.updated_at = time.time()

        return report

    def spawn(self, job: Job, target: Callable[[Job], Any]) -> None:
        def runner() -> None:
            # Wait for a free slot; until then the job simply reports "queued".
            self._slots.acquire()
            try:
                job.status = "running"
                job.message = job.message or "Starting…"
                job.updated_at = time.time()
                try:
                    result = target(job)
                    job.result = result
                    job.status = "done"
                    job.progress = 100.0
                    job.message = "Finished"
                except Exception as exc:  # noqa: BLE001 - surface to the UI
                    job.status = "error"
                    job.error = str(exc)
                    job.message = "Failed"
                    job.result = {"traceback": traceback.format_exc()}
                finally:
                    job.updated_at = time.time()
            finally:
                self._slots.release()

        threading.Thread(target=runner, name=f"job-{job.id}", daemon=True).start()


manager = JobManager()
