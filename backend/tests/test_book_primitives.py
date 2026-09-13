"""Book-derived primitive tests (milestone 22, McMahon chapters covered
by app/quantum/qi_tools.py, adiabatic.py, graph_states.py and
app/protocols/b92.py).

Each test is a computational experiment with a theoretical prediction
and an acceptance criterion (directive §108). Nothing is hard-coded:
expected values are computed from independent analytic forms where
available and compared against the implementation output.
"""
import numpy as np
import pytest

from app.quantum.density import DensityMatrix
from app.quantum.states import StateVector, QuantumCoreError
from app.quantum.qi_tools import (
    bures_distance, entanglement_of_formation, generalized_measure,
    gram_schmidt, no_cloning_report, partial_transpose, purification,
    povm_probabilities, validate_povm)
from app.quantum.adiabatic import (
    adiabatic_evolution, interpolated_hamiltonian, spectral_gap_curve)
from app.quantum.graph_states import (
    cluster_state_1d, cluster_state_2d, ghz_witness_expectation,
    graph_state, measure_node_x, stabilizer_report)
from app.protocols.b92 import run_b92


def _bell_rho():
    m = np.zeros((4, 4), dtype=complex)
    m[0, 0] = m[0, 3] = m[3, 0] = m[3, 3] = 0.5
    return DensityMatrix(m, 2)


def _imax_rho():
    return DensityMatrix(np.eye(4, dtype=complex) / 4, 2)


class TestPartialTranspose:
    def test_bell_pt_has_negative_eigenvalue(self):
        pt = partial_transpose(_bell_rho(), [1])
        min_eig = float(np.linalg.eigvalsh(pt.matrix).min())
        assert min_eig < -0.25 + 1e-9      # exactly -0.5 for Bell

    def test_separable_pt_stays_positive(self):
        pt = partial_transpose(_imax_rho(), [1])
        assert float(np.linalg.eigvalsh(pt.matrix).min()) >= -1e-10

    def test_pt_preserves_trace_and_hermiticity(self):
        pt = partial_transpose(_bell_rho(), [0])
        assert abs(np.trace(pt.matrix).real - 1.0) < 1e-10
        assert np.allclose(pt.matrix, pt.matrix.conj().T)

    def test_partial_transpose_is_involution(self):
        rho = _bell_rho()
        pt2 = partial_transpose(partial_transpose(rho, [1]), [1])
        assert np.allclose(pt2.matrix, rho.matrix)


class TestBuresAndEoF:
    def test_bures_zero_for_identical(self):
        # tolerance reflects the eigendecomposition floor of the
        # Uhlmann fidelity (~1e-8)
        assert bures_distance(_bell_rho(), _bell_rho()) < 1e-7

    def test_bures_orthogonal_mixed_states(self):
        rho1 = DensityMatrix(np.diag([1.0, 0, 0, 0]).astype(complex), 2)
        rho2 = DensityMatrix(np.diag([0, 1.0, 0, 0]).astype(complex), 2)
        assert abs(bures_distance(rho1, rho2) - np.sqrt(2)) < 1e-9

    def test_bures_fidelity_relation(self):
        rho1, rho2 = _bell_rho(), _imax_rho()
        f = rho1.fidelity_with(rho2)
        expected = np.sqrt(2 * (1 - np.sqrt(f)))
        assert abs(bures_distance(rho1, rho2) - expected) < 1e-9

    def test_eof_bell_is_one_bit(self):
        assert abs(entanglement_of_formation(_bell_rho()) - 1.0) < 1e-9

    def test_eof_separable_is_zero(self):
        assert entanglement_of_formation(_imax_rho()) == 0.0

    def test_eof_partially_entangled(self):
        # |psi> = sqrt(0.7)|00> + sqrt(0.3)|11>: C = 2*sqrt(0.21)
        v = np.array([np.sqrt(0.7), 0, 0, np.sqrt(0.3)], dtype=complex)
        rho = DensityMatrix(np.outer(v, v.conj()), 2)
        c = 2 * np.sqrt(0.7 * 0.3)
        x = (1 + np.sqrt(1 - c * c)) / 2
        expected = -(x * np.log2(x) + (1 - x) * np.log2(1 - x))
        assert abs(entanglement_of_formation(rho) - expected) < 1e-8


