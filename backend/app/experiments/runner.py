"""Experiment definitions and the module registry (directives §97-107, §165).

Experiment = definition (what to study). Run = one execution with a resolved
configuration and seed. Sweeps create multiple runs from one experiment.

Every runner returns a standardized result document:
  {
    "schema": "quantumlab.run-result", "version": 1,
    "module": ..., "metrics": {...}, "summary": {...},
    "artifacts": {"tables": [...], "series": [...], ...},
    "notes": [...]
  }
Runner functions are pure w.r.t. (config, seed): identical inputs reproduce
identical outputs bit-for-bit.
"""
from __future__ import annotations

import numpy as np

from dataclasses import dataclass, field

RESULT_SCHEMA = "quantumlab.run-result"
RESULT_VERSION = 1


@dataclass
class SweepParameter:
    name: str
    values: list[float]


@dataclass
class ExperimentSpec:
    """A complete experiment definition (JSON-serializable)."""

    name: str
    module: str                      # registry key below
    config: dict = field(default_factory=dict)
    sweep: list[SweepParameter] = field(default_factory=list)
    backend: str = "statevector"
    noise_model: str | None = None   # named noise preset
    seed: int = 0

    def validate(self) -> list[str]:
        issues = []
        if not self.name or not self.name.strip():
            issues.append("Experiment name must be non-empty.")
        if self.module not in RUNNER_REGISTRY:
            issues.append(
                f"Unknown experiment module {self.module!r}; "
                f"available: {', '.join(sorted(RUNNER_REGISTRY))}."
            )
        if not isinstance(self.seed, int):
            issues.append("Seed must be an integer.")
        for sp in self.sweep:
            if not sp.values:
                issues.append(f"Sweep parameter {sp.name!r} has no values.")
        return issues

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "module": self.module,
            "config": self.config,
            "sweep": [{"name": s.name, "values": s.values} for s in self.sweep],
            "backend": self.backend,
            "noise_model": self.noise_model,
            "seed": self.seed,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ExperimentSpec":
        return cls(
            name=str(d["name"]),
            module=str(d["module"]),
            config=dict(d.get("config", {})),
            sweep=[SweepParameter(s["name"], [float(v) for v in s["values"]])
                   for s in d.get("sweep", [])],
            backend=str(d.get("backend", "statevector")),
            noise_model=d.get("noise_model"),
            seed=int(d.get("seed", 0)),
        )


def make_result_document(module: str, metrics: dict, summary: dict | None = None,
                         artifacts: dict | None = None, notes: list[str] | None = None) -> dict:
    return {
        "schema": RESULT_SCHEMA,
        "version": RESULT_VERSION,
        "module": module,
        "metrics": metrics,
        "summary": summary or {},
        "artifacts": artifacts or {},
        "notes": notes or [],
    }


# ---------------------------------------------------------------------------
# Runner implementations
# ---------------------------------------------------------------------------

def run_circuit_shots(config: dict, seed: int) -> dict:
    from ..circuits import circuit_from_dict, simulate as sim
    from ..noise.models import NoiseModel

    circuit = circuit_from_dict(config["circuit"])
    shots = int(config.get("shots", 1024))
    noise_cfg = config.get("noise")
    noise = NoiseModel.from_config(noise_cfg) if noise_cfg else None
    res = sim(circuit, mode=config.get("mode", "statevector"), seed=seed,
              noise_model=noise, shots=shots)
    total = sum(res.counts.values()) or 1
    metrics = {
        "shots": shots,
        "distinct_outcomes": len(res.counts),
        "top_outcome": res.most_likely_outcome(),
        "top_probability": max(res.counts.values()) / total if res.counts else 0.0,
    }
    return make_result_document(
        "circuit_shots", metrics,
        summary={"counts": res.counts},
        artifacts={"probabilities": res.probabilities},
        notes=["Counts sampled with a single seeded RNG stream."],
    )


def run_qec_sweep(config: dict, seed: int) -> dict:
    from ..qec import get_code, sweep_physical_error_rate

    code_name = str(config.get("code", "bit-flip-3"))
    rates = [float(p) / 1000.0 for p in config.get("physical_error_permille", [1, 5, 10, 50])]
    trials = int(config.get("trials_per_point", 2000))
    points = sweep_physical_error_rate(code_name, rates, trials=trials, seed=seed)
    table = [
        {
            "physical_error_rate": p.physical_error_rate,
            "logical_error_rate": p.logical_error_rate,
            "ci95_low": p.ci_low,
            "ci95_high": p.ci_high,
            "trials": p.trials,
        }
        for p in points
    ]
    metrics = {
        "code": code_name,
        "points": len(table),
        "trials_total": sum(t["trials"] for t in table),
        "lowest_logical_error_rate": min((t["logical_error_rate"] for t in table), default=None),
    }
    return make_result_document(
        "qec_sweep", metrics,
        artifacts={"table": table},
        notes=[
            "Wilson score 95% intervals per point.",
            "Depolarizing per-qubit physical errors; syndrome via stabilizer "
            "algebra; lookup decoder corrects up to distance-3 guarantees.",
        ],
    )


