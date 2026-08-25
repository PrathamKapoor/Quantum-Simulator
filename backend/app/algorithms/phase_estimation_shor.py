"""Phase estimation and bounded Shor (period finding).

Scientific notes
----------------
Phase estimation: t precision qubits estimate the eigenphase φ of U acting on
an eigenstate |ψ⟩: U|ψ⟩ = e^{2πiφ}|ψ⟩. Accuracy improves with t; success
probability with rounding is ≥ 4/π² for t = n + ⌈log2(2 + 1/(2ε))⌉ (N&C).

Bounded Shor: period finding for a^x mod N via phase estimation over the
modular-multiplication permutation U_{a,N}: |x⟩→|a·x mod N⟩ (x < N). The
permutation is built as an explicit matrix — feasible only for tiny N (≤ 21,
register width ≤ 5 qubits). This is an honest educational implementation of
the quantum part; classical post-processing uses continued fractions.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..circuits.model import Circuit
from ..circuits.simulate import simulate
from ..quantum.states import QuantumCoreError


# ---------------------------------------------------------------------------
# Phase estimation
# ---------------------------------------------------------------------------

@dataclass
class PhaseEstimationResult:
    true_phase: float | None
    estimated_phase: float
    precision_bits: int
    measured_integer: int
    error: float | None
    counts: dict[str, int]


def controlled_full_matrix(unitary: np.ndarray) -> np.ndarray:
    """Controlled-U with the control as the FIRST (most-significant) operand.

    Returns a dense local matrix of dimension 2·dim(U): identity block for
    control=0, U block for control=1. Keeping this local (not embedded in the
    full register) is what makes QPE/order-finding tractable.
    """
    d = unitary.shape[0]
    out = np.eye(2 * d, dtype=np.complex128)
    out[d:, d:] = unitary
    return out


def build_phase_estimation_circuit(
    unitary: np.ndarray,
    system_qubits: list[int],
    *,
    total_qubits: int,
) -> Circuit:
    """Textbook QPE: precision qubits 0..t-1, then the system register.

    Controlled-U^{2^k} uses precision qubit k as control; the gate matrix is
    the small LOCAL matrix over (control, system...) operands.
    """
    t = total_qubits - len(system_qubits)
    dim_u = 1 << len(system_qubits)
    if unitary.shape != (dim_u, dim_u):
        raise QuantumCoreError(
            f"Unitary shape {unitary.shape} does not match {len(system_qubits)} system qubits."
        )
    from ..quantum.operators import is_unitary

    if not is_unitary(unitary):
        raise QuantumCoreError("QPE requires a unitary operator.")
    if sorted(system_qubits) != list(range(t, total_qubits)):
        raise QuantumCoreError(
            "system_qubits must be exactly the last t..total_qubits-1 indices."
        )

    circuit = Circuit(num_qubits=total_qubits, num_clbits=t, name="qpe")
    u_k = np.asarray(unitary, dtype=np.complex128)
    from .conventions import local_reorder

    for k in range(t):
        circuit.add_gate("H", [k])
        u_sys_local = local_reorder(u_k, system_qubits)
        name = f"CU_POW{k}"
        circuit.metadata.setdefault("custom_gates", {})[name] = {
            "matrix": controlled_full_matrix(u_sys_local).tolist(),
            "n_qubits": len(system_qubits) + 1,
        }
        circuit.add_gate(name, [k] + system_qubits)
        u_k = u_k @ u_k
    from .qft import build_qft

    iqft, _info = build_qft(t, inverse=True)
    for op in iqft.operations:
        circuit.add_gate(op.gate, list(op.qubits), params=list(op.params))
    circuit.add_measure(list(range(t)), list(range(t)))
    return circuit


def run_phase_estimation(
    unitary: np.ndarray,
    initial_state: StateVector,
    precision_bits: int,
    *,
    seed: int = 13,
    shots: int = 256,
    known_eigenphase: float | None = None,
) -> PhaseEstimationResult:
    """Run QPE where `initial_state` is prepared as system register content.

    The system qubits are initialized to `initial_state` by inserting X gates
    when it is a computational basis state (the common case); superposition
    inputs are rejected with a clear message rather than silently misrun.
    """
    if not np.allclose(np.abs(initial_state.amplitudes) ** 2,
                       (np.abs(initial_state.amplitudes) ** 2).astype(int)):
        raise QuantumCoreError(
            "QPE runner currently accepts computational-basis input states only; "
            "build a state-preparation prefix into the circuit for other states."
        )
    basis_index = int(np.argmax(np.abs(initial_state.amplitudes) ** 2))
    circuit = build_phase_estimation_circuit(
        unitary, list(range(precision_bits, precision_bits + initial_state.n_qubits)),
        total_qubits=precision_bits + initial_state.n_qubits,
    )
    # Prepare system register via X gates on set bits of the basis index.
    from ..circuits.model import Operation

    prep_ops: list[Operation] = []
    for q in range(initial_state.n_qubits):
        if (basis_index >> q) & 1:
            prep_ops.append(Operation(kind="gate", gate="X", params=(), qubits=(precision_bits + q,)))
    full = Circuit(
        num_qubits=circuit.num_qubits,
        num_clbits=circuit.num_clbits,
        operations=prep_ops + circuit.operations,
        name="qpe-full",
        metadata=dict(circuit.metadata),
    )
    res = simulate(full, seed=seed, shots=shots)
    best_key = res.most_likely_outcome()
    measured_int = int(best_key, 2)
    estimated = measured_int / (1 << precision_bits)
    err = abs(estimated - known_eigenphase) if known_eigenphase is not None else None
    return PhaseEstimationResult(
        true_phase=known_eigenphase,
        estimated_phase=float(estimated),
        precision_bits=precision_bits,
        measured_integer=measured_int,
        error=float(err) if err is not None else None,
        counts=res.counts,
    )


# ---------------------------------------------------------------------------
# Bounded Shor: order finding for a^x mod N
# ---------------------------------------------------------------------------

def modular_multiplication_matrix(a: int, N: int) -> tuple[np.ndarray, int]:
    """Permutation matrix of x -> a·x mod N on a register of L qubits.

    Values x >= N map to themselves (standard convention keeping the map
    bijective). Returns (matrix, L).
    """
    if N < 2 or N > 32:
        raise QuantumCoreError(
            "Bounded Shor supports only tiny moduli (2 ≤ N ≤ 32) because the "
            "modular multiplication oracle is materialized as a dense matrix."
        )
    if math.gcd(a, N) != 1 or not (1 < a < N):
        raise QuantumCoreError(
            f"a={a} must satisfy gcd(a, N)=1 and 1 < a < N={N}."
        )
    L = max(1, (N - 1).bit_length())
    dim = 1 << L
    perm = np.zeros((dim, dim), dtype=np.complex128)
    for x in range(dim):
        y = (a * x) % N if x < N else x
        perm[y, x] = 1.0
    return perm, L


def find_order_classical(a: int, N: int) -> int:
    r, v = 1, a % N
    while v != 1:
        v = (v * a) % N
        r += 1
        if r > 10 * N:
            raise QuantumCoreError("Order search exceeded bound; invalid input?")
    return r


def continued_fraction_phase_to_order(phase: float, a: int, N: int) -> int | None:
    """Convert measured phase φ ≈ s/r to order r via continued fractions."""
    if phase == 0:
        return None
    frac_limit = 8 * N
    num, den = _continued_fraction(phase, frac_limit)
    if den and den <= N and _is_valid_order(den, a, N):
        return den
    # try small multiples
    for mult in range(2, 8):
        cand = den * mult
        if cand <= N * 2 and _is_valid_order(cand, a, N):
            return cand
    return None


def _is_valid_order(r: int, a: int, N: int) -> bool:
    return r > 0 and pow(a, r, N) == 1


def _continued_fraction(x: float, limit: int) -> tuple[int, int]:
    """Best rational approximation p/q to x with q <= limit."""
    p0, q0, p1, q1 = 0, 1, 1, 0
    y = x
    for _ in range(64):
        ai = int(y)
        p2 = ai * p1 + p0
        q2 = ai * q1 + q0
        if q2 > limit:
            break
        p0, q0, p1, q1 = p1, q1, p2, q2
        frac = y - ai
        if frac < 1e-12:
            break
        y = 1 / frac
    return p1, q1


@dataclass
class OrderFindingResult:
    a: int
    N: int
    measured_phases_top: list[float]
    recovered_order: int | None
    true_order: int
    success: bool
    raw_counts: dict[str, int]


def run_order_finding(a: int, N: int, *, seed: int = 23, shots: int = 128) -> OrderFindingResult:
    """Quantum order finding for a^x mod N (bounded Shor core)."""
    perm, L = modular_multiplication_matrix(a, N)
    # Precision bits: enough for useful resolution at these sizes.
    t = 2 * L + 3
    total_qubits = t + L
    if total_qubits > 16:
        raise QuantumCoreError(
            f"Order finding would need {total_qubits} qubits; bounded demo caps at 16."
        )

    circuit = Circuit(num_qubits=total_qubits, num_clbits=t, name=f"order-finding-{a}mod{N}")

    # Controlled powers as LOCAL matrices over (control, system) operands —
    # each is 2^(L+1) × 2^(L+1), tiny regardless of precision register size.
    u_pows: list[np.ndarray] = []
    u_k = perm.copy()
    for _ in range(t):
        u_pows.append(u_k)
        u_k = np.linalg.matrix_power(u_k, 2)

    for q in range(t):
        circuit.add_gate("H", [q])
    system_qubits = list(range(t, total_qubits))
    # Convert each power from full-register little-endian indexing into the
    # gate-local basis of the system operands before adding the control block.
    from .conventions import local_reorder

    for k in range(t):
        u_sys_local = local_reorder(u_pows[k], system_qubits)
        name = f"CU_{k}"
        circuit.metadata.setdefault("custom_gates", {})[name] = {
            "matrix": controlled_full_matrix(u_sys_local).tolist(),
            "n_qubits": L + 1,
        }
        circuit.add_gate(name, [k] + system_qubits)
    from .qft import build_qft

    iqft, _ = build_qft(t, inverse=True)
    for op in iqft.operations:
        circuit.add_gate(op.gate, list(op.qubits), params=list(op.params))
    circuit.add_measure(list(range(t)), list(range(t)))

    # Initial system state |1> on the modular register.
    prep_ops = []
    from ..circuits.model import Operation

    prep_ops.append(Operation(kind="gate", gate="X", params=(), qubits=(t,)))
    full = Circuit(
        num_qubits=total_qubits, num_clbits=t,
        operations=prep_ops + circuit.operations,
        name="order-finding-full",
        metadata=dict(circuit.metadata),
    )
    res = simulate(full, seed=seed, shots=shots)

    true_order = find_order_classical(a, N)
    phases = []
    recovered = None
    top_keys = sorted(res.counts.items(), key=lambda kv: -kv[1])[:8]
    for key, count in top_keys:
        phi = int(key, 2) / (1 << t)
        phases.append(phi)
        cand = continued_fraction_phase_to_order(phi, a, N)
        if cand == true_order:
            recovered = cand
    return OrderFindingResult(
        a=a, N=N,
        measured_phases_top=phases,
        recovered_order=recovered if recovered is not None else (
            continued_fraction_phase_to_order(phases[0], a, N) if phases else None
        ),
        true_order=true_order,
        success=recovered == true_order,
        raw_counts=res.counts,
    )


def factorize_bounded(N: int, *, seed: int = 23) -> dict:
    """Full bounded factoring pipeline: classical setup → quantum → post."""
    if N < 4 or N % 2 == 0:
        if N % 2 == 0 and N > 2:
            return {"N": N, "factors": [2, N // 2], "method": "parity shortcut",
                    "quantum_used": False}
        raise QuantumCoreError("Choose odd composite N ≥ 15 for the bounded demo.")
    import random

    rng = random.Random(seed)
    attempts = []
    for _ in range(20):
        a = rng.randrange(2, N)
        g = math.gcd(a, N)
        if 1 < g < N:
            attempts.append({"a": a, "shortcut_gcd": g})
            return {"N": N, "factors": [g, N // g], "method": "gcd shortcut",
                    "quantum_used": False, "attempts": attempts}
        result = run_order_finding(a, N, seed=rng.randrange(1 << 30))
        attempts.append({"a": a, "order_result": result.recovered_order,
                         "true_order": result.true_order, "success": result.success})
        r = result.recovered_order
        if result.success and r % 2 == 0:
            candidate = pow(a, r // 2, N)
            if candidate != N - 1 and candidate > 1:
                f1 = math.gcd(candidate - 1, N)
                f2 = math.gcd(candidate + 1, N)
                if 1 < f1 < N:
                    return {"N": N, "factors": [f1, N // f1], "method": "shor-bounded",
                            "quantum_used": True, "attempts": attempts}
                if 1 < f2 < N:
                    return {"N": N, "factors": [f2, N // f2], "method": "shor-bounded",
                            "quantum_used": True, "attempts": attempts}
    return {"N": N, "factors": None, "method": "exhausted", "quantum_used": True,
            "attempts": attempts}


# ---------------------------------------------------------------------------
# Discrete quantum walk vs classical walk
# ---------------------------------------------------------------------------

def discrete_quantum_walk(n_position_qubits: int, steps: int, *, coin_bias: str = "H") -> dict:
    """Coined walk on a cycle of size 2^n using shift + coin operators.

    Coin: Hadamard. Shift: conditional translation ±1 mod N depending on coin.
    Both are explicit permutation/structured matrices (documented model).
    """
    positions = 1 << n_position_qubits
    dim = 2 * positions
    H_coin = np.kron(np.array([[1, 1], [1, -1]]) / np.sqrt(2), np.eye(positions))
    plus = np.zeros((dim, dim))
    minus = np.zeros((dim, dim))
    for pos in range(positions):
        for coin in range(2):
            src = coin * positions + pos
            dst_coin = coin
            dst_pos = (pos + 1) % positions if coin == 0 else (pos - 1) % positions
            dst = dst_coin * positions + dst_pos
            if coin == 0:
                plus[dst, src] = 1
            else:
                minus[dst, src] = 1
    shift = plus + minus
    step = shift @ H_coin
    state = np.zeros(dim, dtype=np.complex128)
    start = 0 * positions + 0  # position 0, coin 0
    state[start] = 1.0
    evolution = np.linalg.matrix_power(step, steps)
    final = evolution @ state
    probs = (np.abs(final) ** 2).reshape(2, positions).sum(axis=0)

    # Classical reference: unbiased random walk on the same cycle.
    rng = np.random.default_rng(steps * 31 + n_position_qubits)
    samples = rng.choice([-1, 1], size=(20000, steps))
    traj = np.cumsum(samples, axis=1) % positions
    hist = np.bincount(traj[:, -1], minlength=positions).astype(float)
    hist /= hist.sum()
    return {
        "n_position_qubits": n_position_qubits,
        "positions": positions,
        "steps": steps,
        "quantum_distribution": probs.tolist(),
        "classical_distribution": hist.tolist(),
        "quantum_std": float(_circular_std(probs)),
        "classical_std": float(_circular_std(hist)),
        "note": "Classical curve from 20000 seeded Monte Carlo walks on the same cycle.",
    }


def _circular_std(distribution) -> float:
    """Spread measure on a cycle via first circular moment."""
    n = len(distribution)
    angles = 2 * np.pi * np.arange(n) / n
    r = np.abs((distribution * np.exp(1j * angles)).sum())
    return float(np.sqrt(max(0.0, -2 * np.log(max(r, 1e-15)))))
