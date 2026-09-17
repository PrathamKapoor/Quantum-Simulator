"""Teleportation must transfer Alice's unknown state, not start it at Bob."""
import numpy as np
import pytest

from app.protocols.communication import run_teleportation


def test_shared_bell_pair_is_independent_of_alice_input():
    theta, phi = 1.13, 0.71
    psi = np.array([np.cos(theta / 2), np.exp(1j * phi) * np.sin(theta / 2)])
    result = run_teleportation(theta, phi)
    bell = np.array([1, 0, 0, 1]) / np.sqrt(2)
    expected = np.kron(psi, bell)
    actual = np.asarray(result["intermediate_states"]["after_bell_pair"])
    np.testing.assert_allclose(actual, expected, atol=1e-12)
    # Tensor order is explicitly Alice input, Alice resource, Bob.
    state = actual.reshape(4, 2)
    np.testing.assert_allclose(state.T @ state.conj(), np.eye(2) / 2, atol=1e-12)
    assert {(b["m1"], b["m2"]) for b in result["branches"]} == {(0, 0), (0, 1), (1, 0), (1, 1)}
    for branch in result["branches"]:
        assert branch["probability"] == pytest.approx(0.25)
        assert branch["bob_fidelity"] == pytest.approx(1.0)
    assert result["teleportation_fidelity"] == pytest.approx(1.0)