def run_bb84_study(config: dict, seed: int) -> dict:
    from ..protocols import run_bb84

    n_qubits = int(config.get("n_qubits", 512))
    eve_levels = [float(v) / 100.0 for v in config.get("eve_intercept_percent", [0, 25, 100])]
    rows = []
    for i, level in enumerate(eve_levels):
        r = run_bb84(n_qubits, eve_intercept_probability=level,
                     sample_fraction=0.5, seed=seed + 31 * i)
        rows.append({
            "eve_intercept_probability": level,
            "qber": r.qber,
            "sifted_bits": len(r.sifted_indices),
            "sample_size": r.sample_size,
        })
    metrics = {
        "n_signal_qubits": n_qubits,
        "qber_no_eve": rows[0]["qber"] if rows else None,
        "qber_full_eve": rows[-1]["qber"] if rows else None,
    }
    return make_result_document(
        "bb84_study", metrics, artifacts={"table": rows},
        notes=[
            "Ideal channel simulation; QBER rises toward ~25% under full "
            "intercept-resend (statistical, finite-size).",
            "Simulation only — no production security claim (§89).",
        ],
    )


def run_network_study(config: dict, seed: int) -> dict:
    from ..network import (
        Topology, NetworkNode, NetworkEngine, NetworkConfig,
    )

    topo_spec = config.get("topology", {})
    topo = Topology()
    for node in topo_spec.get("nodes", []):
        topo.add_node(NetworkNode(
            name=node["name"],
            node_type=node.get("type", "end"),
            memory_slots=int(node.get("memory_slots", 4)),
        ))
    for link in topo_spec.get("links", []):
        topo.add_quantum_link(
            link["source"], link["destination"],
            distance_km=float(link.get("distance_km", 10)),
            base_fidelity=float(link.get("base_fidelity", 0.99)),
        )
    cfg = NetworkConfig(
        routing_strategy=config.get("routing_strategy", "min_expected_time"),
        scheduler_policy=config.get("scheduler_policy", "fifo"),
        swap_success_probability=float(config.get("swap_success_probability", 1.0)),
        classical_latency_mode=config.get("classical_latency_mode", "realistic"),
        node_failure_rate_per_s=float(config.get("node_failure_rate_per_s", 0.0)),
        link_failure_rate_per_s=float(config.get("link_failure_rate_per_s", 0.0)),
        memory_coherence_ns=float(config.get("memory_coherence_ns", 1_000_000)),
        trace_mode="summary",
    )
    requests = config.get("requests", [{"source": "Alice", "destination": "Bob"}])
    engine = NetworkEngine(topo, cfg, seed=seed)
    for rq in requests:
        eng_req = engine.submit_request(
            rq["source"], rq["destination"],
            protocol=rq.get("protocol", "entanglement"),
            fidelity_requirement=rq.get("fidelity_requirement"),
            deadline_ns=rq.get("deadline_ns"),
            priority=int(rq.get("priority", 0)),
        )
        del eng_req
    until_ns = float(config.get("sim_time_ms", 500)) * 1e6
    result = engine.run(until_ns=until_ns)
    successes = [o for o in result.outcomes if o.success]
    fids = [o.fidelity for o in successes if o.fidelity is not None]
    metrics = {
        "requests": len(result.outcomes),
        "successes": result.success_count,
        "failures": result.failure_count,
        "avg_fidelity": sum(fids) / len(fids) if fids else None,
        "sim_time_ns": result.sim_time_ns,
        "jain_index": result.fairness["jain_index"],
        "events_processed": result.stats["events_processed"],
    }
    timeline = [
        {"time_ns": o.completion_ns, "request_id": o.request_id,
         "source": o.source, "destination": o.destination,
         "success": o.success, "fidelity": o.fidelity}
        for o in result.outcomes
    ]
    return make_result_document(
        "network_study", metrics,
        artifacts={"timeline": timeline, "event_log": result.event_log,
                   "utilization": result.utilization},
        notes=[
            "Discrete-event network simulation; logical simulated time is "
            "unrelated to wall-clock execution time (§69).",
            "Swap fidelity model: Werner parameters multiply "
            "(documented in SCIENTIFIC_MODELS.md).",
        ],
    )


