"""Process-isolated worker tests (directive §96-§109, §151).

Adversarial battery: the goal is to BREAK the worker system - crashes, hard
exits, races, concurrency, cancellation, shutdown, database health - and
verify honest state transitions. Every process lifecycle test is bounded in
time; a hang is a failure, never tolerated (§97).

All experiments run through the CANONICAL registry: the `process_probe`
diagnostic experiment exists precisely so spawned children resolve test
behaviors without any experiment-specific worker logic (§64-§65).
"""
import pickle
import time

import pytest

from app.experiments.runner import ExperimentSpec
from app.experiments.service import ExperimentService
from app.persistence.db import Database
from app.workers.jobs import JobQueue
from app.workers.process_worker import (
    WorkerResult,
    WorkerSpec,
    run_spec_in_process,
)

# Generous-but-bounded wait: Windows spawn needs a few seconds cold.
WAIT_S = 60.0


@pytest.fixture()
def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    yield database
    database.close()


@pytest.fixture()
def svc(db):
    return ExperimentService(db)


@pytest.fixture()
def jq(db):
    """Function-scoped queue: bounded, always shut down (§98 cleanup)."""
    queue = JobQueue(db=db, workers=2, process_timeout_s=WAIT_S)
    queue.start()
    yield queue
    queue.shutdown()
    with queue._lock:
        assert not queue._active_procs, "orphan worker process remained"


def make_run(svc: ExperimentService, module: str, config: dict,
             seed: int = 1, name: str = "probe-exp") -> int:
    spec = ExperimentSpec(name=name, module=module, config=dict(config), seed=seed)
    exp = svc.create_experiment(spec)
    return svc.create_runs_for_experiment(exp)[0]


def wait_job(job, statuses: set[str], timeout_s: float = WAIT_S):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if job.status in statuses:
            return job
        time.sleep(0.05)
    raise AssertionError(f"job stuck in {job.status} after {timeout_s}s")


def wait_running(job, timeout_s: float = WAIT_S):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if job.status == "RUNNING":
            return
        time.sleep(0.05)
    raise AssertionError(f"job never started running (status {job.status})")


# ---------------------------------------------------------------------------
# A. Serialization contracts
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_worker_spec_pickles(self):
        spec = WorkerSpec(run_id=3, module="process_probe",
                          resolved_config={"action": "succeed", "n": [1, 2]},
                          seed=42)
        clone = pickle.loads(pickle.dumps(spec))
        assert clone == spec

    def test_worker_result_pickles(self):
        res = WorkerResult(run_id=3, ok=False, error_type="RuntimeError",
                           error_message="boom",
                           traceback_text="Traceback ...")
        clone = pickle.loads(pickle.dumps(res))
        assert clone == res

    def test_spec_carries_no_runtime_objects(self):
        """The spec must be primitives only - the whole point of the
        boundary (§11, §13)."""
        spec = WorkerSpec(run_id=1, module="m", resolved_config={}, seed=0)
        data = pickle.dumps(spec)
        assert b"sqlite3" not in data
        assert b"socket" not in data


# ---------------------------------------------------------------------------
# B/C/D/E/F. Direct supervisor semantics
# ---------------------------------------------------------------------------

