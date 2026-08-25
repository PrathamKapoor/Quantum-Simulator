"""Quantum information measures (directive Layer 5 / §6).

Every function documents: definition, formula, valid input domain, numerical
method, edge cases, expected properties. Property tests validate known states
(|0>, |+>, Bell, GHZ, product mixed, maximally mixed) against ANALYTIC values;
implementations never validate one another silently (RULE 3).

Conventions (platform-wide): little-endian qubit ordering, angles in radians,
entropies in BITS by default unless a function name says `_nats`.

Numerical policy: eigenvalue-based quantities clip eigenvalues into [0,1]
within tolerance 1e-12 before logs/sqrt; significantly negative eigenvalues
raise QuantumCoreError (corrupt input) rather than producing fake results.
"""
from __future__ import annotations

import math

import numpy as np

from .density import DensityMatrix, _sqrtm_psd, trace_distance as _trace_distance
from .states import StateVector, QuantumCoreError

_EIG_CLIP = 1e-12


def _check_psd(rho: DensityMatrix) -> np.ndarray:
    """Eigenvalues of rho clipped to >= 0 within tolerance; raises on corrupt input."""
    evals = np.linalg.eigvalsh(rho.matrix)
    if evals.min() < -1e-8:
        raise QuantumCoreError(
            f"DensityMatrix has eigenvalue {evals.min():.3e} < -1e-8: not positive "
            "semi-definite; refusing to compute an information measure."
        )
    return np.clip(evals, 0.0, None)


# ---------------------------------------------------------------------------
# Entropies
# ---------------------------------------------------------------------------

def von_neumann_entropy_bits(rho: DensityMatrix) -> float:
    """S(rho) = -Tr(rho log2 rho).

    Domain: any density matrix. Pure -> 0 exactly (eigenvalues {0,...,1}).
    Maximally mixed on d dimensions -> log2(d). Method: Hermitian eigendeco.
    """
    return rho.entropy()  # existing implementation is base-2


def renyi_entropy_bits(rho: DensityMatrix, alpha: float) -> float:
    """Renyi entropy S_alpha(rho) = 1/(1-alpha) * log2 Tr(rho^alpha).

    Domain: alpha > 0, alpha != 1 (alpha -> 1 recovers von Neumann; handled by
    explicit limit branch). Computed via eigenvalues: sum lam^alpha.
    Monotone non-increasing in alpha (tested at sampled pairs).
    Edge cases: pure state -> 0 for every alpha.
    """
    if alpha <= 0:
        raise ValueError(f"Renyi alpha must be > 0, got {alpha}.")
    evals = _check_psd(rho)
    nz = evals[evals > _EIG_CLIP]
    if alpha == 1.0:
        return float(-sum(l * math.log2(l) for l in nz))
    tr_pow = float(np.sum(nz ** alpha))
    return float(math.log2(tr_pow) / (1.0 - alpha))


def min_entropy_bits(rho: DensityMatrix) -> float:
    """Min-entropy H_min(rho) = -log2(lambda_max(rho)).

    Domain: any density matrix. Largest possible entropy among Renyi family
    orderings; equals log2(dim) for maximally mixed states and 0 for pure.
    """
    evals = _check_psd(rho)
    lmax = float(np.max(evals))
    if lmax <= 0:
        raise QuantumCoreError("DensityMatrix has no positive eigenvalue.")
    return float(-math.log2(min(1.0, max(lmax, _EIG_CLIP))))


def linear_entropy(rho: DensityMatrix) -> float:
    """Linear entropy S_L = 1 - Tr(rho^2).

    Range: [0, 1 - 1/d] with maximum at maximally mixed; 0 iff pure.
    """
    p = rho.purity()
    dim = rho.matrix.shape[0]
    return float(max(0.0, 1.0 - p)) if dim == 0 else float(np.clip(1.0 - p, 0.0, 1.0 - 1.0 / dim + 1e-9))


# ---------------------------------------------------------------------------
# Distances / distinguishability
# ---------------------------------------------------------------------------

def trace_distance(a: DensityMatrix, b: DensityMatrix) -> float:
    """D(rho, sigma) = 1/2 Tr|rho - sigma|. Range [0,1]; equals 1 for
    orthogonal supports. Re-exported from density.py for a single home."""
    return _trace_distance(a, b)


