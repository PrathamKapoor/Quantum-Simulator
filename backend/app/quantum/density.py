"""Density matrices: mixed states, partial trace, fidelity, purity, entropy.

Scientific notes
----------------
A density matrix is Hermitian, positive semi-definite, unit trace:
``Tr(rho) ≈ 1``, ``rho† = rho``. We validate these on construction
(directive §30) and refuse NaN/Inf data outright (§293).

Fidelity here is the Uhlmann fidelity ``F(ρ,σ) = (Tr √(√ρ σ √ρ))²`` computed
via Hermitian eigendecomposition; the pure-state special case reduces to
``|<ψ|φ>|²``. Tiny negative eigenvalues from floating-point noise are clipped
at -0 tolerance and this clipping is reported through the module constant
documentation (directive §34).
"""
from __future__ import annotations

import numpy as np

from .states import QuantumCoreError, DEFAULT_TOLERANCE, StateVector
from .apply import apply_gate_density


class DensityMatrix:
    """Mixed-state container over an n-qubit system."""

    def __init__(self, matrix: np.ndarray, n_qubits: int, *, tolerance: float = DEFAULT_TOLERANCE):
        m = np.asarray(matrix, dtype=np.complex128)
        dim = 1 << n_qubits
        if m.shape != (dim, dim):
            raise QuantumCoreError(
                f"DensityMatrix shape {m.shape} inconsistent with {n_qubits} qubits "
                f"(expected {(dim, dim)})."
            )
        if not np.all(np.isfinite(m)):
            raise QuantumCoreError("DensityMatrix contains non-finite entries.")
        herm_dev = float(np.max(np.abs(m - m.conj().T)))
        if herm_dev > tolerance:
            raise QuantumCoreError(
                f"DensityMatrix is not Hermitian (max deviation {herm_dev:.3e} > {tolerance:.1e})."
            )
        tr = float(np.trace(m).real)
        if abs(tr - 1.0) > 1e-3:
            raise QuantumCoreError(
                f"DensityMatrix trace is {tr:.6f}, expected ≈ 1. "
                "Normalize explicitly before construction if needed."
            )
        self.matrix = m
        self.n_qubits = n_qubits

    # ---------- constructors ----------

    @classmethod
    def pure(cls, state: StateVector) -> "DensityMatrix":
        psi = state.amplitudes[:, None]
        return cls(psi @ psi.conj().T, state.n_qubits)

    @classmethod
    def maximally_mixed(cls, n_qubits: int) -> "DensityMatrix":
        dim = 1 << n_qubits
        return cls(np.eye(dim, dtype=np.complex128) / dim, n_qubits)

    @classmethod
    def computational_mixture(cls, probs: list[float]) -> "DensityMatrix":
        """Mixture Σ p_i |i><i| over computational basis states."""
        p = np.asarray(probs, dtype=float)
        dim = len(p)
        n = int(np.log2(dim))
        if dim & (dim - 1):
            raise QuantumCoreError("Number of probabilities must be a power of two.")
        if not np.all(np.isfinite(p)) or np.any(p < 0) or abs(p.sum() - 1.0) > 1e-9:
            raise QuantumCoreError("Probabilities must be finite, non-negative, summing to 1.")
        return cls(np.diag(p).astype(np.complex128), n)

    # ---------- basic quantities ----------

    def probabilities(self) -> np.ndarray:
        """Diagonal (computational-basis distribution)."""
        diag = np.real(np.diag(self.matrix))
        return np.clip(diag, 0.0, None)

    def trace(self) -> complex:
        return complex(np.trace(self.matrix))

    def purity(self) -> float:
        """P = Tr(ρ²); equals 1 iff the state is pure."""
        val = float(np.real(np.trace(self.matrix @ self.matrix)))
        return val

    def entropy(self, *, base: float | None = 2.0) -> float:
        """Von Neumann entropy S(ρ) = -Tr(ρ log ρ).

        Eigenvalues below ``-1e-12`` raise an error (numerically corrupt);
        eigenvalues in [-1e-12, 0] are treated as zero — this tolerance is the
        documented numerical policy (directive §34).
        """
        evals = np.linalg.eigvalsh(self.matrix)
        if evals.min() < -1e-8:
            raise QuantumCoreError(
                f"DensityMatrix has significantly negative eigenvalue {evals.min():.3e}; "
                "the state is not positive semi-definite."
            )
        evals = np.clip(evals, 0.0, None)
        evals = evals[evals > 1e-15]
        logs = np.log(evals)
        if base is not None:
            logs = logs / np.log(base)
        return float(-np.sum(evals * logs))

    # ---------- algebra ----------

    def apply_unitary(self, mat: np.ndarray, qubits: list[int]) -> "DensityMatrix":
        out = apply_gate_density(self.matrix, self.n_qubits, qubits, mat)
        result = DensityMatrix(out, self.n_qubits)
        return result

    def partial_trace(self, keep: list[int]) -> "DensityMatrix":
        """Reduced density matrix over ``keep``.

        Output qubit ``j`` corresponds to input qubit ``keep[j]`` exactly as
        listed (order preserved, duplicates rejected).
        """
        n = self.n_qubits
        seen = set()
        for q in keep:
            if not isinstance(q, int) or isinstance(q, bool):
                raise QuantumCoreError(f"Qubit index must be an integer, got {q!r}.")
            if not (0 <= q < n):
                raise QuantumCoreError(f"Qubit {q} out of range for {n} qubits.")
            if q in seen:
                raise QuantumCoreError(f"Duplicate qubit {q} in partial_trace keep list.")
            seen.add(q)
        if not keep:
            raise QuantumCoreError("partial_trace requires at least one kept qubit.")
        traced = [q for q in range(n) if q not in seen]
        t = self.matrix.reshape((2,) * (2 * n))
        # Build einsum subscript strings: kept qubits get distinct row/col
        # letters; traced-out qubits reuse ONE letter for their row/col bit so
        # they are contracted away.
        #
        # CRITICAL (bug fixed 2026-08 session 2): the OUTPUT letter order must
        # list ALL kept ROW letters first, then ALL kept COLUMN letters, so
        # that the reshape to (d, d) yields rows = kept-row-bits and columns =
        # kept-col-bits. Interleaving row/col per qubit silently produced a
        # transposed-axis mixing that only manifested for off-diagonal reduced
        # states with multi-qubit keeps (caught by remote-CNOT validation).
        idx_in = [None] * (2 * n)
        row_letters: list[str] = []
        col_letters: list[str] = []
        letters = iter("abcdefghijklmnopqrstuvwx")
        for q in keep:
            rl = next(letters)
            cl = next(letters)
            idx_in[n - 1 - q] = rl      # row bit of q
            idx_in[2 * n - 1 - q] = cl  # col bit of q
            row_letters.append(rl)
            col_letters.append(cl)
        for q in traced:
            l = next(letters)
            idx_in[n - 1 - q] = l
            idx_in[2 * n - 1 - q] = l
        spec_in = "".join(idx_in)
        spec_out = "".join(row_letters + col_letters)
        k = len(keep)
        reduced = np.einsum(spec_in + "->" + spec_out, t).reshape(1 << k, 1 << k)
        # Normalize trace drift from float error (documented policy: trace is
        # renormalized because physical partial trace preserves trace exactly;
        # drift here is purely numerical).
        tr = float(np.real(np.trace(reduced)))
        if abs(tr - 1.0) > 1e-6 or tr <= 0:
            raise QuantumCoreError(
                f"Partial trace produced trace {tr:.6f}; numerical failure."
            )
        return DensityMatrix(reduced / tr, k)

    def fidelity_with_statevector(self, other: StateVector) -> float:
        """Uhlmann fidelity between this mixed state and a pure state."""
        return self.fidelity_with(DensityMatrix.pure(other))

    def fidelity_with(self, other: "DensityMatrix") -> float:
        """Uhlmann fidelity F(ρ,σ) = (Tr √(√ρ σ √ρ))²."""
        if self.n_qubits != other.n_qubits:
            raise QuantumCoreError("Fidelity requires equal qubit counts.")
        root_self = _sqrtm_psd(self.matrix)
        inner = root_self @ other.matrix @ root_self
        s = np.linalg.eigvalsh(inner)
        s = np.clip(s, 0.0, None)
        return float(min(1.0, max(0.0, float(np.sum(np.sqrt(s)) ** 2))))

    def bloch_vector(self) -> np.ndarray:
        """Bloch vector r with ρ = ½(I + r·σ) for a single-qubit state."""
        if self.n_qubits != 1:
            raise QuantumCoreError(
                "bloch_vector is defined for single-qubit states; use partial_trace first."
            )
        x = float(np.real(np.trace(self.matrix @ PAULI_X)))
        y = float(np.real(np.trace(self.matrix @ PAULI_Y)))
        z = float(np.real(np.trace(self.matrix @ PAULI_Z)))
        return np.array([x, y, z])

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DensityMatrix):
            return NotImplemented
        return (
            self.n_qubits == other.n_qubits
            and np.allclose(self.matrix, other.matrix, atol=DEFAULT_TOLERANCE)
        )


