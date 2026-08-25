"""Algorithm tests (directive §140)."""
import math

import numpy as np
import pytest

from app.algorithms import (
    OracleSpec,
    run_deutsch,
    run_deutsch_jozsa,
    build_bernstein_vazirani,
    run_bernstein_vazirani,
    make_simon_problem,
    run_simon,
    run_grover,
    grover_optimal_iterations,
    run_superdense,
    build_qft,
    dft_matrix,
    run_phase_estimation,
    run_order_finding,
    factorize_bounded,
    discrete_quantum_walk,
)
from app.circuits import simulate, Circuit
from app.quantum.states import StateVector, QuantumCoreError


class TestDeutschJozsa:
    def test_constant_detected(self):
        result = run_deutsch_jozsa(OracleSpec.constant(3, 1), seed=0)
        assert result["correct"] and result["verdict"] == "constant"

    def test_balanced_detected(self):
        result = run_deutsch_jozsa(OracleSpec.balanced(3, seed=4), seed=0)
        assert result["correct"] and result["verdict"] == "balanced"

    def test_deutsch_both_parities(self):
        assert run_deutsch(0)["verdict"] == "constant"
        assert run_deutsch(1)["verdict"] == "balanced"


class TestBernsteinVazirani:
    @pytest.mark.parametrize("secret", [0b101, 0b1101, 0])
    def test_recovers_secret(self, secret):
        result = run_bernstein_vazirani(secret)
        n = max(1, int(secret).bit_length()) if secret else 1
        expected = format(secret, f"0{n}b")
        assert result["recovered"] == expected
        assert result["correct"]

    def test_string_secret(self):
        r = run_bernstein_vazirani("11001")
        assert r["recovered"] == "11001"


class TestSimon:
    def test_hidden_mask_recovered(self):
        problem = make_simon_problem(3, "101", seed=5)
        result = run_simon(problem, shots=48, seed=11)
        assert result["correct"], result

    def test_two_to_one_table(self):
        problem = make_simon_problem(3, "011", seed=2)
        for x in range(8):
            assert problem.evaluate(x) == problem.evaluate(x ^ 0b011)


class TestGrover:
    def test_finds_marked_state(self):
        res = run_grover(3, marked_index=5, shots=1024, seed=7)
        assert res.success_probability_estimate > 0.85

    def test_per_iteration_peak_near_optimal(self):
        res = run_grover(4, marked_index=9, shots=None or 512, seed=1)
        probs = res.per_iteration_probabilities
        best_iter = int(np.argmax(probs)) + 1
        # Optimal iteration count should be within 1 of the true peak.
        assert abs(best_iter - res.optimal_iterations) <= 1
        assert max(probs) > 0.9

    def test_optimal_iteration_formula_sanity(self):
        # For N=8, M=1: optimal ≈ round(pi/4 * sqrt(N)) = 2.
        assert grover_optimal_iterations(3) in (2,)


class TestSuperdense:
    @pytest.mark.parametrize("bits", ["00", "01", "10", "11"])
    def test_all_bit_pairs(self, bits):
        res = run_superdense(bits, shots=128, seed=3)
        assert res["success_rate"] == 1.0


class TestQFT:
    def _apply_circuit_matrix(self, circuit: Circuit) -> np.ndarray:
        """Exact matrix of a unitary-only circuit by applying to basis states."""
        from app.circuits.model import Operation

        dim = 1 << circuit.num_qubits
        cols = []
        for i in range(dim):
            ops = [
                Operation(kind="gate", gate="X", params=(), qubits=(q,))
                for q in range(circuit.num_qubits)
                if (i >> q) & 1
            ]
            full = Circuit(
                num_qubits=circuit.num_qubits,
                operations=ops + list(circuit.operations),
            )
            res = simulate(full, shots=None)
            cols.append(res.final_state.amplitudes)
        return np.column_stack(cols)

    def test_qft_matches_dft_matrix_3q(self):
        circuit, info = build_qft(3)
        assert not info.approximate
        actual = self._apply_circuit_matrix(circuit)
        expected = dft_matrix(3)
        assert np.allclose(actual, expected, atol=1e-10)

    def test_inverse_qft_is_inverse(self):
        qft_c, _ = build_qft(2)
        iqft_c, _ = build_qft(2, inverse=True)
        m = self._apply_circuit_matrix(iqft_c) @ self._apply_circuit_matrix(qft_c)
        assert np.allclose(m, np.eye(4), atol=1e-10)

    def test_qft_of_basis_state(self):
        # QFT|q2=1> (index 4 of 3 qubits) -> uniform magnitudes.
        circuit, _ = build_qft(3)
        from app.circuits.model import Operation

        full = Circuit(num_qubits=3, operations=[
            Operation(kind="gate", gate="X", params=(), qubits=(2,))] + list(circuit.operations))
        res = simulate(full, shots=None)
        probs = res.final_state.probabilities()
        assert np.allclose(probs, np.full(8, 1 / 8), atol=1e-12)

    def test_approximate_qft_flags_itself(self):
        _, info = build_qft(4, cutoff_exponent=1)
        assert info.approximate
        assert info.dropped_rotations > 0
        assert info.warnings


class TestPhaseEstimation:
    def test_estimates_known_phase_gate(self):
        theta = 0.25  # U = diag(1, e^{2πiθ}): |1> has eigenphase θ
        t = 6
        u = np.diag([1.0, np.exp(2j * np.pi * theta)])
        res = run_phase_estimation(
            u, StateVector.basis_state(1, 1), t,
            known_eigenphase=theta, seed=5, shots=64,
        )
        assert abs(res.error) < 1 / (1 << (t - 2)), res

    def test_eigenstate_zero_phase(self):
        u = np.diag([1.0, -1.0])  # Z: |0> has phase 0
        res = run_phase_estimation(u, StateVector.zero(1), 5, known_eigenphase=0.0, seed=1, shots=32)
        assert res.measured_integer == 0


class TestShorBounded:
    def test_modular_matrix_is_permutation(self):
        perm, L = __import__("app.algorithms", fromlist=["modular_multiplication_matrix"]).modular_multiplication_matrix(7, 15)
        assert np.allclose(perm.sum(axis=0), 1)
        assert np.allclose(perm.sum(axis=1), 1)

    def test_order_finding_finds_order(self):
        res = run_order_finding(7, 15, seed=42, shots=256)
        assert res.true_order == 4
        assert res.success, f"phases={res.measured_phases_top}"

    def test_factorize_bounded_15(self):
        out = factorize_bounded(15, seed=3)
        factors = sorted(out["factors"])
        assert factors == [3, 5]

    def test_rejects_large_N(self):
        with pytest.raises(QuantumCoreError):
            factorize_bounded(97)


class TestQuantumWalk:
    def test_quantum_spreads_faster_than_classical(self):
        # On a line-like regime (cycle long enough that walks do not wrap),
        # the quantum walker spreads quadratically faster: Var ~ t^2 vs t.
        out = discrete_quantum_walk(5, steps=8)
        assert out["quantum_std"] > 1.3 * out["classical_std"]
        q = np.array(out["quantum_distribution"])
        assert abs(q.sum() - 1) < 1e-9
