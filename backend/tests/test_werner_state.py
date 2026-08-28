"""Canonical Werner-state tests (noisy-ebit milestone, directive §7-§10, §47, §76).

The constructor under test is DensityMatrix.werner(F). The convention is
documented there and MUST stay consistent with the network subsystem's
Werner parameterization (network.resources.werner_parameter, q = (4F-1)/3),
which swapping, memory decay, and purification already use.
"""
import numpy as np
import pytest

from app.quantum.density import DensityMatrix
from app.quantum.states import QuantumCoreError
from app.quantum.info_theory import negativity, concurrence
from app.network.resources import werner_parameter

# |Phi+> projector in the project's ordering (qubit 0 = most-significant bit):
# |Phi+> = (|00> + |11>)/sqrt(2)  ->  support on indices 0 and 3.
PHI_PLUS_PROJECTOR = 0.5 * np.array([
    [1, 0, 0, 1],
    [0, 0, 0, 0],
    [0, 0, 0, 0],
    [1, 0, 0, 1],
], dtype=np.complex128)


class TestWernerInvariants:
    @pytest.mark.parametrize("f", [0.0, 0.25, 0.5, 0.75, 0.9, 0.99, 1.0])
    def test_trace_hermitian_psd(self, f):
        rho = DensityMatrix.werner(f)
        assert abs(rho.trace().real - 1.0) < 1e-12
        assert abs(rho.trace().imag) < 1e-12
        m = rho.matrix
        assert np.max(np.abs(m - m.conj().T)) < 1e-12
        eigs = np.linalg.eigvalsh(m)
        assert np.min(eigs) > -1e-12

    @pytest.mark.parametrize("f", [0.0, 0.25, 0.5, 0.75, 0.9, 0.99, 1.0])
    def test_target_bell_fidelity_equals_F(self, f):
        rho = DensityMatrix.werner(f)
        assert abs(float(np.real(np.trace(PHI_PLUS_PROJECTOR @ rho.matrix))) - f) < 1e-12

    @pytest.mark.parametrize("f", [0.0, 0.25, 0.5, 0.75, 0.9, 0.99, 1.0])
    def test_reduced_states_are_maximally_mixed(self, f):
        # Every Bell-diagonal state has I/2 marginals.
        rho = rho_red = DensityMatrix.werner(f)
        red = rho.partial_trace([0])
        assert np.max(np.abs(red.matrix - 0.5 * np.eye(2))) < 1e-12
        red1 = rho_red.partial_trace([1])
        assert np.max(np.abs(red1.matrix - 0.5 * np.eye(2))) < 1e-12

    def test_invalid_fidelity_rejected(self):
        for bad in (-0.1, 1.0001, 1.5):
            with pytest.raises(QuantumCoreError):
                DensityMatrix.werner(bad)


class TestWernerLimitCases:
    def test_F1_is_pure_Phi_plus(self):
        rho = DensityMatrix.werner(1.0)
        assert rho.purity() > 1 - 1e-12
        assert np.max(np.abs(rho.matrix - PHI_PLUS_PROJECTOR)) < 1e-12

    def test_F0_is_equal_mixture_of_three_other_bells(self):
        rho = DensityMatrix.werner(0.0)
        # Equal weight on the three orthogonal Bell states -> purity 1/3.
        assert abs(rho.purity() - 1.0 / 3.0) < 1e-12
        # No |Phi+> component: diag shows only the three other Bell weights
        # (|Phi-> contributes 1/6 to each of indices 0,3; |Psi+>,|Psi-> 1/3
        # each at 1,2) and the surviving (0,3) coherence is |Phi->'s 1/6.
        assert abs(rho.matrix[0, 3] + 1.0 / 6.0) < 1e-12  # |Phi-> coherence, negative
        assert abs(rho.matrix[0, 0] - 1.0 / 6.0) < 1e-12  # half of |Phi-> weight
        assert abs(rho.matrix[1, 1] - 1.0 / 3.0) < 1e-12  # |Psi+> + |Psi-> halves

    def test_F_half_is_separability_boundary(self):
        # F = 1/2 (q = 1/3) is the PPT boundary: valid, separable, and NOT
        # maximally mixed (the maximally mixed point of this family is F=1/4).
        rho = DensityMatrix.werner(0.5)
        q = werner_parameter(0.5)
        expected = q * PHI_PLUS_PROJECTOR + (1 - q) * np.eye(4, dtype=np.complex128) / 4.0
        assert np.max(np.abs(rho.matrix - expected)) < 1e-12

    def test_F_quarter_matches_werner_parameter_boundary(self):
        # q = (4F-1)/3 = 0 at F = 0.25: the network model's validity boundary.
        rho = DensityMatrix.werner(0.25)
        assert werner_parameter(0.25) == 0.0
        assert abs(rho.purity() - 0.25) < 1e-12  # equal 4-Bell mixture


class TestWernerConventionConsistency:
    @pytest.mark.parametrize("f", [0.25, 0.5, 0.7, 0.9, 1.0])
    def test_matches_network_q_parameterization(self, f):
        """rho_W(F) must equal q|Phi+><Phi+| + (1-q) I/4 with q = (4F-1)/3."""
        q = werner_parameter(f)
        rho_q = q * PHI_PLUS_PROJECTOR + (1 - q) * np.eye(4, dtype=np.complex128) / 4.0
        rho = DensityMatrix.werner(f)
        assert np.max(np.abs(rho.matrix - rho_q)) < 1e-12

    def test_bell_state_ordering_is_project_convention(self):
        """|Phi+> must have support on |00>,|11> (indices 0,3), not |01>,|10>.

        Guards against silently swapping to the |Psi+> convention, which the
        network swapping/purification math does NOT use.
        """
        rho = DensityMatrix.werner(1.0)
        assert rho.matrix[0, 0] > 0.4 and rho.matrix[3, 3] > 0.4
        assert rho.matrix[1, 1] < 1e-12 and rho.matrix[2, 2] < 1e-12


class TestWernerEntanglementRegime:
    """Documented regime: entangled iff F > 1/2 (PPT for Bell-diagonal states).

    F <= 1/2 values are mathematically valid states but NOT useful
    entanglement; tests must not label them entangled.
    """

    @pytest.mark.parametrize("f,expect_entangled", [
        (0.0, False), (0.25, False), (0.49, False), (0.5, False),
        (0.51, True), (0.75, True), (1.0, True),
    ])
    def test_negativity_sign_regime(self, f, expect_entangled):
        rho = DensityMatrix.werner(f)
        neg = negativity(rho)
        if expect_entangled:
            assert neg > 0
        else:
            assert neg <= 1e-12

    def test_concurrence_at_known_points(self):
        # Analytic concurrence of this family: C = max(0, 2F - 1)
        # (equivalently max(0, (3q-1)/2) with q = (4F-1)/3).
        for f in (1.0, 0.75):
            c = concurrence(DensityMatrix.werner(f))
            assert abs(c - (2 * f - 1)) < 1e-9
        assert concurrence(DensityMatrix.werner(0.5)) < 1e-9
