"""Process-isolated experiment execution (Windows spawn, AD-014).

Architecture: ONE FRESH PROCESS PER EXPERIMENT, supervised by the parent.

    parent (API)                          child (spawn, disposable)
    -------------                         -------------------------
    WorkerSpec  ───────────────────────►  worker_main(spec, events)
    ◄── ("progress", run_id, frac, msg)   execute_run via the CANONICAL
    ◄── ("result", WorkerResult)          RUNNER_REGISTRY (no second
                                          registry, no DB, no sockets)

Everything crossing the boundary is deliberately picklable: the spec is a
dataclass of primitives, progress events are tuples, the result document is
whatever the canonical runner returned (JSON-serializable by construction,
verified at the boundary). Database connections, WebSocket objects, request
objects, locks, and closures NEVER cross (§13, §16).

Ownership:
  * The worker computes and reports; it owns NOTHING else. It does not open
    the database, does not hold queues, and exits when done — the OS reclaims
    its memory (§58, §84).
  * The parent validates every message (§123), owns all persistence, and is
    the authoritative lifecycle owner (§20).

Failure semantics (§21-§26): an exception, an abnormal exit, a missing
result, a timeout, or a serialization failure is reported as a not-ok
WorkerResult and becomes FAILED in the parent — never COMPLETED, never a
fabricated result. Cancellation terminates the child process (documented,
stronger than cooperative thread cancellation).

Honest limits (§73-§74): process isolation contains faults and reclaims
memory; it is NOT a sandbox — a worker runs with the same OS-user rights as
the parent, and no hard CPU/memory quotas are enforced.
"""
from __future__ import annotations

import multiprocessing as mp
import queue as pyqueue
import time
import traceback as tb_module
from dataclasses import dataclass, field

_POLL_SECONDS = 0.1
_JOIN_SECONDS = 10.0


@dataclass
class WorkerSpec:
    """Serializable experiment specification — the ONLY thing a worker needs."""

    run_id: int
    module: str            # key into the canonical RUNNER_REGISTRY
    resolved_config: dict  # resolved experiment configuration
    seed: int


@dataclass
class WorkerResult:
    """Serializable outcome of one worker process (§12)."""

    run_id: int
    ok: bool
    result: dict | None = None
    error_type: str | None = None
    error_message: str | None = None
    traceback_text: str | None = None
    duration_ms: float | None = None
    exitcode: int | None = None
    cancelled: bool = False
    timed_out: bool = False
    worker_pid: int | None = None


def worker_main(spec: WorkerSpec, events: mp.Queue) -> None:
    """Child-process entrypoint (module-level: Windows-spawn safe, §6).

    Executes the experiment through the canonical registry, reports progress
    events tagged with the run_id, and posts exactly one final result. It
    never touches the database, network, or any parent-owned resource.
    """
    start = time.perf_counter()

    def progress_cb(frac: float, detail: str) -> None:
        events.put(("progress", spec.run_id, float(frac), str(detail)))

    try:
        # Import inside the child: spawn re-imports modules fresh, and the
        # canonical registry is the single experiment dispatch table (§64).
        from ..experiments.runner import execute_run

        doc = execute_run(spec.module, spec.resolved_config, spec.seed,
                          progress_cb)
        result = WorkerResult(
            run_id=spec.run_id, ok=True, result=doc,
            duration_ms=(time.perf_counter() - start) * 1000.0,
            worker_pid=mp.current_process().pid,
        )
    except BaseException as exc:  # noqa: BLE001 - the boundary must catch all
        result = WorkerResult(
            run_id=spec.run_id, ok=False,
            error_type=type(exc).__name__,
            error_message=str(exc)[:2000],
            traceback_text="".join(tb_module.format_exception(exc))[-8000:],
            duration_ms=(time.perf_counter() - start) * 1000.0,
            worker_pid=mp.current_process().pid,
        )
    # Validate transportability BEFORE posting: an unserializable result must
    # become an explicit failure, never a silently lost message (§47).
    try:
        import pickle

        pickle.dumps(result)
    except BaseException as exc:  # noqa: BLE001
        result = WorkerResult(
            run_id=spec.run_id, ok=False,
            error_type="SerializationError",
            error_message=f"worker result could not be serialized: {exc}",
            duration_ms=(time.perf_counter() - start) * 1000.0,
            worker_pid=mp.current_process().pid,
        )
    try:
        events.put(("result", result))
        # Ensure the feeder thread flushes before the process exits;
        # otherwise the result can be lost on exit (Windows spawn).
        events.close()
        events.join_thread()
    except BaseException:
        # Result transport failed (e.g. unserializable document, §47): the
        # parent will see a dead process with no result and report FAILED.
        raise SystemExit(71)


