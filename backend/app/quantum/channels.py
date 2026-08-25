"""Quantum channel framework (Kraus operators).

Scientific notes
----------------
A CPTP map acts as ``E(ρ) = Σ_k E_k ρ E_k†`` with completeness
``Σ_k E_k† E_k = I``. We validate trace preservation numerically on
construction (directive §37) because a non-TP "channel" would silently leak or
inject probability.

Channels are deliberately kept separate from gates: gates are unitary
reversible operations, channels are open-system evolution (§13, §37).
"""
from __future__ import annotations

import numpy as np

from .states import QuantumCoreError, DEFAULT_TOLERANCE
from .density import DensityMatrix

PAULI_X = np.array([[0, 1], [1, 0]], dtype=np.complex128)
PAULI_Y = np.array([[0, -1j], [1j, 0]], dtype=np.complex128)
PAULI_Z = np.array([[1, 0], [0, -1]], dtype=np.complex128)


class KrausChannel:
    """A trace-preserving quantum channel in Kraus form."""

    def __init__(
        self,
        kraus_operators: list[np.ndarray],
        n_qubits: int,
        *,
        tolerance: float = 1e-6,
        validate_trace_preserving: bool = True,
    ):
        ops = [np.asarray(k, dtype=np.complex128) for k in kraus_operators]
        if not ops:
            raise QuantumCoreError("KrausChannel requires at least one operator.")
        dim = 1 << n_qubits
        for i, k in enumerate(ops):
            if k.shape != (dim, dim):
                raise QuantumCoreError(
                    f"Kraus operator {i} has shape {k.shape}, expected {(dim, dim)}."
                )
        if validate_trace_preserving:
            completeness = sum(k.conj().T @ k for k in ops)
            dev = float(np.max(np.abs(completeness - np.eye(dim))))
            if dev > tolerance:
                raise QuantumCoreError(
                    f"Channel is not trace preserving: Σ E†E deviates from I by "
                    f"{dev:.3e} > {tolerance:.1e}."
                )
        self.kraus_operators = ops
        self.n_qubits = n_qubits

    def apply(self, rho: DensityMatrix) -> DensityMatrix:
        """Apply the channel to a density matrix of matching size."""
        if rho.n_qubits != self.n_qubits:
            raise QuantumCoreError(
                f"Channel acts on {self.n_qubits} qubit(s), got {rho.n_qubits}."
            )
        out = np.zeros_like(rho.matrix)
        for k in self.kraus_operators:
            out += k @ rho.matrix @ k.conj().T
        tr = float(np.real(np.trace(out)))
        if abs(tr - 1.0) > 1e-6:
            raise QuantumCoreError(
                f"Channel application produced trace {tr:.6f}; numerical failure."
            )
        return DensityMatrix(out / tr, rho.n_qubits)

    def apply_to_qubits(self, rho: DensityMatrix, qubits: list[int]) -> DensityMatrix:
        """Apply the channel to a subsystem of a larger register.

        Implemented by embedding each Kraus operator into the full space via
        the reference embedder; acceptable at QEC/noise-study scales.
        """
        from .apply import embed_operator

        out = np.zeros((rho.matrix.shape), dtype=np.complex128)
        full_ops = [embed_operator(k, rho.n_qubits, qubits) for k in self.kraus_operators]
        for op in full_ops:
            out += op @ rho.matrix @ op.conj().T
        # Trace drift is purely numerical; renormalize with validation.
        tr = float(np.real(np.trace(out)))
        if abs(tr - 1.0) > 1e-6:
            raise QuantumCoreError(
                f"Channel application produced trace {tr:.6f}; numerical failure."
            )
        return DensityMatrix(out / tr, rho.n_qubits)

    def is_unitary_channel(self, tolerance: float = DEFAULT_TOLERANCE) -> bool:
        return len(self.kraus_operators) == 1 and np.allclose(
            self.kraus_operators[0].conj().T @ self.kraus_operators[0],
            np.eye(1 << self.n_qubits),
            atol=tolerance,
        )


def _apply_full(rho: np.ndarray, k: np.ndarray) -> np.ndarray:
    return k @ rho @ k.conj().T


# ---------------------------------------------------------------------------
# Standard channels (directive §38)
# ---------------------------------------------------------------------------

def bit_flip_channel(probability: float) -> KrausChannel:
    p = _check_probability(probability, "bit_flip")
    k0 = np.sqrt(1 - p) * np.eye(2, dtype=np.complex128)
    k1 = np.sqrt(p) * PAULI_X
    return KrausChannel([k0, k1], 1)


def phase_flip_channel(probability: float) -> KrausChannel:
    p = _check_probability(probability, "phase_flip")
    k0 = np.sqrt(1 - p) * np.eye(2, dtype=np.complex128)
    k1 = np.sqrt(p) * PAULI_Z
    return KrausChannel([k0, k1], 1)


def bit_phase_flip_channel(probability: float) -> KrausChannel:
    p = _check_probability(probability, "bit_phase_flip")
    k0 = np.sqrt(1 - p) * np.eye(2, dtype=np.complex128)
    k1 = np.sqrt(p) * PAULI_Y
    return KrausChannel([k0, k1], 1)


