"""Background job queue: threaded workers for long-running experiments.

Design (directives §99, §115, §288-291):
- Jobs run on daemon threads from a small pool; a failed job never kills the
  queue (job-level exception capture).
- Cancellation is COOPERATIVE: the runner checks the cancel flag at progress
  boundaries; runs that cannot checkpoint simply finish and report.
- Job state is mirrored into the runs table so the UI can show live progress.

For heavy scientific workloads this in-process model is adequate for the
local application; process isolation is future work (documented limitation).
"""
from __future__ import annotations

import threading
import queue as pyqueue
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone


JOB_QUEUED = "QUEUED"
JOB_RUNNING = "RUNNING"
JOB_COMPLETED = "COMPLETED"
JOB_FAILED = "FAILED"
JOB_CANCELLED = "CANCELLED"


@dataclass
class Job:
    id: int
    kind: str                     # e.g. "run"
    payload: dict                 # e.g. {"run_id": 5}
    status: str = JOB_QUEUED
    progress: float = 0.0
    detail: str = ""
    error: str | None = None
    result: dict | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    started_at: str | None = None
    completed_at: str | None = None
    _cancel_flag: bool = field(default=False, repr=False)

    def request_cancel(self) -> bool:
        if self.status in (JOB_QUEUED, JOB_RUNNING):
            self._cancel_flag = True
            return True
        return False

    @property
    def cancel_requested(self) -> bool:
        return self._cancel_flag


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class JobQueue:
    """Threaded job runner with bounded concurrency."""

    def __init__(self, db=None, workers: int = 2):
        if workers < 1 or workers > 8:
            raise ValueError("Worker count must be within [1, 8].")
        self.db = db
        self.workers = workers
        self._queue: pyqueue.Queue[Job] = pyqueue.Queue()
        self._jobs: dict[int, Job] = {}
        self._lock = threading.Lock()
        self._next_id = 1
        self._subscribers: list = []   # callables(job) for progress broadcast
        self._threads: list[threading.Thread] = []
        self._shutdown = threading.Event()
        self._started = False

    # ---------------- lifecycle ----------------

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        for i in range(self.workers):
            t = threading.Thread(target=self._worker_loop, name=f"ql-worker-{i}", daemon=True)
            t.start()
            self._threads.append(t)

    def shutdown(self) -> None:
        self._shutdown.set()

    # ---------------- API ----------------

    def submit_run_job(self, run_id: int, executor) -> Job:
        """Queue execution of an experiment run.

        `executor` is a callable(run_id, progress_cb) -> result document,
        typically ExperimentService.execute_run_now bound with its service.
        """
        job = Job(id=self._next_id, kind="run", payload={"run_id": run_id})
        job.result = None
        object.__setattr__(job, "_executor", executor)
        with self._lock:
            self._jobs[job.id] = job
            self._next_id += 1
        self._queue.put(job)
        self._publish(job)
        return job

    def get_job(self, job_id: int) -> Job | None:
        return self._jobs.get(job_id)

    def list_jobs(self, limit: int = 100) -> list[Job]:
        jobs = sorted(self._jobs.values(), key=lambda j: -j.id)[:limit]
        return jobs

    def pending_count(self) -> int:
        return sum(1 for j in self._jobs.values() if j.status == JOB_QUEUED)

    def running_count(self) -> int:
        return sum(1 for j in self._jobs.values() if j.status == JOB_RUNNING)

    def cancel_job(self, job_id: int) -> bool:
        job = self._jobs.get(job_id)
        if not job:
            return False
        requested = job.request_cancel()
        if job.status == JOB_QUEUED:
            job.status = JOB_CANCELLED
            job.completed_at = _now()
            self._publish(job)
        return requested

    def subscribe(self, callback) -> None:
        self._subscribers.append(callback)

    # ---------------- internals ----------------

    def _publish(self, job: Job) -> None:
        for cb in list(self._subscribers):
            try:
                cb(job)
            except Exception:
                pass  # subscriber failures must not affect the queue

    def _worker_loop(self) -> None:
        while not self._shutdown.is_set():
            try:
                job = self._queue.get(timeout=0.25)
            except pyqueue.Empty:
                continue
            if job.status == JOB_CANCELLED:
                continue
            self._run_job(job)

    def _run_job(self, job: Job) -> None:
        job.status = JOB_RUNNING
        job.started_at = _now()
        self._publish(job)
        executor = getattr(job, "_executor", None)
        try:
            def progress_cb(frac: float, detail: str):
                if job.cancel_requested:
                    raise CancelledError("cancellation requested")
                job.progress = float(frac)
                job.detail = str(detail)
                self._publish(job)

            doc = executor(job.payload["run_id"], progress_cb)
            if job.cancel_requested:
                job.status = JOB_CANCELLED
            else:
                job.status = JOB_COMPLETED
                job.result = doc
                job.progress = 1.0
            job.completed_at = _now()
        except CancelledError:
            job.status = JOB_CANCELLED
            job.completed_at = _now()
        except Exception as exc:  # job-level isolation (§288)
            job.status = JOB_FAILED
            job.error = f"{type(exc).__name__}: {exc}"
            job.completed_at = _now()
            traceback.print_exc()
        finally:
            self._publish(job)


class CancelledError(RuntimeError):
    pass
