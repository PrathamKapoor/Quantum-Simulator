"""Channel algebra tests: Choi validation, composition/tensor identities,
process fidelity against analytic references (directive §7, RULE 3)."""
import numpy as np
import pytest

from app.quantum.channels import (
    KrausChannel,
    depolarizing_channel,
    amplitude_damping_channel,
)
from app.quantum.channel_algebra import (
    choi_matrix,
    validate_choi,
    compose_channels,
    tensor_channels,
    verify_composition_identity,
    verify_tensor_identity,
    process_fidelity_to_unitary,
    average_gate_fidelity,
    generalized_amplitude_damping_channel,
    readout_confusion_channel,
    apply_channel_to_operator_basis,
)
from app.quantum.operators import build_gate, custom_gate


PAULIS = [
    np.eye(2, dtype=np.complex128),
    np.array([[0, 1], [1, 0]], dtype=np.complex128),
    np.array([[0, -1j], [1j, 0]], dtype=np.complex128),
    np.array([[1, 0], [0, -1]], dtype=np.complex128),
]

TEST_OPS = [np.array(m, dtype=np.complex128) for m in PAULIS] + [
    (PAULIS[1] + 1j * PAULIS[3]) / np.sqrt(2)  # non-Hermitian operator too
]


class TestChoi:
    def test_identity_channel_choi_is_bell(self):
        ident = KrausChannel([np.eye(2)], 1)
        j = choi_matrix(ident)
        # Un-normalized Choi of the identity channel = |Phi><Phi| with
        # |Phi> = |00> + |11>: entries at (0,0),(0,3),(3,0),(3,3) all equal 1.
        expected = np.zeros((4, 4), dtype=complex)
        for a in (0, 3):
            for b in (0, 3):
                expected[a, b] = 1.0
        assert np.allclose(j, expected)

    def test_all_standard_channels_pass_choi_validation(self):
        channels = [
            depolarizing_channel(0.1),
            depolarizing_channel(1.0),  # fully depolarizing edge case
            amplitude_damping_channel(0.3),
            amplitude_damping_channel(1.0),
            generalized_amplitude_damping_channel(0.4, 0.25),
            readout_confusion_channel(0.05, 0.02),
        ]
        for ch in channels:
            rep = validate_choi(ch)
            assert rep["all_valid"], (type(ch).__name__, rep)

    def test_non_tp_rejected_by_kraus_constructor(self):
        bad = [0.5 * np.eye(2)]  # completeness = 0.25 I != I
        with pytest.raises(Exception):
            KrausChannel(bad, 1)


class TestComposition:
    def test_sequential_equals_composed(self):
        first = depolarizing_channel(0.2)
        second = amplitude_damping_channel(0.35)
        rep = verify_composition_identity(first, second, TEST_OPS)
        assert rep["agrees"], rep

    def test_composition_with_identity_is_identity(self):
        ident = KrausChannel([np.eye(2)], 1)
        ch = depolarizing_channel(0.4)
        composed = compose_channels(ch, ident)
        for x in TEST_OPS:
            assert np.allclose(
                apply_channel_to_operator_basis(composed, x),
                apply_channel_to_operator_basis(ch, x),
            )

    def test_size_mismatch_rejected(self):
        with pytest.raises(Exception):
            compose_channels(KrausChannel([np.eye(2)], 1),
                             KrausChannel([np.eye(4)], 2))


class TestTensor:
    def test_tensor_identity_holds(self):
        a = depolarizing_channel(0.15)
        b = amplitude_damping_channel(0.5)
        ops_a = [np.diag([0.6, 0.4]).astype(complex), PAULIS[1] * 0.5]
        ops_b = [np.diag([0.9, 0.1]).astype(complex), PAULIS[3] * 0.5]
        rep = verify_tensor_identity(a, b, ops_a, ops_b)
        assert rep["agrees"], rep

    def test_tensor_channel_tp(self):
        ab = tensor_channels(depolarizing_channel(0.3), amplitude_damping_channel(0.7))
        assert validate_choi(ab)["all_valid"]


class TestProcessFidelity:
    def test_unitary_channel_matches_itself_exactly(self):
        u = build_gate("H", []).matrix
        ch = KrausChannel([u], 1)
        assert process_fidelity_to_unitary(ch, u) == pytest.approx(1.0)
        assert average_gate_fidelity(ch, u) == pytest.approx(1.0)

    def test_bit_flip_vs_x_is_perfect(self):
        x = build_gate("X", []).matrix
        ch = KrausChannel([x], 1)
        assert process_fidelity_to_unitary(ch, x) == pytest.approx(1.0)

    def test_depolarizing_zero_matches_identity(self):
        ch = depolarizing_channel(0.0)
        assert process_fidelity_to_unitary(ch, np.eye(2)) == pytest.approx(1.0)

    def test_fully_depolyarizing_average_fidelity_half(self):
        """E(rho)=I/2 has F_avg = 1/2 for one qubit (literature reference)."""
        k = [p * np.eye(2, dtype=np.complex128)
             for p in (0.5, 0.5j, -0.5, -0.5j)]
        # Build exactly: { |i><j| / sqrt(2) } implements E(rho)=Tr(rho) I/2.
        basis_ops = []
        for i in range(2):
            for j in range(2):
                m = np.zeros((2, 2), dtype=np.complex128)
                m[i, j] = 1 / np.sqrt(2)
                basis_ops.append(m)
        ch = KrausChannel(basis_ops, 1)
        assert average_gate_fidelity(ch, np.eye(2)) == pytest.approx(0.5, abs=1e-9)

    def test_noisy_depolarizing_between_limits(self):
        ch = depolarizing_channel(0.3)
        f = average_gate_fidelity(ch, np.eye(2))
        assert 0.8 < f < 1.0


class TestNewChannels:
    def test_generalized_amplitude_damping_reduces_to_ad_at_p_zero(self):
        g = 0.4
        gad = generalized_amplitude_damping_channel(g, 0.0)
        ad = amplitude_damping_channel(g)
        for x in TEST_OPS:
            assert np.allclose(
                apply_channel_to_operator_basis(gad, x),
                apply_channel_to_operator_basis(ad, x),
            )

    def test_gad_tps_channel(self):
        assert validate_choi(generalized_amplitude_damping_channel(0.5, 0.5))["all_valid"]

    def test_readout_channel_classical_action(self):
        ch = readout_confusion_channel(0.1, 0.2)
        diag0 = np.diag([1.0, 0.0]).astype(complex)   # |0><0|
        out = apply_channel_to_operator_basis(ch, diag0)
        # P(read 1|0)=0.1: diagonal becomes [0.9, 0.1]
        assert np.allclose(np.real(np.diag(out)), [0.9, 0.1])
