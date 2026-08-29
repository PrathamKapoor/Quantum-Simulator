"""Background job queue: bounded concurrency with PROCESS-ISOLATED execution.

Design (AD-014; directives §4-§26 of the isolation milestone):
- Each submitted run is executed in a FRESH, disposable child process
  (Windows spawn) supervised by a small pool of daemon threads. The threads
  only supervise; the science runs outside the API process.
- The canonical experiment registry (`RUNNER_REGISTRY` via `execute_run`) is
  used by the worker — no second dispatch table, no experiment-specific
  worker logic.
- The PARENT owns all persistence and lifecycle state (§15-§20): workers
  never open the database. The `runner_facade` passed to submit_run_job is
  the ExperimentService, which provides load_run_spec / begin_run /
  update_run_progress / persist_run_success / persist_run_failure /
  mark_run_cancelled.
- Failure semantics (§21-§26): child exception, abnormal exit, missing
  result, serialization failure, or timeout -> the run is FAILED. A crash is
  NEVER COMPLETED. Queue threads survive any single job failure.
- Cancellation (§27-§31): QUEUED jobs cancel without starting; RUNNING jobs
  are cancelled by TERMINATING the child process — stronger than the former
  cooperative thread model. If a result and a cancellation race, the
  cancellation wins when it was requested before result acceptance;
  otherwise the completion stands. Either way exactly one terminal state.
- WebSocket progress: the existing subscribe/publish mechanism is unchanged;
  progress events cross the process boundary as tagged tuples and are routed
  strictly by run_id (§42-§43).
"""
from __future__ import annotations

import threading
import queue as pyqueue
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .process_worker import run_spec_in_process


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
    """Bounded job runner; each job executes in an isolated worker process."""

    def __init__(self, db=None, workers: int = 2,
                 process_timeout_s: float | None = None):
        if workers < 1 or workers > 8:
            raise ValueError("Worker count must be within [1, 8].")
        self.db = db
        self.workers = workers
        # Configurable per-job process timeout; None = no arbitrary cap that
        # could kill legitimate long-running quantum experiments (§32-§33).
        self.process_timeout_s = process_timeout_s
        self._queue: pyqueue.Queue[Job] = pyqueue.Queue()
        self._jobs: dict[int, Job] = {}
        self._lock = threading.Lock()
        self._next_id = 1
        self._subscribers: list = []   # callables(job) for progress broadcast
        self._threads: list[threading.Thread] = []
        self._shutdown = threading.Event()
        self._started = False
        self._active_procs: dict[int, object] = {}  # job id -> child Process

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
        """Stop the queue and TERMINATE active child processes (§52).

        Runs whose workers are terminated here become FAILED (via the
        supervisor's abnormal-exit handling) — never silently COMPLETED.
        """
        self._shutdown.set()
        with self._lock:
            procs = list(self._active_procs.values())
        for proc in procs:
            try:
                if proc.is_alive():
                    proc.terminate()
            except Exception:
                pass  # a dead process cannot fail shutdown

    # ---------------- API ----------------

    def submit_run_job(self, run_id: int, runner_facade) -> Job:
        """Queue execution of an experiment run in an isolated worker process.

        `runner_facade` is the authoritative persistence owner (the
        ExperimentService): it loads the serializable WorkerSpec and records
        RUNNING/progress/result/FAILED/CANCELLED transitions.
        """
        job = Job(id=self._next_id, kind="run", payload={"run_id": run_id})
        job.result = None
        object.__setattr__(job, "_facade", runner_facade)
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
            facade = getattr(job, "_facade", None)
            if facade is not None:
                try:
                    facade.mark_run_cancelled(job.payload["run_id"])
                except Exception:
                    pass  # DB unavailability must not break queue bookkeeping
            self._publish(job)
        # RUNNING jobs are terminated by their supervisor thread, which sees
        # the cancel flag at the next poll (bounded, poll_s = 0.1 s).
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
            if self._shutdown.is_set():
                # Shutdown raced a queued job: do not spawn new workers (§53).
                job.status = JOB_CANCELLED
                job.completed_at = _now()
                self._publish(job)
                continue
            self._run_job(job)

    def _run_job(self, job: Job) -> None:
        job.status = JOB_RUNNING
        job.started_at = _now()
        self._publish(job)
        facade = getattr(job, "_facade", None)
        run_id = job.payload["run_id"]
        try:
            spec = facade.load_run_spec(run_id)
            facade.begin_run(run_id)
        except Exception as exc:
            job.status = JOB_FAILED
            job.error = f"{type(exc).__name__}: {exc}"
            job.completed_at = _now()
            try:
                facade.persist_run_failure(run_id, type(exc).__name__, str(exc))
            except Exception:
                pass
            self._publish(job)
            return

        def on_progress(frac: float, detail: str) -> None:
            job.progress = float(frac)
            job.detail = str(detail)
            try:
                facade.update_run_progress(run_id, frac, detail)
            except Exception:
                pass  # progress persistence must not kill the run (§119)
            self._publish(job)

        def proc_hook(proc) -> None:
            with self._lock:
                self._active_procs[job.id] = proc

        result = run_spec_in_process(
            spec,
            on_progress=on_progress,
            should_cancel=lambda: job.cancel_requested or self._shutdown.is_set(),
            timeout_s=self.process_timeout_s,
            proc_hook=proc_hook,
        )
        with self._lock:
            self._active_procs.pop(job.id, None)

        if result.cancelled:
            job.status = JOB_CANCELLED
            try:
                facade.mark_run_cancelled(run_id)
            except Exception:
                pass
        elif result.ok and isinstance(result.result, dict):
            if job.cancel_requested:
                # Cancel/complete race (§31): a cancellation requested before
                # result acceptance wins deterministically.
                job.status = JOB_CANCELLED
                try:
                    facade.mark_run_cancelled(run_id)
                except Exception:
                    pass
            else:
                try:
                    facade.persist_run_success(run_id, result.result)
                    job.status = JOB_COMPLETED
                    job.result = result.result
                    job.progress = 1.0
                except Exception as exc:
                    # Persistence failure: the result is NOT falsely reported
                    # as persisted (§47-§48).
                    job.status = JOB_FAILED
                    job.error = f"PersistenceError: {exc}"
        else:
            job.status = JOB_FAILED
            if result.error_message:
                job.error = f"{result.error_type or 'WorkerError'}: {result.error_message}"
            else:
                job.error = "worker failed without a diagnostic"
            try:
                facade.persist_run_failure(
                    run_id, result.error_type or "WorkerError",
                    result.error_message or "worker failed without a result")
            except Exception as exc:
                job.error += f" (persistence also failed: {exc})"
        job.completed_at = _now()
        self._publish(job)


class CancelledError(RuntimeError):
    """Legacy cooperative-cancellation signal (pre-AD-014 threaded model).

    Retained for import compatibility; process-isolated cancellation is
    implemented by terminating the worker (process_worker.py)."""
