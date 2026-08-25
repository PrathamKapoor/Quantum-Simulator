"""Protocol tests (directives §142, §306)."""
import math

import numpy as np
import pytest

from app.protocols import (
    run_bb84,
    run_e91,
    run_qrng,
    run_chsh,
    shannon_entropy,
    mutual_information_from_joint,
    quantum_mutual_information,
    bell_state_metrics,
)
from app.quantum.states import StateVector
from app.quantum.density import DensityMatrix


class TestBB84:
    def test_no_eve_gives_near_zero_qber(self):
        """§142/§306: ideal conditions, no Eve -> QBER ~ 0 (statistically)."""
        qbers = [
            run_bb84(512, eve_intercept_probability=0.0, seed=s).qber
            for s in range(5)
        ]
        assert all(q == 0.0 for q in qbers)

    def test_full_eve_raises_qber(self):
        """Full intercept-resend -> QBER near the theoretical 25%."""
        qbers = [
            run_bb84(2048, eve_intercept_probability=1.0, seed=s).qber
            for s in range(3)
        ]
        mean = float(np.mean(qbers))
        assert 0.15 < mean < 0.35, f"QBER {mean} outside intercept-resend band"

    def test_partial_eve_between_bounds(self):
        low = np.mean([run_bb84(1024, eve_intercept_probability=0.25, seed=s).qber for s in range(4)])
        high = np.mean([run_bb84(1024, eve_intercept_probability=0.75, seed=s).qber for s in range(4)])
        assert low < high

    def test_sifted_key_agreement_without_eve(self):
        res = run_bb84(512, seed=42)
        assert res.sifted_key_alice == res.sifted_key_bob

    def test_invalid_parameters_rejected(self):
        with pytest.raises(ValueError):
            run_bb84(4)  # too few qubits
        with pytest.raises(ValueError):
            run_bb84(64, eve_intercept_probability=1.5)
        with pytest.raises(ValueError):
            run_bb84(64, sample_fraction=0)


class TestE91:
    def test_perfect_visibility_violates_chsh(self):
        res = run_e91(4000, noise_correlation_factor=1.0, seed=7)
        assert abs(res.chsh_statistic) > 2.2, f"S={res.chsh_statistic}"
        assert res.chsh_violates_classical

    def test_zero_visibility_does_not_violate(self):
        res = run_e91(4000, noise_correlation_factor=0.0, seed=7)
        assert abs(res.chsh_statistic) < 1.0

    def test_keys_match_after_correction(self):
        res = run_e91(2000, seed=11)
        if res.alice_key and res.bob_key:
            agreement = sum(a == b for a, b in zip(res.alice_key, res.bob_key)) / len(res.alice_key)
            assert agreement > 0.9


class TestQRNG:
    def test_uniformity_and_independence_stats(self):
        out = run_qrng(4096, seed=3)
        assert abs(out["fraction_of_ones"] - 0.5) < 0.03
        assert out["runs_test_passes_5pct"]

    def test_disclaimer_present(self):
        out = run_qrng(64)
        assert "NO physical entropy" in out["disclaimer"]

    def test_range_validation(self):
        with pytest.raises(ValueError):
            run_qrng(8)
        with pytest.raises(ValueError):
            run_qrng(20_000_000)


class TestCHSH:
    def test_perfect_source_hits_quantum_bound(self):
        out = run_chsh(1.0, shots_per_setting=5000, seed=1)
        assert abs(out["chsh_S"]) > 2.6
        assert out["violates_classical_bound"]

    def test_classical_mixture_stays_below_bound(self):
        # Fidelity 0.5 gives S ≈ sqrt(2) < 2.
        out = run_chsh(0.5, shots_per_setting=5000, seed=2)
        assert abs(out["chsh_S"]) < 2.0
        assert not out["violates_classical_bound"]

    def test_threshold_fidelity_near_required(self):
        """Isotropic-model threshold for CHSH violation: visibility/F > 1/sqrt(2).
        Verify monotonic behavior across it (finite-shot noise applies)."""
        below = run_chsh(0.68, shots_per_setting=8000, seed=5)["chsh_abs"]
        above = run_chsh(0.75, shots_per_setting=8000, seed=5)["chsh_abs"]
        assert below < 2.0 < above
        assert above > below


class TestInformationTheory:
    def test_shannon_entropy_reference_values(self):
        assert shannon_entropy([0.5, 0.5]) == pytest.approx(1.0)
        assert shannon_entropy([1.0, 0.0]) == pytest.approx(0.0)
        assert shannon_entropy([0.25] * 4) == pytest.approx(2.0)

    def test_mutual_information_independent_vs_correlated(self):
        independent = [[0.25, 0.25], [0.25, 0.25]]
        correlated = [[0.5, 0.0], [0.0, 0.5]]
        assert mutual_information_from_joint(independent) == pytest.approx(0.0, abs=1e-12)
        assert mutual_information_from_joint(correlated) == pytest.approx(1.0)

    def test_bell_state_entropy_of_entanglement(self):
        m = bell_state_metrics()
        assert m["entropy_of_entanglement_bits"] == pytest.approx(1.0)
        assert m["global_purity"] == pytest.approx(1.0)
        assert m["purity_of_reduced_state"] == pytest.approx(0.5)

    def test_product_state_has_zero_mutual_info(self):
        psi = StateVector.basis_state(2, 0b01)
        rho = DensityMatrix.pure(psi)
        assert quantum_mutual_information(rho, [0]) == pytest.approx(0.0, abs=1e-9)

    def test_bell_state_one_bit_mutual_info(self):
        psi = StateVector.from_amplitudes(np.array([1, 0, 0, 1]) / math.sqrt(2))
        rho = DensityMatrix.pure(psi)
        assert quantum_mutual_information(rho, [0]) == pytest.approx(2.0)
