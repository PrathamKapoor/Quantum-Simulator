"""Efficient operator application to states and density matrices.

Implementation strategy
-----------------------
Instead of materializing full 2**n x 2**n unitaries, we reshape states into
n-axis tensors (C order: axis 0 = most significant bit) and contract only the
axes belonging to the gate's operands. With the little-endian convention,
qubit ``k`` maps to axis ``n-1-k``.

Local basis ordering for a k-qubit gate on operands ``(a_0, ..., a_{k-1})``:
the FIRST operand is the most-significant local bit, matching
:mod:`app.quantum.operators` (e.g. ``CX`` operands ``(control, target)``).

These helpers are cross-checked against explicit Kronecker construction
(:func:`embed_operator`) in the test suite (directive §151).
"""
from __future__ import annotations

import numpy as np

from .states import QuantumCoreError


def _bit_axis(n_qubits: int, qubit: int) -> int:
    """Axis index in the C-order reshape corresponding to little-endian qubit."""
    return n_qubits - 1 - qubit


def apply_matrix_to_axes(
    tensor: np.ndarray, axes: list[int], mat: np.ndarray
) -> np.ndarray:
    """Contract ``mat`` onto the listed axes of ``tensor``.

    ``axes[0]`` is treated as the most-significant index of ``mat``'s local
    basis; subsequent axes follow in decreasing significance. Returns a new
    array; the input is not modified.
    """
    k = len(axes)
    dim_rows, dim_cols = mat.shape
    if dim_rows != dim_cols:
        raise QuantumCoreError("Operator matrix must be square.")
    if dim_rows != (1 << k):
        raise QuantumCoreError(
            f"Operator dimension {dim_rows} inconsistent with {k} axes."
        )
    ndim = tensor.ndim
    if len(set(axes)) != k:
        raise QuantumCoreError("Duplicate axes in operator application.")
    for ax in axes:
        if not (0 <= ax < ndim):
            raise QuantumCoreError(f"Axis {ax} out of range for {ndim}-d tensor.")
        if tensor.shape[ax] != 2:
            raise QuantumCoreError(f"Axis {ax} has size {tensor.shape[ax]}, expected 2.")

    moved = np.moveaxis(tensor, axes, list(range(k)))
    tail_shape = moved.shape[k:]
    flat = moved.reshape((dim_rows,) + (-1,))
    out = mat @ flat
    restored = out.reshape((2,) * k + tuple(tail_shape))
    return np.moveaxis(restored, list(range(k)), axes)


def apply_gate_statevector(
    state: np.ndarray, n_qubits: int, qubits: list[int], mat: np.ndarray
) -> np.ndarray:
    """Apply a gate matrix to the listed qubits of a statevector."""
    axes = [_bit_axis(n_qubits, q) for q in qubits]
    return apply_matrix_to_axes(state.reshape((2,) * n_qubits), axes, mat).reshape(-1)


def apply_gate_density(
    rho: np.ndarray, n_qubits: int, qubits: list[int], mat: np.ndarray
) -> np.ndarray:
    """Apply a unitary gate to a density matrix: ``rho' = M rho M†``.

    rho is reshaped to axes [row-bits MSB..LSB, col-bits MSB..LSB].
    The ket (column) side contracts with M, the bra (row) side with conj(M).
    Operand order is preserved on both sides (first operand = MSB).
    """
    t = rho.reshape((2,) * (2 * n_qubits))
    # Column bits live at positions 2n-1-q, row bits at positions n-1-q.
    ket_axes = [2 * n_qubits - 1 - q for q in qubits]
    bra_axes = [n_qubits - 1 - q for q in qubits]
    t = apply_matrix_to_axes(t, ket_axes, mat)
    t = apply_matrix_to_axes(t, bra_axes, mat.conj())
    return t.reshape(rho.shape)


# ---------------------------------------------------------------------------
# Reference embedding (slow, independent path used by tests / small systems)
# ---------------------------------------------------------------------------

def embed_operator(op: np.ndarray, n_qubits: int, qubits: list[int]) -> np.ndarray:
    """Embed a k-qubit operator into the full n-qubit space.

    Independent reference construction used for validation cross-checks
    (directive §151). Operand list follows the first-operand-is-MSB convention.
    """
    k = len(qubits)
    dim = 1 << n_qubits
    op = np.asarray(op, dtype=np.complex128)
    if op.shape != (1 << k, 1 << k):
        raise QuantumCoreError("Operator dimension mismatch with operand count.")
    full = np.zeros((dim, dim), dtype=np.complex128)
    for col in range(dim):
        for row in range(dim):
            outside_ok = True
            for q in range(n_qubits):
                if q not in qubits and ((row >> q) & 1) != ((col >> q) & 1):
                    outside_ok = False
                    break
            if not outside_ok:
                continue
            r_local = c_local = 0
            for pos, q in enumerate(qubits):
                bitpos = k - 1 - pos
                r_local |= ((row >> q) & 1) << bitpos
                c_local |= ((col >> q) & 1) << bitpos
            full[row, col] += op[r_local, c_local]
    return full