class TestSupervisor:
    def test_success_runs_outside_the_api_process(self):
        """The result must come from a DIFFERENT process (§1, §152 Q1)."""
        spec = WorkerSpec(run_id=1, module="process_probe",
                          resolved_config={"action": "succeed"}, seed=7)
        result = run_spec_in_process(spec, timeout_s=WAIT_S)
        assert result.ok and result.exitcode == 0
        assert result.worker_pid is not None
        import os
        assert result.worker_pid != os.getpid()

    def test_exception_is_reported_not_hidden(self):
        spec = WorkerSpec(run_id=2, module="process_probe",
                          resolved_config={"action": "fail"}, seed=1)
        result = run_spec_in_process(spec, timeout_s=WAIT_S)
        assert not result.ok
        assert result.error_type == "RuntimeError"
        assert "intentional probe failure" in result.error_message
        assert "Traceback" in (result.traceback_text or "")

    def test_hard_exit_detected(self):
        spec = WorkerSpec(run_id=3, module="process_probe",
                          resolved_config={"action": "hard_exit"}, seed=1)
        result = run_spec_in_process(spec, timeout_s=WAIT_S)
        assert not result.ok
        assert result.error_type == "WorkerAborted"
        assert result.exitcode == 70  # non-zero, never treated as success

    def test_timeout_terminates_worker(self):
        spec = WorkerSpec(run_id=4, module="process_probe",
                          resolved_config={"action": "slow", "seconds": 30},
                          seed=1)
        t0 = time.monotonic()
        result = run_spec_in_process(spec, timeout_s=2.0)
        assert not result.ok and result.timed_out
        assert result.error_type == "WorkerTimeout"
        assert time.monotonic() - t0 < 30  # actually bounded (§51)

    def test_cancellation_terminates_worker(self):
        spec = WorkerSpec(run_id=5, module="process_probe",
                          resolved_config={"action": "slow", "seconds": 30},
                          seed=1)
        result = run_spec_in_process(spec, timeout_s=WAIT_S,
                                     should_cancel=lambda: True)
        assert result.cancelled and not result.ok

    def test_serialization_failure_is_explicit(self):
        spec = WorkerSpec(run_id=6, module="process_probe",
                          resolved_config={"action": "unserializable"}, seed=1)
        result = run_spec_in_process(spec, timeout_s=WAIT_S)
        assert not result.ok
        assert result.error_type == "SerializationError"

    def test_unknown_module_fails_in_child(self):
        spec = WorkerSpec(run_id=7, module="no_such_experiment",
                          resolved_config={}, seed=1)
        result = run_spec_in_process(spec, timeout_s=WAIT_S)
        assert not result.ok  # loud failure, never fabricated success


# ---------------------------------------------------------------------------
# Queue lifecycle: crash containment, cancellation, races
# ---------------------------------------------------------------------------

