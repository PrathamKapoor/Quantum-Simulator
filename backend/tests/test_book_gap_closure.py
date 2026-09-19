"""Gap-closure book experiments: source-fixtured worksheets (ch.1, 3, 5, 6,
8, 9, 10, 11, 14).

Each test pairs the runner with an independent oracle recomputed in the
test body (exact integer/rational arithmetic, literal matrices, pow(),
dense diagonalization). Nothing asserts the runner's word for its own
correctness; error paths raise instead of fabricating.
"""
import json
import math
from fractions import Fraction

import numpy as np
import pytest

from app.experiments import book_runner
from app.experiments.runner import RUNNER_REGISTRY, execute_run

NEW_MODULES = [
    "book_classical_info",
    "book_beamsplitter",
    "book_hubbard",
    "book_rsa_toy",
    "book_ghz_superdense",
    "book_adiabatic_nonlinear",
    "book_qutrit_measurement",
    "book_operator_worksheet",
    "book_density_worksheet",
]


class TestRegistration:
    @pytest.mark.parametrize("module", NEW_MODULES)
    def test_registered_in_runner_registry(self, module):
        assert module in RUNNER_REGISTRY

    @pytest.mark.parametrize("module", NEW_MODULES)
    def test_runs_and_validates(self, module):
        doc = execute_run(module, {}, 7)
        assert doc["schema"] == "quantumlab.run-result"
        assert doc["module"] == module
        assert doc["summary"]["validation"]["passed"] is True

    @pytest.mark.parametrize("module", NEW_MODULES)
    def test_document_is_strict_json(self, module):
        json.dumps(execute_run(module, {}, 999))

    @pytest.mark.parametrize("module", NEW_MODULES)
    def test_deterministic_for_fixed_seed(self, module):
        a = execute_run(module, {}, 4242)
        b = execute_run(module, {}, 4242)
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


class TestClassicalInfo:
    def test_source_fixtures_exact(self):
        doc = execute_run("book_classical_info", {}, 0)
        v = doc["summary"]["validation"]
        assert v["code_bits"] == [5, 6] == [(26 - 1).bit_length(), (52 - 1).bit_length()]
        assert v["mode"] == 42
        assert Fraction(v["mean_exact"]) == Fraction(177, 4)
        # Independent rational recomputation of the income variance.
        vals = [Fraction("25.5"), 30, 42, 50, 63, 75, 90]
        counts = [3, 5, 7, 3, 1, 2, 1]
        mean = sum(x * c for x, c in zip(vals, counts)) / sum(counts)
        var = sum(c * (x - mean) ** 2 for x, c in zip(vals, counts)) / sum(counts)
        assert Fraction(v["variance_exact"]) == var
        assert doc["artifacts"]["message_count"] == str(2 ** 8192)

    def test_rejects_bad_inputs(self):
        with pytest.raises(ValueError):
            execute_run("book_classical_info", {"alphabet_sizes": [0]}, 0)
        with pytest.raises(ValueError):
            execute_run("book_classical_info", {"income_counts": [1, 2]}, 0)


class TestBeamsplitter:
    def test_double_application_is_ix(self):
        doc = execute_run("book_beamsplitter", {}, 0)
        # Artifacts store complex numbers as [real, imag] pairs (strict JSON).
        raw = np.array(doc["artifacts"]["beam_splitter"])
        b = raw[..., 0] + 1j * raw[..., 1]
        oracle = 1j * np.array([[0, 1], [1, 0]], dtype=complex)
        assert np.max(np.abs(b @ b - oracle)) < 1e-12
        # Independent definitional check from B = iI/sqrt(2) + X/sqrt(2).
        s = math.sqrt(2)
        assert np.max(np.abs(b - (1j * np.eye(2) / s + oracle / 1j / s))) < 1e-12


class TestHubbard:
    def test_units_and_pauli_expansions(self):
        doc = execute_run("book_hubbard", {}, 0)
        units = doc["artifacts"]["units"]

        def decode(raw):
            arr = np.array(raw)
            return arr[..., 0] + 1j * arr[..., 1]

        kets = np.eye(2, dtype=complex)
        for m in (0, 1):
            for n in (0, 1):
                assert np.max(np.abs(
                    decode(units[f"X^{m}{n}"]) - np.outer(kets[m], kets[n].conj()))) < 1e-12
        from app.quantum.operators import pauli_matrix
        got = {r["operator"]: r["oracle_error"]
               for r in doc["artifacts"]["expansions"]}
        assert set(got) == {"X", "Y", "Z", "I"}
        assert all(e < 1e-12 for e in got.values())
        assert np.max(np.abs(
            (decode(units["X^01"]) + decode(units["X^10"]))
            - pauli_matrix("X"))) < 1e-12