def relative_entropy_bits(rho: DensityMatrix, sigma: DensityMatrix) -> float:
    """Quantum relative entropy D(rho||sigma) = Tr rho (log2 rho - log2 sigma)
              = -S(rho) - Tr(rho log2 sigma).

    Domain: finite support of rho must lie inside support of sigma; otherwise
    D = +infinity -> we RAISE with an explicit message rather than return inf.
    Method: eigendecompositions; zero eigenvalues of rho contribute 0.
    Properties: D(rho||rho)=0; D(rho||I/d) = log2 d - S(rho); non-negative
    (Klein's inequality) up to numerical tolerance.
    """
    if rho.n_qubits != sigma.n_qubits:
        raise ValueError("Relative entropy requires equal qubit counts.")
    rv = _check_psd(rho)
    ls_vals, ls_vecs = np.linalg.eigh(sigma.matrix)
    if ls_vals.min() < -1e-8:
        raise QuantumCoreError("Second argument is not positive semi-definite.")
    # Support check: any rho weight on ker(sigma) => divergent.
    for i, val in enumerate(ls_vals):
        if val <= _EIG_CLIP:
            overlap = float(abs(np.vdot(ls_vecs[:, i], rho.matrix @ ls_vecs[:, i])))
            if overlap > 1e-9:
                raise QuantumCoreError(
                    "Relative entropy diverges: rho has support outside sigma's support."
                )
    s_rho = float(-sum(v * math.log2(v) for v in rv if v > _EIG_CLIP))
    log_diag = np.array(
        [math.log2(v) if v > _EIG_CLIP else 0.0 for v in ls_vals], dtype=float
    )
    log_sigma = (ls_vecs * log_diag[None, :]) @ ls_vecs.conj().T
    tr_rho_log_sigma = float(np.real(np.trace(log_sigma @ rho.matrix)))
    result = -s_rho - tr_rho_log_sigma
    if result < -1e-7:
        raise QuantumCoreError(
            f"Relative entropy computed negative ({result:.3e}); numerical failure."
        )
    return float(max(0.0, result))


# ---------------------------------------------------------------------------
# Correlations / classical-quantum quantities
# ---------------------------------------------------------------------------

def quantum_mutual_information_bits(rho: DensityMatrix, split: list[int]) -> float:
    """I(A:B) = S(A) + S(B) - S(AB) in bits. Non-negative up to numerics."""
    from ..protocols.communication import quantum_mutual_information

    return quantum_mutual_information(rho, split)


def conditional_entropy_bits(rho: DensityMatrix, split: list[int]) -> float:
    """S(A|B) = S(AB) - S(B) in bits.

    NOTE: CAN BE NEGATIVE for entangled states — this is meaningful, not an
    error (state merging interpretation). split lists qubits of A.
    """
    keep = set(split)
    rest = [q for q in range(rho.n_qubits) if q not in keep]
    if not keep or not rest:
        raise ValueError("Conditional entropy needs nonempty A and B.")
    s_ab = rho.entropy()
    s_b = rho.partial_trace(sorted(rest)).entropy()
    return float(s_ab - s_b)


def correlation_matrix(rho: DensityMatrix) -> np.ndarray:
    """3x3 correlation matrix T[i][j] = <sigma_i (x) sigma_j>, i,j in {x,y,z}.

    Defined for exactly TWO qubits (documented limitation; larger systems need
    a chosen pairing). For |Phi+>: diag(1,-1,1). For product states: rank-1
    outer product of local Bloch vectors.
    """
    if rho.n_qubits != 2:
        raise ValueError("correlation_matrix is defined for two-qubit states.")
    paulis = [
        np.array([[0, 1], [1, 0]], dtype=np.complex128),
        np.array([[0, -1j], [1j, 0]], dtype=np.complex128),
        np.array([[1, 0], [0, -1]], dtype=np.complex128),
    ]
    t = np.zeros((3, 3))
    for i in range(3):
        for j in range(3):
            obs = np.kron(paulis[i], paulis[j])
            t[i, j] = float(np.real(np.trace(rho.matrix @ obs)))
    return t


# ---------------------------------------------------------------------------
# Entanglement measures
# ---------------------------------------------------------------------------