class TestQueueLifecycle:
    def test_crash_containment(self, svc, jq):
        """§24 MANDATORY: crash worker A; API + DB stay healthy; worker B
        completes and persists afterwards."""
        rid_a = make_run(svc, "process_probe", {"action": "hard_exit"},
                         name="crash-me")
        job_a = jq.submit_run_job(rid_a, svc)
        wait_job(job_a, {"FAILED"})
        run_a = svc.get_run(rid_a)
        assert run_a["status"] == "FAILED"
        assert run_a["error_code"] == "WorkerAborted"
        assert svc.get_result(rid_a) is None  # no fabricated result

        rid_b = make_run(svc, "process_probe", {"action": "succeed"},
                         name="after-crash", seed=2)
        job_b = jq.submit_run_job(rid_b, svc)
        wait_job(job_b, {"COMPLETED"})
        assert svc.get_run(rid_b)["status"] == "COMPLETED"
        assert (svc.get_result(rid_b)["document"]["metrics"]["action"]
                == "succeed")

    def test_exception_becomes_failed_not_completed(self, svc, jq):
        rid = make_run(svc, "process_probe", {"action": "fail"})
        job = jq.submit_run_job(rid, svc)
        wait_job(job, {"FAILED"})
        run = svc.get_run(rid)
        assert run["status"] == "FAILED"
        assert "intentional probe failure" in run["error_message"]
        assert svc.get_result(rid) is None

    def test_cancel_before_start(self, svc, jq):
        """§28: queued cancellation - the worker never starts."""
        rid = make_run(svc, "process_probe", {"action": "slow", "seconds": 30})
        job = jq.submit_run_job(rid, svc)
        assert jq.cancel_job(job.id)
        wait_job(job, {"CANCELLED"}, timeout_s=15)
        assert svc.get_run(rid)["status"] == "CANCELLED"
        assert svc.get_result(rid) is None

    def test_cancel_during_execution_terminates(self, svc, jq):
        """§29: running cancellation = worker process termination."""
        rid = make_run(svc, "process_probe",
                       {"action": "slow", "seconds": 30})
        job = jq.submit_run_job(rid, svc)
        wait_running(job)
        assert job.cancel_requested is False
        assert jq.cancel_job(job.id)
        wait_job(job, {"CANCELLED"}, timeout_s=30)
        assert svc.get_run(rid)["status"] == "CANCELLED"
        assert svc.get_result(rid) is None  # partial work is not a result

    def test_cancel_completion_race_has_one_terminal_state(self, svc, jq):
        """§30-§31: cancellation and completion racing must end in exactly
        one consistent terminal state, matched between job and run row."""
        rid = make_run(svc, "process_probe", {"action": "succeed"}, seed=5)
        job = jq.submit_run_job(rid, svc)
        wait_running(job)
        job.request_cancel()  # race: the child may already be finishing
        wait_job(job, {"COMPLETED", "CANCELLED"})
        run = svc.get_run(rid)
        assert run["status"] == job.status  # no contradictory state
        if job.status == "COMPLETED":
            assert svc.get_result(rid) is not None
        else:
            assert svc.get_result(rid) is None

    def test_failure_does_not_stop_the_queue(self, svc, jq):
        """§91/§106: after a crash the queue processes remaining jobs."""
        rid_bad = make_run(svc, "process_probe", {"action": "hard_exit"})
        rid_good = make_run(svc, "process_probe", {"action": "succeed"}, seed=9)
        job_bad = jq.submit_run_job(rid_bad, svc)
        job_good = jq.submit_run_job(rid_good, svc)
        wait_job(job_bad, {"FAILED"})
        wait_job(job_good, {"COMPLETED"})

    def test_queue_overload_stays_bounded(self, svc, jq):
        """§105: more jobs than workers -> all jobs run, no process
        explosion (2 workers, 5 jobs)."""
        rids = [make_run(svc, "process_probe", {"action": "succeed"}, seed=i,
                         name=f"bulk-{i}") for i in range(5)]
        jobs = [jq.submit_run_job(rid, svc) for rid in rids]
        for j in jobs:
            wait_job(j, {"COMPLETED"})

    def test_shutdown_terminates_active_worker(self, svc, db):
        """§52: shutdown must not leave workers or RUNNING jobs."""
        queue = JobQueue(db=db, workers=1, process_timeout_s=WAIT_S)
        queue.start()
        try:
            rid = make_run(svc, "process_probe",
                           {"action": "slow", "seconds": 30})
            job = queue.submit_run_job(rid, svc)
            wait_running(job)
            queue.shutdown()
            wait_job(job, {"FAILED", "CANCELLED"}, timeout_s=30)
            assert svc.get_run(rid)["status"] == job.status
            assert svc.get_run(rid)["status"] != "COMPLETED"
            with queue._lock:
                live = [p for p in queue._active_procs.values() if p.is_alive()]
            assert not live
        finally:
            queue.shutdown()


# ---------------------------------------------------------------------------
# Concurrency, RNG isolation, reproducibility
# ---------------------------------------------------------------------------