class TestRsaToy:
    def test_round_trip_and_known_answer(self):
        doc = execute_run("book_rsa_toy", {}, 0)
        v = doc["summary"]["validation"]
        assert (v["modulus"], v["phi"], v["private_exponent"]) == (3233, 3120, 2753)
        assert all(r["matches_pow_oracle"] for r in doc["artifacts"]["rows"])
        assert all(r["ciphertext"] == pow(r["message"], 17, 3233)
                   and r["recovered"] == r["message"]
                   for r in doc["artifacts"]["rows"])
        assert doc["artifacts"]["known_answer"] == {"message": 65, "ciphertext": 2790}

    def test_rejects_bad_keys(self):
        with pytest.raises(ValueError):
            execute_run("book_rsa_toy", {"p": 60, "q": 53}, 0)
        with pytest.raises(ValueError):
            execute_run("book_rsa_toy", {"p": 61, "q": 61}, 0)
        with pytest.raises(ValueError):
            execute_run("book_rsa_toy", {"public_exponent": 12}, 0)


class TestGhzSuperdense:
    def test_gram_identity_and_distinct_decodes(self):
        doc = execute_run("book_ghz_superdense", {}, 0)
        gram = np.array(doc["summary"]["validation"]["gram_max_error_vs_identity"]
                        * np.ones((1, 1)))
        assert doc["summary"]["validation"]["gram_max_error_vs_identity"] < 1e-12
        outcomes = [m["decoded_outcome"] for m in doc["artifacts"]["messages"]]
        assert len(set(outcomes)) == 4
        assert all(m["perfect"] for m in doc["artifacts"]["messages"])
        assert gram.shape == (1, 1)  # scalar error metric present


class TestAdiabaticNonlinear:
    def test_gap_and_branches_against_dense_oracle(self):
        doc = execute_run("book_adiabatic_nonlinear", {}, 0)
        v = doc["summary"]["validation"]
        h0 = np.diag([0.0, 1.0, 3.0, 4.0])
        hc = np.zeros((4, 4))
        hc[2, 3] = hc[3, 2] = 1.0
        h_mid = 0.5 * h0 + 0.5 * np.diag([0.0, 1.0, 4.0, 3.0]) + 0.25 * hc
        assert abs(np.min(np.diff(np.linalg.eigvalsh(h_mid))) - 0.5) < 1e-12
        assert abs(v["min_gap_dense_oracle"] - 0.5) < 1e-9
        assert [b["expected_cnot_image"] for b in doc["artifacts"]["branches"]] == [0, 1, 3, 2]

    def test_rejects_negative_coupling(self):
        with pytest.raises(ValueError):
            execute_run("book_adiabatic_nonlinear", {"coupling_strength": -1.0}, 0)


class TestAdiabaticEngineExtension:
    def test_coupling_none_preserves_linear_path(self):
        from app.quantum.adiabatic import interpolated_hamiltonian
        h0 = np.diag([-1.0, 1.0])
        h1 = -np.array([[0.0, 1.0], [1.0, 0.0]])
        for s in (0.0, 0.25, 0.5, 0.75, 1.0):
            assert np.max(np.abs(
                interpolated_hamiltonian(h0, h1, s)
                - ((1 - s) * h0 + s * h1))) == 0.0

    def test_coupling_adds_symmetric_bump(self):
        from app.quantum.adiabatic import interpolated_hamiltonian
        h0 = np.zeros((2, 2))
        h1 = np.zeros((2, 2))
        hc = np.array([[0.0, 2.0], [2.0, 0.0]])
        mid = interpolated_hamiltonian(h0, h1, 0.5, coupling=hc)
        assert np.max(np.abs(mid - 0.25 * hc)) < 1e-12
        assert np.max(np.abs(
            interpolated_hamiltonian(h0, h1, 0.0, coupling=hc) - h0)) < 1e-12
        assert np.max(np.abs(
            interpolated_hamiltonian(h0, h1, 1.0, coupling=hc) - h1)) < 1e-12

    def test_non_hermitian_coupling_rejected(self):
        from app.quantum.adiabatic import interpolated_hamiltonian
        from app.quantum.states import QuantumCoreError
        with pytest.raises(QuantumCoreError):
            interpolated_hamiltonian(np.eye(2), np.eye(2), 0.5,
                                     coupling=np.array([[0.0, 1.0], [0.0, 0.0]]))

    def test_initial_level_selects_excited_branch(self):
        from app.quantum.adiabatic import adiabatic_evolution
        h = np.diag([0.0, 5.0])
        r = adiabatic_evolution(h, h, total_time=10.0, steps=50, initial_level=1)
        assert r["level_overlaps"][1] > 1 - 1e-9