def entanglement_entropy_bits(rho_or_state, keep: list[int]) -> float:
    """Entropy of entanglement of a reduced subsystem (bits).

    For PURE global states this is the canonical entanglement measure; for
    mixed globals it is not (documented — use negativity/concurrence there).
    """
    if isinstance(rho_or_state, StateVector):
        rho = DensityMatrix.pure(rho_or_state)
    else:
        rho = rho_or_state
    return float(rho.partial_trace(sorted(keep)).entropy())


def schmidt_decomposition(state: StateVector, split_at: int) -> tuple[np.ndarray, np.ndarray, list[np.ndarray]]:
    """Schmidt decomposition |psi> = Sum_k s_k |u_k>(x)|v_k>.

    split_at: number of qubits in subsystem A (qubits 0..split_at-1,
    little-endian). Returns (singular_values, A_vectors, B_vectors) where the
    k-th vectors are A_vectors[:, k] and B_vectors[:, k].
    Method: reshape amplitudes into (dim_A, dim_B) coefficient matrix with
    row index over A bits, SVD.
    Properties: sum s_k^2 = 1; rank 1 iff product; rank maximal for maximally
    entangled states when dimensions allow.
    """
    if not (1 <= split_at < state.n_qubits):
        raise ValueError("Split must strictly partition the qubits.")
    dim_a = 1 << split_at
    dim_b = 1 << (state.n_qubits - split_at)
    coeffs = state.amplitudes.reshape(dim_a, dim_b)
    u, s, vh = np.linalg.svd(coeffs)
    a_vectors = u.T                      # rows -> orthonormal A basis
    b_vectors = [vh[k].conj() for k in range(len(s))]
    return s, a_vectors, b_vectors


def schmidt_rank(state: StateVector, split_at: int) -> int:
    """Number of nonzero Schmidt coefficients (tolerance 1e-10)."""
    s, _, _ = schmidt_decomposition(state, split_at)
    return int(np.sum(s > 1e-10))


def _two_qubit_spin_flip(rho: DensityMatrix) -> np.ndarray:
    """R = rho (sy(x)sy) rho* (sy(x)sy) for the two-qubit concurrence."""
    sy = np.array([[0, -1j], [1j, 0]], dtype=np.complex128)
    yy = np.kron(sy, sy)
    return rho.matrix @ yy @ rho.matrix.conj() @ yy


def concurrence(rho: DensityMatrix) -> float:
    """Wootters concurrence for TWO-QUBIT states.

    C(rho) = max(0, lambda1 - lambda2 - lambda3 - lambda4) where lambdas are
    the square roots of the DECREASING eigenvalues of R = rho (sy(x)sy) rho*
    (sy(x)sy). Range [0,1]: 1 for Bell states, 0 for separable states.
    Valid ONLY for two qubits (raises otherwise) — do not extrapolate.
    """
    if rho.n_qubits != 2:
        raise ValueError("Concurrence is defined for two-qubit states only.")
    r = _two_qubit_spin_flip(rho)
    evals = np.linalg.eigvals(r)
    lams = np.sort(np.sqrt(np.clip(evals.real, 0, None)))[::-1]
    c = float(lams[0] - lams[1] - lams[2] - lams[3])
    return float(np.clip(c, 0.0, 1.0))