def run_vqe_experiment(config: dict, seed: int) -> dict:
    from ..optimization import h2_hamiltonian, transverse_field_ising, two_local_h2_ansatz
    from ..circuits.model import Circuit
    # ROOT-CAUSE FIX (found by the process-isolation battery): run_vqe lives
    # in app.optimization.variational; the previous `from .variational import
    # run_vqe` pointed at a nonexistent module, so the "vqe" experiment
    # module could never run at all.
    from ..optimization.variational import run_vqe as _run

    system = config.get("system", "h2")
    if system == "h2":
        bond = float(config.get("bond_length_angstrom", 0.735))
        ham = h2_hamiltonian(bond)

        def ansatz(params):
            return two_local_h2_ansatz(params)
        param_count = 3
        label = f"H2 @{bond} A"
    elif system == "tfim":
        n = int(config.get("n_qubits", 3))
        ham = transverse_field_ising(n)
        def ansatz(params):
            c = Circuit(num_qubits=n)
            k = 0
            for q in range(n + 1):
                pass
            # simple hardware-efficient ansatz: RY layer + CX ring + RY layer
            for q in range(n):
                c.add_gate("RY", [q], params=[float(params[k])]); k += 1
            for q in range(n - 1):
                c.add_gate("CX", [q, q + 1])
            for q in range(n):
                c.add_gate("RY", [q], params=[float(params[k])]); k += 1
            return c
        param_count = 2 * n
        label = f"TFIM {n}q"
    else:
        raise ValueError(f"Unknown VQE system {system!r}")
    res = _run(ham, ansatz, param_count, max_iter=int(config.get("max_iter", 150)), seed=seed)
    metrics = {
        "estimated_energy": res.estimated_energy,
        "exact_energy": res.exact_energy,
        "error": res.error,
        "iterations": len(res.energy_history),
        "system": label,
    }
    return make_result_document(
        "vqe", metrics,
        artifacts={"energy_history": res.energy_history,
                   "final_params": res.final_params},
        notes=[*res.notes, "Hybrid SPSA + coordinate-descent polish."],
    )


def run_grover_study(config: dict, seed: int) -> dict:
    from ..algorithms import run_grover

    n_qubits = int(config.get("n_qubits", 4))
    marked = int(config.get("marked_index", 0))
    shots = int(config.get("shots", 2048))
    noisy_flag = bool(config.get("compare_noisy", False))
    ideal = run_grover(n_qubits, marked, shots=shots, seed=seed)
    metrics = {
        "marked_state": ideal.marked_state,
        "success_probability": ideal.success_probability_estimate,
        "optimal_iterations": ideal.optimal_iterations,
        "per_iteration_probabilities": ideal.per_iteration_probabilities,
    }
    artifacts = {"counts_ideal": ideal.counts}
    notes = ["Noiseless statevector Grover with dense MCZ oracle (<=10 qubits)."]
    if noisy_flag:
        from ..circuits import simulate as sim
        from ..algorithms import build_grover_circuit
        from ..noise.models import preset_depolarizing_1q

        c, iters = build_grover_circuit(n_qubits, marked, iterations=ideal.optimal_iterations)
        noisy_res = sim(c, seed=seed + 7, shots=min(shots, 4096),
                        noise_model=preset_depolarizing_1q(0.002))
        total = sum(noisy_res.counts.values()) or 1
        metrics["noisy_success_probability"] = noisy_res.counts.get(ideal.marked_state, 0) / total
        artifacts["counts_noisy"] = noisy_res.counts
        notes.append("Noisy variant uses depolarizing preset p=0.001 (2-qubit x10).")
    return make_result_document("grover_study", metrics, artifacts={"counts": artifacts.get("counts_ideal", {})}, notes=notes)


def run_purification_study(config: dict, seed: int) -> dict:
    """Purification protocol comparison across input fidelities/rounds."""
    from ..network.purification import compare_protocols, purify_to_target

    initial = float(config.get("initial_fidelity", 0.8))
    if not (0.5 <= initial <= 1.0):
        raise ValueError("initial_fidelity must be within [0.5, 1].")
    max_rounds = int(config.get("max_rounds", 4))
    target = float(config.get("target_fidelity", 0.95))
    rng = np.random.default_rng(seed)
    schedules = {}
    for proto in ("BBPSSW", "DEJMPS"):
        res = purify_to_target(proto, initial, target, max_rounds=max_rounds, rng=rng)
        schedules[proto] = {
            "achieved": res.achieved,
            "final_fidelity": round(res.final_fidelity, 6) if res.final_fidelity else None,
            "rounds_succeeded": res.rounds_succeeded,
            "pairs_consumed": res.pairs_consumed,
        }
    metrics = {
        "initial_fidelity": initial,
        "target_fidelity": target,
        "max_rounds": max_rounds,
        "bbpsw_achieved": schedules["BBPSSW"]["achieved"],
        "dejmps_achieved": schedules["DEJMPS"]["achieved"],
    }
    return make_result_document(
        "purification_study", metrics,
        artifacts={"schedules": schedules,
                   "analytic_trajectories": compare_protocols(initial, max_rounds=max_rounds)},
        notes=[
            "BBPSSW/DEJMPS exact recurrences on Werner-form inputs; success "
            "sampled per round with the run seed; failures consume both pairs.",
        ],
    )


def run_repeater_study_exp(config: dict, seed: int) -> dict:
    from ..network.repeaters import run_repeater_study

    distances = [float(d) for d in config.get("distances_km", [50, 150, 300])]
    if not distances or len(distances) > 8:
        raise ValueError("Provide 1..8 distances.")
    levels = config.get("levels", ["L0_direct", "L1_swapping", "L2_swap_purify"])
    study = run_repeater_study(
        distances, levels=[str(x) for x in levels],
        requests_per_point=int(config.get("requests_per_point", 12)),
        seed=seed)
    metrics = {
        "points": len(study["table"]),
        "levels": study["levels"],
        "distances_km": study["distances_km"],
    }
    return make_result_document(
        "repeater_study", metrics,
        artifacts={"table": study["table"]}, notes=study["notes"],
    )


