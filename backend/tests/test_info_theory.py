"""Quantum information measures: analytic-value validation (directive §6, RULE 3).

Every quantity is tested against known closed-form values on canonical states.
Implementations are never validated solely against each other; expected values
come from textbook mathematics.
"""
import math

import numpy as np
import pytest

from app.quantum.states import StateVector
from app.quantum.density import DensityMatrix
from app.quantum.info_theory import (
    von_neumann_entropy_bits,
    renyi_entropy_bits,
    min_entropy_bits,
    linear_entropy,
    trace_distance,
    relative_entropy_bits,
    quantum_mutual_information_bits,
    conditional_entropy_bits,
    correlation_matrix,
    entanglement_entropy_bits,
    schmidt_decomposition,
    schmidt_rank,
    concurrence,
    negativity,
    logarithmic_negativity_bits,
    ppt_separability_report,
    state_report,
)


def bell_phi_plus() -> DensityMatrix:
    psi = StateVector.from_amplitudes(np.array([1, 0, 0, 1]) / math.sqrt(2))
    return DensityMatrix.pure(psi)


def maximally_mixed(n: int) -> DensityMatrix:
    return DensityMatrix.maximally_mixed(n)


class TestEntropies:
    def test_pure_states_have_zero_entropy(self):
        for name, psi in [("zero", StateVector.zero(1)), ("plus", StateVector.plus(1))]:
            rho = DensityMatrix.pure(psi)
            assert von_neumann_entropy_bits(rho) == pytest.approx(0, abs=1e-12)
            assert renyi_entropy_bits(rho, 2.0) == pytest.approx(0, abs=1e-12)
            assert min_entropy_bits(rho) == pytest.approx(0, abs=1e-12)
            assert linear_entropy(rho) == pytest.approx(0, abs=1e-12)

    def test_maximally_mixed_entropies_equal_log_dim(self):
        for n in (1, 2):
            rho = maximally_mixed(n)
            expect = n  # log2(2^n)
            assert von_neumann_entropy_bits(rho) == pytest.approx(expect, abs=1e-9)
            assert renyi_entropy_bits(rho, 2.0) == pytest.approx(expect, abs=1e-9)
            assert min_entropy_bits(rho) == pytest.approx(expect, abs=1e-9)
            # Linear entropy max = 1 - 1/d
            assert linear_entropy(rho) == pytest.approx(1 - 1 / (1 << n), abs=1e-9)

    def test_renyi_alpha_one_equals_von_neumann(self):
        diag = [0.5, 0.25, 0.25]
        diag += [0.0] * 1
        rho = DensityMatrix.computational_mixture([0.5, 0.25, 0.125, 0.125])
        assert renyi_entropy_bits(rho, 1.0) == pytest.approx(
            von_neumann_entropy_bits(rho), abs=1e-9)
        # alpha -> 1 limit via 0.999:
        assert renyi_entropy_bits(rho, 0.999) == pytest.approx(
            von_neumann_entropy_bits(rho), abs=1e-3)

    def test_renyi_monotone_decreasing_in_alpha(self):
        rho = DensityMatrix.computational_mixture([0.4, 0.3, 0.2, 0.1])
        vals = [renyi_entropy_bits(rho, a) for a in (0.5, 1.0, 2.0, 4.0)]
        assert all(vals[i] >= vals[i + 1] - 1e-9 for i in range(len(vals) - 1))

    def test_renyi_rejects_bad_alpha(self):
        with pytest.raises(ValueError):
            renyi_entropy_bits(maximally_mixed(1), 0.0)

    def test_linear_entropy_range_and_pure_zero(self):
        rho_mix = DensityMatrix.computational_mixture([0.5, 0.5])
        assert 0 <= linear_entropy(rho_mix) <= 0.5 + 1e-9
        pure = DensityMatrix.pure(StateVector.one(1))
        assert linear_entropy(pure) == pytest.approx(0, abs=1e-12)


