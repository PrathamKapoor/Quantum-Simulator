"""Core quantum tests: statevectors, gates, invariants (directives §138-139)."""
import numpy as np
import pytest

from app.quantum.states import StateVector, QuantumCoreError, DEFAULT_TOLERANCE
from app.quantum.operators import (
    build_gate,
    is_unitary,
    custom_gate,
    rx, ry, rz, u3,
)
from app.quantum.apply import apply_gate_statevector, embed_operator
from app.quantum.density import DensityMatrix, trace_distance


H = build_gate("H", []).matrix
X = build_gate("X", []).matrix
Y = build_gate("Y", []).matrix
Z = build_gate("Z", []).matrix
S = build_gate("S", []).matrix
SDG = build_gate("SDG", []).matrix
T = build_gate("T", []).matrix
TDG = build_gate("TDG", []).matrix
CX = build_gate("CX", []).matrix


class TestStateVector:
    def test_basis_states(self):
        s = StateVector.basis_state(2, 0b01)  # q0=1, q1=0 -> index 1
        assert s.probability_of(1) == 1.0

    def test_norm_invariant(self):
        rng = np.random.default_rng(7)
        amps = rng.normal(size=8) + 1j * rng.normal(size=8)
        with pytest.raises(QuantumCoreError):
            StateVector(amps, 3)  # non-normalized must be rejected by default
        state = StateVector.from_amplitudes(amps, normalize_if_needed=True)
        assert abs(state.norm() - 1) < DEFAULT_TOLERANCE

    def test_rejects_non_finite(self):
        amps = np.array([np.nan, 0])
        with pytest.raises(QuantumCoreError):
            StateVector(amps, 1)

    def test_plus_state(self):
        p = StateVector.plus(1)
        assert np.allclose(p.amplitudes, [1 / np.sqrt(2), 1 / np.sqrt(2)])

    def test_tensor_ordering(self):
        a = StateVector.basis_state(1, 1)  # |1>
        b = StateVector.basis_state(2, 2)  # |10> little-endian: q1=1
        c = a.tensor(b)
        # index = 1 * 4 + 2 = 6 = 0b110 -> q0=0,q1=1,q2=1
        assert c.probability_of(6) == 1.0

    def test_inner_product_and_fidelity(self):
        plus = StateVector.plus(1)
        zero = StateVector.zero(1)
        assert abs(plus.fidelity_with(zero) - 0.5) < 1e-12
        assert abs(plus.fidelity_with(plus) - 1.0) < 1e-12


class TestGates:
    @pytest.mark.parametrize(
        "name,params",
        [
            ("I", []), ("X", []), ("Y", []), ("Z", []), ("H", []),
            ("S", []), ("SDG", []), ("T", []), ("TDG", []),
            ("RX", [0.3]), ("RY", [-1.2]), ("RZ", [np.pi]),
            ("U3", [0.4, 0.9, -0.3]),
            ("CX", []), ("CZ", []), ("SWAP", []),
            ("CRX", [0.5]), ("CRY", [0.5]), ("CRZ", [0.5]),
            ("CCX", []), ("CSWAP", []),
            ("RZZ", [0.7]), ("P", [0.25]),
        ],
    )
    def test_gate_is_unitary(self, name, params):
        spec = build_gate(name, params)
        assert is_unitary(spec.matrix)

    def test_unknown_gate(self):
        with pytest.raises(QuantumCoreError, match="Unknown gate"):
            build_gate("NOT_A_GATE", [])

    def test_wrong_param_count(self):
        with pytest.raises(QuantumCoreError, match="requires 1 parameter"):
            build_gate("RX", [])

    def test_non_unitary_custom_rejected(self):
        with pytest.raises(QuantumCoreError, match="unitarity"):
            custom_gate("bad", np.array([[2, 0], [0, 0.5]]))

    def test_inverse_pairs(self):
        for a, b in (("S", "SDG"), ("T", "TDG")):
            ma, mb = build_gate(a, []).matrix, build_gate(b, []).matrix
            assert np.allclose(ma @ mb, np.eye(2), atol=1e-10)

    def test_h_squared_identity(self):
        assert np.allclose(H @ H, np.eye(2), atol=1e-12)

    def test_rotation_generators(self):
        theta = 0.37
        # Rx(theta) = exp(-i theta X/2): check via small-angle series identity
        expected_x = np.eye(2) * np.cos(theta / 2) - 1j * X * np.sin(theta / 2)
        assert np.allclose(rx(theta), expected_x, atol=1e-14)
        expected_y = np.eye(2) * np.cos(theta / 2) - 1j * Y * np.sin(theta / 2)
        assert np.allclose(ry(theta), expected_y, atol=1e-14)
        expected_z = np.diag([np.exp(-1j * theta / 2), np.exp(1j * theta / 2)])
        assert np.allclose(rz(theta), expected_z, atol=1e-14)

    def test_u3_special_cases(self):
        # U3(pi/2? no) H == U3(pi/2, 0, pi)
        assert np.allclose(u3(np.pi / 2, 0, np.pi), H, atol=1e-12)