def run_network_bb84_exp(config: dict, seed: int) -> dict:
    from ..protocols.network_bb84 import run_bb84_distance_sweep, run_network_bb84

    if config.get("mode") == "distance_sweep":
        sweep = run_bb84_distance_sweep(
            [float(d) for d in config.get("distances_km", [10, 50, 100, 200])],
            n_signals=int(config.get("n_signals", 2048)),
            eve_intercept_probability=float(config.get("eve_intercept_probability", 0.0)),
            seed=seed)
        qbers = [r["qber"] for r in sweep["table"] if r["qber"] is not None]
        metrics = {
            "mode": "distance_sweep",
            "qber_no_eve_max": max(qbers) if qbers else None,
            "rows": len(sweep["table"]),
        }
        return make_result_document("network_bb84", metrics,
                                    artifacts={"table": sweep["table"]},
                                    notes=sweep["notes"])
    from ..protocols.network_bb84 import run_network_bb84

    r = run_network_bb84(
        int(config.get("n_signals", 4096)),
        distance_km=float(config.get("distance_km", 25)),
        attenuation_db_per_km=float(config.get("attenuation_db_per_km", 0.2)),
        detector_efficiency=float(config.get("detector_efficiency", 0.9)),
        dark_count_probability=float(config.get("dark_count_probability", 0.0)),
        eve_intercept_probability=float(config.get("eve_intercept_probability", 0.0)),
        sample_fraction=float(config.get("sample_fraction", 0.5)),
        seed=seed)
    metrics = {
        "distance_km": r.distance_km,
        "detected": r.detected,
        "lost": r.lost,
        "sifted_bits": r.sifted_bits,
        "qber": r.qber,
        "errors_in_sampled": r.errors_in_sampled,
        "sample_size": r.sample_size,
        "key_rate_fraction_estimate": r.key_rate_fraction_estimate,
    }
    return make_result_document("network_bb84", metrics, notes=r.notes)


# ---------------------------------------------------------------------------
# Distributed circuit execution
# ---------------------------------------------------------------------------