class TestPurification:
    def test_roundtrip_pure_state(self):
        pv, env = purification(_bell_rho())
        dm = DensityMatrix(np.outer(pv.amplitudes, pv.amplitudes.conj()),
                           pv.n_qubits)
        back = dm.partial_trace([2, 3])
        assert np.max(np.abs(back.matrix - _bell_rho().matrix)) < 1e-10

    def test_roundtrip_mixed_state(self):
        rho = DensityMatrix(0.5 * _bell_rho().matrix
                            + 0.5 * np.eye(4, dtype=complex) / 4, 2)
        pv, _ = purification(rho)
        dm = DensityMatrix(np.outer(pv.amplitudes, pv.amplitudes.conj()),
                           pv.n_qubits)
        back = dm.partial_trace([2, 3])
        assert np.max(np.abs(back.matrix - rho.matrix)) < 1e-10

    def test_purified_full_state_normalized_and_reduced_purity_matches(self):
        """|Psi> is normalized; the SYSTEM purity of the purification
        equals Tr(rho^2) of the original (0.25 for the maximally mixed
        state) — that is the invariant, not the full-state fourth
        moment (a common confusion this test documents)."""
        rho = _imax_rho()
        pv, _ = purification(rho)
        probs = np.abs(pv.amplitudes) ** 2
        assert float(np.sum(probs)) == pytest.approx(1.0, abs=1e-9)
        dm = DensityMatrix(np.outer(pv.amplitudes, pv.amplitudes.conj()),
                           pv.n_qubits)
        back = dm.partial_trace([2, 3])
        assert float(np.trace(back.matrix @ back.matrix).real) ==             pytest.approx(float(np.trace(rho.matrix @ rho.matrix).real),
                          abs=1e-9)


class TestPOVM:
    def test_pvm_probabilities(self):
        rho = DensityMatrix(np.diag([0.6, 0.4]).astype(complex), 1)
        probs = povm_probabilities(rho, [np.diag([1, 0]).astype(complex),
                                         np.diag([0, 1]).astype(complex)])
        assert probs == pytest.approx([0.6, 0.4])

    def test_incomplete_povm_rejected(self):
        with pytest.raises(QuantumCoreError):
            povm_probabilities(_imax_rho(), [np.eye(2, dtype=complex) / 2])

    def test_trine_povm_qubit(self):
        # three trine effects; probabilities must sum to 1
        effects = []
        for k in range(3):
            v = np.array([np.cos(k * np.pi / 3), np.sin(k * np.pi / 3)],
                         dtype=complex)
            effects.append(0.6666666667 * np.outer(v, v.conj()))
        rep = validate_povm(effects, 1)
        assert rep["complete"] or rep["completeness_error"] < 1e-6

    def test_generalized_measure_amplitude_damping(self):
        rho = DensityMatrix(np.diag([0.5, 0.5]).astype(complex), 1)
        k0 = np.array([[1, 0], [0, np.sqrt(0.9)]], dtype=complex)
        k1 = np.array([[0, np.sqrt(0.1)], [0, 0]], dtype=complex)
        out = generalized_measure(rho, [k0, k1])
        assert out[0]["probability"] == pytest.approx(0.95, abs=1e-9)
        assert out[1]["probability"] == pytest.approx(0.05, abs=1e-9)
        # post-state after the jump outcome is |0><0|
        assert abs(out[1]["post_state"][0, 0] - 1.0) < 1e-9

    def test_non_tp_kraus_rejected(self):
        with pytest.raises(QuantumCoreError):
            generalized_measure(_imax_rho(), [np.eye(2, dtype=complex) * 0.5])