def negativity(rho: DensityMatrix, subsystem: list[int] | None = None) -> float:
    """Negativity N = (||rho^{T_A}||_1 - 1) / 2.

    Partial transpose over `subsystem` (default first half of the qubits).
    Range [0, 0.5] for two qubits; 0 for PPT states. Necessary condition for
    separability in ALL dimensions; sufficient only for 2x2 and 2x3
    (Peres-Horodecki) — documented per-input.
    """
    n = rho.n_qubits
    sub = sorted(subsystem) if subsystem else list(range(max(1, n // 2)))
    if not (0 < len(sub) < n):
        raise ValueError("Partial transpose needs a proper nonempty subset.")
    dim = 1 << n
    mt = rho.matrix.copy().reshape((2,) * (2 * n))
    for q in sub:
        row_ax = n - 1 - q
        col_ax = 2 * n - 1 - q
        # swap row bit q with col bit q (transpose on that qubit)
        perm = list(range(2 * n))
        perm[row_ax], perm[col_ax] = col_ax, row_ax
        mt = np.transpose(mt, perm)
    mt = mt.reshape(dim, dim)
    if not np.allclose(mt.imag, 0, atol=1e-10) and not np.allclose(mt, mt.conj().T, atol=1e-8):
        raise QuantumCoreError("Partial transpose is not Hermitian; input corrupt.")
    evals = np.linalg.eigvalsh(mt)
    trace_norm = float(np.sum(np.abs(evals)))
    return float(max(0.0, (trace_norm - 1.0) / 2.0))


def logarithmic_negativity_bits(rho: DensityMatrix, subsystem: list[int] | None = None) -> float:
    """E_N = log2 ||rho^{T_A}||_1. Zero for PPT states; log2(2N+1) relation to
    negativity holds exactly: E_N = log2(2*N + 1)."""
    n = rho.n_qubits
    sub = sorted(subsystem) if subsystem else list(range(max(1, n // 2)))
    dim = 1 << n
    mt = rho.matrix.copy().reshape((2,) * (2 * n))
    for q in sub:
        row_ax = n - 1 - q
        col_ax = 2 * n - 1 - q
        perm = list(range(2 * n))
        perm[row_ax], perm[col_ax] = col_ax, row_ax
        mt = np.transpose(mt, perm)
    evals = np.linalg.eigvalsh(mt.reshape(dim, dim))
    trace_norm = float(np.sum(np.abs(evals)))
    return float(math.log2(max(trace_norm, 1.0)))


# ---------------------------------------------------------------------------
# Separability diagnostics
# ---------------------------------------------------------------------------

def ppt_separability_report(rho: DensityMatrix, subsystem: list[int] | None = None) -> dict:
    """PPT-based separability diagnostics with EXPLICIT validity scope.

    For 2x2 and 2x3 bipartitions PPT is necessary AND sufficient
    (Peres-Horodecki). In higher dimensions PPT is only necessary: a PASS is
    reported as 'ppt_inconclusive' rather than 'separable' (honest scope).
    """
    n = rho.n_qubits
    sub = sorted(subsystem) if subsystem else list(range(max(1, n // 2)))
    other = [q for q in range(n) if q not in sub]
    dims = (1 << len(sub), 1 << len(other))
    neg = negativity(rho, sub)
    if dims in ((2, 2), (2, 3)):
        verdict = "separable" if neg == 0 else "entangled"
        basis = "PPT necessary AND sufficient (Peres-Horodecki, 2x2/2x3)"
    else:
        verdict = "ppt_inconclusive" if neg == 0 else "entangled (NPT)"
        basis = "PPT necessary only; sufficiency NOT guaranteed in this dimension"
    return {
        "negativity": neg,
        "verdict": verdict,
        "basis": basis,
        "bipartition_dims": dims,
        "note": "PPT test; bound-entangled states would pass PPT while entangled.",
    }


# ---------------------------------------------------------------------------
# Convenience bundle used by the API/UI
# ---------------------------------------------------------------------------

def state_report(rho: DensityMatrix, split: list[int] | None = None) -> dict:
    """Bundle of core measures for one state, with model labels (§106)."""
    split = split or list(range(max(1, rho.n_qubits // 2)))
    out: dict = {
        "purity": rho.purity(),
        "von_neumann_entropy_bits": rho.entropy(),
        "renyi_entropy_bits_alpha2": renyi_entropy_bits(rho, 2.0),
        "min_entropy_bits": min_entropy_bits(rho),
        "linear_entropy": linear_entropy(rho),
    }
    try:
        out["mutual_information_bits"] = quantum_mutual_information_bits(rho, split)
        out["conditional_entropy_bits"] = conditional_entropy_bits(rho, split)
    except (ValueError, QuantumCoreError) as e:
        out["bipartite_error"] = str(e)
    if rho.n_qubits == 2:
        out["concurrence"] = concurrence(rho)
        out["negativity"] = negativity(rho)
        out["logarithmic_negativity_bits"] = logarithmic_negativity_bits(rho)
        out["correlation_matrix"] = correlation_matrix(rho).tolist()
    sep = ppt_separability_report(rho, split)
    out["separability"] = sep
    return out