def run_distributed_circuit(config: dict, seed: int) -> dict:
    """Execute a distributed quantum circuit using the genuine remote-CNOT protocol.

    The configuration should contain:
    - circuit: quantumlab.circuit v1 document
    - protocol: "single_ebit" | "double_teleport"
    - qubit_to_node: optional explicit dict mapping logical qubit index to node
      name. If omitted, qubits are auto-assigned across ``num_nodes`` using the
      deterministic minimise-cross-node heuristic (the effective assignment is
      recorded in reproducibility.assignment).
    - num_nodes: number of compute nodes (used when no explicit mapping given)
    - topology: optional network topology (nodes + links) for real network modeling
    - network_config: optional network simulation config
    - fallback: "error" | "centralized" (default "error")
    - ebit_noise: "ideal" | "network_fidelity" | "fixed" (default "ideal").
      "network_fidelity" consumes each NetworkBridge grant's fidelity as the
      Werner fidelity of the ebit; "fixed" uses ``ebit_noise_fidelity``.
    - ebit_noise_fidelity: Werner fidelity in [0,1], only for ebit_noise="fixed"
    """
    from ..distributed import DistributedExecutor, DistributedConfig, topology_from_nodes_links
    from ..network import NetworkConfig
    from ..circuits import circuit_from_dict

    circuit = circuit_from_dict(config["circuit"])

    q2n = {int(k): v for k, v in (config.get("qubit_to_node") or {}).items()}
    if not q2n and not config.get("num_nodes"):
        raise ValueError(
            "Either an explicit qubit_to_node mapping or num_nodes (>=2) is "
            "required for a distributed circuit."
        )
    num_nodes = int(config.get("num_nodes", 2))
    if num_nodes < 2:
        raise ValueError("num_nodes must be >= 2 for a distributed circuit.")

    protocol = config.get("protocol", "single_ebit")
    fallback = config.get("fallback", "error")
    # Entanglement-resource noise (AD-012): absent -> ideal (legacy behavior).
    ebit_noise = config.get("ebit_noise", "ideal")
    ebit_noise_fidelity = config.get("ebit_noise_fidelity")

    # Build topology if provided
    topology = None
    if config.get("topology"):
        topo_nodes = [{"name": n["name"], "type": n.get("type", "end"),
                       "memory_slots": n.get("memory_slots", 4)} for n in config["topology"]["nodes"]]
        topo_links = [
            {"source": l["source"], "destination": l["destination"],
             "distance_km": l.get("distance_km", 10),
             "base_fidelity": l.get("base_fidelity", 0.95),
             "detector_efficiency": l.get("detector_efficiency", 1.0)}
            for l in config["topology"]["links"]
        ]
        topology = topology_from_nodes_links(topo_nodes, topo_links)

    # Build network config if provided
    network_config = None
    if config.get("network_config"):
        network_config = NetworkConfig(**config["network_config"])

    cfg = DistributedConfig(
        protocol=protocol,
        seed=seed,
        qubit_to_node=q2n or None,
        num_nodes=num_nodes,
        topology=topology,
        network_config=network_config,
        fallback=fallback,
        ebit_noise=ebit_noise,
        ebit_noise_fidelity=ebit_noise_fidelity,
    )

    executor = DistributedExecutor(cfg)
    dresult = executor.execute(circuit)
    dist = dresult.to_dict()

    # A distributed failure is a FAILED run, never a fabricated success.
    if dist["status"] != "success":
        raise ValueError(
            "Distributed execution failed: " + ("; ".join(dist.get("errors") or ["unknown error"]))
        )

    metrics = {
        "status": dist["status"],
        "protocol": dist["protocol"],
        "qubit_count": dist["qubit_count"],
        "node_count": dist["node_count"],
        "local_gate_count": dist["local_gate_count"],
        "remote_gate_count": dist["remote_gate_count"],
        "remote_cnot_count": dist["remote_cnot_count"],
        "ebit_consumption": dist["ebit_consumption"],
        "classical_message_count": dist["classical_message_count"],
        "communication_cost": dist["communication_cost"],
    }
    eq = dist.get("equivalence")
    if eq:
        metrics["equivalence_fidelity"] = eq["fidelity"]
        metrics["equivalence_passed"] = eq["passed"]
    if dist.get("partition_metrics"):
        metrics.update({
            "partition_objective": dist["partition_metrics"]["objective"],
            "cross_node_gate_count": dist["partition_metrics"]["cross_node_gate_count"],
        })
    seeded = dist.get("reproducibility", {}).get("seed")
    if seeded is not None:
        metrics["effective_seed"] = seeded
    metrics["ebit_noise"] = (dist.get("reproducibility") or {}).get("ebit_noise", "ideal")
    applied_fids = [
        r.get("ebit_fidelity_applied")
        for r in dist.get("remote_operations", [])
        if r.get("ebit_fidelity_applied") is not None
    ]
    if applied_fids:
        metrics["mean_ebit_fidelity"] = round(sum(applied_fids) / len(applied_fids), 6)

    modeled_latency_ms = None
    for g in dist.get("entanglement_operations", []):
        if g.get("latency_ns") is not None:
            modeled_latency_ms = max(modeled_latency_ms or 0.0, g["latency_ns"] / 1e6)
    if modeled_latency_ms is not None:
        metrics["modeled_network_latency_ms"] = round(modeled_latency_ms, 6)

    notes = list(dist.get("notes", []))
    notes.append(
        "Full distributed result document (quantumlab.distributed-result v1) is "
        "available in artifacts.distributed_result."
    )
    notes.append(
        "Simulator wall-clock runtime is NOT physical hardware performance; modelled "
        "network latency is reported separately in metrics.modeled_network_latency_ms."
    )
    for w in dist.get("warnings", []):
        notes.append(f"warning: {w}")

    return make_result_document(
        "distributed_circuit", metrics,
        summary={
            "equivalence": eq,
            "partition_metrics": dist.get("partition_metrics"),
            "reproducibility": dist.get("reproducibility"),
        },
        artifacts={
            "distributed_result": dist,
            "remote_operations": dist.get("remote_operations", []),
            "entanglement_operations": dist.get("entanglement_operations", []),
            "classical_messages": dist.get("classical_messages", []),
            "output_probabilities": (dist.get("output_state") or {}).get("probabilities", {}),
        },
        notes=notes,
    )


def run_repeated_round_surface_code(config: dict, seed: int) -> dict:
    """Monte Carlo repeated-round (space-time) surface-code decoding study.

    Configuration:
    - distances: odd distances, e.g. [3, 5]
    - rounds: number of syndrome-measurement rounds
    - p_data: data-qubit depolarizing probability (float)
    - p_measurement: per-round measurement-flip probability (float)
    - trials_per_point: Monte Carlo trials per (d, p) point
    - error_model: "depolarizing" | "x_only" | "z_only"
    """
    from ..qec import simulate_repeated

    distances = [int(d) for d in config.get("distances", [3, 5])]
    if not distances:
        raise ValueError("distances must be a non-empty list.")
    rounds = int(config.get("rounds", 4))
    if rounds < 1:
        raise ValueError("rounds must be >= 1.")
    p_data = float(config.get("p_data", 0.03))
    p_measurement = float(config.get("p_measurement", 0.03))
    if not (0 <= p_data <= 1) or not (0 <= p_measurement <= 1):
        raise ValueError("p_data and p_measurement must be within [0,1].")
    trials = int(config.get("trials_per_point", 2000))
    if trials <= 0:
        raise ValueError("trials_per_point must be positive.")
    error_model = config.get("error_model", "depolarizing")

    table = []
    for di, d in enumerate(distances):
        point_seed = seed + 1000 + di * 7919
        res = simulate_repeated(d, rounds, p_data, p_measurement,
                                trials=trials, seed=point_seed,
                                error_model=error_model)
        table.append({
            "d": res["d"], "rounds": res["rounds"], "p_data": res["p_data"],
            "p_measurement": res["p_measurement"],
            "logical_error_rate": res["logical_error_rate"],
            "logical_failures": res["logical_failures"],
            "ci95_low": res["ci95"][0], "ci95_high": res["ci95"][1],
            "trials": res["trials"], "seed": res["seed"],
        })
    metrics = {
        "distances": distances, "rounds": rounds, "p_data": p_data,
        "p_measurement": p_measurement, "error_model": error_model,
        "points": len(table),
        "trials_per_point": trials,
        "trials_total": sum(t["trials"] for t in table),
        "lowest_logical_error_rate": min(
            (t["logical_error_rate"] for t in table), default=None),
    }
    notes = [
        "Repeated-round (space-time) MWPM decoding of the rotated planar "
        "surface code under the PHENOMENOLOGICAL model: per-slot persistent "
        "depolarizing data noise and per-round measurement flips (rounds "
        "1..R-1; the final round is ideal).",
        "p_L is the logical error rate (failures/trials, Wilson 95% "
        "interval); distinct from p_data and p_measurement.",
        "Perfect stabilizer circuits (no circuit-level noise); no threshold "
        "is claimed from this bounded study.",
    ]
    return make_result_document(
        "repeated_round_surface_code", metrics,
        artifacts={"table": table}, notes=notes)