class TestApplication:
    def _ref_apply(self, amps, n, qubits, mat):
        full = embed_operator(mat, n, qubits)
        return full @ amps

    @pytest.mark.parametrize(
        "n,qubits,name",
        [(3, [0], "H"), (3, [1], "X"), (4, [3], "T"), (5, [2], "RY")],
    )
    def test_1q_against_reference(self, n, qubits, name):
        rng = np.random.default_rng(n * 100 + qubits[0])
        amps = rng.normal(size=1 << n) + 1j * rng.normal(size=1 << n)
        amps /= np.linalg.norm(amps)
        mat = build_gate(name, [0.4] if name in ("RY",) else []).matrix
        fast = apply_gate_statevector(amps, n, qubits, mat)
        ref = self._ref_apply(amps, n, qubits, mat)
        assert np.allclose(fast, ref, atol=1e-12)

    @pytest.mark.parametrize(
        "n,qubits,name,params",
        [(2, [0, 1], "CX", []), (3, [1, 2], "CZ", []), (3, [0, 2], "SWAP", []),
         (4, [2, 3], "RZZ", [0.6]), (4, [1, 3], "CRX", [0.4])],
    )
    def test_2q_against_reference(self, n, qubits, name, params):
        rng = np.random.default_rng(hash((n, tuple(qubits), name)) % 10000)
        amps = rng.normal(size=1 << n) + 1j * rng.normal(size=1 << n)
        amps /= np.linalg.norm(amps)
        mat = build_gate(name, params).matrix
        fast = apply_gate_statevector(amps, n, qubits, mat)
        ref = self._ref_apply(amps, n, qubits, mat)
        assert np.allclose(fast, ref, atol=1e-12)

    def test_3q_toffoli_against_reference(self):
        n, qubits, name, params = 3, [0, 1, 2], "CCX", []
        rng = np.random.default_rng(42)
        amps = rng.normal(size=8) + 1j * rng.normal(size=8)
        amps /= np.linalg.norm(amps)
        mat = build_gate(name, params).matrix
        assert np.allclose(
            apply_gate_statevector(amps, n, qubits, mat),
            self._ref_apply(amps, n, qubits, mat),
            atol=1e-12,
        )


