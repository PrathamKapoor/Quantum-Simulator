"""Stabilizer-formalism utilities for QEC simulations.

Model scope (documented honestly, directive §61):
Errors and corrections are Pauli strings; syndromes are computed GROUP-
THEORETICALLY (does the error anticommute with each stabilizer generator?)
rather than by simulating ancilla-measurement circuits. This is the standard
technique for Monte Carlo logical-error benchmarking and is exact for Pauli
noise. Circuit-based syndrome extraction is demonstrated separately for the
3-qubit code (tests/integration), but the benchmark path uses this algebraic
method for speed.

Phases (+/-i factors) are ignored throughout: they carry no syndrome or
logical-flip information relevant here.
"""
from __future__ import annotations

import numpy as np

PAULI_I, PAULI_X, PAULI_Y, PAULI_Z = "I", "X", "Y", "Z"
_PAULIS = (PAULI_I, PAULI_X, PAULI_Y, PAULI_Z)


def validate_pauli_string(s: str) -> str:
    if not s or any(c not in _PAULIS for c in s.upper()):
        raise ValueError(f"Invalid Pauli string {s!r}.")
    return s.upper()


def pauli_commutes(a: str, b: str) -> bool:
    """Two Pauli strings commute iff they anticommute on an even number of positions."""
    validate_pauli_string(a)
    validate_pauli_string(b)
    if len(a) != len(b):
        raise ValueError(f"Pauli length mismatch: {len(a)} vs {len(b)}.")
    anti = sum(
        1
        for ca, cb in zip(a, b)
        if ca != PAULI_I and cb != PAULI_I and ca != cb
    )
    return anti % 2 == 0


def anticommuting_positions(a: str, b: str) -> list[int]:
    return [
        i
        for i, (ca, cb) in enumerate(zip(a, b))
        if ca != PAULI_I and cb != PAULI_I and ca != cb
    ]


def pauli_product_phase_ignorant(a: str, b: str) -> str:
    """Multiply Pauli strings ignoring global phase (X·Y = Z etc.)."""
    validate_pauli_string(a)
    validate_pauli_string(b)
    table = {
        # (left, right) -> product up to phase
        ("I", "I"): "I", ("I", "X"): "X", ("I", "Y"): "Y", ("I", "Z"): "Z",
        ("X", "I"): "X", ("X", "X"): "I", ("X", "Y"): "Z", ("X", "Z"): "Y",
        ("Y", "I"): "Y", ("Y", "X"): "Z", ("Y", "Y"): "I", ("Y", "Z"): "X",
        ("Z", "I"): "Z", ("Z", "X"): "Y", ("Z", "Y"): "X", ("Z", "Z"): "I",
    }
    return "".join(table[(ca, cb)] for ca, cb in zip(a, b))


def syndrome_of(error: str, generators: list[str]) -> tuple[int, ...]:
    """Syndrome bits: 1 where the error anticommutes with the generator."""
    return tuple(0 if pauli_commutes(error, g) else 1 for g in generators)


def apply_pauli_string(state_amplitudes: np.ndarray, pauli: str) -> np.ndarray:
    """Apply a tensor-product Pauli string to a little-endian statevector."""
    dim = state_amplitudes.shape[0]
    n = int(np.log2(dim))
    if len(pauli) != n:
        raise ValueError(f"Pauli length {len(pauli)} does not match {n} qubits.")
    out = state_amplitudes.copy()
    idx = np.arange(dim)
    vec = out.copy()
    for pos, ch in enumerate(pauli):
        q = n - 1 - pos  # leftmost char acts on highest qubit
        if ch == PAULI_X:
            vec = vec[idx ^ (1 << q)]
        elif ch == PAULI_Y:
            vec = vec[idx ^ (1 << q)] * np.where((idx >> q) & 1, 1j, -1j)
        elif ch == PAULI_Z:
            vec = vec * np.where((idx >> q) & 1, -1.0, 1.0)
    return vec


def random_pauli_errors(
    n_qubits: int, p: float, trials: int, rng: np.random.Generator
) -> np.ndarray:
    """Sample independent depolarizing errors per qubit: I w.p. 1-p, else X/Y/Z equally.

    Returns uint8 array of shape (trials, n_qubits) with values 0=I,1=X,2=Y,3=Z.
    """
    if not (0 <= p <= 1):
        raise ValueError(f"Physical error rate must be within [0,1], got {p}.")
    labels = rng.choice([0, 1, 2, 3], size=(trials, n_qubits), p=[1 - p, p / 3, p / 3, p / 3])
    return labels


_LABELS = _PAULIS


def error_labels_to_strings(labels: np.ndarray) -> list[str]:
    return ["".join(_LABELS[int(v)] for v in row) for row in labels]