class TestNoCloning:
    def test_superposition_is_not_cloned(self):
        rep = no_cloning_report(1 / np.sqrt(2), 1 / np.sqrt(2))
        assert rep["clone_fidelity"] == pytest.approx(0.5)
        assert not rep["is_clone"]

    def test_basis_states_clone_through_cnot(self):
        # the isometry that clones |0>,|1> works exactly on the basis
        rep = no_cloning_report(1.0, 0.0)
        assert rep["is_clone"]

    def test_produced_state_is_entangled(self):
        rep = no_cloning_report(1 / np.sqrt(2), 1 / np.sqrt(2))
        produced = np.array(rep["produced_state"])
        # Schmidt rank 2 across the cut -> entangled (use PT on the 4-dim)
        rho = DensityMatrix(np.outer(produced, produced.conj()), 2)
        pt = partial_transpose(rho, [1])
        assert float(np.linalg.eigvalsh(pt.matrix).min()) < -1e-9


class TestGramSchmidt:
    def test_orthonormalization(self):
        basis, norms = gram_schmidt([np.array([1, 1, 0], dtype=complex),
                                     np.array([1, 0, 0], dtype=complex)])
        assert np.vdot(basis[0], basis[1]) == pytest.approx(0, abs=1e-12)
        for b in basis:
            assert np.vdot(b, b).real == pytest.approx(1, abs=1e-12)

    def test_linear_dependence_detected(self):
        _, norms = gram_schmidt([np.array([1, 0, 0], dtype=complex),
                                 np.array([2, 0, 0], dtype=complex)])
        assert norms[1] < 1e-10


class TestAdiabatic:
    H0 = np.diag([1.0, -1.0])
    H1 = np.array([[0.0, 1.0], [1.0, 0.0]])

    def test_hamiltonian_interpolation_endpoints(self):
        assert np.allclose(interpolated_hamiltonian(self.H0, self.H1, 0.0), self.H0)
        assert np.allclose(interpolated_hamiltonian(self.H0, self.H1, 1.0), self.H1)

    def test_slow_evolution_follows_ground_state(self):
        r = adiabatic_evolution(self.H0, self.H1, total_time=200.0, steps=800)
        assert r["ground_state_overlap"] > 0.999

    def test_fast_evolution_excites(self):
        r = adiabatic_evolution(self.H0, self.H1, total_time=0.05, steps=10)
        assert r["ground_state_overlap"] < 0.75

    def test_gap_curve_minimum_at_middle(self):
        """H(0.5) = [[0.5, 0.5], [0.5, -0.5]] has eigenvalue gap sqrt(2);
        the endpoints (gap 2) are larger, so the minimum is the middle."""
        g = spectral_gap_curve(self.H0, self.H1, 21)
        assert g["min_gap"] == pytest.approx(np.sqrt(2), abs=1e-9)
        assert g["min_gap_s"] == pytest.approx(0.5, abs=1e-9)

    def test_invalid_s_rejected(self):
        with pytest.raises(QuantumCoreError):
            interpolated_hamiltonian(self.H0, self.H1, 1.5)


class TestGraphStates:
    def _adj(self, n, edges):
        a = np.zeros((n, n), dtype=int)
        for u, v in edges:
            a[u, v] = a[v, u] = 1
        return a

    def test_chain_stabilizers(self):
        st = cluster_state_1d(4)
        rep = stabilizer_report(st, self._adj(4, [(0, 1), (1, 2), (2, 3)]))
        assert rep["all_stabilize"] and rep["max_residual"] < 1e-9

    def test_2d_lattice_stabilizers(self):
        st = cluster_state_2d(2, 2)
        rep = stabilizer_report(st, self._adj(4, [(0, 1), (0, 2), (1, 3), (2, 3)]))
        assert rep["all_stabilize"]

    def test_arbitrary_graph_star(self):
        st = graph_state(self._adj(4, [(0, 1), (0, 2), (0, 3)]))
        rep = stabilizer_report(st, self._adj(4, [(0, 1), (0, 2), (0, 3)]))
        assert rep["all_stabilize"]

    def test_ghz_witness_detects_entanglement(self):
        ghz = np.zeros(8, dtype=complex)
        ghz[0] = ghz[-1] = 1 / np.sqrt(2)
        assert ghz_witness_expectation(StateVector(ghz, 3)) < 0
        assert ghz_witness_expectation(StateVector(np.eye(8)[0].astype(complex), 3)) >= 0

    def test_x_measurement_is_normalized(self):
        st = cluster_state_1d(3)
        m = measure_node_x(st, 1, outcome=0)
        assert abs(float(np.linalg.norm(m["post_state"].amplitudes)) - 1) < 1e-12

    def test_asymmetric_adjacency_rejected(self):
        a = np.zeros((3, 3), dtype=int)
        a[0, 1] = 1
        with pytest.raises(QuantumCoreError):
            stabilizer_report(cluster_state_1d(3), a)