def run_surface_code_circuit_level(config: dict, seed: int) -> dict:
    """Circuit-level surface-code Monte Carlo decoding study.

    Config: distances (odd, e.g. [3,5]), rounds, p_gate, p_readout, p_reset,
    p_prep, trials_per_point.
    """
    from ..qec import simulate_circuit_level_mc

    distances = [int(d) for d in config.get("distances", [3, 5])]
    if not distances:
        raise ValueError("distances must be a non-empty list.")
    rounds = int(config.get("rounds", 4))
    p_gate = float(config.get("p_gate", 0.005))
    p_readout = float(config.get("p_readout", 0.005))
    p_reset = float(config.get("p_reset", 0.003))
    p_prep = float(config.get("p_prep", 0.003))
    trials = int(config.get("trials_per_point", 2000))
    if trials <= 0:
        raise ValueError("trials_per_point must be positive.")
    table = []
    for di, d in enumerate(distances):
        point_seed = seed + 1000 + di * 7919
        res = simulate_circuit_level_mc(
            d, rounds, p_gate, p_readout, p_reset, p_prep,
            trials=trials, seed=point_seed)
        table.append({
            "d": res["d"], "rounds": res["rounds"], "p_gate": res["p_gate"],
            "p_readout": res["p_readout"], "p_reset": res["p_reset"],
            "p_prep": res["p_prep"],
            "logical_error_rate": res["logical_error_rate"],
            "logical_failures": res["logical_failures"],
            "ci95_low": res["ci95"][0], "ci95_high": res["ci95"][1],
            "hook_error_events": res.get("hook_error_events"),
            "trials": res["trials"], "seed": res["seed"],
        })
    metrics = {
        "distances": distances, "rounds": rounds, "p_gate": p_gate,
        "p_readout": p_readout, "p_reset": p_reset, "p_prep": p_prep,
        "points": len(table), "trials_per_point": trials,
        "trials_total": sum(t["trials"] for t in table),
        "lowest_logical_error_rate": min(
            (t["logical_error_rate"] for t in table), default=None),
    }
    notes = [
        "Circuit-level surface-code decoding: explicit ancilla stabilizer "
        "circuits (reset/prep/CNOT/measure) with gate, readout, reset, and "
        "preparation noise, decoded by the repeated-round MWPM. Ideal final "
        "round readout; single-qubit gates ideal.",
        "p_L is the logical error rate (Wilson 95% interval); distinct from "
        "the four physical noise probabilities.",
        "Correlated hook errors from ancilla faults are modeled; the naive "
        "schedule does not exhibit distance suppression at d=3 (documented). "
        "No hardware or threshold claims.",
    ]
    return make_result_document(
        "surface_code_circuit_level", metrics,
        artifacts={"table": table}, notes=notes)


