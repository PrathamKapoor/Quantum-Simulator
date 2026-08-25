"""Quantum Fourier transform (QFT) and inverse QFT.

Scientific notes
----------------
Implements the textbook QFT circuit (Hadamards + controlled phase rotations +
final qubit reversal) under QuantumLab's little-endian convention. Correctness
is verified against the explicit discrete-Fourier-transform matrix
F_{kj} = e^{2πi jk/N}/√N in tests (directive §151).

Approximate QFT: controlled rotations with angle below `cutoff_exponent`
(2π/2^m with m > cutoff) are dropped, reducing gate count. When approximation
is active, results carry an explicit warning flag — never silently (§46).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..circuits.model import Circuit


@dataclass
class QFTInfo:
    n_qubits: int
    approximate: bool
    dropped_rotations: int
    warnings: list[str] = field(default_factory=list)


def build_qft(n_qubits: int, *, inverse: bool = False, cutoff_exponent: int | None = None) -> tuple[Circuit, QFTInfo]:
    """Build a QFT (or inverse QFT) circuit.

    cutoff_exponent: if set, controlled rotations CP(2π/2^m) with m > cutoff
    are omitted (approximate QFT).
    """
    if n_qubits < 1:
        raise ValueError("QFT requires at least 1 qubit.")
    circuit = Circuit(num_qubits=n_qubits, num_clbits=0, name=f"{'iqft' if inverse else 'qft'}-{n_qubits}")
    info = QFTInfo(n_qubits=n_qubits, approximate=False, dropped_rotations=0)

    def add_cp(control: int, target: int, angle: float) -> None:
        # CP(angle) == CRZ-like controlled phase; expressed via RZZ+RZ pair:
        # CP(λ) on (a,b) equals RZ(λ/2) on a, RZ(λ/2) on b, RZZ(-λ/2)(a,b)
        # up to global phase. We instead emit the native PHASE-based identity:
        # CP(λ) = P(λ/2)_a · P(λ/2)_b · CX(a,b) P(-λ/2)_b CX(a,b).
        circuit.add_gate("P", [control], params=[angle / 2])
        circuit.add_gate("P", [target], params=[angle / 2])
        circuit.add_gate("CX", [control, target])
        circuit.add_gate("P", [target], params=[-angle / 2])
        circuit.add_gate("CX", [control, target])

    # Process qubits from most significant (n-1) down to least significant.
    for target in range(n_qubits - 1, -1, -1):
        circuit.add_gate("H", [target])
        # Controls: lower-significance qubits relative to processing order.
        distance = 1
        for control in range(target - 1, -1, -1):
            angle = math.pi / (2 ** distance)
            if cutoff_exponent is not None and distance > cutoff_exponent:
                info.dropped_rotations += 1
            else:
                add_cp(control, target, angle)
            distance += 1
    # Reverse qubit order to fix endianness of the textbook construction.
    for i in range(n_qubits // 2):
        circuit.add_gate("SWAP", [i, n_qubits - 1 - i])

    if inverse:
        inv = Circuit(num_qubits=n_qubits, name=f"iqft-{n_qubits}")
        for op in reversed(circuit.operations):
            _append_inverse(inv, op)
        circuit = inv

    if info.dropped_rotations:
        info.approximate = True
        info.warnings.append(
            f"Approximate QFT active: {info.dropped_rotations} rotation(s) with "
            f"angle < 2π/2^{cutoff_exponent} were dropped."
        )
    return circuit, info


def _append_inverse(target: Circuit, op) -> None:
    """Append the inverse of operation `op` onto `target` (reversed order)."""
    import math

    kind = op.kind
    if kind == "gate":
        name = op.gate
        params = list(op.params)
        qubits = list(op.qubits)
        if name == "H":
            target.add_gate("H", qubits)
        elif name == "SWAP":
            target.add_gate("SWAP", qubits)
        elif name == "P":
            target.add_gate("P", qubits, params=[-params[0]])
        elif name == "CX":
            target.add_gate("CX", qubits)
        elif name in ("RX", "RY", "RZ"):
            target.add_gate(name, qubits, params=[-params[0]])
        else:
            raise NotImplementedError(f"No inverse rule for gate {name}")
    elif kind in ("barrier",):
        target.add_barrier(list(op.qubits))
    else:
        raise NotImplementedError(f"Cannot invert operation kind {kind}")


def dft_matrix(n_qubits: int) -> "np.ndarray":
    """Explicit QFT matrix F_{kj} = ω^{jk}/√N — reference implementation."""
    import numpy as np

    dim = 1 << n_qubits
    j = np.arange(dim)
    omega = np.exp(2j * np.pi * np.outer(j, j) / dim)
    return omega / math.sqrt(dim)
