"""Benchmark subsystem: measured performance, never fabricated (directive §112).

Measures wall-clock execution of representative workloads on THIS machine:
  - statevector circuit throughput at several qubit counts (Bell / GHZ / QFT /
    random circuits)
  - shot-sampling throughput
  - density-matrix execution at its documented ceiling
  - network event throughput

Results include machine-context metadata so numbers can be compared across
runs; they describe this machine only and are not portable claims.
"""
from __future__ import annotations

import platform
import time
from dataclasses import dataclass

import numpy as np

from ..circuits.model import Circuit, Operation
from ..circuits.simulate import simulate
from .runner import make_result_document


def _timed(fn, repeats: int = 3) -> tuple[float, float]:
    """Return (best_seconds, mean_seconds) over `repeats` runs."""
    times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return min(times), sum(times) / len(times)


def _make_circuit(kind: str, n_qubits: int) -> Circuit:
    c = Circuit(num_qubits=n_qubits, name=f"bench-{kind}-{n_qubits}")
    if kind == "bell":
        c.add_gate("H", [0]).add_gate("CX", [0, 1 % n_qubits])
    elif kind == "ghz":
        c.add_gate("H", [0])
        for q in range(n_qubits - 1):
            c.add_gate("CX", [q, q + 1])
    elif kind == "qft":
        from ..algorithms import build_qft

        built, _ = build_qft(n_qubits)
        c.operations = list(built.operations)
        c.metadata.update(built.metadata)
    elif kind == "random":
        rng = np.random.default_rng(n_qubits)
        depth = max(4, n_qubits * 2)
        for _ in range(depth):
            q1 = int(rng.integers(n_qubits))
            gate = "H" if rng.random() < 0.5 else "T"
            c.add_gate(gate, [q1])
            if n_qubits > 1 and rng.random() < 0.6:
                q2 = int(rng.integers(n_qubits))
                if q2 != q1:
                    c.add_gate("CX", sorted([q1, q2]))
    else:
        raise ValueError(f"Unknown benchmark circuit {kind!r}")
    return c


@dataclass
class BenchEntry:
    workload: str
    metric: str
    value: float
    unit: str


def run_circuit_benchmarks(max_qubits: int = 18, *, repeats: int = 3) -> dict:
    entries: list[BenchEntry] = []
    for kind in ("bell", "ghz", "qft", "random"):
        for n in range(4, max_qubits + 1, max(2, (max_qubits - 4) // 5)):
            if kind == "random" and n > 16:
                continue
            circuit = _make_circuit(kind, n)
            best, mean = _timed(lambda: simulate(circuit), repeats=repeats)
            gates = len(circuit.operations)
            entries.append(BenchEntry(
                f"{kind}-{n}q ({gates} gates)", "evolution_time_best",
                round(best * 1000, 3), "ms"))
    # Shot throughput on a mid-size GHZ.
    circuit = _make_circuit("ghz", 10)
    shot_circuit = Circuit(
        num_qubits=10, num_clbits=10,
        operations=list(circuit.operations)
        + [Operation(kind="measure", qubits=tuple(range(10)), clbits=tuple(range(10)))],
        name=circuit.name + "-measured",
    )
    shots = 20000
    best, _ = _timed(lambda: simulate(shot_circuit, seed=1, shots=shots), repeats=3)
    entries.append(BenchEntry(
        f"ghz-10q shots fast-path", "shots_per_second", round(shots / best, 0), "1/s"))
    return {
        "entries": [e.__dict__ for e in entries],
        "max_qubits": max_qubits,
        "repeats": repeats,
    }


def run_density_benchmark(n_qubits: int = 8, *, repeats: int = 2) -> dict:
    circuit = _make_circuit("ghz", min(n_qubits, 12))
    best, _ = _timed(lambda: simulate(circuit, mode="density_matrix"), repeats=repeats)
    return {"n_qubits": circuit.num_qubits,
            "evolution_time_best_ms": round(best * 1000, 3)}


def run_network_benchmark(*, requests: int = 30, sim_time_ms: int = 1000,
                          chain_length: int = 4, repeats: int = 2) -> dict:
    from ..network import Topology, NetworkNode, NetworkEngine, NetworkConfig

    best_events = 0.0
    best_time = None
    for r in range(repeats):
        topo = Topology()
        names = ["A"] + [f"R{i}" for i in range(1, chain_length)] + ["B"]
        for i, n in enumerate(names):
            topo.add_node(NetworkNode(n, "end" if i in (0, len(names) - 1) else "repeater",
                                      memory_slots=8))
        for i in range(len(names) - 1):
            topo.add_quantum_link(names[i], names[i + 1], distance_km=15 + 5 * i)
        eng = NetworkEngine(topo, NetworkConfig(trace_mode="summary"), seed=900 + r)
        for i in range(requests):
            eng.submit_request(names[0], names[-1], priority=i % 3)
        t0 = time.perf_counter()
        res = eng.run(until_ns=sim_time_ms * 1e6)
        dt = time.perf_counter() - t0
        best_events = max(best_events, res.stats["events_processed"])
        best_time = dt if best_time is None else min(best_time, dt)
    eps = best_events / max(best_time or 1e-9, 1e-9)
    return {
        "requests": requests,
        "chain_length": chain_length + 1,
        "events_processed_best": best_events,
        "wall_seconds_best": round(best_time, 3),
        "events_per_second_best": round(eps, 0),
    }


def run_all_benchmarks(**kwargs) -> dict:
    circuits = run_circuit_benchmarks(**{k: v for k, v in kwargs.items() if k in ("repeats",)})
    density = run_density_benchmark()
    network = run_network_benchmark()
    doc = make_result_document(
        "benchmarks",
        metrics={
            "statevector_workloads": len(circuits["entries"]),
            "slowest_statevector_ms": max(e["value"] for e in circuits["entries"]
                                          if e["metric"] == "evolution_time_best"),
            "shot_throughput_1_per_s": next(e["value"] for e in circuits["entries"]
                                            if e["metric"] == "shots_per_second"),
            "density_evolution_ms": density["evolution_time_best_ms"],
            "network_events_per_s": network["events_per_second_best"],
        },
        summary={"circuits": circuits, "density": density, "network": network},
        notes=[
            "Wall-clock measurements of THIS machine at execution time; "
            "numbers are not portable across machines.",
            "Statevector timings evolve once without measurement collapse.",
        ],
    )
    doc["environment"] = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "processor": platform.processor() or "unknown",
    }
    return doc