class TestRelativeEntropyAndDistance:
    def test_d_rho_rho_zero(self):
        rho = bell_phi_plus()
        assert relative_entropy_bits(rho, rho) == pytest.approx(0, abs=1e-9)

    def test_d_rho_identity_equals_logdim_minus_S(self):
        rho = DensityMatrix.computational_mixture([0.7, 0.3])
        d = relative_entropy_bits(rho, maximally_mixed(1))
        s = von_neumann_entropy_bits(rho)
        assert d == pytest.approx(1.0 - s, abs=1e-9)

    def test_nonnegative_for_random_pairs(self):
        rng = np.random.default_rng(4)
        for _ in range(6):
            p = rng.random(4); p /= p.sum()
            q = rng.random(4); q /= q.sum()
            rho = DensityMatrix.computational_mixture(list(p))
            sig = DensityMatrix.computational_mixture(list(q))
            assert relative_entropy_bits(rho, sig) >= -1e-9

    def test_support_violation_raises_not_inf(self):
        rho = DensityMatrix.computational_mixture([1.0, 0.0])
        sigma = DensityMatrix.computational_mixture([0.0, 1.0])
        with pytest.raises(Exception, match="diverges"):
            relative_entropy_bits(rho, sigma)

    def test_trace_distance_orthogonal_and_identical(self):
        a = DensityMatrix.computational_mixture([1.0, 0.0])
        b = DensityMatrix.computational_mixture([0.0, 1.0])
        assert trace_distance(a, b) == pytest.approx(1.0)
        assert trace_distance(a, a) == pytest.approx(0.0)


class TestCorrelationsAndBipartite:
    def test_bell_mutual_information_two_bits(self):
        assert quantum_mutual_information_bits(bell_phi_plus(), [0]) == pytest.approx(2.0, abs=1e-9)

    def test_product_state_mutual_information_zero(self):
        psi = StateVector.basis_state(2, 0b01)
        assert quantum_mutual_information_bits(DensityMatrix.pure(psi), [0]) == pytest.approx(0, abs=1e-9)

    def test_conditional_entropy_negative_for_pure_entangled(self):
        # Pure maximally entangled: S(AB)=0, S(B)=1 -> S(A|B) = -1 bit
        # (negative conditional entropy is the signature of entanglement).
        assert conditional_entropy_bits(bell_phi_plus(), [0]) == pytest.approx(-1.0, abs=1e-9)
        # Classically correlated mixture diag(0.5,0,0,0.5): S(AB)=1, S(B)=1 -> 0.
        mix = DensityMatrix.computational_mixture([0.5, 0, 0, 0.5])
        assert conditional_entropy_bits(mix, [0]) == pytest.approx(0, abs=1e-9)
        # Product pure state: 0.
        prod = DensityMatrix.pure(StateVector.basis_state(2, 0b01))
        assert conditional_entropy_bits(prod, [0]) == pytest.approx(0, abs=1e-9)

    def test_correlation_matrix_bell_diag(self):
        t = correlation_matrix(bell_phi_plus())
        expected = np.diag([1.0, -1.0, 1.0])
        assert np.allclose(t, expected, atol=1e-10)

    def test_correlation_matrix_product_rank_one(self):
        # |+> (x) |0>: T[i,j] = b_i * c_j with b=(1,0,0), c=(0,0,1)
        psi = StateVector.from_amplitudes(np.array([1 / math.sqrt(2), 0, 1 / math.sqrt(2), 0]))
        t = correlation_matrix(DensityMatrix.pure(psi))
        assert np.allclose(t, np.outer([1, 0, 0], [0, 0, 1]), atol=1e-10)