def run_surface_code_fault_aware(config: dict, seed: int) -> dict:
    """Fault-aware + circuit-derived comparison study (AD-018, milestone 12).

    Runs two complementary experiments at the same (d, R, noise) points:
      (a) phenomenological repeated-round MWPM (the LEGACY decoder;
          unchanged, AD-016, AD-017);
      (b) the same noise history fed to the same decoder (logical-error
          classification is preserved) WITH the circuit-derived graph
          coverage reported as structural metadata (the graph itself is
          NOT the decoder — directrive §41, §42).

    The fault-catalogue optimizer is run for every distance and its
    schedule selection is reported. The naive schedule is preserved as
    a separate reference. A structural graph-coverage report is
    produced for each distance, including the exact-pairwise coverage
    ratio and the multi-event-mechanism excluded mass.
    """
    from ..qec import (
        RotatedSurfaceCode, simulate_circuit_derived_mc,
    )
    from ..qec.fault_catalogue import compare_naive_vs_optimized
    from ..qec.circuit_graph_decoder import build_circuit_graph
    distances = [int(d) for d in config.get("distances", [3, 5])]
    if not distances:
        raise ValueError("distances must be a non-empty list.")
    rounds = int(config.get("rounds", 4))
    if rounds < 1:
        raise ValueError("rounds must be >= 1.")
    p_gate = float(config.get("p_gate", 0.005))
    p_readout = float(config.get("p_readout", 0.005))
    p_reset = float(config.get("p_reset", 0.003))
    p_prep = float(config.get("p_prep", 0.003))
    trials = int(config.get("trials_per_point", 2000))
    if trials <= 0:
        raise ValueError("trials_per_point must be positive.")
    table: list[dict] = []
    schedule_reports: list[dict] = {}
    for di, d in enumerate(distances):
        point_seed = seed + 1000 + di * 7919
        res = simulate_circuit_derived_mc(
            d, rounds, p_gate, p_readout, p_reset, p_prep,
            trials=trials, seed=point_seed)
        code = RotatedSurfaceCode.build(d)
        sched_cmp = compare_naive_vs_optimized(code, exhaustive=False)
        graph = build_circuit_graph(
            code, rounds, p_gate, p_readout, p_reset, p_prep)
        schedule_reports[str(d)] = {
            "naive_total_hooks": sched_cmp["naive_total_hooks"],
            "optimized_total_hooks": sched_cmp["optimized_total_hooks"],
            "stabilizers_with_changed_schedule":
                sched_cmp["stabilizers_with_changed_schedule"],
            "stabilizers_total": len(sched_cmp["per_stabilizer"]),
            "graph_coverage_ratio": graph.coverage.coverage_ratio,
            "graph_excluded_ratio": graph.coverage.excluded_ratio,
            "graph_n_vertices": len(graph.vertex_index),
            "graph_n_edges": len(graph.pair_weights),
            "graph_n_exits": len(graph.exit_weights),
        }
        table.append({
            "d": res["d"], "rounds": res["rounds"],
            "p_gate": res["p_gate"], "p_readout": res["p_readout"],
            "p_reset": res["p_reset"], "p_prep": res["p_prep"],
            "logical_error_rate": res["logical_error_rate"],
            "logical_failures": res["logical_failures"],
            "ci95_low": res["ci95"][0], "ci95_high": res["ci95"][1],
            "graph_coverage_ratio": graph.coverage.coverage_ratio,
            "graph_excluded_ratio": graph.coverage.excluded_ratio,
            "trials": res["trials"], "seed": res["seed"],
        })
    metrics = {
        "distances": distances, "rounds": rounds, "p_gate": p_gate,
        "p_readout": p_readout, "p_reset": p_reset, "p_prep": p_prep,
        "points": len(table), "trials_per_point": trials,
        "trials_total": sum(t["trials"] for t in table),
        "lowest_logical_error_rate": min(
            (t["logical_error_rate"] for t in table), default=None),
        "schedule_reports": schedule_reports,
    }
    notes = [
        "Fault-aware + circuit-derived comparison study. Logical-error "
        "classification uses the EXISTING phenomenological MWPM "
        "(preserved semantics, AD-016/AD-017); the circuit-derived "
        "graph is reported as structural metadata only — the graph "
        "is the deterministic single-fault-mechanism summary, not a "
        "replacement decoder (directive §41, §42).",
        "Schedule analysis: under the H-CNOTs-H stabilizer-measurement "
        "circuit, the schedule is provably degenerate (every permutation "
        "of a stabilizer's CNOT support produces the same risk profile); "
        "the optimizer therefore selects the naive schedule as optimal.",
        "Graph coverage: the exact pairwise-MWPM fraction of the "
        "single-fault probability mass; the remainder is multi-event "
        "correlations, reported as graph_excluded_ratio (Approach A).",
        "p_L is the logical error rate (Wilson 95% interval); distinct "
        "from the four physical noise probabilities. No threshold or "
        "hardware claims.",
    ]
    return make_result_document(
        "surface_code_fault_aware", metrics,
        artifacts={"table": table}, notes=notes)


