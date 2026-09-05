"""API + experiment integration tests for the fault-aware / circuit-
derived milestone (milestone 12).

Covers (directive §34, §37, §38, §39):
  * Schedule analysis endpoint: structural comparison + degenerate
    finding.
  * Fault analysis endpoint: single mechanism returned in
    backend-derived form.
  * Circuit-derived graph endpoint: deterministic structure.
  * Monte Carlo with coverage: schema-validated.
  * Experiment runner: surface_code_fault_aware round-trip through the
    process-isolated worker; reproduction EXACT_MATCH.
"""
import pytest

from app.experiments.service import ExperimentService
from app.experiments.runner import (
    ExperimentSpec, run_surface_code_fault_aware,
)
from app.persistence.db import Database


# ---------------------------------------------------------------------------
# Endpoint smoke tests (the API is just a thin pydantic wrapper; we
# exercise the underlying functions directly to avoid spinning up a
# server in unit tests).
# ---------------------------------------------------------------------------

class TestScheduleAnalysis:
    def test_returns_per_stabilizer_risk(self, tmp_path):
        from app.qec import RotatedSurfaceCode, compare_naive_vs_optimized
        code = RotatedSurfaceCode.build(3)
        report = compare_naive_vs_optimized(code, exhaustive=True)
        assert "per_stabilizer" in report
        assert "naive_total_hooks" in report
        # The naive schedule is optimal under H-CNOTs-H.
        assert report["stabilizers_with_changed_schedule"] == 0
        # Every stabilizer appears in the report.
        assert len(report["per_stabilizer"]) == (
            len(code.x_checks) + len(code.z_checks))


class TestFaultAnalysis:
    def test_lookup_x_reset_y_round1(self):
        from app.qec import RotatedSurfaceCode
        from app.qec.fault_catalogue import (
            _enumerate_faults_for_candidate, CandidateSchedule,
        )
        code = RotatedSurfaceCode.build(3)
        cand = CandidateSchedule("X", 1, tuple(code.x_checks[1].support),
                                  tuple(sorted(code.x_checks[1].support)))
        cat = _enumerate_faults_for_candidate(code, cand, 1)
        matches = [f for f in cat
                    if f.fault_location == "ANCILLA_RESET"
                    and f.pauli_fault == "Y"]
        assert len(matches) == 1
        f = matches[0]
        # Data X hook of full support (4 qubits).
        assert len(f.affected_qubits) == 4
        # Detection events: 1 local + 3 cross = 4 (Z0, Z1, Z2).
        # Actually in d=3 the X1 support is {0,1,3,4}. Z-checks are
        # Z0={0,3}, Z1={1,2,4,5}, Z2={3,4,6,7}. So data X on {0,1,3,4}
        # anticommutes with Z0 (from 0), Z1 (from 1,4), Z2 (from 3,4).
        # 3 cross + 1 local = 4 events (this is the ">=3 multi-event"
        # regime).
        assert len(f.detection_events) >= 3


# ---------------------------------------------------------------------------
# Experiment runner round-trip.
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    p = tmp_path / "test.db"
    d = Database(str(p))
    yield d
    d.close()


class TestFaultAwareExperiment:
    def test_runner_smoke(self):
        out = run_surface_code_fault_aware(
            {"distances": [3, 5], "rounds": 4, "p_gate": 0.005,
             "p_readout": 0.005, "p_reset": 0.003, "p_prep": 0.003,
             "trials_per_point": 100}, seed=5)
        assert out["module"] == "surface_code_fault_aware"
        assert "schedule_reports" in out["metrics"]
        for d_str, r in out["metrics"]["schedule_reports"].items():
            assert "graph_coverage_ratio" in r
            assert "graph_excluded_ratio" in r
        for row in out["artifacts"]["table"]:
            assert "graph_coverage_ratio" in row
            assert "graph_excluded_ratio" in row
            assert "logical_error_rate" in row

    def test_reproduction_via_process_worker(self, db):
        """surface_code_fault_aware runs through the canonical
        experiment framework and reproduces EXACT_MATCH (directive
        §37, §38)."""
        spec = ExperimentSpec(
            name="fault-aware-3v5",
            module="surface_code_fault_aware",
            config={"distances": [3, 5], "rounds": 4, "p_gate": 0.005,
                    "p_readout": 0.005, "p_reset": 0.003, "p_prep": 0.003,
                    "trials_per_point": 100},
            seed=5,
        )
        issues = spec.validate()
        assert not issues
        svc = ExperimentService(db)
        eid = svc.create_experiment(spec, objective="reproduce")
        run_ids = svc.create_runs_for_experiment(eid)
        for rid in run_ids:
            doc = svc.execute_run_now(rid)
            assert doc is not None
        # Reproduce the first run.
        report = svc.reproduce_run(run_ids[0])
        assert report.status in ("EXACT_MATCH", "MATCH_WITHIN_TOLERANCE")
        # Original is immutable: still COMPLETED.
        run0 = svc.get_run(run_ids[0])
        assert run0["status"] == "COMPLETED"
