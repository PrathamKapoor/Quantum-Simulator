"""Source-semantics regressions for chapter 2/3 book runners.

Independent oracles (no reuse of runner internals): textbook Pauli matrices,
Born-rule formulas and the Robertson bound. A failing runner validation flag
must fail these tests; a hard-coded pass must be detectable.
"""
import math

import numpy as np
import pytest

from app.experiments import book_runner


PAULIS = {
    "I": np.eye(2, dtype=complex),
    "X": np.array([[0, 1], [1, 0]], dtype=complex),
    "Y": np.array([[0, -1j], [1j, 0]], dtype=complex),
    "Z": np.array([[1, 0], [0, -1]], dtype=complex),
}


def _analytic_qubit(theta: float, phi: float) -> dict:
    v = np.array([math.cos(theta / 2), np.exp(1j * phi) * math.sin(theta / 2)],
                 dtype=complex)
    out = {}
    # Born probabilities of +1 eigenstates: P(+) = |<+_P|psi>|^2 = (1+<P>)/2.
    for name in ("x", "y", "z"):
        m = PAULIS[name.upper()]
        expectation = float(np.real(np.vdot(v, m @ v)))
        out[f"p_{name}_plus"] = (1 + expectation) / 2
    return out


def test_qubit_state_probabilities_match_born_rule_oracle():
    for theta, phi in ((1.1, 0.6), (0.0, 0.0), (np.pi, 1.3)):
        doc = book_runner.book_qubit_state({"theta": theta, "phi": phi}, 0)
        oracle = _analytic_qubit(theta, phi)
        for key, expected in oracle.items():
            runner_key = "p_z0" if key == "p_z_plus" else key
            assert doc["metrics"][runner_key] == pytest.approx(expected, abs=1e-12), key

def test_operator_report_classifies_pauli_relations():
    for a_name, b_name, expect_anticommute in (("X", "Y", True), ("X", "Z", True),
                                               ("Z", "X", True), ("X", "X", False),
                                               ("X", "I", False), ("Z", "Z", False)):
        doc = book_runner.book_operator_report(
            {"operator_a": a_name, "operator_b": b_name}, 0)
        v = doc["summary"]["validation"]
        assert v["anticommutes"] is expect_anticommute, (a_name, b_name, v)


def test_operator_report_validation_is_computed_not_constant():
    doc = book_runner.book_operator_report({"operator_a": "X", "operator_b": "Y"}, 0)
    v = doc["summary"]["validation"]
    # On |+>, <[X,Y]> = <2iZ> = 0, so the Robertson bound is exactly 0 and
    # the variance product (ΔX·ΔY = 1·0 = 0) saturates it.
    assert v["robertson_bound"] == pytest.approx(0.0)
    assert v["product_std"] >= v["robertson_bound"] - 1e-9
    assert v["satisfies_inequality"] is True
    assert isinstance(v["passed"], bool)
    # On |+>, <[Z,X]> = 2i<Y> = 0. A pair with a nonzero bound on |+> is
    # (Y, Z): <[Y,Z]> = 2i<X> = 2i, so the bound is exactly 1.
    doc2 = book_runner.book_operator_report({"operator_a": "Y", "operator_b": "Z"}, 0)
    assert doc2["summary"]["validation"]["robertson_bound"] == pytest.approx(1.0)
