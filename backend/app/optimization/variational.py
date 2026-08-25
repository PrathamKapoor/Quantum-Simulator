"""Variational quantum algorithms: ansaetze, optimizers, VQE, QAOA.

Framework (directive §50-51): a variational experiment = ansatz + objective +
classical optimizer. Convergence histories are always returned so results can
be plotted honestly; optimizers are deterministic given seeds.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ..circuits.model import Circuit, Operation
from ..circuits.simulate import simulate
from .hamiltonians import Hamiltonian


# ---------------------------------------------------------------------------
# Ansaetze
# ---------------------------------------------------------------------------

def hardware_efficient_ansatz(n_qubits: int, layers: int, params: np.ndarray) -> Circuit:
    """RY+CX hardware-efficient ansatz.

    Params: 2 * n_qubits * layers values in radians (RY per qubit per layer,
    RZ per qubit per layer).
    """
    expected = 2 * n_qubits * layers
    if len(params) != expected:
        raise ValueError(f"Ansatz needs {expected} parameters, got {len(params)}.")
    c = Circuit(num_qubits=n_qubits, name="hea")
    k = 0
    for layer in range(layers):
        for q in range(n_qubits):
            c.add_gate("RY", [q], params=[float(params[k])])
            k += 1
        for q in range(n_qubits):
            c.add_gate("RZ", [q], params=[float(params[k])])
            k += 1
        if layer < layers - 1:
            for q in range(0, n_qubits - 1):
                c.add_gate("CX", [q, q + 1])
    return c


def two_local_h2_ansatz(params: np.ndarray) -> Circuit:
    """Standard 2-qubit H2 ansatz: X0 I; RY on q1; CX; RY on q0."""
    if len(params) != 3:
        raise ValueError("H2 ansatz needs 3 parameters.")
    c = Circuit(num_qubits=2, name="h2-ansatz")
    c.add_gate("X", [0])
    c.add_gate("RY", [1], params=[float(params[0])])
    c.add_gate("CX", [1, 0])
    c.add_gate("RY", [0], params=[float(params[1])])
    c.add_gate("RY", [1], params=[float(params[2])])
    return c


ANSATZ_REGISTRY = {
    "hardware_efficient": hardware_efficient_ansatz,
    "h2_two_local": lambda n, layers, params: two_local_h2_ansatz(params),
}


# ---------------------------------------------------------------------------
# Classical optimizers (bounded, derivative-free)
# ---------------------------------------------------------------------------

def optimize_spsa(
    objective, x0: np.ndarray, *, max_iter: int = 120, step: float = 0.25,
    perturb: float = 0.15, seed: int = 0, convergence_tol: float = 1e-6,
) -> dict:
    """Simultaneous Perturbation Stochastic Approximation — robust and cheap.

    Returns history of best values; deterministic under seed.
    """
    rng = np.random.default_rng(seed)
    x = x0.astype(float).copy()
    best_x = x.copy()
    best_f = objective(x)
    history = [best_f]
    a = step
    for k in range(max_iter):
        ak = a / (k + 1 + 10) ** 0.602
        ck = perturb / (k + 1) ** 0.101
        delta = rng.choice([-1.0, 1.0], size=x.shape)
        fp = objective(x + ck * delta)
        fm = objective(x - ck * delta)
        ghat = (fp - fm) / (2 * ck) * (-delta)  # minimize
        x = np.clip(x - ak * ghat, -2 * math.pi, 4 * math.pi)
        f = objective(x)
        if f < best_f:
            best_f = f
            best_x = x.copy()
        history.append(best_f)
        if len(history) > 12 and abs(history[-1] - history[-12]) < convergence_tol:
            break
    return {"x": best_x, "f": float(best_f), "history": [float(h) for h in history],
            "iterations": max_iter}


def optimize_coordinate_descent(objective, x0: np.ndarray, *, max_iter: int = 200,
                                step: float = 0.35, tol: float = 1e-7) -> dict:
    """Simple cyclic coordinate descent with numeric gradients."""
    x = x0.astype(float).copy()
    best_f = objective(x)
    history = [best_f]
    for _ in range(max_iter):
        improved = False
        for i in range(len(x)):
            for direction in (+step, -step):
                xp = x.copy()
                xp[i] += direction
                f = objective(xp)
                if f < best_f - 1e-15:
                    x, best_f, improved = xp, f, True
        history.append(best_f)
        if not improved:
            step *= 0.5
            if step < 1e-4 or abs(history[-1] - history[-min(len(history), 8)]) < tol:
                break
    return {"x": x, "f": float(best_f), "history": [float(h) for h in history],
            "iterations": max_iter}


def multi_start_optimize(objective, param_count: int, *, starts: int = 8,
                         probe_iter: int = 25, full_iter: int = 120,
                         seed: int = 0, bounds: float = math.pi) -> dict:
    """Multi-start strategy: SPSA probes from broad random inits, then a full
    run from the most promising start. Documented and deterministic under seed.

    Settings rationale (measured, not guessed): variational-classifier
    landscapes contain symmetric plateaus where small-step SPSA stalls, so
    probes use enlarged step/perturbation (0.8/0.3) and enough iterations to
    escape them. Default 8 starts × 25 probe iterations.
    """
    rng = np.random.default_rng(seed)
    candidates = []
    for s in range(starts):
        x0 = rng.uniform(-bounds / 3, bounds / 3, size=param_count)
        probe = optimize_spsa(objective, x0, max_iter=probe_iter, step=0.8,
                              perturb=0.3, seed=seed + 100 + s)
        candidates.append((probe["f"], x0))
    candidates.sort(key=lambda t: t[0])
    best_x0 = candidates[0][1]
    return optimize_spsa(objective, best_x0, max_iter=full_iter, step=0.6,
                         perturb=0.25, seed=seed + 999)


OPTIMIZERS = {
    "spsa": optimize_spsa,
    "coordinate_descent": optimize_coordinate_descent,
}


# ---------------------------------------------------------------------------
# VQE
# ---------------------------------------------------------------------------

@dataclass
class VQEResult:
    hamiltonian_name: str
    estimated_energy: float
    exact_energy: float | None
    error: float | None
    optimizer_iterations: int
    energy_history: list[float]
    final_params: list[float]
    notes: list[str]


def run_vqe(
    hamiltonian: Hamiltonian,
    ansatz_builder,
    param_count: int,
    *,
    optimizer: str = "spsa",
    max_iter: int = 150,
    seed: int = 0,
    polish: bool = True,
) -> VQEResult:
    """Variational eigensolver using noiseless statevector expectations.

    With ``polish=True`` (default) a short coordinate-descent pass follows the
    main optimizer — a documented hybrid strategy that removes small residual
    gradients SPSA leaves behind.
    """
    if hamiltonian.n_qubits > 14:
        raise ValueError("VQE demo bounded to <= 14 qubits.")

    def objective(theta: np.ndarray) -> float:
        circuit = ansatz_builder(np.asarray(theta))
        res = simulate(circuit, shots=None)
        return hamiltonian.expectation(res.final_state)

    rng = np.random.default_rng(seed)
    x0 = rng.uniform(-0.3, 0.3, size=param_count)
    opt_fn = OPTIMIZERS.get(optimizer)
    if opt_fn is None:
        raise ValueError(f"Unknown optimizer {optimizer!r}; use {list(OPTIMIZERS)}.")
    result = opt_fn(objective, x0, max_iter=max_iter)
    history = list(result["history"])
    if polish:
        polished = optimize_coordinate_descent(objective, result["x"], max_iter=60)
        if polished["f"] <= result["f"]:
            result = polished
            history = history + polished["history"]

    exact = None
    err = None
    try:
        exact_energy, _psi = hamiltonian.ground_state_energy_exact()
        exact = exact_energy
        err = abs(result["f"] - exact)
    except ValueError:
        pass
    notes = [
        "Noiseless statevector expectation values; no shot noise modeled.",
        "Energies are simulation outputs; convergence depends on ansatz "
        "expressibility and optimizer budget.",
    ]
    return VQEResult(
        hamiltonian_name=hamiltonian.name,
        estimated_energy=result["f"],
        exact_energy=exact,
        error=err,
        optimizer_iterations=result["iterations"],
        energy_history=history,
        final_params=[float(p) for p in result["x"]],
        notes=notes,
    )


# ---------------------------------------------------------------------------
# QAOA for MaxCut
# ---------------------------------------------------------------------------

def qaoa_circuit(n_nodes: int, graph_edges: list[tuple[int, int]], gammas, betas) -> Circuit:
    """QAOA circuit: |+>^n, then p layers of cost/mixer unitaries.

    Cost layer: exp(-i gamma C) implemented via ZZ interactions:
      C = Σ (I − Z_i Z_j)/2  =>  cost unitary = Π exp(+i γ/2 Z_i Z_j)
      implemented with RZZ gates.
    Mixer: exp(-i beta Σ X_i) via RX(beta).
    """
    p = len(gammas)
    if len(betas) != p:
        raise ValueError("Need equal numbers of gammas and betas.")
    c = Circuit(num_qubits=n_nodes, name=f"qaoa-p{p}")
    for q in range(n_nodes):
        c.add_gate("H", [q])
    for layer in range(p):
        for a, b in graph_edges:
            c.add_gate("RZZ", [a, b], params=[-2.0 * float(gammas[layer])])
        for q in range(n_nodes):
            c.add_gate("RX", [q], params=[2.0 * float(betas[layer])])
    return c


@dataclass
class QAOAResult:
    p_layers: int
    best_cut_value: int
    exact_optimum: int
    approximation_ratio: float
    most_likely_bitstring: str
    probability_distribution_top: list[tuple[str, float]]
    optimization_history: list[float]
    notes: list[str]


def run_qaoa_maxcut(
    graph_edges: list[tuple[int, int]],
    n_nodes: int,
    *,
    p_layers: int = 2,
    seed: int = 0,
) -> QAOAResult:
    """QAOA with SPSA parameter search; compared against exact brute force."""
    from .hamiltonians import maxcut_cost, maxcut_brute_force

    if not (2 <= n_nodes <= 12):
        raise ValueError("QAOA demo bounded to 2..12 nodes (brute-force baseline).")
    if p_layers < 1 or p_layers > 5:
        raise ValueError("p_layers must be within [1,5].")

    def objective(theta: np.ndarray) -> float:
        gammas = theta[:p_layers]
        betas = theta[p_layers:]
        circuit = qaoa_circuit(n_nodes, graph_edges, gammas, betas)
        res = simulate(circuit, shots=None)
        probs = res.final_state.probabilities()
        expected_cost = sum(
            probs[x] * maxcut_cost(graph_edges, format(x, f"0{n_nodes}b"))
            for x in range(1 << n_nodes)
        )
        return -float(expected_cost)  # maximize cut

    rng = np.random.default_rng(seed)
    x0 = rng.uniform(0.05, 0.6, size=2 * p_layers)
    result = optimize_spsa(objective, x0, max_iter=140, seed=seed + 1)

    theta = result["x"]
    circuit = qaoa_circuit(
        n_nodes, graph_edges, theta[:p_layers], theta[p_layers:]
    )
    probs = simulate(circuit, shots=None).final_state.probabilities()
    best_idx = int(np.argmax(probs))
    best_bits = format(best_idx, f"0{n_nodes}b")
    best_cut = maxcut_cost(graph_edges, best_bits)
    exact_opt, exact_bits = maxcut_brute_force(n_nodes, graph_edges)
    top = sorted(
        ((format(i, f"0{n_nodes}b"), float(probs[i])) for i in range(1 << n_nodes)),
        key=lambda kv: -kv[1],
    )[:8]
    return QAOAResult(
        p_layers=p_layers,
        best_cut_value=int(best_cut),
        exact_optimum=int(exact_opt),
        approximation_ratio=float(best_cut / max(exact_opt, 1)),
        most_likely_bitstring=best_bits,
        probability_distribution_top=top,
        optimization_history=result["history"],
        notes=[
            "Noiseless statevector QAOA; parameters optimized by SPSA.",
            "Approximation ratio compares the MOST LIKELY sample's cut against "
            "the exact optimum — not a claim of quantum advantage (§54, §324).",
        ],
    )


# ---------------------------------------------------------------------------
# H2 pipeline (§55)
# ---------------------------------------------------------------------------

@dataclass
class H2Result:
    bond_length_angstrom: float
    vqe_energy_hartree: float
    exact_energy_hartree: float
    error_hartree: float
    energy_history: list[float]
    notes: list[str]


def run_h2_experiment(bond_length_angstrom: float = 0.735, *, seed: int = 0) -> H2Result:
    """Bounded H2 experiment: effective Hamiltonian -> ansatz -> VQE."""
    h2 = __import__("app.optimization.hamiltonians", fromlist=["h2_hamiltonian"]).h2_hamiltonian(
        bond_length_angstrom
    )
    vqe = run_vqe(
        h2,
        lambda params: two_local_h2_ansatz(params),
        param_count=3,
        optimizer="spsa",
        max_iter=160,
        seed=seed,
    )
    exact, _ = h2.ground_state_energy_exact()
    return H2Result(
        bond_length_angstrom=bond_length_angstrom,
        vqe_energy_hartree=vqe.estimated_energy,
        exact_energy_hartree=float(exact),
        error_hartree=vqe.error if vqe.error is not None else abs(vqe.estimated_energy - float(exact)),
        energy_history=vqe.energy_history,
        notes=[
            "Two-qubit effective Hamiltonian with tabulated/interpolated "
            "coefficients — an approximate molecular model, NOT full "
            "electronic structure (documented simplification, §55).",
            *vqe.notes,
        ],
    )


def h2_dissociation_curve(lengths: list[float] | None = None, *, seed: int = 0) -> dict:
    lengths = lengths or [0.35, 0.5, 0.65, 0.735, 0.9, 1.1, 1.4, 1.75]
    points = []
    for r in lengths:
        out = run_h2_experiment(r, seed=seed)
        points.append({
            "bond_length_angstrom": out.bond_length_angstrom,
            "vqe_hartree": out.vqe_energy_hartree,
            "exact_hartree": out.exact_energy_hartree,
        })
    return {"points": points, "unit": "hartree (effective model)"}