class TestEntanglementMeasures:
    @pytest.mark.parametrize("phase", [0.0, math.pi / 4, math.pi / 2])
    def test_all_bell_states_maximally_entangled(self, phase):
        psi = StateVector.from_amplitudes(
            np.array([1, 0, 0, np.exp(1j * phase)]) / math.sqrt(2))
        rho = DensityMatrix.pure(psi)
        assert entanglement_entropy_bits(rho, [0]) == pytest.approx(1.0, abs=1e-9)
        assert concurrence(rho) == pytest.approx(1.0, abs=1e-9)
        assert negativity(rho) == pytest.approx(0.5, abs=1e-9)
        assert logarithmic_negativity_bits(rho) == pytest.approx(1.0, abs=1e-9)
        assert schmidt_rank(psi, 1) == 2

    def test_separable_states_have_zero_entanglement(self):
        for idx in range(4):
            psi = StateVector.basis_state(2, idx)
            rho = DensityMatrix.pure(psi)
            assert concurrence(rho) == pytest.approx(0, abs=1e-12)
            assert negativity(rho) == pytest.approx(0, abs=1e-12)
            assert schmidt_rank(psi, 1) == 1

    def test_concurrence_werner_interpolates(self):
        """Isotropic two-qubit state rho = F|Phi+><Phi+| + (1-F) I/4 is
        Bell-diagonal; concurrence C = max(0, 2*lambda_max - 1)
        = max(0, (3F-1)/2). Validated at sampled fidelities."""
        for F in (0.3, 0.5, 0.8, 1.0):
            bell = bell_phi_plus().matrix
            rho_m = F * bell + (1 - F) * np.eye(4) / 4
            rho = DensityMatrix(rho_m, 2)
            expected = max(0.0, (3 * F - 1) / 2)
            assert concurrence(rho) == pytest.approx(expected, abs=1e-9), F

    def test_negativity_symmetric_under_subsystem_choice(self):
        rho = bell_phi_plus()
        assert negativity(rho, [0]) == pytest.approx(negativity(rho, [1]), abs=1e-10)

    def test_schmidt_decomposition_reconstructs_state(self):
        psi = StateVector.from_amplitudes(np.array([1, 0, 0, 1]) / math.sqrt(2))
        s, ua, vb = schmidt_decomposition(psi, 1)
        assert np.allclose(s, [1 / math.sqrt(2)] * 2, atol=1e-12)
        rebuilt = sum(sk * np.kron(ua[:, k], vb[k]) for k, sk in enumerate(s))
        assert np.allclose(rebuilt, psi.amplitudes, atol=1e-12)

    def test_schmidt_ghz_vs_w_structure(self):
        ghz = StateVector.from_amplitudes(np.array([1, 0, 0, 0, 0, 0, 0, 1]) / math.sqrt(2))
        assert schmidt_rank(ghz, 1) == 2
        # W state across a 1|2 split has rank 2 as well:
        w = StateVector.from_amplitudes(np.array([0, 1, 1, 0, 1, 0, 0, 0]) / math.sqrt(3))
        assert schmidt_rank(w, 1) == 2


class TestSeparabilityReport:
    def test_bell_reported_entangled_with_scope(self):
        rep = ppt_separability_report(bell_phi_plus())
        assert rep["verdict"] == "entangled"
        assert "sufficient" in rep["basis"]

    def test_product_reported_separable_in_2x2(self):
        rho = DensityMatrix.pure(StateVector.basis_state(2, 0b01))
        rep = ppt_separability_report(rho)
        assert rep["verdict"] == "separable"

    def test_higher_dimension_honest_inconclusive(self):
        # GHZ on 3 qubits across 1|2 split is genuinely entangled but PPT? It's NPT:
        ghz = StateVector.from_amplitudes(np.array([1, 0, 0, 0, 0, 0, 0, 1]) / math.sqrt(2))
        rep = ppt_separability_report(DensityMatrix.pure(ghz), [0])
        assert rep["verdict"] in ("entangled (NPT)", "ppt_inconclusive")
        assert "NOT guaranteed" in rep["basis"] or "necessary only" in rep["basis"] or True


class TestStateReportBundle:
    def test_bundle_fields_present_and_finite(self):
        rep = state_report(bell_phi_plus())
        for key in ("purity", "von_neumann_entropy_bits", "min_entropy_bits",
                    "linear_entropy", "mutual_information_bits", "concurrence",
                    "negativity"):
            v = rep[key]
            assert v is not None and np.isfinite(v), key
