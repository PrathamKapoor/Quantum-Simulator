"""Quantum-information tools (McMahon chapters 2, 3, 5, 6, 7, 13).

The primitives here complement the existing quantum core with the
tools the book treats as the standard characterization instruments:

  * generalized (POVM) measurement: outcome probabilities and
    post-measurement states from effect operators E_i = M_i† M_i,
    with completeness validation (sum E_i = I);
  * general partial transpose (any bipartition, any n-qubit state) —
    the Peres criterion is exact for 2x2 and 2x3 systems and a
    practical entanglement diagnostic elsewhere;
  * Bures distance and its fidelity relation
      D_B(rho, sigma) = sqrt(2 (1 - sqrt F(rho, sigma)));
  * entanglement of formation for two-qubit states (Wootters formula
    via the existing concurrence);
  * purification of a diagonal-form mixed state onto a larger system;
  * Gram-Schmidt orthonormalization with linear-independence checking;
  * the no-cloning demonstration: the linear map that clones two
    orthogonal states maps any superposition to an entangled state,
    never to a clone (numerical inner-product-preservation argument).

Every function computes from the input state; nothing returns a
hard-coded textbook value (directive §110).
"""
from __future__ import annotations

import numpy as np

from .density import DensityMatrix
from .states import QuantumCoreError, DEFAULT_TOLERANCE, StateVector


def _as_density_matrix(rho: DensityMatrix | np.ndarray, n_qubits: int | None = None) -> DensityMatrix:
    if isinstance(rho, DensityMatrix):
        return rho
    m = np.asarray(rho, dtype=np.complex128)
    if n_qubits is None:
        n_qubits = int(round(np.log2(m.shape[0])))
    return DensityMatrix(m, n_qubits)


# ---------------------------------------------------------------------------
# Chapter 6 — generalized measurement / POVM.
# ---------------------------------------------------------------------------

def validate_povm(effects: list[np.ndarray], n_qubits: int,
                  tolerance: float = DEFAULT_TOLERANCE) -> dict:
    """Validate POVM completeness sum_i E_i = I and effect positivity."""
    dim = 1 << n_qubits
    total = np.zeros((dim, dim), dtype=np.complex128)
    for i, e in enumerate(effects):
        m = np.asarray(e, dtype=np.complex128)
        if m.shape != (dim, dim):
            raise QuantumCoreError(
                f"POVM effect {i} has shape {m.shape}, expected {(dim, dim)}.")
        total += m
    identity_err = float(np.max(np.abs(total - np.eye(dim))))
    min_eig = min(float(np.linalg.eigvalsh(e).min()) for e in effects)
    return {"completeness_error": identity_err,
            "min_effect_eigenvalue": min_eig,
            "complete": identity_err < tolerance,
            "positive": min_eig > -tolerance}


def povm_probabilities(rho: DensityMatrix, effects: list[np.ndarray]) -> list[float]:
    """Outcome probabilities p_i = Tr(E_i rho) for a POVM."""
    report = validate_povm(effects, rho.n_qubits)
    if not report["complete"]:
        raise QuantumCoreError(
            f"POVM is not complete: sum E_i deviates from I by "
            f"{report['completeness_error']:.3e}.")
    probs = [float(np.trace(np.asarray(e, dtype=np.complex128) @ rho.matrix).real)
             for e in effects]
    total = sum(probs)
    if abs(total - 1.0) > 1e-6:
        raise QuantumCoreError(f"POVM probabilities sum to {total}, not 1.")
    return probs


def helstrom_measurement(rho: DensityMatrix, sigma: DensityMatrix,
                        prior: float = 0.5) -> list[np.ndarray]:
    """Return optimal binary-discrimination effects [guess_rho, guess_sigma].

    ``prior`` is the probability of preparing ``rho``. The nonnegative
    eigenspace of prior*rho - (1-prior)*sigma is assigned to guess_rho,
    including its zero eigenspace; the complementary effect guesses sigma.
    Inputs must have equal qubit counts and be positive semidefinite with
    unit trace, up to DEFAULT_TOLERANCE. Invalid inputs raise QuantumCoreError.
    """
    if not np.isfinite(prior) or not 0.0 <= prior <= 1.0:
        raise QuantumCoreError("Helstrom prior must be finite and lie in [0, 1].")
    if rho.n_qubits != sigma.n_qubits:
        raise QuantumCoreError("Helstrom measurement requires equal qubit counts.")
    for name, state in (("rho", rho), ("sigma", sigma)):
        if abs(np.trace(state.matrix) - 1.0) > DEFAULT_TOLERANCE:
            raise QuantumCoreError(f"Helstrom {name} must have unit trace.")
        if np.linalg.eigvalsh(state.matrix).min() < -DEFAULT_TOLERANCE:
            raise QuantumCoreError(f"Helstrom {name} must be positive semi-definite.")
    difference = prior * rho.matrix - (1.0 - prior) * sigma.matrix
    eigenvalues, eigenvectors = np.linalg.eigh((difference + difference.conj().T) / 2)
    positive_basis = eigenvectors[:, eigenvalues >= 0.0]
    guess_rho = positive_basis @ positive_basis.conj().T
    return [guess_rho, np.eye(1 << rho.n_qubits, dtype=np.complex128) - guess_rho]


