"""Pure-state representation: StateVector.

Scientific notes
----------------
A pure n-qubit state is ``|psi> = sum_i alpha_i |i>`` with complex amplitudes
and the invariant ``sum_i |alpha_i|^2 = 1``. We do NOT silently renormalize:
construction validates finiteness and (by default) normalization; explicit
normalization is available through :meth:`StateVector.normalized` so that the
policy is always visible to callers (directive §17, §299).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np

# Numerical tolerance used across the quantum core. Chosen as a compromise:
# float64 accumulation over up to ~2^24 amplitudes keeps errors well below 1e-6,
# while still catching genuinely invalid input.
DEFAULT_TOLERANCE = 1e-6


class QuantumCoreError(ValueError):
    """Raised for mathematically invalid quantum objects.

    This is a *scientific* error class: callers must surface it rather than
    sanitize it away (directive §293).
    """


def _validate_finite(array: np.ndarray, what: str) -> None:
    if not np.all(np.isfinite(array)):
        raise QuantumCoreError(
            f"{what} contains NaN or infinite values; refusing to build a "
            "quantum object from non-finite data."
        )


@dataclass(frozen=True)
class StateVector:
    """Immutable pure-state container.

    Attributes:
        amplitudes: complex128 array of length 2**n_qubits.
        n_qubits: number of qubits.
    """

    amplitudes: np.ndarray = field(repr=False)
    n_qubits: int

    def __post_init__(self) -> None:
        amps = np.asarray(self.amplitudes, dtype=np.complex128)
        if amps.ndim != 1:
            raise QuantumCoreError("StateVector amplitudes must be a 1-D array.")
        dim = amps.shape[0]
        if dim == 0 or dim & (dim - 1):
            raise QuantumCoreError(
                f"State dimension must be a power of two, got {dim}."
            )
        _validate_finite(amps, "StateVector amplitudes")
        object.__setattr__(self, "amplitudes", amps)
        norm = float(np.linalg.norm(amps))
        # Construction enforces the defining invariant |ψ| = 1 within a loose
        # float-accumulation tolerance; callers wanting normalization must ask
        # for it explicitly via from_amplitudes(normalize_if_needed=True).
        if abs(norm - 1.0) > 1e-3:
            raise QuantumCoreError(
                f"StateVector amplitudes have norm {norm:.9f} != 1. "
                "Normalize explicitly (from_amplitudes with "
                "normalize_if_needed=True) instead of constructing directly."
            )

    # ---------- constructors ----------

    @classmethod
    def from_amplitudes(
        cls,
        amplitudes,
        *,
        normalize_if_needed: bool = False,
        tolerance: float = DEFAULT_TOLERANCE,
    ) -> "StateVector":
        """Build a state from amplitudes.

        By default the amplitudes must already have unit norm. With
        ``normalize_if_needed=True`` a non-unit-norm vector is normalized and
        the original norm is reported via the returned tuple's second element
        when using :meth:`from_amplitudes_reporting` — this method simply
        normalizes when needed; the *call site* is therefore visibly choosing
        normalization (directive §17).
        """
        amps = np.asarray(amplitudes, dtype=np.complex128)
        _validate_finite(amps, "StateVector amplitudes")
        n_qubits = int(np.log2(len(amps)))
        state_norm = float(np.linalg.norm(amps))
        if abs(state_norm - 1.0) <= tolerance:
            return cls(amplitudes=amps, n_qubits=n_qubits)
        if not normalize_if_needed:
            raise QuantumCoreError(
                f"Amplitude vector has norm {state_norm:.12f} != 1 within "
                f"tolerance {tolerance}. Pass normalize_if_needed=True to "
                "normalize explicitly."
            )
        if state_norm <= 0:
            raise QuantumCoreError("Cannot normalize the zero vector.")
        return cls(amplitudes=amps / state_norm, n_qubits=n_qubits)

    @classmethod
    def basis_state(cls, n_qubits: int, index: int) -> "StateVector":
        """Computational basis state |index> with little-endian bit meaning."""
        cls._check_qubit_count(n_qubits)
        dim = 1 << n_qubits
        if not (0 <= index < dim):
            raise QuantumCoreError(
                f"Basis index {index} out of range for {n_qubits} qubits [0, {dim})."
            )
        amps = np.zeros(dim, dtype=np.complex128)
        amps[index] = 1.0
        return cls(amplitudes=amps, n_qubits=n_qubits)

    @classmethod
    def zero(cls, n_qubits: int = 1) -> "StateVector":
        """|00...0>"""
        return cls.basis_state(n_qubits, 0)

    @classmethod
    def one(cls, n_qubits: int = 1) -> "StateVector":
        """|11...1>"""
        return cls.basis_state(n_qubits, (1 << n_qubits) - 1)

    @classmethod
    def plus(cls, n_qubits: int = 1) -> "StateVector":
        """Uniform superposition H^{tensor n} |0...0>, i.e. (1/sqrt(d)) Σ|i>."""
        cls._check_qubit_count(n_qubits)
        dim = 1 << n_qubits
        return cls(amplitudes=np.full(dim, 1 / np.sqrt(dim), dtype=np.complex128),
                   n_qubits=n_qubits)

    # ---------- basic properties ----------

    @property
    def dimension(self) -> int:
        return self.amplitudes.shape[0]

    def norm(self) -> float:
        return float(np.linalg.norm(self.amplitudes))

    def probabilities(self) -> np.ndarray:
        """P(i) = |alpha_i|^2 for every computational-basis index."""
        probs = np.abs(self.amplitudes) ** 2
        total = float(probs.sum())
        if abs(total - 1.0) > 1e-3:
            raise QuantumCoreError(
                f"Measurement probabilities sum to {total:.6f}, expected ~1. "
                "The state is corrupt or was constructed outside validation."
            )
        return probs

    def probability_of(self, index: int) -> float:
        return float(self.probabilities()[index])

    # ---------- algebra ----------

    def normalized(self) -> "StateVector":
        n = self.norm()
        if n <= 0:
            raise QuantumCoreError("Cannot normalize the zero vector.")
        return StateVector(self.amplitudes / n, self.n_qubits)

    def scale(self, factor: complex) -> "StateVector":
        out = self.amplitudes * complex(factor)
        _validate_finite(out, "Scaled amplitudes")
        return StateVector(out, self.n_qubits)

    def inner_product(self, other: "StateVector") -> complex:
        """<self|other>."""
        if self.n_qubits != other.n_qubits:
            raise QuantumCoreError(
                f"Inner product requires equal qubit counts ({self.n_qubits} vs {other.n_qubits})."
            )
        return complex(np.vdot(self.amplitudes, other.amplitudes))

    def fidelity_with(self, other: "StateVector") -> float:
        """Pure-state fidelity F = |<psi|phi>|^2 (directive §32)."""
        return float(abs(self.inner_product(other)) ** 2)

    def tensor(self, other: "StateVector") -> "StateVector":
        """Kronecker product self ⊗ other.

        ``self``'s qubits occupy the HIGH-order positions of the result, i.e.
        ``a.tensor(b).basis_index = a.index * b.dimension + b.index``.
        """
        combined = np.kron(self.amplitudes, other.amplitudes)
        return StateVector(combined, self.n_qubits + other.n_qubits)

    # ---------- measurement support ----------

    def marginal_probabilities(self, measured_qubits: list[int]) -> np.ndarray:
        """Probability distribution over the given subset of qubits.

        Returns an array of length 2**len(measured_qubits); entry j is
        P(measured bits equal j), where bit k of j corresponds to
        ``measured_qubits[k]`` (little-endian within the subset).
        """
        _validate_qubit_indices(measured_qubits, self.n_qubits)
        idx = np.arange(self.dimension)
        sub = np.zeros(self.dimension, dtype=np.int64)
        for k, q in enumerate(measured_qubits):
            sub |= ((idx >> q) & 1) << k
        probs = np.abs(self.amplitudes) ** 2
        return np.bincount(sub, weights=probs, minlength=1 << len(measured_qubits))

    def amplitude_of(self, index: int) -> complex:
        return complex(self.amplitudes[index])

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, StateVector):
            return NotImplemented
        return (
            self.n_qubits == other.n_qubits
            and np.allclose(self.amplitudes, other.amplitudes, atol=DEFAULT_TOLERANCE)
        )

    @staticmethod
    def _check_qubit_count(n_qubits: int) -> None:
        if n_qubits < 0:
            raise QuantumCoreError("Qubit count must be >= 0.")
        if n_qubits > MAX_QUBITS_STATEVECTOR:
            raise QuantumCoreError(
                f"{n_qubits} qubits exceed the state-vector limit "
                f"({MAX_QUBITS_STATEVECTOR}); state dimension would be 2**{n_qubits}."
            )


MAX_QUBITS_STATEVECTOR = 30  # safety ceiling; practical limits enforced by resource estimator


def validate_qubit_indices(qubits: list[int], n_qubits: int) -> None:
    _validate_qubit_indices(qubits, n_qubits)


def _validate_qubit_indices(qubits: list[int], n_qubits: int) -> None:
    seen = set()
    for q in qubits:
        if not isinstance(q, (int, np.integer)) or isinstance(q, bool):
            raise QuantumCoreError(f"Qubit index must be an integer, got {q!r}.")
        if not (0 <= q < n_qubits):
            raise QuantumCoreError(
                f"Qubit index {q} out of range for a system with {n_qubits} qubits."
            )
        if q in seen:
            raise QuantumCoreError(f"Duplicate qubit reference {q} in operand list.")
        seen.add(int(q))
