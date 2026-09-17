"""Observable MBQC experiment contracts through the canonical runner."""
import json

import numpy as np
import pytest

from app.experiments.runner import execute_run
from app.quantum.graph_states import run_mbqc_pattern
from app.quantum.states import QuantumCoreError


PATH = [[0, 1, 0], [1, 0, 1], [0, 1, 0]]


def test_registered_mbqc_validates_every_branch_and_serializes():
    doc = execute_run("book_mbqc", {"theta": 1.0, "phi": 0.37,
                                  "alpha": 0.4, "beta": 1.1}, 7)
    json.dumps(doc, allow_nan=False)
    branches = doc["artifacts"]["branches"]
    assert {tuple(b["outcomes"]) for b in branches} == {(0, 0), (0, 1), (1, 0), (1, 1)}
    assert sum(b["probability"] for b in branches) == pytest.approx(1)
    assert all(b["fidelity"] == pytest.approx(1, abs=1e-10) for b in branches)
    assert doc["summary"]["validation"]["passed"] is True
    assert any(b["uncorrected_fidelity"] < 0.99 for b in branches)
    assert doc == execute_run("book_mbqc", {"theta": 1.0, "phi": 0.37,
                                           "alpha": 0.4, "beta": 1.1}, 7)


@pytest.mark.parametrize("angles", [[0], [0, float("nan")]])
def test_mbqc_rejects_invalid_angles(angles):
    with pytest.raises((QuantumCoreError, ValueError)):
        run_mbqc_pattern(PATH, [1, 0], angles)


def test_mbqc_rejects_unnormalized_input():
    with pytest.raises(QuantumCoreError):
        run_mbqc_pattern(PATH, [1, 1], [0.2, 0.5])


def test_second_measurement_uses_first_outcome():
    ket = np.array([np.cos(0.5), np.exp(0.37j) * np.sin(0.5)])
    out = run_mbqc_pattern(PATH, ket, [0.4, 1.1], outcomes=[1, 0])
    assert out["measurement_angles"] == pytest.approx([0.4, -1.1])
    h = np.array([[1, 1], [1, -1]]) / np.sqrt(2)
    # No feed-forward has the opposite effective beta in this branch.
    wrong = h @ np.diag(np.exp(np.array([-1, 1]) * 0.55j)) @ h
    wrong = wrong @ np.diag(np.exp(np.array([1, -1]) * 0.2j)) @ ket
    assert abs(np.vdot(wrong, out["state"].amplitudes)) ** 2 < 0.99
