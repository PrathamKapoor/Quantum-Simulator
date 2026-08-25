"""Index-convention utilities for building custom gate matrices.

QuantumLab uses two index spaces and they MUST be converted explicitly:

1. **Full-register little-endian index** — used by state amplitudes and by
   algorithm tables (e.g. ``f(x)`` truth tables). Bit k = qubit k.
2. **Gate-local basis** — a k-qubit gate matrix is written with the FIRST
   operand as most-significant local bit (matches operators.py, e.g. CX with
   operands ``(control, target)``).

:func:`local_reorder` converts a matrix expressed in full-register indexing
over ``qubits_ascending`` into the equivalent gate-local matrix.
"""
from __future__ import annotations

import numpy as np

from ..quantum.states import QuantumCoreError


def operand_bit_mapping(qubits_ascending: list[int]) -> tuple[np.ndarray, np.ndarray]:
    """Return (full_to_local, local_to_full) index maps for the operand list.

    ``full`` here means the subsystem value space: bit j of a full-space index
    corresponds to operand ``qubits_ascending[j]`` (little-endian register
    reading). ``local`` is the gate-local basis with the first operand as MSB.
    """
    k = len(qubits_ascending)
    dim = 1 << k
    full_to_local = np.empty(dim, dtype=np.int64)
    local_to_full = np.empty(dim, dtype=np.int64)
    for full_idx in range(dim):
        m = 0
        for pos in range(k):
            m |= ((full_idx >> pos) & 1) << (k - 1 - pos)
        full_to_local[full_idx] = m
        local_to_full[m] = full_idx
    return full_to_local, local_to_full


def local_reorder(
    matrix_full: np.ndarray,
    qubits_ascending: list[int],
) -> np.ndarray:
    """Convert a matrix from full-register little-endian indexing over
    ``qubits_ascending`` into the gate-local basis (first operand = MSB).

    Example: diag([1,-1]) applied with operands [a, b] under full indexing
    (sign by qubit-a value) becomes diag([1,1,-1,-1]) locally.
    """
    m = np.asarray(matrix_full, dtype=np.complex128)
    k = len(qubits_ascending)
    dim = 1 << k
    if m.shape != (dim, dim):
        raise QuantumCoreError(
            f"Matrix shape {m.shape} does not match {len(qubits_ascending)} qubits."
        )
    full_to_local, _ = operand_bit_mapping(list(qubits_ascending))
    out = np.empty_like(m)
    out[np.ix_(full_to_local, full_to_local)] = m
    return out


def value_from_local_index(local_index: int, k: int) -> int:
    """Little-endian register value encoded in a gate-local index where
    operand j (ascending register qubit j) supplies local bit (k-1-j)."""
    val = 0
    for j in range(k):
        val |= ((local_index >> (k - 1 - j)) & 1) << j
    return val
