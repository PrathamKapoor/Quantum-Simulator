"""Graph and cluster states (McMahon chapter 15).

A graph state is prepared from |+>^n and CZ along the graph edges:

    |G> = prod_{(u,v) in E} CZ_{uv} |+>^n

with stabilizer generators

    K_v = X_v * prod_{u in N(v)} Z_u,   K_v |G> = |G>.

Also implemented (chapter 15's measurement-based processing): one-
qubit measurement on a graph node with all X-basis corrections, and
the GHZ-style entanglement witness  W = I - |GHZ><GHZ| - |GHZ_perp><GHZ_perp|
reduced to the book's construction  W = I/2 - |GHZ><GHZ|  on the
symmetric subspace; <W> < 0 certifies entanglement.

Exactness (directive §79): state preparation and stabilizer checks are
exact linear algebra on the full state vector; measurement statistics
are Monte Carlo when shots are requested.
"""
from __future__ import annotations

import numpy as np

from .states import QuantumCoreError, StateVector
from .operators import pauli_matrix

_CZ = np.diag([1, 1, 1, -1]).astype(np.complex128)
_H = np.array([[1, 1], [1, -1]], dtype=np.complex128) / np.sqrt(2)
_H_STATE = np.array([1, 1], dtype=np.complex128) / np.sqrt(2)


def _kron_list(mats: list[np.ndarray]) -> np.ndarray:
    out = np.array([1.0 + 0j])
    for m in mats:
        out = np.kron(out, m)
    return out


def _single_qubit_op(mat: np.ndarray, qubit: int, n: int) -> np.ndarray:
    ops = [np.eye(2, dtype=np.complex128)] * n
    ops[qubit] = mat
    return _kron_list(ops)


def cz_gate(edge: tuple[int, int], n: int) -> np.ndarray:
    """CZ on (u, v) as projector sum: P0⊗I + P1⊗Z."""
    u, v = edge
    if u == v:
        raise QuantumCoreError("Self-loops are not valid graph edges.")
    p0 = np.array([[1, 0], [0, 0]], dtype=np.complex128)
    p1 = np.array([[0, 0], [0, 1]], dtype=np.complex128)
    z = np.array([[1, 0], [0, -1]], dtype=np.complex128)
    left, right = [], []
    for q in range(n):
        if q == u:
            left.append(p0); right.append(p1)
        elif q == v:
            left.append(np.eye(2, dtype=np.complex128))
            right.append(z)
        else:
            left.append(np.eye(2, dtype=np.complex128))
            right.append(np.eye(2, dtype=np.complex128))
    return _kron_list(left) + _kron_list(right)


def graph_state(adjacency: list[list[int]] | np.ndarray) -> StateVector:
    """Prepare the graph state for an adjacency matrix (symmetric, 0/1,
    zero diagonal)."""
    adj = np.asarray(adjacency)
    n = adj.shape[0] if adj.ndim == 2 else int(adj.size)
    if adj.ndim != 2 or adj.shape[0] != adj.shape[1]:
        raise QuantumCoreError("Adjacency must be a square matrix.")
    if not np.all((adj == 0) | (adj == 1)):
        raise QuantumCoreError("Adjacency must be 0/1.")
    if np.any(np.diag(adj)):
        raise QuantumCoreError("Adjacency diagonal must be zero (no self-loops).")
    if not np.allclose(adj, adj.T):
        raise QuantumCoreError("Adjacency must be symmetric (undirected graph).")
    state = _kron_list([_H_STATE] * n)
    for u in range(n):
        for v in range(u + 1, n):
            if adj[u, v]:
                state = cz_gate((u, v), n) @ state
    return StateVector(state, n)


def cluster_state_1d(length: int) -> StateVector:
    """1D chain cluster state (the book's linear cluster)."""
    if length < 1:
        raise QuantumCoreError("length must be >= 1.")
    adj = np.zeros((length, length), dtype=int)
    for i in range(length - 1):
        adj[i, i + 1] = adj[i + 1, i] = 1
    return graph_state(adj)


