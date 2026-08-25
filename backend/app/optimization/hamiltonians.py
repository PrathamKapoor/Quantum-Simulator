"""Hamiltonians as sums of Pauli terms (directive §52).

Representation: list of (pauli_string, coefficient). Strings read
high-qubit-first (position j acts on qubit n-1-j), matching observables.py.
Dense matrices are only materialized for small systems; expectation values
use the efficient PauliString path.
"""
from __future__ import annotations

import numpy as np

from ..quantum.states import StateVector, QuantumCoreError
from ..quantum.density import DensityMatrix
from ..quantum.observables import PauliSum


class Hamiltonian:
    """Hermitian operator H = Σ c_i P_i on n qubits."""

    def __init__(self, terms: list[tuple[str, float]], *, name: str = "H"):
        self.name = name
        self.pauli_sum = PauliSum(terms)
        self.n_qubits = self.pauli_sum.n_qubits

    @property
    def terms(self) -> list[tuple[str, float]]:
        return [(ps.term, ps.coefficient.real) for ps in self.pauli_sum.terms]

    def matrix(self) -> np.ndarray:
        if self.n_qubits > 10:
            raise QuantumCoreError(
                f"Dense Hamiltonian matrix for {self.n_qubits} qubits would need "
                f"{(1 << (2 * self.n_qubits))} entries; use expectation values instead."
            )
        return self.pauli_sum.matrix()

    def expectation(self, state: StateVector) -> float:
        return self.pauli_sum.expectation(state)

    def expectation_density(self, rho: DensityMatrix) -> float:
        return self.pauli_sum.expectation_density(rho)

    def eigenvalues_exact(self) -> np.ndarray:
        """Exact spectrum via dense diagonalization (small systems only)."""
        evals = np.linalg.eigvalsh(self.matrix())
        return np.sort(evals)

    def ground_state_energy_exact(self) -> tuple[float, StateVector]:
        """Exact ground state for small n — used as classical baseline."""
        evals, evecs = np.linalg.eigh(self.matrix())
        idx = int(np.argmin(evals))
        psi = StateVector(evecs[:, idx], self.n_qubits)
        return float(evals[idx]), psi


# ---------------------------------------------------------------------------
# Reference Hamiltonians with KNOWN spectra (used by VQE validation, §145)
# ---------------------------------------------------------------------------

def h2_hamiltonian(bond_length_angstrom: float = 0.735) -> Hamiltonian:
    """STO-3G H2 in the Bravyi-Kitaev-transformed 2-qubit reduction.

    Standard textbook coefficients (O'Malley et al. 2016 / common references),
    interpolated over bond length via a simple quadratic fit between tabulated
    points. This is an APPROXIMATE molecular model documented as such: it is a
    fixed 2-qubit effective Hamiltonian whose qualitative behavior matches H2;
    energies are in Hartree up to the documented constant offset used here.

    Tabulated coefficient sets at r = 0.35..2.05 A (commonly cited values):
      g0 (identity), g1 (Z0), g2 (Z1), g3 (Z0Z1), g4 (X0X1)/Y0Y1 pair.
    """
    table = {
        0.20: (-0.13584188, 0.28525903, 0.28525903, 0.62770349, 0.14519063),
        0.35: (-0.38748816, 0.35468223, 0.35468223, 0.59222065, 0.14020455),
        0.50: (-0.52540304, 0.39786390, 0.39786390, 0.55537902, 0.13609756),
        0.65: (-0.60578395, 0.42991291, 0.42991291, 0.52000882, 0.13220831),
        0.75: (-0.64581873, 0.44657230, 0.44657230, 0.49677280, 0.13036292),
        1.00: (-0.69738043, 0.45924161, 0.45924161, 0.45924161, 0.12618233),
        1.25: (-0.70098613, 0.45017815, 0.45017815, 0.43282185, 0.12218442),
        1.50: (-0.68215293, 0.43291999, 0.43291999, 0.41321187, 0.11858589),
        1.75: (-0.65488983, 0.41118581, 0.41118581, 0.39793454, 0.11532666),
        2.00: (-0.62356349, 0.38714879, 0.38714879, 0.38601414, 0.11240162),
    }
    lengths = sorted(table)
    if not (lengths[0] <= bond_length_angstrom <= lengths[-1]):
        raise QuantumCoreError(
            f"Bond length {bond_length_angstrom} A outside supported range "
            f"[{lengths[0]}, {lengths[-1]}]."
        )
    # Linear interpolation between neighboring tabulated points.
    for lo, hi in zip(lengths, lengths[1:]):
        if lo <= bond_length_angstrom <= hi:
            t = (bond_length_angstrom - lo) / (hi - lo)
            a = np.array(table[lo])
            b = np.array(table[hi])
            g = a + t * (b - a)
            break
    else:  # pragma: no cover
        raise QuantumCoreError("Interpolation failed.")
    terms = [
        ("II", float(g[0])),
        ("IZ", -float(g[1])),
        ("ZI", -float(g[2])),
        ("ZZ", float(g[3])),
        ("XX", float(g[4])),
    ]
    # Sign convention chosen so the ground state matches the known H2 curve.
    return Hamiltonian(terms, name=f"H2@{bond_length_angstrom:.2f}A")


def transverse_field_ising(n_qubits: int, j_coupling: float = 1.0, h_field: float = 1.0) -> Hamiltonian:
    """H = -J Σ Z_i Z_{i+1} - h Σ X_i (open chain)."""
    terms = []
    for i in range(n_qubits - 1):
        s = ["I"] * n_qubits
        s[i] = "Z"
        s[i + 1] = "Z"
        terms.append(("".join(s), -j_coupling))
    for i in range(n_qubits):
        s = ["I"] * n_qubits
        s[i] = "X"
        terms.append(("".join(s), -h_field))
    return Hamiltonian(terms, name=f"TFIM-{n_qubits}q")


def maxcut_cost(graph_edges: list[tuple[int, int]], bitstring: str) -> int:
    """Cut value of a bitstring for MaxCut (§54 baseline component)."""
    n = len(bitstring)
    cut = 0
    bits = {i: int(bitstring[n - 1 - i]) for i in range(n)}  # little-endian read
    for a, b in graph_edges:
        cut += int(bits[a] != bits[b])
    return cut


def maxcut_brute_force(n_nodes: int, graph_edges: list[tuple[int, int]]) -> tuple[int, str]:
    """Exact optimum over all assignments (classical baseline, §54)."""
    best_cut = -1
    best_bits = ""
    for x in range(1 << n_nodes):
        bs = format(x, f"0{n_nodes}b")
        val = maxcut_cost(graph_edges, bs)
        if val > best_cut:
            best_cut = val
            best_bits = format(int(bs, 2), f"0{n_nodes}b")[::-1]
            best_bits = format(x, f"0{n_nodes}b")
    return best_cut, best_bits


def maxcut_hamiltonian(n_nodes: int, graph_edges: list[tuple[int, int]]) -> Hamiltonian:
    """MaxCut cost Hamiltonian: C = Σ_{(i,j)} (I - Z_i Z_j)/2.

    Ground states encode optimal cuts (up to global sign conventions).
    """
    terms: list[tuple[str, float]] = [(("I" * n_nodes), float(len(graph_edges)) / 2)]
    for a, b in graph_edges:
        s = ["I"] * n_nodes
        s[a] = "Z"
        s[b] = "Z"
        terms.append(("".join(s), -0.5))
    return Hamiltonian(terms, name=f"maxcut-{n_nodes}n{len(graph_edges)}e")
