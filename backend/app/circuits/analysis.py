"""Circuit analysis: measured structural metrics, never fabricated (§9).

Metrics that are undefined for a circuit's gate set are reported as None
rather than invented.
"""
from __future__ import annotations

from dataclasses import dataclass

from .model import Circuit


# Gates whose T-count/T-depth contributions are defined in the standard
# Clifford+T accounting. All other gates report None for T metrics.
_T_COSTS_1Q = {"T": 1, "TDG": 1}
_H_AND_PHASE = {"H", "S", "SDG", "P", "PHASE"}


@dataclass
class CircuitAnalysis:
    n_qubits: int
    n_clbits: int
    gate_count: int
    single_qubit_gate_count: int
    two_qubit_gate_count: int
    three_qubit_gate_count: int
    measurement_count: int
    reset_count: int
    barrier_count: int
    depth: int
    parameter_count: int
    t_count_total: int | None      # None when non-Clifford+T gates present
    t_depth: int | None            # None when non-Clifford+T gates present
    connectivity_pairs_used: list[list[int]]   # qubit pairs requiring 2q interaction
    gate_histogram: dict[str, int]

    def to_dict(self) -> dict:
        return {
            "n_qubits": self.n_qubits,
            "n_clbits": self.n_clbits,
            "gate_count": self.gate_count,
            "single_qubit_gate_count": self.single_qubit_gate_count,
            "two_qubit_gate_count": self.two_qubit_gate_count,
            "three_qubit_gate_count": self.three_qubit_gate_count,
            "measurement_count": self.measurement_count,
            "reset_count": self.reset_count,
            "barrier_count": self.barrier_count,
            "depth": self.depth,
            "parameter_count": self.parameter_count,
            "t_count_total": self.t_count_total,
            "t_depth": self.t_depth,
            "connectivity_pairs_used": self.connectivity_pairs_used,
            "gate_histogram": self.gate_histogram,
        }


def analyze_circuit(circuit: Circuit) -> CircuitAnalysis:
    from ..quantum.operators import build_gate, PARAMETERIZED_1Q, PARAMETERIZED_2Q
    from ..circuits.simulate import resolve_gate

    histogram: dict[str, int] = {}
    sq = tq = thq = meas = resets = barriers = params = 0
    pairs: set[frozenset[int]] = set()

    # T accounting: track whether any gate outside our defined cost table exists
    known_t_accounting = set(_T_COSTS_1Q) | _H_AND_PHASE | {"X", "Y", "Z", "I", "CX"}
    all_gates_known = True
    t_depth_frontier = [0] * max(circuit.num_qubits, 1)
    t_count = 0

    for op in circuit.operations:
        if op.kind == "barrier":
            barriers += 1
            continue
        if op.kind == "measure":
            meas += len(op.qubits)
            continue
        if op.kind == "reset":
            resets += len(op.qubits)
            continue
        name = op.gate or "?"
        histogram[name] = histogram.get(name, 0) + 1
        params += len(op.params)
        spec = resolve_gate(circuit, name, list(op.params))
        arity = len(op.qubits)
        if arity == 1:
            sq += 1
        elif arity == 2:
            tq += 1
            pairs.add(frozenset(op.qubits))
        elif arity == 3:
            thq += 1
            pairs.add(frozenset((op.qubits[0], op.qubits[1])))
            pairs.add(frozenset((op.qubits[0], op.qubits[2])))
            pairs.add(frozenset((op.qubits[1], op.qubits[2])))
        # T accounting
        if name not in known_t_accounting:
            all_gates_known = False
        else:
            if name in _T_COSTS_1Q:
                t_count += _T_COSTS_1Q[name]
                lvl = max(t_depth_frontier[op.qubits[0]] for _ in [0]) + 1
                t_depth_frontier[op.qubits[0]] = lvl
            elif name in ("CX",):
                new_level = max(t_depth_frontier[q] for q in op.qubits)
                # CX propagates T-depth without adding a layer
                for q in op.qubits:
                    t_depth_frontier[q] = new_level
            elif name in _H_AND_PHASE or name in ("X", "Y", "Z", "I"):
                # H/S/P and Paulis have T-depth cost 1 only if T-count context...
                # standard accounting: H/S/P are T-free; they do NOT advance T-depth
                pass

    return CircuitAnalysis(
        n_qubits=circuit.num_qubits,
        n_clbits=circuit.num_clbits,
        gate_count=sum(1 for op in circuit.operations if op.kind == "gate"),
        single_qubit_gate_count=sq,
        two_qubit_gate_count=tq,
        three_qubit_gate_count=thq,
        measurement_count=meas,
        reset_count=resets,
        barrier_count=barriers,
        depth=circuit.depth(),
        parameter_count=params,
        t_count_total=t_count if all_gates_known else None,
        t_depth=max(t_depth_frontier) if all_gates_known else None,
        connectivity_pairs_used=[sorted(list(p)) for p in sorted(pairs, key=lambda s: sorted(s))],
        gate_histogram=histogram,
    )