class TestConcurrencyAndIsolation:
    def test_concurrent_experiments_isolated(self, svc, jq):
        """§40-§41/§157: two experiments, different seeds and configs,
        concurrently - results belong to the right runs."""
        rid_a = make_run(svc, "process_probe", {"action": "succeed"}, seed=11,
                         name="concurrent-a")
        rid_b = make_run(svc, "bb84_study",
                         {"n_signals": 512, "distance_km": 25}, seed=12,
                         name="concurrent-b")
        job_a = jq.submit_run_job(rid_a, svc)
        job_b = jq.submit_run_job(rid_b, svc)
        wait_job(job_a, {"COMPLETED"})
        wait_job(job_b, {"COMPLETED"})
        assert (svc.get_result(rid_a)["document"]["metrics"]["action"]
                == "succeed")
        assert "qber_no_eve" in svc.get_result(rid_b)["document"]["metrics"]
        # seeds stayed with their runs
        assert svc.get_run(rid_a)["seed"] == 11
        assert svc.get_run(rid_b)["seed"] == 12

    def test_rng_isolation_same_seed_same_result(self, svc, jq):
        """§37-§38: identical config+seed in different worker processes must
        produce identical results - no pid/time/worker-index influence."""
        rid1 = make_run(svc, "process_probe", {"action": "succeed"}, seed=99,
                        name="rng-1")
        rid2 = make_run(svc, "process_probe", {"action": "succeed"}, seed=99,
                        name="rng-2")
        job1 = jq.submit_run_job(rid1, svc)
        job2 = jq.submit_run_job(rid2, svc)
        wait_job(job1, {"COMPLETED"})
        wait_job(job2, {"COMPLETED"})
        assert (svc.get_result(rid1)["document"]["metrics"]
                == svc.get_result(rid2)["document"]["metrics"])

    def test_progress_events_attributed_to_correct_run(self, svc, jq):
        """§44/§81/§95: progress crossing the boundary carries the run id and
        never cross-contaminates."""
        seen: dict[int, list[float]] = {}

        def watch(job):
            seen.setdefault(job.payload["run_id"], []).append(job.progress)

        rid_a = make_run(svc, "process_probe", {"action": "succeed"}, seed=1,
                         name="prog-a")
        rid_b = make_run(svc, "process_probe", {"action": "succeed"}, seed=2,
                         name="prog-b")
        jq.subscribe(watch)
        job_a = jq.submit_run_job(rid_a, svc)
        job_b = jq.submit_run_job(rid_b, svc)
        wait_job(job_a, {"COMPLETED"})
        wait_job(job_b, {"COMPLETED"})
        assert seen[rid_a] and seen[rid_b]
        assert seen[rid_a][-1] == 1.0 and seen[rid_b][-1] == 1.0

    def test_reproduction_through_process_boundary(self, svc):
        """§39/§102/§158: reproduce creates a NEW run executed by a different
        worker process with EXACT_MATCH and immutable original."""
        rid = make_run(svc, "process_probe", {"action": "succeed"}, seed=77,
                       name="repro-original")
        svc.execute_run_isolated(rid, timeout_s=WAIT_S)
        report = svc.reproduce_run(rid)
        assert report.status == "EXACT_MATCH"
        assert report.reproduced_run_id != rid
        assert svc.get_run(rid)["status"] == "COMPLETED"  # original immutable

    def test_stale_run_recovery(self, svc):
        """§54/§110-§111: RUNNING runs orphaned by a dead process become
        FAILED (never COMPLETED); volatile QUEUED returns to CREATED."""
        rid_run = make_run(svc, "process_probe", {"action": "succeed"}, seed=1,
                           name="stale-running")
        svc.db.execute(
            "UPDATE runs SET status='RUNNING' WHERE id=?", (rid_run,))
        rid_queued = make_run(svc, "process_probe", {"action": "succeed"},
                              seed=1, name="stale-queued")
        svc.db.execute(
            "UPDATE runs SET status='QUEUED' WHERE id=?", (rid_queued,))
        recovered = svc.recover_interrupted_runs()
        assert recovered["failed"] >= 1 and recovered["unqueued"] >= 1
        assert svc.get_run(rid_run)["status"] == "FAILED"
        assert svc.get_run(rid_run)["error_code"] == "INTERRUPTED_BY_RESTART"
        assert svc.get_run(rid_queued)["status"] == "CREATED"

    def test_persistence_failure_is_honest(self, svc, jq):
        """§47-§48: if the parent cannot persist a successful result, the run
        must NOT be COMPLETED."""

        class BrokenPersist:
            def load_run_spec(self, run_id):
                return svc.load_run_spec(run_id)

            def begin_run(self, run_id):
                svc.begin_run(run_id)

            def update_run_progress(self, run_id, frac, detail):
                pass

            def persist_run_success(self, run_id, doc):
                raise RuntimeError("db unavailable")

            def persist_run_failure(self, run_id, code, message):
                pass

            def mark_run_cancelled(self, run_id):
                pass

        rid = make_run(svc, "process_probe", {"action": "succeed"}, seed=3)
        job = jq.submit_run_job(rid, BrokenPersist())
        wait_job(job, {"FAILED"})
        assert "persistence" in (job.error or "").lower()
        assert svc.get_run(rid)["status"] != "COMPLETED"
        assert svc.get_result(rid) is None

    def test_result_write_failure_records_terminal_run(self, svc, jq, monkeypatch):
        """A rejected result INSERT must terminate the persisted run, not only the job."""
        execute = svc.db.execute

        def reject_result_insert(sql, *args, **kwargs):
            if sql.startswith("INSERT INTO results"):
                raise RuntimeError("result storage unavailable")
            return execute(sql, *args, **kwargs)

        monkeypatch.setattr(svc.db, "execute", reject_result_insert)
        rid = make_run(svc, "process_probe", {"action": "succeed"}, seed=31)
        job = jq.submit_run_job(rid, svc)
        deadline = time.monotonic() + WAIT_S
        while job.completed_at is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert job.completed_at is not None
        assert job.status == "FAILED"
        run = svc.get_run(rid)
        assert run["status"] == "FAILED"
        assert run["error_code"] == "PersistenceError"
        assert "result storage unavailable" in run["error_message"]
        assert svc.get_result(rid) is None


