"""Core algorithm suite built on the common circuit API (directive §44).

Each builder returns a `Circuit` plus structured metadata; convenience runners
simulate and analyze. All stochastic parts are seed-driven.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..circuits.model import Circuit, Condition
from ..circuits.simulate import simulate
from ..quantum.states import StateVector, QuantumCoreError


# ---------------------------------------------------------------------------
# Deutsch / Deutsch-Jozsa
# ---------------------------------------------------------------------------

@dataclass
class OracleSpec:
    """Boolean oracle defined by an explicit truth table (no code execution)."""

    n_input: int
    outputs: tuple[int, ...]

    @classmethod
    def constant(cls, n: int, value: int) -> "OracleSpec":
        return cls(n, tuple([value] * (1 << n)))

    @classmethod
    def balanced(cls, n: int, seed: int = 0) -> "OracleSpec":
        rng = np.random.default_rng(seed)
        outs = list(rng.permutation([0, 1] * (1 << (n - 1))))
        return cls(n, tuple(outs))

    def is_constant(self) -> bool:
        return len(set(self.outputs)) == 1

    def is_balanced(self) -> bool:
        return sum(self.outputs) == (1 << self.n_input) // 2

    def validate(self) -> None:
        dim = 1 << self.n_input
        if len(self.outputs) != dim or any(o not in (0, 1) for o in self.outputs):
            raise QuantumCoreError(
                f"Oracle must define f for all {dim} inputs with values in {{0,1}}."
            )


def build_deutsch_jozsa_circuit(oracle: OracleSpec) -> Circuit:
    """DJ circuit: ancilla convention — oracle flips phase via phase kickback.

    Qubit n is the ancilla; input register qubits 0..n-1. The oracle is applied
    as a diagonal sign function U_f|x>|a> = (-1)^{f(x)}|x>|a> using the phase-
    kickback identity on the ancilla prepared in |->.
    """
    oracle.validate()
    n = oracle.n_input
    c = Circuit(num_qubits=n + 1, num_clbits=n, name="deutsch-jozsa")
    for q in range(n):
        c.add_gate("H", [q])
    c.add_gate("X", [n])
    c.add_gate("H", [n])
    _add_phase_oracle(c, oracle, list(range(n)), n)
    for q in range(n):
        c.add_gate("H", [q])
    c.add_measure(list(range(n)), list(range(n)))
    return c


def _add_phase_oracle(circuit: Circuit, oracle: OracleSpec, input_qubits: list[int], ancilla: int) -> None:
    """Diagonal (-1)^{f(x)} oracle as a custom gate (structured data only).

    The matrix is first written in full-register little-endian indexing
    (input register = low bits) and then converted to the gate-local basis
    via :mod:`app.algorithms.conventions` — operand order matters and this
    conversion is tested explicitly.
    """
    import numpy as np

    from .conventions import local_reorder

    dim_in = 1 << oracle.n_input
    signs = np.array([1 - 2 * o for o in oracle.outputs], dtype=np.complex128)
    total_qubits = oracle.n_input + 1
    full_dim = 1 << total_qubits
    # Full-register indexing over qubits [0..n]: input value x = low n bits;
    # the sign depends only on x (both ancilla values get the same phase).
    diag_full = np.ones(full_dim, dtype=np.complex128)
    for i in range(full_dim):
        diag_full[i] = signs[i % dim_in]
    matrix = local_reorder(np.diag(diag_full), list(range(total_qubits)))
    gate_name = "DJ_ORACLE"
    circuit.metadata.setdefault("custom_gates", {})[gate_name] = {
        "matrix": matrix.tolist(),
        "n_qubits": total_qubits,
    }
    circuit.add_gate(gate_name, list(range(total_qubits)))


def run_deutsch_jozsa(oracle: OracleSpec, seed: int = 0) -> dict:
    circuit = build_deutsch_jozsa_circuit(oracle)
    res = simulate(circuit, seed=seed, shots=64)
    outcome = res.most_likely_outcome()
    verdict_constant = outcome == "0" * oracle.n_input
    expected = oracle.is_constant()
    return {
        "algorithm": "deutsch-jozsa",
        "outcome_bitstring": outcome,
        "verdict": "constant" if verdict_constant else "balanced",
        "expected": "constant" if expected else "balanced",
        "correct": ("constant" if verdict_constant else "balanced")
        == ("constant" if expected else "balanced"),
        "counts": res.counts,
    }


def run_deutsch(f_xor: int, seed: int = 0) -> dict:
    """Deutsch's algorithm: determine f(0) xor f(1) with one oracle query.

    `f_xor` is the expected parity; for one bit, constant vs balanced is fully
    determined by which of (0,0),(1,1) vs (0,1),(1,0) the truth table is.
    """
    outputs = (0, 1) if int(f_xor) == 1 else (0, 0)
    return run_deutsch_jozsa(OracleSpec(1, outputs), seed=seed)


# ---------------------------------------------------------------------------
# Bernstein-Vazirani
# ---------------------------------------------------------------------------

def build_bernstein_vazirani(secret: str | int, n_bits: int | None = None) -> Circuit:
    """Hidden bitstring s recovered with one query via phase kickback."""
    if isinstance(secret, str):
        bits_str = secret.replace(" ", "")
        if any(b not in "01" for b in bits_str):
            raise QuantumCoreError("Secret bitstring may contain only 0/1.")
        s_int = int(bits_str, 2)
        n = len(bits_str)
    else:
        s_int = int(secret)
        n = n_bits or max(1, s_int.bit_length())
    if not (0 <= s_int < (1 << n)):
        raise QuantumCoreError(f"Secret {s_int} does not fit in {n} bits.")

    c = Circuit(num_qubits=n + 1, num_clbits=n, name="bernstein-vazirani")
    for q in range(n):
        c.add_gate("H", [q])
    c.add_gate("X", [n]).add_gate("H", [n])
    # Phase oracle for s: (-1)^{s·x}. Implemented as CX from each set bit of s
    # into the |-⟩ ancilla (phase kickback).
    for i in range(n):
        if (s_int >> i) & 1:
            c.add_gate("CX", [i, n])
    for q in range(n):
        c.add_gate("H", [q])
    c.add_measure(list(range(n)), list(range(n)))
    return c


def run_bernstein_vazirani(secret: str | int, shots: int = 128, seed: int = 3) -> dict:
    circuit = build_bernstein_vazirani(secret)
    n = circuit.num_qubits - 1
    res = simulate(circuit, seed=seed, shots=shots)
    found = res.most_likely_outcome()
    expected = format(int(str(secret), 2) if isinstance(secret, str) else int(secret), f"0{n}b")
    return {
        "algorithm": "bernstein-vazirani",
        "recovered": found,
        "expected": expected,
        "correct": found == expected,
        "counts": res.counts,
    }


# ---------------------------------------------------------------------------
# Simon's algorithm
# ---------------------------------------------------------------------------

@dataclass
class SimonProblem:
    """Two-to-one function with hidden mask s over n bits."""

    n: int
    s: str
    table: dict[int, int] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.n, int) or isinstance(self.n, bool) or self.n < 1:
            raise QuantumCoreError("Simon requires a positive integer register size.")
        if len(self.s) != self.n or any(b not in "01" for b in self.s):
            raise QuantumCoreError("Simon mask s must be an n-bit 0/1 string.")
        self.s_int = int(self.s, 2)
        if self.s_int == 0:
            raise QuantumCoreError("This Simon implementation requires the nonzero two-to-one promise.")

    def evaluate(self, x: int) -> int:
        return self.table[x]


def make_simon_problem(n: int, s: str, seed: int = 5) -> SimonProblem:
    """Construct a canonical promised table; seed is retained for caller compatibility."""
    problem = SimonProblem(n=n, s=s)
    s_int = problem.s_int
    assignment: dict[int, int] = {}
    next_value = 0
    for x in range(1 << n):
        partner = x ^ s_int
        if partner in assignment:
            continue
        assignment[x] = next_value
        assignment[partner] = next_value
        next_value += 1
    problem.table = assignment
    return problem


def build_simon_circuit(problem: SimonProblem) -> Circuit:
    """Oracle U_f|x>|y> = |x>|y xor f(x)> as an explicit permutation matrix.

    The permutation is first expressed in full-register little-endian indexing
    (first register = low bits) and converted to gate-local basis.
    """
    n = problem.n
    # Verify both directions of the promise: every output has exactly one pair.
    if set(problem.table) != set(range(1 << n)):
        raise QuantumCoreError("Simon oracle must define every n-bit input.")
    preimages: dict[int, list[int]] = {}
    for x, value in problem.table.items():
        if not isinstance(value, (int, np.integer)) or not 0 <= value < (1 << n):
            raise QuantumCoreError("Simon oracle outputs must be n-bit integers.")
        preimages.setdefault(value, []).append(x)
    if any(len(xs) != 2 or xs[0] ^ xs[1] != problem.s_int for xs in preimages.values()):
        raise QuantumCoreError("Simon oracle violates the nonzero two-to-one promise.")
    total = 2 * n
    dim = 1 << total
    from .conventions import local_reorder

    perm_full = np.zeros((dim, dim), dtype=np.complex128)
    for x in range(1 << n):
        fx = problem.evaluate(x)
        for y in range(1 << n):
            src = x | (y << n)   # first register in low bits (little-endian)
            dst = x | ((y ^ fx) << n)
            perm_full[dst, src] = 1.0
    perm_local = local_reorder(perm_full, list(range(total)))
    c = Circuit(num_qubits=total, num_clbits=2 * n, name="simon")
    c.metadata["custom_gates"] = {
        "SIMON_ORACLE": {"matrix": perm_local.tolist(), "n_qubits": total}
    }
    for q in range(n):
        c.add_gate("H", [q])
    c.add_gate("SIMON_ORACLE", list(range(total)))
    # Measure/collapse the SECOND register (discarded value) so the first
    # register collapses onto {x0, x0 xor s}; then Hadamards reveal mask info.
    c.add_measure(list(range(n, total)), list(range(n, 2 * n)))
    for q in range(n):
        c.add_gate("H", [q])
    c.add_measure(list(range(n)), list(range(n)))
    return c


def run_simon(problem: SimonProblem, shots: int = 32, seed: int = 9) -> dict:
    """Acquire independent low-register equations until rank n-1 or budget.

    ``shots`` is a maximum query budget, not a promise of successful recovery.
    The returned secret is derived only from observations and the nonzero promise.
    """
    if not isinstance(shots, int) or isinstance(shots, bool) or shots < 1:
        raise QuantumCoreError("Simon shots must be a positive integer budget.")
    circuit = build_simon_circuit(problem)
    basis: dict[int, int] = {}
    independent: list[int] = []
    samples: list[int] = []
    counts: dict[str, int] = {}
    target_rank = problem.n - 1
    while len(basis) < target_rank and len(samples) < shots:
        result = simulate(circuit, seed=seed + len(samples), shots=1)
        # Printed keys include the discarded high output register. Only the
        # low n bits are y; including the high register corrupts the equations.
        y = int(next(iter(result.counts)), 2) & ((1 << problem.n) - 1)
        samples.append(y)
        key = format(y, f"0{problem.n}b")
        counts[key] = counts.get(key, 0) + 1
        row = y
        while row:
            pivot = row.bit_length() - 1
            if pivot not in basis:
                basis[pivot] = row
                independent.append(y)
                break
            row ^= basis[pivot]
    rank = len(basis)
    recovered = solve_gf2_linear_system(independent, problem.n) if rank == target_rank else None
    return {
        "algorithm": "simon",
        "hidden_mask": problem.s,
        "recovered_mask": recovered,
        "orthogonal_samples": sorted(set(samples)),
        "independent_equations": [format(y, f"0{problem.n}b") for y in independent],
        "rank": rank,
        "target_rank": target_rank,
        "shots_used": len(samples),
        "shot_budget": shots,
        "stopping_reason": "rank_reached" if rank == target_rank else "shot_budget_exhausted",
        "promise": "nonzero_two_to_one",
        "counts": counts,
        "correct": recovered == problem.s,
    }


def solve_gf2_linear_system(vectors: list[int], n: int) -> str | None:
    """Find s with y·s = 0 (mod 2) for all sampled y; returns s as bitstring or None.

    Brute-force nullspace search over 2^n candidates — appropriate because
    Simon instances here are small; a Gaussian-elimination solver would replace
    this at larger n. Returns None when samples underdetermine s.
    """
    rows = [v for v in vectors if v != 0]
    solutions = []
    for cand in range(1, 1 << n):
        if all(bin(y & cand).count("1") % 2 == 0 for y in set(rows)):
            solutions.append(cand)
            if len(solutions) > 1:
                return None
    if len(solutions) != 1:
        return None
    return format(solutions[0], f"0{n}b")


# ---------------------------------------------------------------------------
# Grover search
# ---------------------------------------------------------------------------

@dataclass
class GroverResult:
    marked_states: list[str]
    marked_state: str | None
    counts: dict[str, int]
    iterations_used: int
    optimal_iterations: int
    success_probability_estimate: float
    exact_success_probability: float
    marked_fraction: float
    analytic_per_iteration_probabilities: list[float]
    per_iteration_probabilities: list[float] = field(default_factory=list)


def _mcz_matrix(n_qubits: int) -> "np.ndarray":
    """Diagonal multi-controlled Z over all n qubits (bounded-size helper).

    Documented limitation: explicit dense construction, so n <= 12 (memory).
    """
    if n_qubits > 12:
        raise QuantumCoreError(
            "Grover's dense MCZ oracle supports at most 12 qubits; larger "
            "instances need a decomposed oracle (not yet implemented)."
        )
    diag = np.ones(1 << n_qubits, dtype=np.complex128)
    diag[-1] = -1.0
    return np.diag(diag)


def grover_optimal_iterations(n_qubits: int, marked_count: int = 1) -> int:
    """Nearest integer to the first rotation peak; ties prefer fewer queries.

    This is the usual first-peak query prescription, not a global maximum
    over arbitrarily many later oscillations. It allows k=0 when M/N >= 1/2.
    """
    if not isinstance(n_qubits, int) or isinstance(n_qubits, bool) or not 1 <= n_qubits <= 12:
        raise QuantumCoreError("Grover supports 1 through 12 qubits.")
    if not isinstance(marked_count, int) or isinstance(marked_count, bool) or not 1 <= marked_count <= (1 << n_qubits):
        raise QuantumCoreError("marked_count must be between 1 and the register size.")
    theta = np.arcsin(np.sqrt(marked_count / (1 << n_qubits)))
    peak = (np.pi / (2 * theta) - 1) / 2
    return max(0, int(np.ceil(peak - 0.5 - 1e-12)))


def grover_analytic_success_probability(n_qubits: int, marked_count: int, iterations: int) -> float:
    """sin^2((2k+1) asin(sqrt(M/N))) for the two-dimensional Grover rotation."""
    if not 1 <= marked_count <= (1 << n_qubits):
        raise QuantumCoreError("marked_count must be between 1 and the register size.")
    if not isinstance(iterations, int) or isinstance(iterations, bool) or iterations < 0:
        raise QuantumCoreError("iterations must be a nonnegative integer.")
    theta = np.arcsin(np.sqrt(marked_count / (1 << n_qubits)))
    return float(np.sin((2 * iterations + 1) * theta) ** 2)


def build_grover_circuit(
    n_qubits: int,
    marked_index: int | list[int] | None = None,
    iterations: int | None = None,
    *,
    marked_indices: int | list[int] | None = None,
) -> tuple[Circuit, int]:
    """Grover phase oracle over a distinct, nonempty marked set."""
    if not isinstance(n_qubits, int) or isinstance(n_qubits, bool) or not 1 <= n_qubits <= 12:
        raise QuantumCoreError("Grover supports 1 through 12 qubits.")
    if marked_index is not None and marked_indices is not None:
        raise QuantumCoreError("Specify marked_index or marked_indices, not both.")
    if marked_indices is None and marked_index is not None:
        marked_indices = marked_index
    if marked_indices is None:
        raise QuantumCoreError("Grover requires at least one marked state.")
    if isinstance(marked_indices, int):
        marked_list = [marked_indices]
    else:
        marked_list = list(marked_indices)
    if not marked_list or any(not isinstance(m, int) or isinstance(m, bool) or not 0 <= m < (1 << n_qubits) for m in marked_list):
        raise QuantumCoreError(f"marked indices must be distinct integers in [0, 2^{n_qubits}).")
    if len(set(marked_list)) != len(marked_list):
        raise QuantumCoreError("Grover marked indices must be distinct.")
    iters = iterations if iterations is not None else grover_optimal_iterations(n_qubits, len(marked_list))
    if not isinstance(iters, int) or isinstance(iters, bool) or iters < 0:
        raise QuantumCoreError("Grover iterations must be a nonnegative integer.")
    c = Circuit(num_qubits=n_qubits, num_clbits=n_qubits, name=f"grover-{n_qubits}q")
    from ..quantum.operators import custom_gate

    mcz = custom_gate("MCZ", _mcz_matrix(n_qubits))
    c.metadata["custom_gates"] = {"MCZ": {"matrix": mcz.matrix.tolist(), "n_qubits": n_qubits}}
    c.metadata["marked_indices"] = sorted(marked_list)
    for q in range(n_qubits):
        c.add_gate("H", [q])

    def add_oracle():
        # Phase-flip each marked basis state: map it to |11..1>, MCZ, map back.
        for marked in marked_list:
            flip_bits = [i for i in range(n_qubits) if not ((marked >> i) & 1)]
            for i in flip_bits:
                c.add_gate("X", [i])
            c.add_gate("MCZ", list(range(n_qubits)))
            for i in flip_bits:
                c.add_gate("X", [i])

    def add_diffusion():
        for q in range(n_qubits):
            c.add_gate("H", [q])
            c.add_gate("X", [q])
        c.add_gate("MCZ", list(range(n_qubits)))
        for q in range(n_qubits):
            c.add_gate("X", [q])
            c.add_gate("H", [q])

    for _ in range(iters):
        add_oracle()
        add_diffusion()
    c.add_measure(list(range(n_qubits)), list(range(n_qubits)))
    return c, iters


def run_grover(
    n_qubits: int,
    marked_index: int | list[int] | None = None,
    *,
    marked_indices: int | list[int] | None = None,
    shots: int = 1024,
    seed: int = 17,
    iterations: int | None = None,
) -> GroverResult:
    if not isinstance(shots, int) or isinstance(shots, bool) or shots < 1:
        raise QuantumCoreError("Grover shots must be a positive integer.")
    c, iters = build_grover_circuit(
        n_qubits, marked_index, iterations, marked_indices=marked_indices)
    marked_list = c.metadata["marked_indices"]
    m = len(marked_list)
    n = 2 ** n_qubits
    res = simulate(c, seed=seed, shots=shots)
    keys = [format(i, f"0{n_qubits}b") for i in marked_list]
    success = sum(res.counts.get(k, 0) for k in keys) / shots
    analytic = [grover_analytic_success_probability(n_qubits, m, k) for k in range(1, iters + 1)]
    # Exact per-iteration marked probability via noiseless evolution:
    per_iter = []
    for k in range(1, iters + 1):
        ck, _ = build_grover_circuit(n_qubits, marked_list, k)
        r = simulate(ck, shots=None)
        probs = r.final_state.probabilities()
        per_iter.append(float(sum(probs[i] for i in marked_list)))
    return GroverResult(
        marked_states=sorted(keys),
        marked_state=keys[0] if m == 1 else None,
        counts=res.counts,
        iterations_used=iters,
        optimal_iterations=grover_optimal_iterations(n_qubits, m),
        success_probability_estimate=success,
        exact_success_probability=float(res.final_state.probabilities()[marked_list].sum()),
        marked_fraction=m / n,
        analytic_per_iteration_probabilities=analytic,
        per_iteration_probabilities=per_iter,
    )


# ---------------------------------------------------------------------------
# Superdense coding
# ---------------------------------------------------------------------------

def build_superdense(bits_to_send: str) -> Circuit:
    """Alice sends 2 classical bits using 1 shared Bell pair + 1 qubit."""
    if len(bits_to_send) != 2 or any(b not in "01" for b in bits_to_send):
        raise QuantumCoreError("Superdense coding sends exactly two classical bits.")
    b1, b2 = (int(b) for b in bits_to_send)
    c = Circuit(num_qubits=2, num_clbits=2, name="superdense")
    c.add_gate("H", [0]).add_gate("CX", [0, 1])   # shared Bell pair
    # Alice encodes on qubit 0: Z for first bit, X for second.
    if b1:
        c.add_gate("Z", [0])
    if b2:
        c.add_gate("X", [0])
    # Bob decodes.
    c.add_gate("CX", [0, 1])
    c.add_gate("H", [0])
    c.add_measure([0, 1], [0, 1])
    return c


def run_superdense(bits_to_send: str, shots: int = 256, seed: int = 21) -> dict:
    c = build_superdense(bits_to_send)
    res = simulate(c, seed=seed, shots=shots)
    # Little-endian: clbit0 holds first encoded bit.
    decoded_keys = res.counts
    expected = f"{bits_to_send[1]}{bits_to_send[0]}"  # register prints high bit first
    return {
        "algorithm": "superdense-coding",
        "sent": bits_to_send,
        "received_distribution": decoded_keys,
        "decoded": res.most_likely_outcome(),
        "expected_key": expected,
        "success_rate": decoded_keys.get(expected, 0) / shots,
    }
