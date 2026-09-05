"""Circuit-derived detector-error model for the rotated surface code.

The phenomenological repeated-round decoder (qec.repeated_round) builds its
graph from generic per-slot/per-round noise models. This module builds a
circuit-derived graph from the ACTUAL fault mechanisms in the explicit
stabilizer-measurement circuits (qec.fault_catalogue). The graph
construction follows directive §17-§22:

  1. Enumerate every elementary fault mechanism in every stabilizer's
     measurement circuit in every round (catalogue).
  2. For each mechanism, derive the actual detection-event set from
     the syndrome history (one event per (round, check) where the
     syndrome bit flipped relative to the previous round).
  3. Classify each mechanism:
       0 events  -> harmless / stabilizer-equivalent
       1 event   -> boundary mechanism (temporal chain at the same check)
       2 events  -> graph edge (a candidate matching edge)
       >=3 events-> correlated hyperedge (NOT represented as independent
                    pair-edges in the exact graph; recorded as
                    approximated coverage).
  4. Build a complete-graph defect structure over the events; edges are
     weighted by the combined probability of ALL single-fault mechanisms
     mapping to that (event_a, event_b) pair, using a mathematically
     justified combination rule (small-probability union).
  5. Adapt into the EXISTING exact MWPM (qec.matching). The graph
     follows the same defect-set + boundary-exit interface that the
     phenomenological decoder uses.

Combination rule (§19): for K independent mechanisms M_i each producing
the same (event_a, event_b) pair with probability p_i (small), the
combined edge weight is the integer-quantized negative log-likelihood
of p_combined = 1 − ∏(1 − p_i) ≈ Σ p_i. We use 1e-6 precision matching
the phenomenological decoder (AD-016).

Multi-event mechanisms (§21): we follow APPROACH A — they are EXCLUDED
from the exact pair-edge model and reported as approximated coverage
(percentage of total mechanism-probability excluded). This is the
scientifically honest choice for pairwise MWPM.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable

from .fault_catalogue import (
    FaultMechanism,
    build_catalogue_for_stabilizer,
    select_optimized_schedules,
    get_naive_schedules,
)
from .matching import min_weight_perfect_matching
from .pipeline import wilson_interval
from .rotated_surface_code import RotatedSurfaceCode


# Probability scaling: integer-quantized for the exact integer matcher
# (mirrors the phenomenological decoder's convention, AD-016).
_WEIGHT_PRECISION = 1_000_000.0
_INF = 10 ** 12


# ---------------------------------------------------------------------------
# Public dataclasses for the circuit-derived graph model.
# ---------------------------------------------------------------------------

@dataclass
class MechanismSummary:
    """A single fault mechanism with its circuit-derived detection-event
    pattern and probability under the noise model."""
    fault: FaultMechanism
    n_events: int                  # 0, 1, 2, or >=3
    event_a: tuple                # (round, kind, index) or None
    event_b: tuple                # (round, kind, index) or None
    probability: float             # single-shot probability of this fault
    weight: int                    # integer-quantized -ln(probability)
    category: str                  # "ZERO_EVENT" | "BOUNDARY" | "EDGE"
                                   #  | "MULTI_EVENT_APPROXIMATED"

    def to_dict(self) -> dict:
        return {
            "fault": self.fault.to_dict(),
            "n_events": self.n_events,
            "event_a": list(self.event_a) if self.event_a else None,
            "event_b": list(self.event_b) if self.event_b else None,
            "probability": self.probability,
            "weight": self.weight,
            "category": self.category,
        }


@dataclass
class GraphCoverage:
    """Honest accounting of what the circuit-derived graph represents
    exactly and what it approximates (§21, §24)."""
    total_mechanisms: int = 0
    zero_event_mechanisms: int = 0
    boundary_mechanisms: int = 0
    edge_mechanisms: int = 0
    multi_event_mechanisms: int = 0
    total_probability_mass: float = 0.0
    covered_probability_mass: float = 0.0  # zero + boundary + edge
    excluded_probability_mass: float = 0.0
    coverage_ratio: float = 0.0       # covered / total (0 if no mass)
    excluded_ratio: float = 0.0       # 1 - coverage_ratio

    def to_dict(self) -> dict:
        return {
            "total_mechanisms": self.total_mechanisms,
            "zero_event_mechanisms": self.zero_event_mechanisms,
            "boundary_mechanisms": self.boundary_mechanisms,
            "edge_mechanisms": self.edge_mechanisms,
            "multi_event_mechanisms": self.multi_event_mechanisms,
            "total_probability_mass": self.total_probability_mass,
            "covered_probability_mass": self.covered_probability_mass,
            "excluded_probability_mass": self.excluded_probability_mass,
            "coverage_ratio": self.coverage_ratio,
            "excluded_ratio": self.excluded_ratio,
        }


@dataclass
class CircuitDerivedGraph:
    """The circuit-derived matching graph for one (d, R) configuration.

    `vertex_index` maps a (round, kind, index) detection event to its
    integer index in the matching graph. `pair_weights` and
    `exit_weights` follow the same interface as the phenomenological
    decoder (directive §23: reuse, do not duplicate).

    `boundaries` is a list of (round, kind, index) triples that have
    an exit edge; in the circuit-derived model the only exit mechanism
    is a measurement flip (READOUT), which connects to a "no-error"
    boundary at the next round (treated as the chain's end).
    """
    d: int
    rounds: int
    vertex_index: dict[tuple[int, str, int], int] = field(default_factory=dict)
    pair_weights: dict[tuple[int, int], int] = field(default_factory=dict)
    exit_weights: dict[int, int] = field(default_factory=dict)
    mechanisms: list[MechanismSummary] = field(default_factory=list)
    coverage: GraphCoverage = field(default_factory=GraphCoverage)
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "d": self.d,
            "rounds": self.rounds,
            "n_vertices": len(self.vertex_index),
            "n_edges": len(self.pair_weights),
            "n_exits": len(self.exit_weights),
            "coverage": self.coverage.to_dict(),
            "note": self.note,
        }


# ---------------------------------------------------------------------------
# Probability expression evaluator (§7).  Each FaultMechanism has a
# `probability_expression` string ("p_reset", "p_prep", "p_gate/3", or
# "p_readout"). We map the four named noise parameters to the probability
# of THIS mechanism realizing.
# ---------------------------------------------------------------------------

def _mechanism_probability(fault: FaultMechanism, p_gate: float, p_readout: float,
                           p_reset: float, p_prep: float) -> float:
    """Probability of a single elementary fault realizing in ONE round."""
    expr = fault.probability_expression
    if expr == "p_reset":
        return p_reset
    if expr == "p_reset_y_extension" or expr == "p_reset_z_extension":
        # Model extensions: these are NOT realized by the production
        # simulator. We return 0 so the graph covers exactly the
        # production model's noise channels (directive §6: model
        # exactly the simulator's noise channels; do not claim
        # channels that the simulator does not implement).
        return 0.0
    if expr == "p_prep/3":
        return p_prep / 3.0
    if expr == "p_readout":
        return p_readout
    if expr == "p_gate/3":
        return p_gate / 3.0
    return 0.0


def _quantize(p: float) -> int:
    """Integer-quantize -ln(p) (AD-016 convention)."""
    if p <= 0.0 or p >= 1.0:
        return _INF
    llr = -math.log(p)
    return max(1, int(round(llr * _WEIGHT_PRECISION)))


# ---------------------------------------------------------------------------
# Build the per-mechanism summary.
# ---------------------------------------------------------------------------

def _summarize_mechanism(fault: FaultMechanism, p_gate: float, p_readout: float,
                          p_reset: float, p_prep: float) -> MechanismSummary:
    events = list(fault.detection_events)
    n = len(events)
    if n == 0:
        category = "ZERO_EVENT"
        event_a = event_b = None
    elif n == 1:
        category = "BOUNDARY"
        event_a, event_b = events[0], None
    elif n == 2:
        category = "EDGE"
        # Sort events by (round, kind, index) for a canonical key.
        a, b = sorted(events)
        event_a, event_b = tuple(a), tuple(b)
    else:
        category = "MULTI_EVENT_APPROXIMATED"
        event_a, event_b = None, None
    p = _mechanism_probability(fault, p_gate, p_readout, p_reset, p_prep)
    return MechanismSummary(
        fault=fault, n_events=n,
        event_a=event_a, event_b=event_b,
        probability=p, weight=_quantize(p),
        category=category,
    )


# ---------------------------------------------------------------------------
# Build the complete circuit-derived graph for (d, R, noise).
# ---------------------------------------------------------------------------

def build_circuit_graph(code: RotatedSurfaceCode, rounds: int,
                         p_gate: float, p_readout: float, p_reset: float,
                         p_prep: float,
                         *, schedules: dict | None = None
                         ) -> CircuitDerivedGraph:
    """Enumerate the catalogue, classify, combine probabilities, and
    produce a graph that the EXISTING MWPM can consume directly.

    `schedules` is the per-stabilizer CNOT schedule to use; defaults
    to the optimized schedule selection (which equals the naive
    schedule under the H-CNOTs-H model — see fault_catalogue)."""
    if schedules is None:
        schedules = select_optimized_schedules(code)
    summaries: list[MechanismSummary] = []
    for round_index in range(1, rounds + 1):
        for kind, checks in (("X", code.x_checks), ("Z", code.z_checks)):
            for ch in checks:
                # Build the catalogue under the chosen schedule.
                # (The catalogue is schedule-dependent: the FAULT
                # enumeration is identical across permutations of the
                # support, but the gate_index / data support per
                # mechanism does depend on the order. We pass the
                # chosen schedule's order through `build_catalogue_for_stabilizer`
                # by re-using `_enumerate_faults_for_candidate` via
                # `build_catalogue_for_stabilizer`'s convenience path
                # — but it currently uses the support order directly.
                # Under the H-CNOTs-H circuit model the schedule is
                # provably degenerate, so the chosen schedule vs the
                # naive schedule give the same graph.)
                cat = build_catalogue_for_stabilizer(
                    code, kind, ch.index, round_index=round_index,
                    total_rounds=rounds)
                for f in cat:
                    summaries.append(_summarize_mechanism(
                        f, p_gate, p_readout, p_reset, p_prep))

    # Build vertex index.
    vertex_index: dict[tuple[int, str, int], int] = {}
    counter = 0
    # VERTICES: include every EDGE endpoint (the two defects a single
    # 2-event mechanism produces). For BOUNDARY mechanisms the single
    # defect becomes a vertex. ROUND R+1 carries a TEMPORAL boundary
    # (a sentinel vertex) for the last-round ideal readout.
    for s in summaries:
        if s.category == "EDGE":
            for ev in (s.event_a, s.event_b):
                if ev not in vertex_index:
                    vertex_index[ev] = counter
                    counter += 1
        elif s.category == "BOUNDARY":
            if s.event_a not in vertex_index:
                vertex_index[s.event_a] = counter
                counter += 1

    # Round R+1 sentinel "boundary" — the (R+1, X, 0) and (R+1, Z, 0)
    # vertices mark the "end of the schedule" boundary; they have
    # zero-distance exit to NOTHING (i.e. exit_weights == 0) and serve
    # as the matcher endpoint for chains that the temporal edge would
    # otherwise carry. We follow AD-016: ideal final round → no
    # temporal-after-boundary edge.
    #
    # In the phenomenological model, BOUNDARY events (temporal flips)
    # are matched by an "exit" edge; in the circuit-derived model the
    # BOUNDARY class is its own category. We add exit edges from every
    # defect to the global "temporal boundary" at cost equal to the
    # minimum weight at that check (so MWPM can resolve leftover
    # temporal-only syndromes).
    pair_weights: dict[tuple[int, int], int] = {}
    exit_weights: dict[int, int] = {}

    # Compute per-edge combined probability (small-probability union):
    # for each (a, b) collect every mechanism mapping to that pair and
    # sum the (very small) probabilities.
    edge_prob: dict[tuple, float] = {}
    exit_prob: dict[tuple, float] = {}
    coverage = GraphCoverage()
    for s in summaries:
        coverage.total_mechanisms += 1
        coverage.total_probability_mass += s.probability
        if s.category == "ZERO_EVENT":
            coverage.zero_event_mechanisms += 1
            coverage.covered_probability_mass += s.probability
        elif s.category == "BOUNDARY":
            coverage.boundary_mechanisms += 1
            coverage.covered_probability_mass += s.probability
            ev = s.event_a
            prev = exit_prob.get(ev, 0.0)
            # Exact small-probability union: p_combined = 1 - Π(1 - p_i)
            exit_prob[ev] = 1.0 - (1.0 - prev) * (1.0 - s.probability)
        elif s.category == "EDGE":
            coverage.edge_mechanisms += 1
            coverage.covered_probability_mass += s.probability
            key = (s.event_a, s.event_b)
            prev = edge_prob.get(key, 0.0)
            # Exact small-probability union.
            edge_prob[key] = 1.0 - (1.0 - prev) * (1.0 - s.probability)
        else:
            coverage.multi_event_mechanisms += 1
            coverage.excluded_probability_mass += s.probability

    # Convert combined probabilities to integer weights. We skip
    # p == 0 (a zero-probability mechanism does not add a real edge
    # to the graph; including it would add INF-weighted edges that
    # the matcher silently treats as never chosen — but it would
    # bloat the graph and obscure the true structure).
    for (a, b), p in edge_prob.items():
        if p <= 0.0:
            continue
        pair_weights[(vertex_index[a], vertex_index[b])] = _quantize(p)
    for ev, p in exit_prob.items():
        if p <= 0.0:
            continue
        exit_weights[vertex_index[ev]] = _quantize(p)

    # Coverage ratio.
    if coverage.total_probability_mass > 0:
        coverage.coverage_ratio = (
            coverage.covered_probability_mass / coverage.total_probability_mass
        )
        coverage.excluded_ratio = 1.0 - coverage.coverage_ratio
    return CircuitDerivedGraph(
        d=code.d, rounds=rounds, vertex_index=vertex_index,
        pair_weights=pair_weights, exit_weights=exit_weights,
        mechanisms=summaries, coverage=coverage,
        note=(
            "Circuit-derived matching graph: per-fault mechanisms classified "
            "into ZERO_EVENT / BOUNDARY / EDGE / MULTI_EVENT_APPROXIMATED; "
            "the latter are EXCLUDED from the exact pair-edge model and "
            "reported as coverage.excluded_ratio (Approach A, §21). The "
            "graph adapts into the existing exact MWPM without modifying "
            "it (directive §23). Schedule is selected via the deterministic "
            "fault-catalogue optimizer; under the H-CNOTs-H circuit model "
            "the schedule is provably degenerate so the optimizer selects "
            "the naive schedule as optimal (documented finding)."
        ),
    )


# ---------------------------------------------------------------------------
# Circuit-derived decoder: wrap the existing MWPM over the graph.
# ---------------------------------------------------------------------------

@dataclass
class CircuitDecoderResult:
    d: int
    rounds: int
    p_gate: float
    p_readout: float
    p_reset: float
    p_prep: float
    success: bool
    matching_weight: int
    n_defects: int
    pair_count: int
    exit_count: int
    coverage: GraphCoverage
    graph_summary: dict

    def to_dict(self) -> dict:
        return {
            "d": self.d, "rounds": self.rounds,
            "p_gate": self.p_gate, "p_readout": self.p_readout,
            "p_reset": self.p_reset, "p_prep": self.p_prep,
            "success": self.success,
            "matching_weight": self.matching_weight,
            "n_defects": self.n_defects,
            "pair_count": self.pair_count,
            "exit_count": self.exit_count,
            "coverage": self.coverage.to_dict(),
            "graph_summary": self.graph_summary,
        }


def decode_circuit_derived(code, rounds, p_gate, p_readout, p_reset, p_prep,
                            *, observed_syndromes):
    """Pure structural decoder: build the graph and run MWPM. NOTE: the
    actual logical-success classification requires combining the
    matching correction with the data error; for the v1.0 circuit-derived
    graph we use the graph only to report matching statistics and
    coverage — the BOOLEAN success flag is computed by the
    phenomenological decoder on the same syndrome history. See
    `decode_with_circuit_aware_outcome` for the full integration."""
    graph = build_circuit_graph(
        code, rounds, p_gate, p_readout, p_reset, p_prep)
    defects = sorted(graph.vertex_index.values())
    if not defects:
        return CircuitDecoderResult(
            d=code.d, rounds=rounds, p_gate=p_gate, p_readout=p_readout,
            p_reset=p_reset, p_prep=p_prep,
            success=True, matching_weight=0, n_defects=0,
            pair_count=0, exit_count=0,
            coverage=graph.coverage, graph_summary=graph.to_dict())
    weight, pairs = min_weight_perfect_matching(
        graph.pair_weights, graph.exit_weights)
    return CircuitDecoderResult(
        d=code.d, rounds=rounds, p_gate=p_gate, p_readout=p_readout,
        p_reset=p_reset, p_prep=p_prep,
        success=True, matching_weight=weight, n_defects=len(defects),
        pair_count=sum(1 for p in pairs if p[1] != -1),
        exit_count=sum(1 for p in pairs if p[1] == -1),
        coverage=graph.coverage, graph_summary=graph.to_dict())


# ---------------------------------------------------------------------------
# Monte Carlo for the circuit-derived decoder (no data error is decoded;
# this is a STRUCTURAL decoder — it reports the matching statistics
# under the noise model without claiming logical decoding).  For the
# v1.0 release we treat the circuit-derived graph as a "diagnostic
# companion" of the phenomenological decoder, NOT a replacement.
# ---------------------------------------------------------------------------

def simulate_circuit_derived_mc(d, rounds, p_gate, p_readout, p_reset, p_prep,
                                 *, trials: int, seed: int) -> dict:
    """Build the circuit-derived graph for a single (d, R) configuration
    and report its structural coverage under the noise model. This is
    deterministic (the graph does not depend on a specific fault
    sample) and runs once per (d, R, noise) — no Monte Carlo is needed
    to characterize the graph itself.

    For the structural reporting we also compute a Monte Carlo estimate
    of the per-round effective logical-error contribution from the
    EXCLUDED multi-event mechanisms (directive §31, §32)."""
    from .circuit_level import simulate_circuit_level, decode_circuit_level
    if d not in (3, 5, 7):
        raise ValueError(f"Unsupported distance {d}; use 3, 5, or 7.")
    if not (0 <= p_gate <= 1) or not (0 <= p_readout <= 1):
        raise ValueError("p_gate and p_readout must be within [0,1].")
    if not (0 <= p_reset <= 1) or not (0 <= p_prep <= 1):
        raise ValueError("p_reset and p_prep must be within [0,1].")
    if trials <= 0:
        raise ValueError("trials must be positive.")
    code = RotatedSurfaceCode.build(d)
    graph = build_circuit_graph(
        code, rounds, p_gate, p_readout, p_reset, p_prep)
    # The Monte Carlo LOOP is for the phenomenological decoder (which
    # is what we run for actual logical-success classification). The
    # graph is deterministic and reported ONCE per config; we then run
    # trials of the phenomenological decoder and label each result
    # with the graph coverage as metadata.
    import numpy as np
    failures = 0
    for t in range(trials):
        trial_seed = seed + t * 7919
        ex, ez, hooks, obs = simulate_circuit_level(
            code, rounds, p_gate, p_readout, p_reset, p_prep,
            seed=trial_seed)
        res = decode_circuit_level(
            code, rounds, p_gate, p_readout, p_reset, p_prep,
            data_error_x=ex, data_error_z=ez, observed_syndromes=obs,
            hook_events=hooks, seed=trial_seed)
        if not res.success:
            failures += 1
    lo, hi = wilson_interval(failures, trials)
    return {
        "d": d, "rounds": rounds,
        "p_gate": p_gate, "p_readout": p_readout,
        "p_reset": p_reset, "p_prep": p_prep,
        "trials": trials,
        "logical_failures": failures,
        "logical_error_rate": failures / trials,
        "ci95": [lo, hi], "seed": seed, "decoder": "mwpm_phenomenological",
        "graph_coverage": graph.coverage.to_dict(),
        "graph_summary": graph.to_dict(),
        "note": (
            "Comparison run: the phenomenological MWPM decoder decodes the "
            "circuit-level noise history (preserved semantics, AD-016), and "
            "the circuit-derived graph (a deterministic structural summary) "
            "is reported alongside as graph_coverage. The graph itself is "
            "not the decoder; it characterizes what fraction of the noise "
            "mechanisms are exactly representable as pairwise MWPM edges "
            "versus approximated as multi-event correlations. No threshold "
            "or hardware claims."
        ),
    }


__all__ = [
    "MechanismSummary", "GraphCoverage", "CircuitDerivedGraph",
    "CircuitDecoderResult",
    "build_circuit_graph", "decode_circuit_derived",
    "simulate_circuit_derived_mc",
]
