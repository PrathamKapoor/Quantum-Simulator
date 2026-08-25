"""Repeater strategy framework (directive §22).

Levels (honest scope):
    L0 direct transmission      — one long link, no repeaters
    L1 swapping                  — repeater chain, Werner-model swaps
    L2 swapping + purification   — chain plus DEJMPS post-generation
                                   purification when duplicate pairs appear

Each study runs the SAME request workload across strategies at several total
distances and reports success probability (Wilson CI), mean end-to-end
fidelity, mean service latency, and entanglement resource consumption.
These are simulation comparisons on model profiles — not claims about real
deployments.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..quantum.states import QuantumCoreError
from .engine import NetworkConfig, NetworkEngine
from .topology import Topology, NetworkNode


LEVELS = {
    "L0_direct": {"repeaters": 0, "purification": None},
    "L1_swapping": {"repeaters": "auto", "purification": None},
    "L2_swap_purify": {"repeaters": "auto", "purification": "DEJMPS"},
}


def _build_chain(total_distance_km: float, n_repeaters: int) -> tuple[Topology, list[str]]:
    topo = Topology()
    names = ["A"] + [f"R{i}" for i in range(1, n_repeaters + 1)] + ["B"]
    for i, name in enumerate(names):
        topo.add_node(NetworkNode(
            name=name,
            node_type="end" if i in (0, len(names) - 1) else "repeater",
            memory_slots=8,
        ))
    seg = total_distance_km / (n_repeaters + 1)
    for i in range(len(names) - 1):
        topo.add_quantum_link(names[i], names[i + 1], distance_km=seg,
                              base_fidelity=0.97)
    return topo, names


@dataclass
class RepeaterStudyPoint:
    level: str
    total_distance_km: float
    requests: int
    successes: int
    success_probability: float
    ci95: tuple[float, float]
    mean_fidelity: float | None
    mean_service_ms: float | None
    mean_pairs_consumed_per_success: float | None


def run_repeater_point(
    level: str,
    total_distance_km: float,
    *,
    requests: int,
    seed: int,
    sim_time_ms: float = 800.0,
) -> RepeaterStudyPoint:
    """Run one (level, distance) point with `requests` competing requests."""
    if level not in LEVELS:
        raise ValueError(f"Unknown repeater level {level!r}; use {sorted(LEVELS)}.")
    cfg_level = LEVELS[level]
    n_rep = cfg_level["repeaters"]
    if n_rep == "auto":
        # ~25 km spacing, bounded to keep event counts sane
        n_rep = int(np.clip(round(total_distance_km / 25.0) - 1, 0, 8))
    topo, names = _build_chain(total_distance_km, int(n_rep))
    config_kwargs = dict(classical_latency_mode="realistic")
    if cfg_level["purification"]:
        config_kwargs["purification_protocol"] = cfg_level["purification"]
    engine = NetworkEngine(topo, NetworkConfig(**config_kwargs), seed=seed)
    baseline_pairs = engine.resources.pairs._next_id
    for _ in range(requests):
        engine.submit_request(names[0], names[-1])
    result = engine.run(until_ns=sim_time_ms * 1e6)
    successes = [o for o in result.outcomes if o.success]
    lo, hi = wilson_interval(len(successes), max(requests, 1))
    fids = [o.fidelity for o in successes if o.fidelity is not None]
    services = [o.service_ns for o in successes if o.service_ns is not None]
    return RepeaterStudyPoint(
        level=level,
        total_distance_km=total_distance_km,
        requests=requests,
        successes=len(successes),
        success_probability=len(successes) / max(requests, 1),
        ci95=(lo, hi),
        mean_fidelity=(sum(fids) / len(fids)) if fids else None,
        mean_service_ms=(sum(services) / len(services) / 1e6) if services else None,
        mean_pairs_consumed_per_success=(
            result.stats["links_generated"] / len(successes)) if successes else None,
    )


def wilson_interval(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion (kept local to avoid a
    circular import with app.qec)."""
    if trials <= 0:
        raise ValueError("trials must be positive.")
    phat = successes / trials
    denom = 1 + z * z / trials
    center = (phat + z * z / (2 * trials)) / denom
    half = z * np.sqrt(phat * (1 - phat) / trials + z * z / (4 * trials * trials)) / denom
    return float(max(0.0, center - half)), float(min(1.0, center + half))


def run_repeater_study(
    distances_km: list[float],
    *,
    levels: list[str] | None = None,
    requests_per_point: int = 20,
    seed: int = 100,
) -> dict:
    """Full comparison grid across levels x distances. Each point gets an
    independent deterministic seed."""
    levels = levels or list(LEVELS)
    for lvl in levels:
        if lvl not in LEVELS:
            raise ValueError(f"Unknown level {lvl!r}.")
    table = []
    for d_idx, d in enumerate(distances_km):
        for lvl in levels:
            pt = run_repeater_point(
                lvl, float(d), requests=requests_per_point,
                seed=seed + 7919 * d_idx + hash(lvl) % 997)
            table.append({
                "level": pt.level,
                "total_distance_km": pt.total_distance_km,
                "successes": pt.successes,
                "requests": pt.requests,
                "success_probability": round(pt.success_probability, 6),
                "ci95_low": round(pt.ci95[0], 6),
                "ci95_high": round(pt.ci95[1], 6),
                "mean_fidelity": round(pt.mean_fidelity, 6) if pt.mean_fidelity else None,
                "mean_service_ms": round(pt.mean_service_ms, 4) if pt.mean_service_ms else None,
                "pairs_generated_per_success": (
                    round(pt.mean_pairs_consumed_per_success, 3)
                    if pt.mean_pairs_consumed_per_success else None),
            })
    return {
        "levels": levels,
        "distances_km": distances_km,
        "table": table,
        "notes": [
            "MODEL COMPARISON: Werner-form links, idealized swap/purification "
            "operations, ~25 km repeater spacing heuristic.",
            "Wilson score 95% CIs per point; sample counts included per row.",
            "Not a claim about real hardware performance (§124, §324).",
        ],
    }