def depolarizing_channel(probability: float, n_qubits: int = 1) -> KrausChannel:
    """Depolarizing: ρ → (1-p) ρ + p · I/d.

    Implemented in Pauli-twirl form: with probability p/4^d... For d=1 we use
    the standard K0=√(1−3p/4)·I plus √(p/4)(X,Y,Z). The documented relation is
    ``E(ρ) = (1 − p)ρ + p·I/2``, i.e. `p` is the total depolarization
    probability toward maximally mixed.
    """
    p = _check_probability(probability, "depolarizing")
    if n_qubits != 1:
        raise NotImplementedError(
            "Multi-qubit depolarizing channel not yet provided; compose single-qubit channels."
        )
    q = p / 4.0
    k0 = np.sqrt(1 - 3 * q) * np.eye(2, dtype=np.complex128)
    kx = np.sqrt(q) * PAULI_X
    ky = np.sqrt(q) * PAULI_Y
    kz = np.sqrt(q) * PAULI_Z
    return KrausChannel([k0, kx, ky, kz], 1)


def amplitude_damping_channel(gamma: float) -> KrausChannel:
    """|1⟩ decays toward |0⟩ with probability γ (energy relaxation T1 model).

    Kraus: K0=[[1,0],[0,√(1−γ)]], K1=[[0,√γ],[0,0]].
    """
    g = _check_probability(gamma, "amplitude_damping gamma")
    k0 = np.array([[1, 0], [0, np.sqrt(1 - g)]], dtype=np.complex128)
    k1 = np.array([[0, np.sqrt(g)], [0, 0]], dtype=np.complex128)
    return KrausChannel([k0, k1], 1)


def phase_damping_channel(gamma: float) -> KrausChannel:
    """Pure dephasing without energy loss (T2-type model).

    Uses the standard K0=√(1−γ)I, K1=√γ|0⟩⟨0|, K2=√γ|1⟩⟨1|.
    """
    g = _check_probability(gamma, "phase_damping gamma")
    k0 = np.sqrt(1 - g) * np.eye(2, dtype=np.complex128)
    k1 = np.sqrt(g) * np.array([[1, 0], [0, 0]], dtype=np.complex128)
    k2 = np.sqrt(g) * np.array([[0, 0], [0, 1]], dtype=np.complex128)
    return KrausChannel([k0, k1, k2], 1)


def thermal_relaxation_channel(t1_ns: float, t2_ns: float, duration_ns: float) -> KrausChannel:
    """T1/T2-inspired thermal relaxation channel.

    Model (documented simplification, zero-temperature bath):
      γ₁ = 1 − exp(−duration/T1)   (amplitude damping probability)
      dephasing: pure-dephasing rate satisfies 1/T2 = 1/(2T1) + 1/T_phi,
      hence pure-dephasing probability γ_φ over the gate duration is derived
      from exp(−duration·(1/T2 − 1/(2T1))) — implemented as composition of
      amplitude damping then phase damping with consistent rates.

    Requires T2 ≤ 2·T1 (physical bound); violations are rejected rather than
    clamped (directive §299).
    """
    if t1_ns <= 0 or t2_ns <= 0 or duration_ns < 0:
        raise QuantumCoreError("T1 and T2 must be > 0 and duration >= 0.")
    if t2_ns > 2 * t1_ns + 1e-12:
        raise QuantumCoreError(
            f"T2={t2_ns} ns violates the physical bound T2 ≤ 2·T1={2*t1_ns} ns."
        )
    gamma1 = 1.0 - float(np.exp(-duration_ns / t1_ns))
    # Pure dephasing factor exp(-t/T_phi):
    rate_phi = max(1.0 / t2_ns - 1.0 / (2.0 * t1_ns), 0.0)
    gamma_phi = 1.0 - float(np.exp(-duration_ns * rate_phi))
    amp = amplitude_damping_channel(gamma1)
    ph = phase_damping_channel(gamma_phi)
    return CompositeChannel([amp, ph])


class CompositeChannel(KrausChannel):
    """Sequential composition of channels acting on the same subsystem size.

    The composed Kraus set is {L_i K_j}; validated for trace preservation.
    """

    def __init__(self, channels: list[KrausChannel]):
        sizes = {c.n_qubits for c in channels}
        if len(sizes) != 1:
            raise QuantumCoreError(f"CompositeChannel requires uniform sizes, got {sizes}.")
        kraus: list[np.ndarray] = []
        # channels[0] applies first, then subsequent ones.
        current = [np.eye(1 << next(iter(sizes)), dtype=np.complex128)]
        for ch in channels:
            current = [k2 @ k1 for k1 in current for k2 in ch.kraus_operators]
        kraus = current
        super().__init__(kraus, next(iter(sizes)), tolerance=1e-5)


def _check_probability(value: float, name: str) -> float:
    v = float(value)
    if not np.isfinite(v) or not (0.0 <= v <= 1.0):
        raise QuantumCoreError(
            f"{name}: probability must satisfy 0 ≤ p ≤ 1, got {value!r}."
        )
    return v
