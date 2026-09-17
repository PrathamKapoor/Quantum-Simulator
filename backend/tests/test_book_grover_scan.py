"""Grover scan validation must test evolution, not sampled peak placement."""
import pytest

from app.experiments.runner import execute_run


def test_scan_before_optimum_validates_exact_rotation():
    result = execute_run("book_grover_scan", {
        "n_qubits": 3, "target": 5, "max_iterations": 1,
    }, 17)
    row = result["artifacts"]["scan"][0]
    # One Grover iteration with N=8 gives sin(3 asin(1/sqrt(8)))^2 = 25/32.
    assert row["exact_success_probability"] == pytest.approx(25 / 32, abs=1e-12)
    assert row["analytic_success_probability"] == pytest.approx(25 / 32, abs=1e-12)
    assert row["success_probability"] == row["successes"] / row["shots"]
    validation = result["summary"]["validation"]
    assert validation["optimal_iterations_theory"] == 2
    assert validation["measured_peak_iterations"] == 1
    assert validation["passed"] is True
