"""Multi-node circuit partitioning for distributed quantum computing (§28-29).

Given a circuit and a mapping of physical qubits to compute nodes, this module
splits the operations into node-local work and cross-node (remote) interactions,
and accounts for the entanglement / classical-communication cost of realising
those remote interactions with the remote-CNOT protocols in this package.

Two APIs are provided:

  * :func:`partition_circuit` / :func:`remote_gate_cost` — a lightweight
    analysis + cost summary (kept for backwards compatibility).
  * :func:`partition_circuit_full` / :func:`heuristic_assignment` — a richer
    :class:`PartitionPlan` used by the distributed execution engine, with a
    deterministic, explainable qubit-to-node heuristic assigner.

Honesty note: the cost figures are counts of *primitive remote-CNOT invocations*;
they are lower bounds on the true distributed-compilation cost because they assume
every supported remote gate decomposes into exactly one remote-CNOT call. Gates
that span more than two nodes, or that are not 2-qubit, are reported separately as
``requires_decomposition`` and excluded from the ebit/bit cost totals.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..circuits.model import Circuit, Operation
from .model import NodeSpec, LocalOp, RemoteOp, PartitionMetrics


# ---------------------------------------------------------------------------
# Lightweight analysis API (backwards compatible)
# ---------------------------------------------------------------------------

@dataclass
class RemoteGate:
    """A gate whose qubits are not all resident on a single node."""

    gate: str
    qubits: tuple[int, ...]
    nodes: tuple[str, ...]
    supported_as_single_remote_cnot: bool


@dataclass
class PartitionResult:
    node_ids: list[str]
    partition: dict[int, str]
    local_operations: dict[str, list[Operation]] = field(default_factory=dict)
    remote_gates: list[RemoteGate] = field(default_factory=list)
    local_gate_count: int = 0
    remote_gate_count: int = 0
    supported_remote_gate_count: int = 0
    unsupported_remote_gate_count: int = 0
    requires_decomposition: list[RemoteGate] = field(default_factory=list)
    ebits_single_ebit: int = 0
    classical_bits_single_ebit: int = 0
    ebits_double_teleport: int = 0
    classical_bits_double_teleport: int = 0


def _validate_partition(circuit: Circuit, partition: dict[int, str]) -> list[str]:
    if not partition:
        raise ValueError("partition must map every qubit to a node id.")
    node_ids: list[str] = []
    for q in range(circuit.num_qubits):
        if q not in partition:
            raise ValueError(f"qubit {q} is not assigned to any node.")
        nid = partition[q]
        if nid not in node_ids:
            node_ids.append(nid)
    return node_ids


def _classify(op: Operation, partition: dict[int, str]) -> tuple[str, tuple[str, ...]]:
    nodes = tuple(sorted({partition[q] for q in op.qubits}))
    return nodes[0] if len(nodes) == 1 else "", nodes


def partition_circuit(circuit: Circuit, partition: dict[int, str]) -> PartitionResult:
    """Partition ``circuit`` across nodes defined by ``partition``.

    ``partition`` maps physical qubit index -> node id (string). Every qubit must
    be assigned. Operations touching only one node are node-local; operations
    touching more than one node are remote.
    """
    node_ids = _validate_partition(circuit, partition)
    result = PartitionResult(node_ids=node_ids, partition=dict(partition))
    result.local_operations = {nid: [] for nid in node_ids}

    for op in circuit.operations:
        if op.kind in ("barrier",):
            continue
        if not op.qubits:
            continue
        node, nodes = _classify(op, partition)
        if node:
            result.local_operations[node].append(op)
            if op.kind == "gate":
                result.local_gate_count += 1
        else:
            is_two_qubit = op.kind == "gate" and len(op.qubits) == 2
            supported = is_two_qubit and len(nodes) == 2
            rg = RemoteGate(
                gate=op.gate or op.kind,
                qubits=tuple(op.qubits),
                nodes=nodes,
                supported_as_single_remote_cnot=supported,
            )
            result.remote_gates.append(rg)
            result.remote_gate_count += 1
            if supported:
                result.supported_remote_gate_count += 1
            else:
                result.unsupported_remote_gate_count += 1
                result.requires_decomposition.append(rg)

    result.ebits_single_ebit = result.supported_remote_gate_count
    result.classical_bits_single_ebit = 2 * result.supported_remote_gate_count
    result.ebits_double_teleport = 2 * result.supported_remote_gate_count
    result.classical_bits_double_teleport = 4 * result.supported_remote_gate_count
    return result


def remote_gate_cost(circuit: Circuit, partition: dict[int, str],
                     protocol: str = "single_ebit") -> dict:
    """Convenience cost summary for ``circuit`` under ``partition``."""
    if protocol not in ("single_ebit", "double_teleport"):
        raise ValueError("protocol must be 'single_ebit' or 'double_teleport'.")
    res = partition_circuit(circuit, partition)
    if protocol == "single_ebit":
        ebits = res.ebits_single_ebit
        cbits = res.classical_bits_single_ebit
    else:
        ebits = res.ebits_double_teleport
        cbits = res.classical_bits_double_teleport
    return {
        "protocol": protocol,
        "supported_remote_gates": res.supported_remote_gate_count,
        "unsupported_remote_gates": res.unsupported_remote_gate_count,
        "ebits": ebits,
        "classical_bits": cbits,
        "requires_decomposition": [
            {"gate": rg.gate, "qubits": list(rg.qubits), "nodes": list(rg.nodes)}
            for rg in res.requires_decomposition
        ],
    }


# ---------------------------------------------------------------------------
# Richer partition plan + deterministic heuristic assignment
# ---------------------------------------------------------------------------

class PartitionPlan:
    """Full distributed partition of a circuit across nodes."""

    def __init__(self, assignment: dict[int, str], objective: str = "explicit"):
        self.assignment = assignment
        self.objective = objective
        self.nodes: list[NodeSpec] = []
        self.local_operations: list[LocalOp] = []
        self.remote_operations: list[RemoteOp] = []
        self.metrics = PartitionMetrics(objective=objective)
        self.inter_node_dependencies: list[dict] = []
        self.requires_decomposition: list[RemoteOp] = []

    def to_dict(self) -> dict:
        return {
            "assignment": {str(k): v for k, v in self.assignment.items()},
            "objective": self.objective,
            "nodes": [n.to_dict() for n in self.nodes],
            "local_operations": [o.to_dict() for o in self.local_operations],
            "remote_operations": [o.to_dict() for o in self.remote_operations],
            "metrics": self.metrics.to_dict(),
            "inter_node_dependencies": self.inter_node_dependencies,
            "requires_decomposition": [o.to_dict() for o in self.requires_decomposition],
        }


def _gate_control_target(op) -> tuple[int, int] | None:
    if op.kind != "gate" or len(op.qubits) != 2:
        return None
    return op.qubits[0], op.qubits[1]


def partition_circuit_full(
    circuit: Circuit, assignment: dict[int, str], objective: str = "explicit"
) -> PartitionPlan:
    """Partition ``circuit`` into a :class:`PartitionPlan`.

    ``assignment`` maps every logical qubit to a node id. Each operation is
    classified as node-local (single node) or remote (operands on >1 node).
    Remote 2-qubit CNOT-class gates between exactly two nodes are marked as
    ``supported`` single remote-CNOT primitives; everything else that is
    cross-node is flagged ``requires_decomposition``.
    """
    if not assignment:
        raise ValueError("assignment must map every qubit to a node id.")
    node_ids: list[str] = []
    for q in range(circuit.num_qubits):
        if q not in assignment:
            raise ValueError(f"qubit {q} is not assigned to any node.")
        nid = assignment[q]
        if nid not in node_ids:
            node_ids.append(nid)
    plan = PartitionPlan(dict(assignment), objective)
    plan.nodes = [NodeSpec(name=n, qubits=sorted(q for q, n_ in assignment.items() if n_ == n))
                  for n in node_ids]

    for idx, op in enumerate(circuit.operations):
        if op.kind in ("barrier",) or not op.qubits:
            continue
        nodes = sorted({assignment[q] for q in op.qubits})
        if len(nodes) == 1:
            plan.local_operations.append(
                LocalOp(node=nodes[0], op_index=idx, gate=op.gate, qubits=list(op.qubits), kind=op.kind)
            )
            if op.kind == "gate":
                plan.metrics.local_gate_count += 1
        else:
            ct = _gate_control_target(op)
            if ct is not None:
                control_q, target_q = ct
                source_node = assignment[control_q]
                target_node = assignment[target_q]
                supported = len(nodes) == 2
            else:
                control_q, target_q = op.qubits[0], op.qubits[-1]
                source_node = assignment[control_q]
                target_node = assignment[target_q]
                supported = False
            ebits = 1 if supported else 0
            cbits = 2 if supported else 0
            rop = RemoteOp(
                op_index=idx, gate=op.gate or op.kind, qubits=list(op.qubits),
                control_qubit=control_q, target_qubit=target_q,
                source_node=source_node, target_node=target_node,
                protocol="single_ebit", ebits_required=ebits,
                classical_messages=cbits,
            )
            plan.remote_operations.append(rop)
            plan.metrics.remote_gate_count += 1
            plan.metrics.cross_node_gate_count += 1
            gname = (op.gate or op.kind).upper()
            if supported and gname in ("CX", "CNOT", "CZ", "CY"):
                plan.metrics.remote_cnot_count += 1
            else:
                plan.requires_decomposition.append(rop)
            plan.inter_node_dependencies.append({
                "op_index": idx,
                "nodes": nodes,
                "control_node": source_node,
                "target_node": target_node,
            })

    supported = [r for r in plan.remote_operations if r.ebits_required == 1]
    plan.metrics.ebit_consumption = len(supported)
    plan.metrics.classical_message_count = sum(r.classical_messages for r in supported)
    plan.metrics.communication_cost = plan.metrics.classical_message_count
    plan.metrics.node_count = len(node_ids)
    plan.metrics.qubit_count = circuit.num_qubits
    return plan


def _cross_node_gate_count(circuit: Circuit, assignment: dict[int, str]) -> int:
    count = 0
    for op in circuit.operations:
        if op.kind in ("barrier",) or not op.qubits:
            continue
        nodes = {assignment[q] for q in op.qubits}
        if len(nodes) > 1:
            count += 1
    return count


def heuristic_assignment(
    circuit: Circuit, num_nodes: int = 2, qubit_to_node: dict[int, str] | None = None,
    node_names: list[str] | None = None, objective: str = "minimize_cross_node",
    max_passes: int = 8,
) -> dict[int, str]:
    """Deterministic, reproducible qubit-to-node assignment (§PARTITIONING STRATEGY).

    Priority:
      1. explicit ``qubit_to_node`` mapping wins,
      2. otherwise a balanced round-robin seed,
      3. then deterministic local-search that swaps assignments to minimise the
         cross-node gate count (objective ``minimize_cross_node``).
    The objective is reported; it is NOT claimed globally optimal.
    """
    n = circuit.num_qubits
    if n == 0:
        return {}
    if node_names is None:
        if qubit_to_node:
            node_names = sorted(set(qubit_to_node.values()))
        else:
            node_names = [f"node_{i}" for i in range(max(2, num_nodes))]
    # A single-node assignment is a valid local execution (zero remote
    # operations); only the degenerate auto case with <2 requested nodes is
    # rejected below when no qubits were explicitly placed.

    assignment: dict[int, str] = {}
    if qubit_to_node:
        for q, node in qubit_to_node.items():
            if node not in node_names:
                raise ValueError(f"explicit mapping references unknown node {node!r}.")
            assignment[int(q)] = node
    remaining = [q for q in range(n) if q not in assignment]
    for i, q in enumerate(remaining):
        assignment[q] = node_names[i % len(node_names)]

    # Explicit user mappings are honoured as intent: no local search is run on
    # them. Local search only refines the auto-seeded (remaining) qubits.
    if qubit_to_node or objective != "minimize_cross_node":
        return assignment

    def cost(assign):
        return _cross_node_gate_count(circuit, assign)

    current = dict(assignment)
    cur_cost = cost(current)
    improved = True
    passes = 0
    while improved and passes < max_passes:
        improved = False
        passes += 1
        for q in remaining:
            base_node = current[q]
            best_node = base_node
            best_cost = cur_cost
            for cand in node_names:
                if cand == base_node:
                    continue
                # Constraint: never empty a node. Distributed computation must
                # actually span the requested nodes, so every node keeps at
                # least one hosted qubit (otherwise the local search would
                # collapse the whole circuit onto a single node and produce
                # zero remote operations).
                others_on_base = sum(1 for x in remaining if x != q and current[x] == base_node)
                if others_on_base == 0:
                    continue
                trial = dict(current)
                trial[q] = cand
                c = cost(trial)
                if c < best_cost:
                    best_cost = c
                    best_node = cand
            if best_node != base_node:
                current[q] = best_node
                cur_cost = best_cost
                improved = True
    return current