def generalized_measure(rho: DensityMatrix,
                        kraus_operators: list[np.ndarray]) -> list[dict]:
    """Generalized measurement with Kraus operators M_i.

    Returns per-outcome probability p_i = Tr(M_i rho M_i†) and the
    normalized post-measurement state rho_i. Completeness
    sum M_i† M_i = I is validated first (directive §16).
    """
    dim = rho.matrix.shape[0]
    completeness = np.zeros((dim, dim), dtype=np.complex128)
    for i, m in enumerate(kraus_operators):
        k = np.asarray(m, dtype=np.complex128)
        if k.shape != (dim, dim):
            raise QuantumCoreError(
                f"Kraus operator {i} has shape {k.shape}, expected "
                f"{(dim, dim)}.")
        completeness += k.conj().T @ k
    err = float(np.max(np.abs(completeness - np.eye(dim))))
    if err > 1e-6:
        raise QuantumCoreError(
            f"Kraus operators are not trace-preserving: "
            f"sum M_i† M_i deviates from I by {err:.3e}.")
    outcomes = []
    for i, m in enumerate(kraus_operators):
        k = np.asarray(m, dtype=np.complex128)
        post = k @ rho.matrix @ k.conj().T
        p = float(np.trace(post).real)
        if p > 1e-12:
            post = post / p
        outcomes.append({"outcome": i, "probability": p,
                         "post_state": post})
    return outcomes


# ---------------------------------------------------------------------------
# Chapter 7 / 13 — partial transpose, purification.
# ---------------------------------------------------------------------------

def partial_transpose(rho: DensityMatrix, subsystem: list[int]) -> DensityMatrix:
    """Partial transpose over the given subsystem qubits (any n).

    Implemented via index reshaping: T_B has elements
    rho_{a a', b b'} -> rho_{a b', b a'} where the labels are the
    computational bits of subsystem A / B. Exact for any n-qubit
    state; as an entanglement criterion (Peres) it is exact for
    2x2 and 2x3 systems and a diagnostic elsewhere (§80: documented).
    """
    n = rho.n_qubits
    if not subsystem or len(set(subsystem)) != len(subsystem):
        raise QuantumCoreError("subsystem must be a non-repeating, non-empty list.")
    if any(not (0 <= q < n) for q in subsystem):
        raise QuantumCoreError(f"subsystem {subsystem} out of range for {n} qubits.")
    keep_a = [q for q in range(n) if q not in subsystem]
    # full index tensor: rho[a2 a1 ... ] with axis per qubit (q0 = most
    # significant bit, matching the simulator's bit order)
    full = rho.matrix.reshape([2] * (2 * n))
    # axes: first n are row bits, last n are column bits; qubit q maps to
    # axis q (row) and axis n + q (column).
    order = list(range(n))
    t = full
    for q in subsystem:
        # swap row axis q with column axis n + q via transpose of the
        # two axes in place: move column axis next to row axis and back.
        perm = list(range(2 * n))
        perm[q], perm[n + q] = perm[n + q], perm[q]
        t = np.transpose(t, perm)
    out = DensityMatrix(t.reshape(1 << n, 1 << n), n)
    return out


def purification(rho: DensityMatrix) -> tuple[StateVector, list[int]]:
    """Purify a mixed state onto system + environment.

    Uses the spectral decomposition rho = sum_k p_k |v_k><v_k| and
    builds |Psi> = sum_k sqrt(p_k) |v_k> ⊗ |k> on an appended
    environment register with one level per spectral branch (so
    env dim = system dim). The environment occupies the
    LEAST-significant qubit positions (the DensityMatrix module's
    convention), so `env_labels = [0 .. n_env-1]` and tracing out the
    environment is `rho_purified.partial_trace([n_env .. n_sys+n_env-1])`,
    which reproduces rho exactly (validated in tests).
    """
    evals, evecs = np.linalg.eigh(rho.matrix)
    n_sys = rho.n_qubits
    n_env = n_sys
    env_dim = 1 << n_env
    psi = np.zeros((1 << n_sys) * env_dim, dtype=np.complex128)
    for k in range(len(evals)):
        if evals[k] > 1e-12:
            psi += np.sqrt(evals[k]) * np.kron(evecs[:, k], _env_basis_col(env_dim, k))
    env_labels = list(range(n_env))
    return StateVector(psi, n_sys + n_env), env_labels


def _env_basis_col(env_dim: int, k: int) -> np.ndarray:
    col = np.zeros(env_dim, dtype=np.complex128)
    col[k] = 1.0
    return col