class TestWellExtension:
    def test_contraction_follows_level_two(self):
        doc = execute_run("book_adiabatic_well",
                          {"initial_level": 2, "width_from": 1.0, "width_to": 0.5}, 0)
        v = doc["summary"]["validation"]
        assert v["passed"] is True
        assert v["slow_level_probability"] > 0.95
        assert abs(v["energy_ratio_numerical"] - 4.0) / 4.0 < 0.03
        # Final n=2 energy is the source's 8 hbar^2 pi^2/(m a^2) in hbar=m=a=1 units.
        assert abs(v["energy_final"]["analytic"] - 8 * math.pi ** 2) < 1e-9

    def test_rejects_bad_level(self):
        with pytest.raises(ValueError):
            execute_run("book_adiabatic_well", {"initial_level": 9}, 0)


class TestQutrit:
    def test_ch06_preset_reproduces_source_outputs(self):
        doc = execute_run("book_qutrit_measurement", {"preset": "ch06_ex2"}, 0)
        v = doc["summary"]["validation"]
        assert [round(p, 12) for p in v["probabilities"]] == [0.25, 0.5, 0.25]
        assert abs(v["mean_energy"] - 2.0) < 1e-12

    def test_ch03_preset_probabilities(self):
        doc = execute_run("book_qutrit_measurement", {"preset": "ch03_ex10"}, 0)
        assert [round(p, 12) for p in
                doc["summary"]["validation"]["probabilities"]] == [0.25, 0.25, 0.5]

    def test_custom_and_rejections(self):
        doc = execute_run("book_qutrit_measurement",
                          {"preset": "custom",
                           "amplitudes": [[1, 0], [0, 0], [0, 0]],
                           "energies": [0.0, 1.0, 2.0]}, 0)
        assert doc["summary"]["validation"]["probabilities"][0] == pytest.approx(1.0)
        with pytest.raises(ValueError):
            execute_run("book_qutrit_measurement", {"preset": "nope"}, 0)
        with pytest.raises(ValueError):
            execute_run("book_qutrit_measurement",
                        {"preset": "custom",
                         "amplitudes": [[1, 0], [1, 0], [0, 0]],
                         "energies": [0.0, 1.0, 2.0]}, 0)


class TestOperatorWorksheet:
    def test_pauli_x_known_answers(self):
        doc = execute_run("book_operator_worksheet",
                          {"matrix": [[0, 1], [1, 0]]}, 0)
        v = doc["summary"]["validation"]
        assert v["hermitian"] and v["unitary"] and v["normal"]
        assert sorted(x if isinstance(x, float) else x[0]
                      for x in v["eigenvalues"]) == pytest.approx([-1.0, 1.0])
        assert v["singular_values"] == pytest.approx([1.0, 1.0])

    def test_default_rotation_scaling(self):
        doc = execute_run("book_operator_worksheet", {}, 0)
        v = doc["summary"]["validation"]
        assert v["normal"] and not v["hermitian"] and not v["unitary"]
        assert v["singular_values"] == pytest.approx([math.sqrt(5)] * 2)

    def test_rejects_non_square(self):
        with pytest.raises(ValueError):
            execute_run("book_operator_worksheet", {"matrix": [[1, 2, 3]]}, 0)


class TestDensityWorksheet:
    def test_default_state_known_answers(self):
        doc = execute_run("book_density_worksheet", {}, 0)
        v = doc["summary"]["validation"]
        assert v["valid_density"] is True
        assert v["purity"] == pytest.approx(0.6)
        assert v["bloch_vector"] == pytest.approx([0.4, 0.0, 0.2])
        # Independent eigenvalue oracle: purity = sum lambda^2.
        lam = np.linalg.eigvalsh(np.array([[0.6, 0.2], [0.2, 0.4]]))
        assert float(np.sum(lam ** 2)) == pytest.approx(0.6)

    def test_invalid_state_reported_not_repaired(self):
        doc = execute_run("book_density_worksheet",
                          {"rho": [[2.0, 0.0], [0.0, -1.0]]}, 0)
        assert doc["summary"]["validation"]["valid_density"] is False
        assert doc["summary"]["validation"]["passed"] is False

    def test_rejects_wrong_shape(self):
        with pytest.raises(ValueError):
            execute_run("book_density_worksheet", {"rho": [[1.0]]}, 0)