class TestDensityMatrix:
    def test_pure_construction(self):
        rho = DensityMatrix.pure(StateVector.plus(1))
        assert abs(rho.purity() - 1) < 1e-12
        assert abs(rho.trace().real - 1) < 1e-12

    def test_hermiticity_enforced(self):
        bad = np.array([[0.5, 0.1], [0.0, 0.5]])
        with pytest.raises(QuantumCoreError, match="not Hermitian"):
            DensityMatrix(bad, 1)

    def test_trace_enforced(self):
        with pytest.raises(QuantumCoreError, match="trace"):
            DensityMatrix(np.eye(2) * 0.4, 1)

    def test_maximally_mixed(self):
        rho = DensityMatrix.maximally_mixed(1)
        assert abs(rho.purity() - 0.5) < 1e-12
        assert abs(rho.entropy() - 1.0) < 1e-9  # 1 bit

    def test_partial_trace_bell(self):
        # Bell state |Phi+> = (|00>+|11>)/sqrt2 -> reduced state is maximally mixed.
        psi = StateVector.from_amplitudes(np.array([1, 0, 0, 1]) / np.sqrt(2))
        rho = DensityMatrix.pure(psi)
        reduced = rho.partial_trace([0])
        assert np.allclose(reduced.matrix, np.eye(2) / 2, atol=1e-12)
        reduced_q1 = rho.partial_trace([1])
        assert np.allclose(reduced_q1.matrix, np.eye(2) / 2, atol=1e-12)

    def test_partial_trace_product_state(self):
        psi = StateVector.basis_state(2, 0b01)  # q0=1, q1=0
        rho = DensityMatrix.pure(psi)
        r0 = rho.partial_trace([0])
        assert np.allclose(r0.matrix, np.array([[0, 0], [0, 1]]), atol=1e-12)

    def test_partial_trace_keeps_listed_order(self):
        # GHZ on 3 qubits: any two-qubit marginal is diag(1/2,0,0,1/2),
        # i.e. classical mixture of |00> and |11> — NOT maximally mixed.
        psi = StateVector.from_amplitudes(np.array([1, 0, 0, 0, 0, 0, 0, 1]) / np.sqrt(2))
        rho = DensityMatrix.pure(psi)
        reduced = rho.partial_trace([2, 0])
        expected = np.zeros((4, 4), dtype=complex)
        expected[0, 0] = 0.5
        expected[3, 3] = 0.5
        assert np.allclose(reduced.matrix, expected, atol=1e-12)
        # Entropy of the GHZ marginal is exactly 1 bit.
        assert abs(reduced.entropy() - 1.0) < 1e-9

    def test_uhlmann_fidelity_matches_pure_formula(self):
        psi = StateVector.plus(1)
        phi = StateVector.zero(1)
        mixed = DensityMatrix.pure(psi)
        other = DensityMatrix.pure(phi)
        f_mixed = mixed.fidelity_with(other)
        f_pure = psi.fidelity_with(phi)
        assert abs(f_mixed - f_pure) < 1e-10

    def test_fidelity_with_self_is_one(self):
        rng = np.random.default_rng(3)
        diag = rng.random(4)
        diag /= diag.sum()
        rho = DensityMatrix.computational_mixture(diag.tolist())
        assert abs(rho.fidelity_with(rho) - 1.0) < 1e-8

    def test_bloch_vector(self):
        rho = DensityMatrix.pure(StateVector.zero(1))
        r = rho.bloch_vector()
        assert np.allclose(r, [0, 0, 1], atol=1e-12)
        # |+>: x=1
        rho_plus = DensityMatrix.pure(StateVector.plus(1))
        assert np.allclose(rho_plus.bloch_vector(), [1, 0, 0], atol=1e-12)

    def test_entropy_pure_zero(self):
        rho = DensityMatrix.pure(StateVector.basis_state(3, 5))
        assert abs(rho.entropy()) < 1e-12

    def test_density_matches_statevector_evolution(self):
        # Cross-check: unitary evolution via density engine vs statevector path.
        from app.quantum.apply import apply_gate_density

        rng = np.random.default_rng(11)
        amps = rng.normal(size=8) + 1j * rng.normal(size=8)
        amps /= np.linalg.norm(amps)
        psi = StateVector(amps, 3)
        rho = DensityMatrix.pure(psi)
        mat = build_gate("CX", []).matrix
        evolved_sv = StateVector(apply_gate_statevector(amps, 3, [0, 1], mat), 3)
        evolved_rho = rho.apply_unitary(mat, [0, 1])
        assert evolved_rho.fidelity_with_statevector(evolved_sv) > 1 - 1e-10

    def test_trace_distance_bounds(self):
        rho = DensityMatrix.pure(StateVector.zero(1))
        sig = DensityMatrix.pure(StateVector.one(1))
        assert abs(trace_distance(rho, sig) - 1.0) < 1e-12


class TestPartialTraceMultiQubitRegression:
    """Regression for the interleaved-output-order partial-trace bug: with
    len(keep) >= 2 the reduced state was axis-mixed and only diagonal
    marginals (GHZ) masked it. Off-diagonal validation added per RULE 3."""

    def test_bell_full_system_identity(self):
        psi = StateVector.from_amplitudes(np.array([1, 0, 0, 1]) / np.sqrt(2))
        rho = DensityMatrix.pure(psi)
        red = rho.partial_trace([0, 1])
        assert np.allclose(red.matrix, rho.matrix, atol=1e-12)

    def test_ghz_offdiagonal_two_qubit_keep(self):
        # |W> state has off-diagonal reduced entries on a 1|2 split.
        w = StateVector.from_amplitudes(
            np.array([0, 1, 1, 0, 1, 0, 0, 0]) / np.sqrt(3))
        rho = DensityMatrix.pure(w)
        red = rho.partial_trace([0])
        # reference: each qubit of |W> is excited with probability 1/3
        assert np.allclose(np.real(np.diag(red.matrix)), [2 / 3, 1 / 3], atol=1e-9)

    def test_two_qubit_keep_order_matches_documented_mapping(self):
        # |01> on qubits (q1=0? no): basis_state(2, 0b10) -> q1=1,q0=0.
        psi = StateVector.basis_state(2, 0b10)
        red = DensityMatrix.pure(psi).partial_trace([1, 0])
        # keep=[1,0]: output qubit0 <-> input q1 (=1), qubit1 <-> q0 (=0)
        expected = np.zeros((4, 4)); expected[1 * 2 + 0, 1 * 2 + 0] = 1.0
        assert np.allclose(red.matrix, expected)

    def test_trace_preserved_for_random_states_multi_keep(self):
        rng = np.random.default_rng(12)
        for _ in range(5):
            amps = rng.normal(size=16) + 1j * rng.normal(size=16)
            psi = StateVector.from_amplitudes(amps, normalize_if_needed=True)
            rho = DensityMatrix.pure(psi)
            red = rho.partial_trace([0, 3])
            tr = float(np.real(np.trace(red.matrix)))
            assert abs(tr - 1) < 1e-9
            assert abs(red.purity()) <= 1 + 1e-9
