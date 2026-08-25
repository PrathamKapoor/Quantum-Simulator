"""Measurement semantics: probabilities, collapse, seeded sampling.

Scientific notes
----------------
Computational-basis measurement of a set S of qubits yields outcome ``m`` with
probability ``P(m) = Σ_{i: i_S = m} |α_i|²``; afterwards the state collapses to
the projected subspace renormalized. This module never fabricates outcomes:
sampling always goes through the provided RNG so results are reproducible from
a seed (directive §27, §327).
"""
from __future__ import annotations

import numpy as np

from .states import QuantumCoreError, StateVector


def outcome_index_for_qubits(full_index: int, qubits: list[int]) -> int:
    """Map a full-basis index to the sub-index over ``qubits``.

    Bit k of the result corresponds to ``qubits[k]`` (subset-local little-
    endian). """
    out = 0
    for k, q in enumerate(qubits):
        out |= ((full_index >> q) & 1) << k
    return out


def measurement_probabilities(state: StateVector, qubits: list[int]) -> np.ndarray:
    """Probability vector over outcomes of measuring ``qubits``."""
    return state.marginal_probabilities(qubits)


def project_statevector(
    state: StateVector, qubits: list[int], outcome: int
) -> StateVector:
    """Collapse ``state`` onto the subspace where measured bits equal ``outcome``."""
    amps = state.amplitudes.copy()
    mask = 0
    for k, q in enumerate(qubits):
        bit = (outcome >> k) & 1
        mask |= bit << q
    keep_idx = np.array(
        [
            i
            for i in range(state.dimension)
            if outcome_index_for_qubits(i, qubits) == outcome
        ],
        dtype=np.int64,
    )
    projected = np.zeros_like(amps)
    projected[keep_idx] = amps[keep_idx]
    norm = float(np.linalg.norm(projected))
    if norm <= 0:
        raise QuantumCoreError(
            "Projection produced the zero vector: outcome has zero probability."
        )
    return StateVector(projected / norm, state.n_qubits)


def sample_outcome(probabilities: np.ndarray, rng: np.random.Generator) -> int:
    """Draw one outcome index according to `probabilities` using `rng`."""
    p = np.asarray(probabilities, dtype=float)
    total = p.sum()
    if abs(total - 1.0) > 1e-6:
        raise QuantumCoreError(
            f"Cannot sample from distribution summing to {total:.9f}."
        )
    return int(rng.choice(len(p), p=p / total))


def apply_readout_error(
    bits: list[int],
    p_wrong_0to1: float,
    p_wrong_1to0: float,
    rng: np.random.Generator,
) -> list[int]:
    """Classical readout confusion channel on measured bits.

    P(read 1 | actual 0) = p_wrong_0to1, P(read 0 | actual 1) = p_wrong_1to0
    (directive §260). Explicitly separate rates are kept because asymmetric
    readout errors are common on real devices.
    """
    out = []
    for b in bits:
        if b not in (0, 1):
            raise QuantumCoreError(f"Measured bit must be 0/1, got {b!r}.")
        flip_prob = p_wrong_0to1 if b == 0 else p_wrong_1to0
        flipped = rng.random() < flip_prob
        out.append(1 - b if flipped else b)
    return out


class MeasurementResult:
    """Outcome of one or more mid-circuit measurements."""

    def __init__(self, values: dict[int, int]):
        # maps clbit index -> measured bit value
        self.values = dict(values)

    def get(self, clbit: int) -> int:
        return self.values.get(clbit, 0)

    def as_int(self, clbits: list[int] | None = None) -> int:
        keys = sorted(self.values) if clbits is None else clbits
        val = 0
        for k in keys:
            val |= self.values.get(k, 0) << k
        return val
