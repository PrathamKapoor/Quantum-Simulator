"""Milestone 23 book-experiment tests (expansion).

Covers the promoted primitives (Gram-Schmidt, purification) and the new
chapter experiments (entanglement swapping, QEC codes, state tomography,
Landau-Zener). Every test is a computational experiment with a theoretical
prediction and an acceptance criterion (directive 108); nothing is
hard-coded - expected values come from independent analytic forms.
"""
import json
import numpy as np

import pytest

from app.experiments import book_runner
from app.experiments.runner import RUNNER_REGISTRY, execute_run

NEW_MODULES = [
    "book_gram_schmidt",
    "book_purification",
    "book_entanglement_swapping",
    "book_qec_codes",
    "book_state_tomography",
    "book_rabi_oscillations",
    "book_helstrom",
    "book_channel_algebra",
]


class TestRegistration:
    @pytest.mark.parametrize("module", NEW_MODULES)
    def test_registered_in_runner_registry(self, module):
        assert module in RUNNER_REGISTRY

    @pytest.mark.parametrize("module", NEW_MODULES)
    def test_runner_is_callable(self, module):
        assert callable(RUNNER_REGISTRY[module])


class TestExecutionAndValidation:
    def test_numpy_validation_booleans_survive_json_roundtrip(self):
        doc = book_runner.make_result_document_sanitized(
            "book_probe", {}, summary={"validation": {
                "passed": np.bool_(False), "checks": [np.bool_(True)]}})
        validation = json.loads(json.dumps(doc, allow_nan=False))["summary"]["validation"]
        assert validation["passed"] is False
        assert validation["checks"][0] is True

    @pytest.mark.parametrize("module", NEW_MODULES)
    def test_runs_and_validates(self, module):
        doc = execute_run(module, {}, 12345)
        assert doc["schema"] == "quantumlab.run-result"
        assert doc["module"] == module
        assert doc["summary"]["validation"]["passed"] is True

    @pytest.mark.parametrize("module", NEW_MODULES)
    def test_document_is_strict_json(self, module):
        doc = execute_run(module, {}, 999)
        json.dumps(doc)          # must not raise (complex/numpy sanitized)

    @pytest.mark.parametrize("module", NEW_MODULES)
    def test_deterministic_for_fixed_seed(self, module):
        a = execute_run(module, {}, 4242)
        b = execute_run(module, {}, 4242)
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


class TestEdgeCases:
    def test_gram_schmidt_rejects_dimension_below_two(self):
        with pytest.raises(ValueError):
            book_runner.book_gram_schmidt({"dimension": 1}, 0)

    def test_tomography_rejects_too_few_shots(self):
        with pytest.raises(ValueError):
            book_runner.book_state_tomography({"shots": 3}, 0)

    def test_rabi_rejects_nonpositive_frequency(self):
        with pytest.raises(ValueError):
            book_runner.book_rabi_oscillations({"rabi_frequency": 0.0}, 0)

    def test_qec_codes_unknown_code_raises(self):
        with pytest.raises(KeyError):
            book_runner.book_qec_codes({"codes": ["not-a-code"]}, 0)


class TestScientificOracles:
    def test_purification_reduces_back_to_rho(self):
        doc = book_runner.book_purification({}, 5)
        rows = doc["summary"]["validation"]["states"]
        assert all(r["trace_distance_to_rho"] < 1e-9 for r in rows)
        assert all(r["schmidt_spectrum_error"] < 1e-9 for r in rows)
        assert all(r["schmidt_rank"] == r["rho_rank"] for r in rows)

    def test_swapping_entangles_outer_pair_only_after_bsm(self):
        doc = book_runner.book_entanglement_swapping({}, 1)
        v = doc["summary"]["validation"]
        assert v["outer_concurrence_before_bsm"] < 1e-9
        assert v["outcomes"]
        assert all(o["outer_concurrence"] > 1 - 1e-9 for o in v["outcomes"])
        assert abs(v["total_probability"] - 1.0) < 1e-9

    def test_qec_corrects_all_guaranteed_single_errors(self):
        doc = book_runner.book_qec_codes({}, 1)
        codes = doc["summary"]["validation"]["codes"]
        assert codes
        for r in codes:
            assert r["guaranteed_cases"] > 0
            assert r["guaranteed_success"] == r["guaranteed_cases"]

    def test_gram_schmidt_rank_matches_numpy(self):
        doc = book_runner.book_gram_schmidt({"dimension": 5}, 3)
        v = doc["summary"]["validation"]
        assert v["detected_rank"] == v["numpy_matrix_rank_oracle"] == 2

    def test_rabi_matches_closed_form(self):
        doc = book_runner.book_rabi_oscillations({}, 1)
        v = doc["summary"]["validation"]
        assert v["max_trajectory_error"] < 1e-9
        assert abs(v["resonant_peak_population"] - 1.0) < 1e-6

    def test_tomography_ideal_inversion_is_exact(self):
        doc = book_runner.book_state_tomography({}, 1)
        v = doc["summary"]["validation"]
        assert v["ideal_reconstruction_error"] < 1e-12
        assert abs(v["min_eigenvalue_ideal"]) < 1e-9

    def test_tomography_low_shots_returns_physical_estimate(self):
        doc = book_runner.book_state_tomography({"shots": 10}, 1)
        vector = np.array(doc["artifacts"]["reconstructed_bloch_finite"])
        assert np.linalg.norm(vector) <= 1 + 1e-12
        assert doc["summary"]["validation"]["min_eigenvalue_finite"] >= -1e-12

    def test_rabi_detuned_unaligned_grid_matches_sampled_oracle(self):
        doc = book_runner.book_rabi_oscillations({"detunings": [1.0], "steps": 101}, 1)
        assert doc["summary"]["validation"]["passed"] is True

    def test_helstrom_nonorthogonal_unequal_prior(self):
        doc = execute_run("book_helstrom", {"theta": 1.2, "phi": 0.7, "prior": 0.3}, 1)
        expected = (1 + np.sqrt(1 - 4 * 0.3 * 0.7 * np.cos(0.6) ** 2)) / 2
        assert doc["metrics"]["success_probability"] == pytest.approx(expected)

    def test_channel_order_has_analytic_population_difference(self):
        doc = execute_run("book_channel_algebra", {"flip_probability": 0.3, "gamma": 0.4}, 1)
        assert doc["metrics"]["order_trace_distance"] == pytest.approx(0.12)
        assert doc["summary"]["validation"]["passed"] is True

    @pytest.mark.parametrize("module, config", [
        ("book_helstrom", {"prior": -0.1}),
        ("book_helstrom", {"mixing": float("nan")}),
        ("book_channel_algebra", {"gamma": 1.1}),
    ])
    def test_selected_experiment_rejects_invalid_probability(self, module, config):
        with pytest.raises(ValueError):
            execute_run(module, config, 1)
