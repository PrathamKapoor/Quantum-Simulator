"""Independent mathematical contracts for bounded book algorithm studies."""
import math

import numpy as np
import pytest

from app.algorithms.core_algorithms import (
    SimonProblem, make_simon_problem, run_simon, build_simon_circuit,
    build_grover_circuit, run_grover, grover_optimal_iterations,
)
from app.algorithms.qft import build_qft
from app.algorithms.phase_estimation_shor import run_phase_estimation
from app.circuits.simulate import simulate
from app.quantum.states import StateVector, QuantumCoreError


def test_simon_low_register_equations_identify_unique_nonzero_mask():
    result = run_simon(make_simon_problem(3, "101"), shots=64, seed=11)
    equations = result["independent_equations"]
    candidates = [s for s in range(1, 8)
                  if all((int(y, 2) & s).bit_count() % 2 == 0 for y in equations)]
    assert candidates == [5]
    assert result["rank"] == 2
    assert result["stopping_reason"] == "rank_reached"
    assert result["shots_used"] <= 64
    assert result["recovered_mask"] == "101"
    assert all(0 <= y < 8 and (y & 5).bit_count() % 2 == 0
               for y in result["orthogonal_samples"])


def test_simon_budget_exhaustion_does_not_claim_recovery():
    result = run_simon(make_simon_problem(3, "110"), shots=1, seed=2)
    assert result["rank"] < 2
    assert result["recovered_mask"] is None
    assert result["stopping_reason"] == "shot_budget_exhausted"
    assert not result["correct"]


def test_simon_nonzero_promise_and_minimal_register():
    with pytest.raises(QuantumCoreError):
        make_simon_problem(2, "00")
    with pytest.raises(QuantumCoreError):
        build_simon_circuit(SimonProblem(2, "01", {0: 0, 1: 0, 2: 0, 3: 0}))
    result = run_simon(make_simon_problem(1, "1"), shots=1)
    assert result["recovered_mask"] == "1"
    assert result["rank"] == 0
    assert result["shots_used"] == 0  # unique from the nonzero promise alone


def test_qft_cutoff_uses_rotation_denominator_exponent():
    state = StateVector.basis_state(3, 3)
    exact, exact_info = build_qft(3, cutoff_exponent=3)
    actual = simulate(exact, initial_state=state).final_state.amplitudes
    expected = np.exp(2j * np.pi * 3 * np.arange(8) / 8) / np.sqrt(8)
    np.testing.assert_allclose(actual, expected, atol=1e-12)
    assert not exact_info.approximate
    truncated, info = build_qft(3, cutoff_exponent=2)
    approximate = simulate(truncated, initial_state=state).final_state.amplitudes
    assert info.dropped_rotations == 1  # CP(pi/4), not CP(pi/2)
    # Removing CP(pi/4) deletes the x0*y0*pi/4 term (after bit reversal).
    truncated_reference = expected * np.exp(-1j * np.pi / 4 * (np.arange(8) & 1))
    np.testing.assert_allclose(approximate, truncated_reference, atol=1e-12)
    inverse, _ = build_qft(3, inverse=True, cutoff_exponent=2)
    restored = simulate(inverse, initial_state=StateVector(approximate, 3)).final_state.amplitudes
    np.testing.assert_allclose(restored, state.amplitudes, atol=1e-12)
    with pytest.raises(ValueError):
        build_qft(3, cutoff_exponent=1.5)


def test_qpe_complex_eigenvector_matches_finite_geometric_sum():
    phi = 0.173
    psi = np.array([1, 2j, -1j, 2], dtype=complex) / np.sqrt(10)
    projector = np.outer(psi, psi.conj())
    unitary = np.eye(4) + (np.exp(2j * np.pi * phi) - 1) * projector
    result = run_phase_estimation(unitary, StateVector(psi, 2), 4,
                                  known_eigenphase=phi, shots=64, seed=18)
    expected = [abs(sum(np.exp(2j * np.pi * x * (phi - y / 16))
                        for x in range(16)) / 16) ** 2 for y in range(16)]
    np.testing.assert_allclose([result.probabilities[f"{y:04b}"] for y in range(16)],
                               expected, atol=1e-12)
    assert result.eigenstate_residual < 1e-12
    assert sum(result.counts.values()) == 64


def test_qpe_rejects_non_eigenstate_nonunitary_and_bad_reference():
    plus = StateVector.from_amplitudes([1 / np.sqrt(2), 1 / np.sqrt(2)])
    with pytest.raises(QuantumCoreError):
        run_phase_estimation(np.diag([1, -1]), plus, 3)
    with pytest.raises(QuantumCoreError):
        run_phase_estimation(np.diag([1, 2]), StateVector.zero(1), 3)
    with pytest.raises(QuantumCoreError):
        run_phase_estimation(np.eye(2), plus, 3, known_eigenphase=0.25)
    with pytest.raises(QuantumCoreError):
        run_phase_estimation(np.eye(2), StateVector(np.array([1.0001, 0]), 1), 3)