PAULI_X = np.array([[0, 1], [1, 0]], dtype=np.complex128)
PAULI_Y = np.array([[0, -1j], [1j, 0]], dtype=np.complex128)
PAULI_Z = np.array([[1, 0], [0, -1]], dtype=np.complex128)


def _sqrtm_psd(m: np.ndarray) -> np.ndarray:
    """Matrix square root of a Hermitian PSD matrix via eigh.

    Eigenvalues in [-1e-12, 0) are clipped to zero; more negative values are
    treated as corruption upstream (entropy raises earlier for such inputs).
    """
    evals, evecs = np.linalg.eigh((m + m.conj().T) / 2)
    evals = np.clip(evals, 0.0, None)
    sqrt_evals = np.sqrt(evals)
    return (evecs * sqrt_evals[None, :]) @ evecs.conj().T


def trace_distance(a: DensityMatrix, b: DensityMatrix) -> float:
    """D(ρ,σ) = ½ Tr|ρ-σ|. Equals 1 − F only for pure states (documented)."""
    if a.n_qubits != b.n_qubits:
        raise QuantumCoreError("Trace distance requires equal qubit counts.")
    diff = a.matrix - b.matrix
    evals = np.linalg.eigvalsh(diff)
    return float(0.5 * np.sum(np.abs(evals)))