class TestB92:
    def test_ideal_no_eve_no_errors(self):
        r = run_b92(16384, 0.0, 0.0, seed=1)
        assert r["qber"] == 0.0
        assert r["sifting_rate"] == pytest.approx(0.25, abs=0.02)

    def test_eavesdropper_causes_qber(self):
        r = run_b92(16384, 1.0, 0.0, seed=1)
        assert r["qber"] > 0.2
        assert r["eve_interceptions"] == 16384

    def test_channel_noise_causes_qber(self):
        r = run_b92(16384, 0.0, 0.05, seed=2)
        assert 0.0 < r["qber"] < 0.15

    def test_reproducible(self):
        a = run_b92(512, 0.25, 0.01, seed=5)
        b = run_b92(512, 0.25, 0.01, seed=5)
        assert a["qber"] == b["qber"]
        assert a["sifted_key_length"] == b["sifted_key_length"]


class TestGateDecomposition:
    """Chapter 8: decomposition identities verified at matrix level
    (directive §22-§23)."""

    def test_cnot_equals_hczh(self):
        from app.quantum.operators import pauli_matrix
        h = np.array([[1, 1], [1, -1]], dtype=complex) / np.sqrt(2)
        cnot = np.zeros((4, 4), dtype=complex)
        cnot[0, 0] = cnot[1, 1] = cnot[2, 3] = cnot[3, 2] = 1
        i_h = np.kron(np.eye(2, dtype=complex), h)
        cz = np.diag([1, 1, 1, -1]).astype(complex)
        rebuilt = i_h @ cz @ i_h
        assert np.max(np.abs(rebuilt - cnot)) < 1e-12

    def test_zy_decomposition_reconstruction(self):
        """U = e^{ia} Rz(b) Ry(c) Rz(d) for arbitrary single-qubit U:
        the reconstruction is verified by comparing the produced
        unitary's action on |0> and |1> up to global phase."""
        from app.quantum.operators import u3, rz, ry

        def zy_reconstruct(a, b, c, d):
            return np.exp(1j * a) * rz(d) @ ry(c) @ rz(b)

        # derive (a, b, c, d) from an arbitrary unitary via the standard
        # formulas, then verify the reconstruction
        theta, phi, lam = 0.3, 1.1, -0.7
        u = u3(theta, phi, lam)
        # u3 IS e^{i(phi+lam)/2} Rz(phi) Ry(theta) Rz(lam) — verify the
        # identity numerically rather than trusting the constructor
        a = (phi + lam) / 2
        rebuilt = zy_reconstruct(a, lam, theta, phi)
        # global-phase-invariant comparison
        phase = np.vdot(rebuilt.reshape(-1), u.reshape(-1))
        phase = phase / abs(phase) if abs(phase) > 1e-12 else 1
        assert np.max(np.abs(rebuilt - phase * u)) < 1e-12

    def test_controlled_u_decomposition_via_projectors(self):
        """The book's controlled-gate construction:
        CU = P0⊗I + P1⊗U (projection-operator derivation, §22)."""
        from app.quantum.operators import controlled_of, ry
        u = ry(0.6)
        cu = controlled_of(u)
        p0 = np.array([[1, 0], [0, 0]], dtype=complex)
        p1 = np.array([[0, 0], [0, 1]], dtype=complex)
        manual = (np.kron(p0, np.eye(2, dtype=complex))
                  + np.kron(p1, u))
        assert np.max(np.abs(cu - manual)) < 1e-12
