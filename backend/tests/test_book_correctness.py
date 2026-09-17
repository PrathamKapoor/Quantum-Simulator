"""Phase-sensitive recovery, Bell-target and common-channel analytic oracles."""
import numpy as np
import pytest

from app.experiments import book_runner


def _complex_matrix(value):
    pairs = np.asarray(value)
    return pairs[..., 0] + 1j * pairs[..., 1]


@pytest.mark.parametrize("name", ["bit-flip-3", "phase-flip-3", "shor-9", "steane-7", "five-qubit"])
def test_qec_preserves_complex_logical_coherence_in_every_recovery_branch(name):
    doc = book_runner.book_qec_codes({"codes": [name]}, 0)
    row = doc["artifacts"]["codes"][0]
    states = {s["label"]: _complex_matrix(s["amplitudes"]) for s in doc["artifacts"]["logical_states"]}
    assert any(abs((a[0] * a[1].conjugate()).imag) > 0.1 for a in states.values())
    for case in row["cases"]:
        if not case["guaranteed"]:
            continue
        a = states[case["logical"]]
        expected = np.outer(a, a.conj())
        assert sum(b["probability"] for b in case["branches"]) == pytest.approx(1, abs=1e-10)
        assert case["state_fidelity"] == pytest.approx(1, abs=1e-10)
        for branch in case["branches"]:
            np.testing.assert_allclose(_complex_matrix(branch["logical_density"]), expected, atol=1e-10)
        if case["noise"] == "coherent_rotation" and len(case["branches"]) == 2:
            angle = doc["artifacts"]["coherent_angle"]
            assert sorted(b["probability"] for b in case["branches"]) == pytest.approx(
                sorted([np.cos(angle / 2) ** 2, np.sin(angle / 2) ** 2]), abs=1e-10)
    assert row["guaranteed_success"] == row["guaranteed_cases"]
    if name in ("bit-flip-3", "phase-flip-3"):
        assert any(c["logical"] == "complex" and c["state_fidelity"] < 0.9
                   for c in row["cases"] if not c["guaranteed"])


def test_qec_validation_rejects_logical_phase_damage(monkeypatch):
    from app.qec import codes
    from app.qec.stabilizer import pauli_product_phase_ignorant
    original = codes.build_recovery_table

    def phase_damaged_table(code, *args, **kwargs):
        return {s: pauli_product_phase_ignorant(r, code.logical_z)
                for s, r in original(code, *args, **kwargs).items()}

    monkeypatch.setattr(codes, "build_recovery_table", phase_damaged_table)
    result = book_runner.book_qec_codes({"codes": ["bit-flip-3"]}, 0)
    assert result["summary"]["validation"]["passed"] is False
    cases = result["artifacts"]["codes"][0]["cases"]
    assert all(c["state_fidelity"] == pytest.approx(1) for c in cases
               if c["guaranteed"] and c["logical"] in (0, 1))
    assert any(c["state_fidelity"] < 0.1 for c in cases
               if c["guaranteed"] and c["logical"] == "plus_i")


def test_swapping_has_correct_bell_target_for_all_four_outcomes():
    result = book_runner.book_entanglement_swapping({}, 0)
    rows = result["artifacts"]["outcomes"]
    assert {tuple(r["outcome_bc"]) for r in rows} == {(0, 0), (0, 1), (1, 0), (1, 1)}
    phi = np.array([1, 0, 0, 1]) / np.sqrt(2)
    for row in rows:
        phase, flip = row["outcome_bc"]
        bell = np.zeros(4)
        bell[2 * flip] = 1 / np.sqrt(2)
        bell[2 * (1 - flip) + 1] = (-1) ** phase / np.sqrt(2)
        assert row["probability"] == pytest.approx(0.25)
        np.testing.assert_allclose(_complex_matrix(row["outer_density_before_correction"]), np.outer(bell, bell), atol=1e-10)
        np.testing.assert_allclose(_complex_matrix(row["outer_density_after_correction"]), np.outer(phi, phi), atol=1e-10)
        assert row["corrected_target_fidelity"] == pytest.approx(1)


def test_common_channel_metrics_match_bloch_vector_formulas():
    result = book_runner.book_qi_metrics({}, 0)
    r = np.array([0.6, 0.2, 0.3])
    s = np.array([-0.2, 0.5, -0.4])

    def metrics(a, b):
        return np.linalg.norm(a - b) / 2, (1 + a @ b + np.sqrt((1 - a @ a) * (1 - b @ b))) / 2

    before_d, before_f = metrics(r, s)
    for row in result["artifacts"]["contractivity"]:
        p = row["strength"]
        if row["channel"] == "depolarizing":
            a, b = (1 - p) * r, (1 - p) * s
        elif row["channel"] == "amplitude_damping":
            a, b = [np.array([np.sqrt(1 - p) * v[0], np.sqrt(1 - p) * v[1], (1 - p) * v[2] + p]) for v in (r, s)]
        else:
            assert row["channel"] == "phase_damping"
            a, b = [v * [1 - p, 1 - p, 1] for v in (r, s)]
        expected_d, expected_f = metrics(a, b)
        assert row["trace_distance_before"] == pytest.approx(before_d)
        assert row["fidelity_before"] == pytest.approx(before_f)
        assert row["trace_distance_after"] == pytest.approx(expected_d, abs=1e-9)
        assert row["fidelity_after"] == pytest.approx(expected_f, abs=1e-9)
        assert row["trace_distance_after"] <= before_d + 1e-9
        assert row["fidelity_after"] >= before_f - 1e-9