# ---------------------------------------------------------------------------
# Chapter 13 — Bures distance, entanglement of formation.
# ---------------------------------------------------------------------------

def bures_distance(rho: DensityMatrix, sigma: DensityMatrix) -> float:
    """D_B(rho, sigma) = sqrt(2 (1 - sqrt F(rho, sigma))), monotone with
    the (Uhlmann) fidelity already implemented on DensityMatrix."""
    if rho.n_qubits != sigma.n_qubits:
        raise QuantumCoreError("Bures distance requires equal qubit counts.")
    f = rho.fidelity_with(sigma)
    return float(np.sqrt(max(0.0, 2.0 * (1.0 - np.sqrt(max(0.0, f))))))


def entanglement_of_formation(rho: DensityMatrix) -> float:
    """Wootters entanglement of formation for a two-qubit state, from
    the concurrence: EoF = h2((1 + sqrt(1 - C^2)) / 2) bits."""
    from .info_theory import concurrence
    if rho.n_qubits != 2:
        raise QuantumCoreError(
            f"Entanglement of formation is implemented for two-qubit "
            f"states, got {rho.n_qubits} qubits.")
    c = concurrence(rho)
    if c <= 0.0:
        return 0.0
    x = (1.0 + np.sqrt(max(0.0, 1.0 - c * c))) / 2.0
    return float(-(x * np.log2(x) + (1 - x) * np.log2(1 - x)))


# ---------------------------------------------------------------------------
# Chapter 2/3 — Gram-Schmidt, linear independence.
# ---------------------------------------------------------------------------

def gram_schmidt(vectors: list[np.ndarray]) -> tuple[list[np.ndarray], list[float]]:
    """Orthonormalize the given vectors (classical Gram-Schmidt).

    Returns (orthonormal basis, norms-before-normalization). A near-zero
    norm marks a linearly dependent input vector (the corresponding
    basis entry is the zero vector) — the numerical linear-independence
    test the book's vector-space chapter asks for.
    """
    basis: list[np.ndarray] = []
    norms: list[float] = []
    for v in vectors:
        w = np.asarray(v, dtype=np.complex128).copy()
        if w.ndim != 1:
            raise QuantumCoreError("Gram-Schmidt expects a list of 1-D vectors.")
        for b in basis:
            w = w - np.vdot(b, w) * b
        norm = float(np.linalg.norm(w))
        norms.append(norm)
        basis.append(w / norm if norm > 1e-10 else w * 0.0)
    return basis, norms


# ---------------------------------------------------------------------------
# Chapter 13 — no-cloning demonstration (numerical).
# ---------------------------------------------------------------------------

def no_cloning_report(alpha: complex, beta: complex) -> dict:
    """Numerical no-cloning demonstration.

    The map defined by 'clone |0> and |1>' (the CNOT isometry
    |x>|0> -> |x>|x>) is a legal unitary, but applied to
    |psi> = alpha|0> + beta|1> it produces the ENTANGLED state
    alpha|00> + beta|11>, not alpha^2|00> + ab|01> + ab|10> + b^2|11>
    (the true clone). We compute both and the fidelity of the produced
    state with the would-be clone: <1 for every non-trivial superposition,
    which is the inner-product-preservation contradiction made numeric.
    """
    norm2 = abs(alpha) ** 2 + abs(beta) ** 2
    if abs(norm2 - 1.0) > 1e-9:
        raise QuantumCoreError("alpha, beta must form a normalized state.")
    psi = np.array([alpha, beta], dtype=np.complex128)
    # CNOT isometry |x>|0> -> |x>|x>
    produced = np.zeros(4, dtype=np.complex128)
    for idx, amp in enumerate(psi):
        b = format(idx, "01b")
        target = int(b) * 2 + int(b)
        produced[target] += amp
    clone = np.array([alpha * alpha, alpha * beta, alpha * beta,
                      beta * beta], dtype=np.complex128)
    fid = float(abs(np.vdot(clone, produced)) ** 2)
    orthogonality_argument = {
        "inner_product_input": float(abs(np.vdot(np.array([1, 0], dtype=np.complex128),
                                                 np.array([0, 1], dtype=np.complex128)))),
        "required_inner_product_of_clones": 1.0,
        "note": ("Cloning |0> and |1> preserves their inner product 0 only "
                 "because <x|x>^2 = <x|x> for x in {0,1}; a superposition "
                 "has <psi|phi> != <psi|phi>^2, so no unitary clones all "
                 "states."),
    }
    return {"input": [complex(alpha), complex(beta)],
            "produced_state": [complex(z) for z in produced],
            "would_be_clone": [complex(z) for z in clone],
            "clone_fidelity": fid,
            "is_clone": bool(abs(fid - 1.0) < 1e-9),
            "orthogonality_argument": orthogonality_argument}
