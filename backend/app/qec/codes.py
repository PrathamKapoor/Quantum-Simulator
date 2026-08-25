"""Quantum error-correcting codes: stabilizer data, logicals, encoders.

Each code declares:
  - stabilizer generators (Pauli strings, leftmost char = highest qubit)
  - logical X and Z operators
  - a syndrome->recovery lookup table built by enumerating correctable errors
    (weight <= floor((d-1)/2) patterns are guaranteed correctable; the table is
    constructed from actual group algebra, not hand-typed)

Codes provided: 3-qubit bit-flip, 3-qubit phase-flip, Shor-9, Steane-7,
5-qubit perfect code, plus the toric surface code (surface_code.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .stabilizer import (
    PAULI_I,
    anticommuting_positions,
    pauli_commutes,
    pauli_product_phase_ignorant,
    syndrome_of,
    validate_pauli_string,
)


@dataclass(frozen=True)
class QECode:
    name: str
    n: int                      # physical qubits
    k: int                      # logical qubits encoded (1 for all codes here)
    distance: int               # code distance d
    generators: tuple[str, ...]  # n-k stabilizer generators
    logical_x: str              # logical X operator
    logical_z: str              # logical Z operator
    description: str = ""
    # Which single-qubit Pauli types the code guarantees to correct at weight
    # <= floor((d-1)/2). Repetition codes protect ONE error type only; e.g.
    # Y carries both X and Z components so it fails on bit-flip-3.
    corrects_paulis: tuple[str, ...] = ("X", "Y", "Z")
    encoder_circuit_builder: str | None = None  # registered builder name, if any

    def __post_init__(self):
        for g in self.generators:
            validate_pauli_string(g)
            if len(g) != self.n:
                raise ValueError(f"Generator {g!r} length != {self.n}.")
        validate_pauli_string(self.logical_x)
        validate_pauli_string(self.logical_z)
        # Stabilizers must mutually commute.
        gens = list(self.generators)
        for i in range(len(gens)):
            for j in range(i + 1, len(gens)):
                if not pauli_commutes(gens[i], gens[j]):
                    raise ValueError(
                        f"Code {self.name}: generators {gens[i]} and {gens[j]} anticommute."
                    )
        # Logicals must commute with all stabilizers.
        for g in gens:
            if not pauli_commutes(g, self.logical_x) or not pauli_commutes(g, self.logical_z):
                raise ValueError(f"Code {self.name}: logical anticommutes with stabilizer {g}.")
        # Logical X and Z must anticommute with each other.
        if pauli_commutes(self.logical_x, self.logical_z):
            raise ValueError(f"Code {self.name}: logical X and Z must anticommute.")

    def is_logical_failure(self, residual: str) -> bool:
        """A residual Pauli (commuting with all stabilizers) fails the code iff
        it acts nontrivially on the logical qubit, i.e. anticommutes with the
        opposite-type logical operator."""
        return (not pauli_commutes(residual, self.logical_x)) or (
            not pauli_commutes(residual, self.logical_z)
        )


# ---------------------------------------------------------------------------
# Code definitions
# ---------------------------------------------------------------------------

BIT_FLIP_3 = QECode(
    name="bit-flip-3",
    n=3, k=1, distance=3,
    generators=("ZZI", "IZZ"),
    logical_x="XXX",
    logical_z="ZII",
    corrects_paulis=("X",),
    description="3-qubit repetition code correcting one X (bit-flip) error.",
)

PHASE_FLIP_3 = QECode(
    name="phase-flip-3",
    n=3, k=1, distance=3,
    generators=("XXI", "IXX"),
    # Encoded states |0L>=|+++>, |1L>=|--->; the logical NOT is ZZZ
    # (flips each qubit between + and -), logical phase flip is XII.
    logical_x="ZZZ",
    logical_z="XII",
    corrects_paulis=("Z",),
    description="3-qubit repetition code correcting one Z (phase-flip) error.",
)

SHOR_9 = QECode(
    name="shor-9",
    n=9, k=1, distance=3,
    generators=(
        "ZZIIIIIII", "IZZIIIIII",
        "IIIZZIIII", "IIIIZZIII",
        "IIIIIIZZI", "IIIIIIIZZ",
        "XXXXXXIII", "IIIXXXXXX",
    ),
    # Derived from the encoding |0L>=(|000>+|111>)^x3 / 2sqrt2:
    # logical NOT flips one block's sign per block: Z0 Z3 Z6;
    # logical phase flip flips the sign of |111>-components: X0 X1 X2.
    logical_x="ZIIZIIZII",
    logical_z="XXXIIIIII",
    description="Shor's 9-qubit code correcting one arbitrary single-qubit error.",
)

STEANE_7 = QECode(
    name="steane-7",
    n=7, k=1, distance=3,
    # CSS from the self-orthogonal [7,4] Hamming code; X- and Z-checks share
    # support patterns so every X/Z generator pair overlaps evenly.
    generators=(
        "XIXIXIX", "XXIIXXI", "XXXXIII",
        "ZIZIZIZ", "ZZIIZZI", "ZZZZIII",
    ),
    logical_x="XXXXXXX",
    logical_z="ZZZZZZZ",
    description="Steane [[7,1,3]] CSS code correcting one arbitrary error.",
)

FIVE_QUBIT = QECode(
    name="five-qubit",
    n=5, k=1, distance=3,
    generators=("XZZXI", "IXZZX", "XIXZZ", "ZXIXZ"),
    logical_x="XXXXX",
    logical_z="ZZZZZ",
    description="Perfect [[5,1,3]] code correcting one arbitrary error.",
)


CODE_REGISTRY: dict[str, QECode] = {
    c.name: c for c in (BIT_FLIP_3, PHASE_FLIP_3, SHOR_9, STEANE_7, FIVE_QUBIT)
}


def get_code(name: str) -> QECode:
    try:
        return CODE_REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"Unknown code {name!r}. Available: {', '.join(sorted(CODE_REGISTRY))}, toric-surface."
        ) from None


# ---------------------------------------------------------------------------
# Syndrome -> recovery lookup construction
# ---------------------------------------------------------------------------

def build_recovery_table(code: QECode, max_weight: int | None = None) -> dict[tuple[int, ...], str]:
    """Enumerate errors up to `max_weight` non-identity factors, compute their
    syndromes, and record the FIRST matching recovery.

    Ties (degenerate syndromes among correctable errors) are resolved by
    choosing any error of that class — valid because degenerate errors differ
    by a stabilizer and act identically on the code space. The resulting table
    is verified against every enumerated error before returning; construction
    failures raise rather than silently degrading.
    """
    if max_weight is None:
        max_weight = (code.distance - 1) // 2
    table: dict[tuple[int, ...], str] = {}
    labels = ("I",) + tuple(code.corrects_paulis)
    import itertools

    positions = range(code.n)
    for weight in range(0, max_weight + 1):
        for support in itertools.combinations(positions, weight):
            for combo in itertools.product(labels[1:], repeat=weight):
                chars = [PAULI_I] * code.n
                for pos, ch in zip(support, combo):
                    chars[pos] = ch
                error = "".join(chars)
                syn = syndrome_of(error, list(code.generators))
                if syn not in table:
                    table[syn] = error
    # Strong verification pass: re-enumerate every guaranteed-correctable
    # error and confirm its recovery leaves no logical damage.
    import itertools

    for weight in range(0, max_weight + 1):
        for support in itertools.combinations(positions, weight):
            for combo in itertools.product(labels[1:], repeat=weight):
                chars = [PAULI_I] * code.n
                for pos, ch in zip(support, combo):
                    chars[pos] = ch
                error = "".join(chars)
                recovery = table[syndrome_of(error, list(code.generators))]
                residual = pauli_product_phase_ignorant(recovery, error)
                if code.is_logical_failure(residual):
                    raise AssertionError(
                        f"Recovery table verification failed for {code.name}: "
                        f"error {error} recovered by {recovery} leaves logical residual."
                    )
    return table


def _is_stabilizer_equivalent(code: QECode, pauli: str) -> bool:
    """True iff `pauli` equals a product of generators (stabilizer element)."""
    gens = list(code.generators)
    elements = {PAULI_I * code.n}
    for g in gens:
        elements |= {pauli_product_phase_ignorant(e, g) for e in list(elements)}
    return pauli in elements


def decode_and_recover(code: QECode, table: dict[tuple[int, ...], str], error: str) -> tuple[str, bool]:
    """Return (recovery, corrected_flag) for a given physical error."""
    syn = syndrome_of(error, list(code.generators))
    recovery = table.get(syn)
    if recovery is None:
        return "", False
    residual = pauli_product_phase_ignorant(recovery, error)
    failed = code.is_logical_failure(residual)
    return recovery, not failed