def run_spec_in_process(
    spec: WorkerSpec,
    *,
    on_progress=None,
    should_cancel=None,
    timeout_s: float | None = None,
    poll_s: float = _POLL_SECONDS,
    proc_hook=None,
) -> WorkerResult:
    """Supervise one child process executing `spec` (parent side).

    Returns a WorkerResult in every outcome: success, child exception,
    abnormal exit / lost result, timeout, or cancellation. The child is
    always joined or terminated — no orphan remains (§50, §51).
    """
    ctx = mp.get_context("spawn")
    events = ctx.Queue()
    proc = ctx.Process(target=worker_main, args=(spec, events),
                       name=f"ql-proc-worker-{spec.run_id}", daemon=True)
    proc.start()
    if proc_hook is not None:
        proc_hook(proc)

    def finish(res: WorkerResult, *, join: bool = True) -> WorkerResult:
        res.exitcode = proc.exitcode if proc.exitcode is not None else res.exitcode
        res.worker_pid = res.worker_pid or proc.pid
        if join and proc.is_alive():
            proc.join(timeout=_JOIN_SECONDS)
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=_JOIN_SECONDS)
        events.close()
        return res

    deadline = (time.monotonic() + timeout_s) if timeout_s else None
    got_result: WorkerResult | None = None
    while True:
        if should_cancel is not None and should_cancel():
            proc.terminate()
            proc.join(timeout=_JOIN_SECONDS)
            return finish(WorkerResult(
                run_id=spec.run_id, ok=False, cancelled=True,
                error_type="Cancelled",
                error_message="worker process terminated by cancellation.",
                worker_pid=proc.pid,
            ), join=False)
        if deadline is not None and time.monotonic() > deadline:
            proc.terminate()
            proc.join(timeout=_JOIN_SECONDS)
            return finish(WorkerResult(
                run_id=spec.run_id, ok=False, timed_out=True,
                error_type="WorkerTimeout",
                error_message=f"worker exceeded timeout of {timeout_s}s.",
                worker_pid=proc.pid,
            ), join=False)
        try:
            msg = events.get(timeout=poll_s)
        except EOFError:
            # Windows closed pipes can surface as EOFError instead of Empty
            # once the child is gone; fall through to the dead-process check.
            if proc.is_alive():
                continue
            if got_result is not None:
                return finish(got_result)
            return finish(WorkerResult(
                run_id=spec.run_id, ok=False,
                error_type="WorkerAborted",
                error_message=(
                    "worker process exited without a result "
                    f"(exitcode {proc.exitcode})."
                ),
                worker_pid=proc.pid,
            ))
        except pyqueue.Empty:
            if not proc.is_alive():
                # Drain any final messages the feeder managed to flush.
                try:
                    while True:
                        msg = events.get_nowait()
                        if msg[0] == "progress" and on_progress is not None:
                            on_progress(msg[2], msg[3])
                        elif msg[0] == "result":
                            got_result = msg[1]
                except pyqueue.Empty:
                    pass
                if got_result is not None:
                    return finish(got_result)
                return finish(WorkerResult(
                    run_id=spec.run_id, ok=False,
                    error_type="WorkerAborted",
                    error_message=(
                        "worker process exited without a result "
                        f"(exitcode {proc.exitcode})."
                    ),
                    worker_pid=proc.pid,
                ))
            continue
        if msg[0] == "progress":
            _, run_id, frac, detail = msg
            if run_id != spec.run_id:
                continue  # misrouted event: never apply to another run (§81)
            if on_progress is not None:
                try:
                    on_progress(frac, detail)
                except Exception:
                    pass  # observability must never kill the run (§119)
        elif msg[0] == "result":
            got_result = msg[1]
            # Keep draining progress briefly, then finish when the process
            # exits on its own.
            proc.join(timeout=_JOIN_SECONDS)
            if got_result.run_id != spec.run_id:
                return finish(WorkerResult(
                    run_id=spec.run_id, ok=False,
                    error_type="WorkerProtocolError",
                    error_message="worker returned a mismatched run_id.",
                    worker_pid=proc.pid,
                ))
            return finish(got_result, join=False)
        # Unknown message kinds are ignored (forward compatibility), §125.