def run_surface_code_mwpm(config: dict, seed: int) -> dict:
    """Monte Carlo threshold-style study: rotated planar surface code decoded
    by exact MWPM (code capacity, perfect syndrome).

    Configuration:
    - distances: list of odd distances, e.g. [3, 5, 7]
    - physical_error_permille: physical error rates in permille (e.g. [10, 30, 50])
    - trials_per_point: Monte Carlo trials per (d, p) point
    - error_model: "depolarizing" | "x_only" | "z_only"
    """
    from ..qec import sweep_rotated_surface_code

    distances = [int(d) for d in config.get("distances", [3, 5])]
    if not distances:
        raise ValueError("distances must be a non-empty list.")
    rates = [float(pm) / 1000.0
             for pm in config.get("physical_error_permille", [10, 30, 50])]
    if not rates:
        raise ValueError("physical_error_permille must be a non-empty list.")
    trials = int(config.get("trials_per_point", 2000))
    if trials <= 0:
        raise ValueError("trials_per_point must be positive.")
    error_model = config.get("error_model", "depolarizing")

    points = sweep_rotated_surface_code(
        distances, rates, trials=trials, seed=seed, error_model=error_model)
    table = [
        {
            "d": pt["d"],
            "physical_error_rate": pt["physical_error_rate"],
            "logical_error_rate": pt["logical_error_rate"],
            "logical_failures": pt["logical_failures"],
            "ci95_low": pt["ci95"][0],
            "ci95_high": pt["ci95"][1],
            "trials": pt["trials"],
            "seed": pt["seed"],
        }
        for pt in points
    ]
    metrics = {
        "distances": distances,
        "error_model": error_model,
        "physical_error_rates": rates,
        "points": len(table),
        "trials_per_point": trials,
        "trials_total": sum(t["trials"] for t in table),
        "lowest_logical_error_rate": min(
            (t["logical_error_rate"] for t in table), default=None),
    }
    notes = [
        "Rotated planar surface code, exact MWPM decoder, code-capacity "
        "model with PERFECT syndrome measurement (single round).",
        "p_L is the logical error rate (failures/trials, Wilson 95% "
        "interval); it is distinct from the physical error rate p.",
        "This bounded sweep is evidence of behaviour, not a threshold "
        "determination; no threshold value is claimed.",
    ]
    return make_result_document(
        "surface_code_mwpm", metrics,
        artifacts={"table": table},
        notes=notes,
    )


def run_process_probe(config: dict, seed: int) -> dict:
    """Diagnostic experiment for the process-isolation milestone (AD-014).

    Config-driven actions used ONLY by the worker-lifecycle test suite and
    operational verification; it is a registered experiment so spawned
    workers resolve it through the CANONICAL registry (§64 - no second
    dispatch table, no experiment-specific worker logic).

    Actions:
      "succeed"        - return a small valid document (default)
      "fail"           - raise an intentional exception
      "hard_exit"      - exit the process abnormally (os._exit(70))
      "slow"           - sleep config["seconds"] (timeout/cancel tests)
      "unserializable" - return a document that cannot cross the pickling
                         boundary (result-transport failure, §47)
    """
    import os
    import time as _time

    action = str(config.get("action", "succeed"))
    if action == "fail":
        raise RuntimeError("intentional probe failure (process_probe)")
    if action == "hard_exit":
        # Test-only abnormal termination path (directive §23); never used by
        # production experiments.
        os._exit(70)
    if action == "slow":
        _time.sleep(float(config.get("seconds", 2.0)))
    result: dict = {"action": action, "note": "process probe document"}
    if action == "unserializable":
        # A lambda cannot be pickled: the child cannot transport its result.
        result["payload"] = lambda: None
    return make_result_document("process_probe", {"action": action},
                                summary=result)


RUNNER_REGISTRY = {
    "circuit_shots": run_circuit_shots,
    "qec_sweep": run_qec_sweep,
    "bb84_study": run_bb84_study,
    "network_study": run_network_study,
    "vqe": run_vqe_experiment,
    "grover_study": run_grover_study,
    "purification_study": run_purification_study,
    "repeater_study": run_repeater_study_exp,
    "network_bb84": run_network_bb84_exp,
    "distributed_circuit": run_distributed_circuit,
    "surface_code_mwpm": run_surface_code_mwpm,
    "repeated_round_surface_code": run_repeated_round_surface_code,
    "surface_code_circuit_level": run_surface_code_circuit_level,
    "surface_code_fault_aware": run_surface_code_fault_aware,
    "process_probe": run_process_probe,
}


# ---------------------------------------------------------------------------
# Execution of one run (resolved config -> result document)
# ---------------------------------------------------------------------------

def execute_run(module: str, resolved_config: dict, seed: int,
                progress_callback=None) -> dict:
    """Execute a single run; raises on invalid configs (never fabricates)."""
    runner = RUNNER_REGISTRY[module]
    if progress_callback:
        progress_callback(0.05, "starting")
    doc = runner(resolved_config, seed)
    if progress_callback:
        progress_callback(1.0, "completed")
    return doc


def expand_sweep(spec: ExperimentSpec) -> list[tuple[str, dict]]:
    """Cartesian expansion of sweep parameters into labeled resolved configs.

    A single-parameter sweep produces len(values) runs; multi-parameter sweeps
    produce the full grid (bounded).
    """
    if not spec.sweep:
        return [("baseline", dict(spec.config))]
    combos: list[tuple[str, dict]] = []
    def rec(idx: int, acc: dict, labels: list[str]):
        if idx == len(spec.sweep):
            combos.append(("|".join(labels), dict(acc)))
            return
        if len(combos) > 256:
            raise ValueError("Sweep grid exceeds 256 runs; reduce the grid size.")
        sp = spec.sweep[idx]
        for v in sp.values:
            acc2 = dict(acc)
            acc2[sp.name] = v
            rec(idx + 1, acc2, labels + [f"{sp.name}={v:g}"])
    # The base configuration is the seed for every combo; each sweep value is
    # layered on top of it (swept keys override). Without this, sweep runs
    # would silently lose the experiment's base configuration.
    rec(0, dict(spec.config), [])
    return combos
