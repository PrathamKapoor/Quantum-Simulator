"""Persistence + experiment engine integration tests (§97-116, §164-169)."""
import json

import pytest

from app.persistence.db import Database, ensure_default_project, MIGRATIONS
from app.experiments.runner import ExperimentSpec, SweepParameter, expand_sweep
from app.experiments.service import ExperimentService
from app.workers.jobs import JobQueue


@pytest.fixture()
def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    yield database
    database.close()


def bell_circuit_document() -> dict:
    from app.circuits import Circuit

    c = Circuit(num_qubits=2, num_clbits=2, name="bell-exp")
    c.add_gate("H", [0]).add_gate("CX", [0, 1])
    c.add_measure([0, 1], [0, 1])
    from app.circuits import circuit_to_dict

    return circuit_to_dict(c)


class TestMigrations:
    def test_migrations_apply_once_and_recorded(self, db):
        rows = db.query("SELECT number FROM schema_migrations ORDER BY number")
        numbers = [r["number"] for r in rows]
        assert numbers == sorted(m[0] for m in MIGRATIONS)

    def test_core_tables_exist(self, db):
        tables = {r["name"] for r in db.query(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"projects", "experiments", "runs", "results",
                "notes", "audit_log"} <= tables


class TestExperimentLifecycle:
    def _service(self, db):
        return ExperimentService(db)

    def test_create_and_expand_sweep(self, db):
        svc = self._service(db)
        spec = ExperimentSpec(
            name="repeater spacing study",
            module="network_study",
            config={"topology": {"nodes": [], "links": []}, "sim_time_ms": 10},
            sweep=[SweepParameter("distance_km", [5, 10, 20])],
            seed=3,
        )
        exp_id = svc.create_experiment(spec, objective="spacing vs fidelity")
        combos = expand_sweep(spec)
        assert len(combos) == 3
        run_ids = svc.create_runs_for_experiment(exp_id)
        assert len(run_ids) == 3
        runs = svc.list_runs(exp_id)
        labels = [r["label"] for r in runs]
        assert "distance_km=5" in labels[0]
        # Seeds differ deterministically per run index.
        seeds = {r["seed"] for r in runs}
        assert len(seeds) == 3

    def test_run_circuit_shots_end_to_end(self, db):
        svc = self._service(db)
        spec = ExperimentSpec(
            name="bell shots", module="circuit_shots",
            config={"circuit": bell_circuit_document(), "shots": 512},
            seed=11,
        )
        exp_id = svc.create_experiment(spec)
        run_ids = svc.create_runs_for_experiment(exp_id)
        doc = svc.execute_run_now(run_ids[0])
        assert doc["schema"] == "quantumlab.run-result"
        metrics = svc.get_result(run_ids[0])["document"]["metrics"]
        assert metrics["top_outcome"] in ("00", "11")
        assert metrics["top_probability"] > 0.45
        run = svc.get_run(run_ids[0])
        assert run["status"] == "COMPLETED"
        # Reload persistence: everything still there.
        run_again = svc.get_run(run_ids[0])
        assert json.loads(run_again["metrics"])["shots"] == 512

    def test_export_reload_consistency(self, db):
        """§168: save -> export -> reload consistency."""
        svc = self._service(db)
        spec = ExperimentSpec(name="export check", module="circuit_shots",
                              config={"circuit": bell_circuit_document(), "shots": 64},
                              seed=2)
        exp = svc.create_experiment(spec)
        rid = svc.create_runs_for_experiment(exp)[0]
        svc.execute_run_now(rid)
        exported = {
            "experiment": svc.get_experiment(exp),
            "run": svc.get_run(rid),
            "result": svc.get_result(rid),
        }
        blob = json.dumps(exported)
        reloaded = json.loads(blob)
        assert reloaded["result"]["document"]["module"] == "circuit_shots"
        assert reloaded["run"]["status"] == "COMPLETED"

    def test_failed_run_records_error_not_fake_success(self, db):
        """§293/§329: failures are recorded as failures."""
        svc = self._service(db)
        bad_doc = bell_circuit_document()
        bad_doc["operations"][0]["qubits"] = [99]  # corrupt on purpose
        spec = ExperimentSpec(name="bad run", module="circuit_shots",
                              config={"circuit": bad_doc, "shots": 8}, seed=1)
        exp = svc.create_experiment(spec)
        rid = svc.create_runs_for_experiment(exp)[0]
        with pytest.raises(Exception):
            svc.execute_run_now(rid)
        run = svc.get_run(rid)
        assert run["status"] == "FAILED"
        assert run["error_code"]

    def test_compare_runs_reports_differing_parameters(self, db):
        """§107 comparison."""
        svc = self._service(db)
        spec = ExperimentSpec(
            name="compare me", module="bb84_study",
            config={"n_qubits": 128, "eve_intercept_percent": [0]},
            seed=4,
        )
        exp = svc.create_experiment(spec)
        ids = svc.create_runs_for_experiment(exp)
        for rid in ids:
            svc.execute_run_now(rid)
        cmp = svc.compare_runs(ids)
        assert cmp["differing_parameters"] == []
        # Now two runs differing in n_qubits:
        spec2 = ExperimentSpec(
            name="compare me v2", module="bb84_study",
            config={"n_qubits": 128, "eve_intercept_percent": [0, 100]},
            sweep=[SweepParameter("n_qubits", [128, 256])], seed=4,
        )
        exp2 = svc.create_experiment(spec2)
        ids2 = svc.create_runs_for_experiment(exp2)
        cmp2 = svc.compare_runs(ids2[:2])
        assert "n_qubits" in cmp2["differing_parameters"] or \
               any("eve" in k for k in cmp2["differing_parameters"])

    def test_notes_and_audit_trail(self, db):
        svc = self._service(db)
        spec = ExperimentSpec(name="noted", module="bb84_study",
                              config={"n_qubits": 64}, seed=1)
        exp = svc.create_experiment(spec, objective="demo", hypothesis="QBER ~ 25% under Eve")
        svc.db.execute(
            "INSERT INTO notes (experiment_id, body, created_at) VALUES (?, ?, ?)",
            (exp, "Fidelity degrades sharply above 200 km.", "2026-08-25T00:00:00+00:00"))
        audits = svc.db.query("SELECT * FROM audit_log WHERE entity='experiment'")
        assert any(a["action"] == "created" for a in audits)


class TestJobQueue:
    def test_job_completes_and_updates_progress(self, db):
        svc = ExperimentService(db)
        spec = ExperimentSpec(name="job test", module="circuit_shots",
                              config={"circuit": bell_circuit_document(), "shots": 128},
                              seed=6)
        exp = svc.create_experiment(spec)
        rid = svc.create_runs_for_experiment(exp)[0]
        jq = JobQueue(db=db, workers=1)
        updates: list[float] = []
        job = jq.submit_run_job(rid, lambda r, cb=None: svc.execute_run_now(r, cb))
        jq.subscribe(lambda j: updates.append(j.progress))
        jq.start()
        import time

        for _ in range(200):
            if job.status == "COMPLETED":
                break
            time.sleep(0.05)
        assert job.status == "COMPLETED"
        assert job.result is not None
        assert svc.get_run(rid)["status"] == "COMPLETED"
        jq.shutdown()

    def test_failing_job_does_not_kill_queue(self, db):
        svc = ExperimentService(db)
        bad = bell_circuit_document()
        bad["operations"][0]["qubits"] = [42]
        spec = ExperimentSpec(name="will fail", module="circuit_shots",
                              config={"circuit": bad, "shots": 8}, seed=1)
        exp = svc.create_experiment(spec)
        rid_bad = svc.create_runs_for_experiment(exp)[0]

        good_spec = ExperimentSpec(name="will pass", module="circuit_shots",
                                   config={"circuit": bell_circuit_document(), "shots": 32},
                                   seed=2)
        exp2 = svc.create_experiment(good_spec)
        rid_good = svc.create_runs_for_experiment(exp2)[0]

        jq = JobQueue(db=db, workers=1)
        jbad = jq.submit_run_job(rid_bad, lambda r, cb=None: svc.execute_run_now(r, cb))
        jgood = jq.submit_run_job(rid_good, lambda r, cb=None: svc.execute_run_now(r, cb))
        jq.start()
        import time

        for _ in range(200):
            if jgood.status in ("COMPLETED", "FAILED"):
                break
            time.sleep(0.05)
        assert jbad.status == "FAILED"
        assert jgood.status == "COMPLETED"
        jq.shutdown()

    def test_cancel_queued_job(self, db):
        svc = ExperimentService(db)
        spec = ExperimentSpec(name="cancel me", module="bb84_study",
                              config={"n_qubits": 64}, seed=1)
        exp = svc.create_experiment(spec)
        rid = svc.create_runs_for_experiment(exp)[0]
        jq = JobQueue(db=db, workers=1)
        job = jq.submit_run_job(rid, lambda r, cb=None: svc.execute_run_now(r, cb))
        assert jq.cancel_job(job.id)
        jq.start()
        import time

        for _ in range(40):
            if job.status == "CANCELLED":
                break
            time.sleep(0.05)
        assert job.status == "CANCELLED"
        jq.shutdown()


class TestNewRunners:
    def test_purification_study_runner(self, db):
        svc = ExperimentService(db)
        spec = ExperimentSpec(name="purify", module="purification_study",
                              config={"initial_fidelity": 0.85, "max_rounds": 3,
                                      "target_fidelity": 0.95}, seed=2)
        exp = svc.create_experiment(spec)
        rid = svc.create_runs_for_experiment(exp)[0]
        doc = svc.execute_run_now(rid)
        assert doc["metrics"]["bbpsw_achieved"] in (True, False)
        assert "analytic_trajectories" in doc["artifacts"]

    def test_repeater_study_runner(self, db):
        svc = ExperimentService(db)
        spec = ExperimentSpec(name="rep", module="repeater_study",
                              config={"distances_km": [60, 240],
                                      "levels": ["L0_direct", "L1_swapping"],
                                      "requests_per_point": 8}, seed=5)
        exp = svc.create_experiment(spec)
        rid = svc.create_runs_for_experiment(exp)[0]
        doc = svc.execute_run_now(rid)
        rows = doc["artifacts"]["table"]
        assert len(rows) == 4
        for row in rows:
            assert row["ci95_low"] <= row["success_probability"] <= row["ci95_high"]

    def test_network_bb84_runner_with_sweep(self, db):
        svc = ExperimentService(db)
        spec = ExperimentSpec(name="netqkd", module="network_bb84",
                              config={"mode": "distance_sweep",
                                      "distances_km": [10, 80, 160],
                                      "n_signals": 512}, seed=7)
        exp = svc.create_experiment(spec)
        rid = svc.create_runs_for_experiment(exp)[0]
        doc = svc.execute_run_now(rid)
        table = doc["artifacts"]["table"]
        det = [r["detected"] for r in table]
        assert det[0] >= det[-1]  # loss model reduces detections with distance


class TestReproducibilityAndExport:
    def test_reproduce_deterministic_run_exact_match(self, db):
        """§44: same config+seed => identical result document."""
        svc = ExperimentService(db)
        spec = ExperimentSpec(name="deterministic", module="circuit_shots",
                              config={"circuit": bell_circuit_document(),
                                      "shots": 256},
                              seed=77)
        exp = svc.create_experiment(spec)
        rid = svc.create_runs_for_experiment(exp)[0]
        svc.execute_run_now(rid)
        report = svc.reproduce_run(rid)
        assert report.status == "EXACT_MATCH", report.differences
        assert report.reproduced_run_id != rid
        # original untouched:
        assert svc.get_run(rid)["status"] == "COMPLETED"

    def test_export_csv_contains_provenance_columns(self, db):
        svc = ExperimentService(db)
        spec = ExperimentSpec(name="csv check", module="qec_sweep",
                              config={"code": "bit-flip-3",
                                      "physical_error_permille": [5],
                                      "trials_per_point": 200}, seed=9)
        exp = svc.create_experiment(spec)
        rid = svc.create_runs_for_experiment(exp)[0]
        svc.execute_run_now(rid)
        csv_text = svc.export_run_csv(rid)
        header = csv_text.splitlines()[0]
        assert "experiment_id" in header and "seed" in header and "run_id" in header
        assert len(csv_text.splitlines()) >= 2

    def test_reproduce_rejects_incomplete_run(self, db):
        svc = ExperimentService(db)
        spec = ExperimentSpec(name="not run yet", module="bb84_study",
                              config={"n_qubits": 64}, seed=1)
        exp = svc.create_experiment(spec)
        rid = svc.create_runs_for_experiment(exp)[0]
        with pytest.raises(ValueError, match="only COMPLETED"):
            svc.reproduce_run(rid)


class TestStatisticsSubsystem:
    def test_summary_includes_n_and_interval(self):
        from app.analytics.statistics import summarize_samples, proportion_summary
        import numpy as np

        vals = list(np.random.default_rng(1).normal(10, 2, size=200))
        s = summarize_samples(vals)
        assert s["n"] == 200
        assert abs(s["mean"] - 10) < 0.5
        assert s["ci_low"] < s["mean"] < s["ci_high"]
        assert s["small_sample_warning"] is False

    def test_proportion_summary_explicit_counts(self):
        from app.analytics.statistics import proportion_summary

        p = proportion_summary(3, 100)
        assert p["successes"] == 3 and p["trials"] == 100
        assert p["proportion"] == 0.03
        assert p["ci_low"] <= 0.03 <= p["ci_high"]

    def test_bootstrap_median_robust(self):
        from app.analytics.statistics import bootstrap_confidence_interval

        vals = [1.0] * 50 + [1000.0]   # heavy outlier
        ci = bootstrap_confidence_interval(vals, statistic="median", seed=3)
        assert ci.low == pytest.approx(1.0)
        assert ci.high == pytest.approx(1.0)