def test_qpe_phase_error_wraps_at_one():
    phi = 0.999
    unitary = np.diag([1, np.exp(2j * np.pi * phi)])
    result = run_phase_estimation(unitary, StateVector.basis_state(1, 1), 3,
                                  known_eigenphase=phi, seed=1, shots=32)
    assert result.measured_integer == 0
    assert result.error == pytest.approx(0.001)


@pytest.mark.parametrize("marked", [[1, 6], [0, 1, 2, 3, 4, 7], list(range(8))])
def test_multigrover_probability_matches_two_dimensional_rotation(marked):
    theta = math.asin(math.sqrt(len(marked) / 8))
    for k in range(4):
        circuit, _ = build_grover_circuit(3, marked_indices=marked, iterations=k)
        probabilities = simulate(circuit).final_state.probabilities()
        expected = math.sin((2 * k + 1) * theta) ** 2
        assert sum(probabilities[i] for i in marked) == pytest.approx(expected, abs=1e-12)
    result = run_grover(3, marked_indices=marked, iterations=3, shots=32)
    assert result.exact_success_probability == pytest.approx(math.sin(7 * theta) ** 2)
    np.testing.assert_allclose(result.per_iteration_probabilities,
                              result.analytic_per_iteration_probabilities, atol=1e-12)


def test_multigrover_high_fraction_and_distinct_set_contract():
    assert grover_optimal_iterations(3, 6) == 0
    assert grover_optimal_iterations(3, 8) == 0
    result = run_grover(3, marked_indices=list(range(8)), shots=16)
    assert result.iterations_used == 0
    assert result.success_probability_estimate == 1
    for marked in ([], [1, 1], [8]):
        with pytest.raises(QuantumCoreError):
            build_grover_circuit(3, marked_indices=marked)
    with pytest.raises(QuantumCoreError):
        build_grover_circuit(3, 1, iterations=-1)


def test_book_simon_exhaustion_cannot_pass_validation():
    from app.experiments.book_runner import book_simon
    result = book_simon({"shots": 1}, seed=2)
    validation = result["summary"]["validation"]
    assert not validation["passed"]
    assert validation["candidate_count"] > 1
    assert validation["budget_recovery_probability"] == 0
    assert result["metrics"]["recovered_mask"] is None


def test_book_qft_basis_phase_error_is_not_hidden_by_uniform_probabilities():
    from app.experiments.book_runner import book_qft
    result = book_qft({}, seed=12)
    assert result["summary"]["validation"]["passed"]
    assert result["metrics"]["state_error"] == pytest.approx(np.sqrt(1 - 1 / np.sqrt(2)))
    assert result["metrics"]["fidelity_to_exact"] == pytest.approx((1 + 1 / np.sqrt(2)) / 2)
    exact = book_qft({"input_mode": "seeded_random", "cutoff_exponent": None}, seed=12)
    assert exact["metrics"]["state_error"] < 1e-12


def test_book_qpe_off_grid_probabilities_and_finite_shot_uncertainty():
    from app.experiments.book_runner import book_qpe
    result = book_qpe({"eigenphase": 0.173, "shots": 16}, seed=3)
    rows = result["artifacts"]["distribution"]
    assert result["summary"]["validation"]["passed"]
    for row in rows:
        delta = 0.173 - row["phase"]
        expected = (np.sin(16 * np.pi * delta) / (16 * np.sin(np.pi * delta))) ** 2
        assert row["probability"] == pytest.approx(expected, abs=1e-12)
        interval = row["sampling"]
        assert interval["ci_low"] <= interval["proportion"] <= interval["ci_high"]
        assert interval["ci_high"] > interval["ci_low"]
    assert sum(row["sampling"]["successes"] for row in rows) == 16


def test_book_multigrover_high_fraction_includes_zero_queries():
    from app.experiments.book_runner import book_multigrover
    result = book_multigrover({"marked_indices": list(range(6)), "max_iterations": 2, "shots": 16}, seed=5)
    assert result["metrics"]["optimal_iterations"] == 0
    rows = result["artifacts"]["sweep"]
    np.testing.assert_allclose([row["exact_success_probability"] for row in rows], [0.75, 0, 0.75], atol=1e-12)
    assert rows[1]["sampling"]["ci_high"] > 0  # zero observed hits is not certainty
    assert result["summary"]["validation"]["passed"]


@pytest.mark.parametrize("name,config", [
    ("book_simon", {"n_qubits": 5}), ("book_simon", {"secret": 0}),
    ("book_qft", {"n_qubits": 7}), ("book_qft", {"cutoff_exponent": 2.5}),
    ("book_qpe", {"precision_bits": 7}), ("book_qpe", {"eigenphase": 1}),
    ("book_multigrover", {"marked_indices": [1, 1]}),
    ("book_multigrover", {"max_iterations": 9}),
])
def test_book_algorithm_wrappers_reject_out_of_domain_requests(name, config):
    from app.experiments import book_runner
    with pytest.raises(ValueError):
        getattr(book_runner, name)(config, seed=1)