def cluster_state_2d(rows: int, cols: int) -> StateVector:
    """2D lattice cluster state."""
    if rows < 1 or cols < 1:
        raise QuantumCoreError("rows/cols must be >= 1.")
    n = rows * cols
    adj = np.zeros((n, n), dtype=int)

    def node(r, c):
        return r * cols + c
    for r in range(rows):
        for c in range(cols):
            if c + 1 < cols:
                adj[node(r, c), node(r, c + 1)] = 1
                adj[node(r, c + 1), node(r, c)] = 1
            if r + 1 < rows:
                adj[node(r, c), node(r + 1, c)] = 1
                adj[node(r + 1, c), node(r, c)] = 1
    return graph_state(adj)


def stabilizer_report(state: StateVector, adjacency: list[list[int]] | np.ndarray) -> dict:
    """Compute every generator K_v and verify K_v|psi> = |psi>."""
    adj = np.asarray(adjacency)
    n = adj.shape[0]
    if adj.ndim != 2 or adj.shape[0] != adj.shape[1]:
        raise QuantumCoreError("Adjacency must be a square matrix.")
    if not np.allclose(adj, adj.T):
        raise QuantumCoreError("Adjacency must be symmetric (undirected graph).")
    x = pauli_matrix("X")
    z = pauli_matrix("Z")
    generators, residuals = [], []
    for v in range(n):
        op = _single_qubit_op(x, v, n)
        for u in range(n):
            if adj[v, u]:
                op = op @ _single_qubit_op(z, u, n)
        out = op @ state.amplitudes
        residual = float(np.linalg.norm(out - state.amplitudes))
        generators.append({"qubit": v, "operator": op,
                           "residual": residual,
                           "stabilizes": residual < 1e-9})
        residuals.append(residual)
    return {"generators": generators,
            "all_stabilize": all(g["stabilizes"] for g in generators),
            "max_residual": max(residuals)}


def ghz_witness_expectation(state: StateVector) -> float:
    """<W> for W = I/2 - |GHZ><GHZ| (book construction, normalized so
    <W> < 0 certifies GHZ-type entanglement). |GHZ> is taken as the
    equal (|0...0> + |1...1>)/sqrt(2) on `state.n_qubits`."""
    n = state.n_qubits
    ghz = np.zeros(1 << n, dtype=np.complex128)
    ghz[0] = 1 / np.sqrt(2)
    ghz[-1] = 1 / np.sqrt(2)
    projector = np.outer(ghz, ghz.conj())
    rho = np.outer(state.amplitudes, state.amplitudes.conj())
    w = np.eye(1 << n) / 2 - projector
    return float(np.trace(w @ rho).real)


def measure_node_x(state: StateVector, node: int,
                   outcome: int | None = None,
                   rng: np.random.Generator | None = None) -> dict:
    """X-basis measurement of one graph node (the chapter-15 processing
    primitive). Returns the outcome, post-measurement state, and the
    byproduct correction note. `outcome` forces a branch (for exact
    experiments); otherwise it is sampled."""
    n = state.n_qubits
    if not (0 <= node < n):
        raise QuantumCoreError(f"node {node} out of range for {n} qubits.")
    plus = np.array([1, 1], dtype=np.complex128) / np.sqrt(2)
    minus = np.array([1, -1], dtype=np.complex128) / np.sqrt(2)
    p_plus_op = _single_qubit_op(np.outer(plus, plus.conj()), node, n)
    p_minus_op = _single_qubit_op(np.outer(minus, minus.conj()), node, n)
    post_plus = p_plus_op @ state.amplitudes
    post_minus = p_minus_op @ state.amplitudes
    p_plus = float(np.linalg.norm(post_plus) ** 2)
    if outcome is None:
        rng = rng or np.random.default_rng()
        outcome = int(rng.random() < 1 - p_plus)   # 0 -> plus, 1 -> minus
    post = post_plus if outcome == 0 else post_minus
    norm = float(np.linalg.norm(post))
    post = post / norm
    return {"node": node, "outcome": outcome,
            "probability": p_plus if outcome == 0 else 1.0 - p_plus,
            "post_state": StateVector(post, n),
            "byproduct": "Z" if outcome == 1 else "I"}