# ---------------------------------------------------------------------------
# Real experiment types through the process boundary (§60-§63, §159)
# ---------------------------------------------------------------------------

class TestRealExperimentsThroughWorkers:
    def test_surface_code_mwpm(self, svc, jq):
        rid = make_run(svc, "surface_code_mwpm",
                       {"distances": [3], "physical_error_permille": [50],
                        "trials_per_point": 300}, seed=21, name="qec-iso")
        job = jq.submit_run_job(rid, svc)
        wait_job(job, {"COMPLETED"})
        row = svc.get_result(rid)["document"]["artifacts"]["table"][0]
        assert row["d"] == 3
        assert 0.0 <= row["logical_error_rate"] <= 1.0
        assert row["ci95_low"] <= row["logical_error_rate"] <= row["ci95_high"]

    def test_distributed_circuit(self, svc, jq):
        from app.circuits import Circuit, circuit_to_dict
        c = Circuit(num_qubits=2)
        c.add_gate("H", [0])
        c.add_gate("CX", [0, 1])
        rid = make_run(svc, "distributed_circuit",
                       {"circuit": circuit_to_dict(c),
                        "qubit_to_node": {0: "node_0", 1: "node_1"},
                        "protocol": "single_ebit"},
                       seed=33, name="dist-iso")
        job = jq.submit_run_job(rid, svc)
        wait_job(job, {"COMPLETED"})
        doc = svc.get_result(rid)["document"]
        assert doc["metrics"]["status"] == "success"
        assert doc["summary"]["equivalence"]["passed"]

    def test_cryptography_bb84(self, svc, jq):
        rid = make_run(svc, "bb84_study",
                       {"n_qubits": 128, "eve_intercept_percent": [0]},
                       seed=44, name="crypto-iso")
        job = jq.submit_run_job(rid, svc)
        wait_job(job, {"COMPLETED"})
        metrics = svc.get_result(rid)["document"]["metrics"]
        assert "qber_no_eve" in metrics  # statistical behavior, zero eve

    def test_optimization_vqe(self, svc, jq):
        rid = make_run(svc, "vqe",
                       {"system": "tfim", "n_qubits": 3, "max_iter": 15},
                       seed=55, name="vqe-iso")
        job = jq.submit_run_job(rid, svc)
        wait_job(job, {"COMPLETED"})
        assert svc.get_result(rid)["document"]["module"] == "vqe"
