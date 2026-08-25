"""Observables: Pauli strings and expectation values.

Scientific notes
----------------
A Pauli string like ``"XIZ"`` acts on n qubits with position j (left-to-right)
acting on qubit n-1-j, so that the string reads naturally high-order-first
(same convention as writing ket labels ``|q2 q1 q0>``). This is documented and
tested; it is the single place this display convention is defined.
"""
from __future__ import annotations

import numpy as np

from .states import QuantumCoreError, StateVector, DEFAULT_TOLERANCE
from .density import DensityMatrix
from .apply import embed_operator

_PAULI_MATRICES = {
    "I": np.eye(2, dtype=np.complex128),
    "X": np.array([[0, 1], [1, 0]], dtype=np.complex128),
    "Y": np.array([[0, -1j], [1j, 0]], dtype=np.complex128),
    "Z": np.array([[1, 0], [0, -1]], dtype=np.complex128),
}


class PauliString:
    """A tensor product of single-qubit Paulis with a scalar coefficient."""

    def __init__(self, term: str, coefficient: complex = 1.0):
        term_u = term.upper()
        if not term_u or any(c not in "IXYZ" for c in term_u):
            raise QuantumCoreError(
                f"Invalid Pauli string {term!r}; only characters I,X,Y,Z allowed."
            )
        self.term = term_u
        self.coefficient = complex(coefficient)

    @property
    def n_qubits(self) -> int:
        return len(self.term)

    def matrix(self) -> np.ndarray:
        """Dense matrix via Kronecker products (reference implementation).

        Position 0 of the string is the most significant qubit, matching the
        reading order of ket labels.
        """
        out = np.array([[self.coefficient]], dtype=np.complex128)
        for ch in self.term:
            out = np.kron(out, _PAULI_MATRICES[ch])
        return out

    def expectation(self, state: StateVector) -> complex:
        """<ψ| P |ψ> computed without densifying when possible."""
        vec = state.amplitudes
        dim = 1 << state.n_qubits
        if self.n_qubits != state.n_qubits:
            raise QuantumCoreError(
                f"Pauli string acts on {self.n_qubits} qubits, state has {state.n_qubits}."
            )
        result = np.zeros(dim, dtype=np.complex128)
        idx = np.arange(dim)
        phase = np.ones(dim, dtype=np.float64)
        for pos, ch in enumerate(self.term):
            q = self.n_qubits - 1 - pos
            bit = (idx >> q) & 1
            if ch == "X":
                partner = idx ^ (1 << q)
                vec = vec[partner]
            elif ch == "Y":
                partner = idx ^ (1 << q)
                vec = vec[partner]
                sign = np.where(bit == 1, 1.0, -1.0)
                vec = vec * (sign * 1j)
            elif ch == "Z":
                sign = np.where(bit == 1, -1.0, 1.0)
                vec = vec * sign
        exp = float(np.real(np.vdot(state.amplitudes, vec))) * self.coefficient
        return complex(exp)

    def expectation_density(self, rho: DensityMatrix) -> complex:
        m = self.matrix()
        if rho.n_qubits != self.n_qubits:
            raise QuantumCoreError("Pauli string / density matrix size mismatch.")
        return complex(np.trace(rho.matrix @ m))

    def __repr__(self) -> str:
        c = self.coefficient
        return f"{c:+.4g}·{self.term}"


class PauliSum:
    """Hermitian operator expressed as a sum of Pauli strings.

    Used by VQE/QAOA Hamiltonians. Hermiticity is validated at construction
    (all coefficients real within tolerance).
    """

    def __init__(self, terms: list[tuple[str, float]]):
        self.terms: list[PauliString] = []
        n_set = {len(t[0]) for t in terms}
        if len(n_set) != 1:
            raise QuantumCoreError(f"All Pauli terms must share length, got lengths {n_set}.")
        for term, coeff in terms:
            c = float(coeff)
            if abs(complex(coeff).imag) > DEFAULT_TOLERANCE:
                raise QuantumCoreError(
                    f"PauliSum coefficients must be real for Hermitian operators; "
                    f"got {coeff!r} on {term!r}."
                )
            self.terms.append(PauliString(term, c))

    @property
    def n_qubits(self) -> int:
        return self.terms[0].n_qubits if self.terms else 0

    def matrix(self) -> np.ndarray:
        out = np.zeros((1 << self.n_qubits, 1 << self.n_qubits), dtype=np.complex128)
        for ps in self.terms:
            out += ps.matrix()
        herm_dev = float(np.max(np.abs(out - out.conj().T)))
        if herm_dev > 1e-8:
            raise QuantumCoreError("PauliSum matrix is not Hermitian; coefficients corrupt.")
        return out

    def expectation(self, state: StateVector) -> float:
        return float(sum(ps.expectation(state).real for ps in self.terms))

    def expectation_density(self, rho: DensityMatrix) -> float:
        return float(sum(ps.expectation_density(rho).real for ps in self.terms))
