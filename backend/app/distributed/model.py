"""Data model for the distributed quantum-computing subsystem.

These dataclasses describe a partitioned circuit, the resources consumed by
remote operations, the classical-communication events, and the consolidated
distributed execution result. They are plain, serializable structures so the
API layer can return them directly and the frontend can render them without
interpretation (directive §309).

No simulation is performed here; this module only defines the shapes.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NodeSpec:
    """A compute node and the logical qubits it hosts."""

    name: str
    qubits: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"name": self.name, "qubits": list(self.qubits)}


@dataclass
class LocalOp:
    """A circuit operation that executes entirely on a single node."""

    node: str
    op_index: int
    gate: str | None
    qubits: list[int]
    kind: str

    def to_dict(self) -> dict:
        return {
            "node": self.node,
            "op_index": self.op_index,
            "gate": self.gate,
            "qubits": list(self.qubits),
            "kind": self.kind,
        }


@dataclass
class RemoteOp:
    """A cross-node operation requiring shared entanglement + classical comms."""

    op_index: int
    gate: str
    qubits: list[int]
    control_qubit: int
    target_qubit: int
    source_node: str
    target_node: str
    protocol: str
    ebits_required: int
    classical_messages: int
    # Set once the operation is executed:
    ebit_fidelity: float | None = None
    ebit_latency_ns: float | None = None
    ebit_attempts: int | None = None
    # Werner-noise provenance: fidelity actually used for the quantum state
    # (equals ebit_fidelity in network mode; may differ in fixed mode) and the
    # sampled Pauli component per consumed ebit ("I" = ideal component).
    ebit_fidelity_applied: float | None = None
    ebit_noise: list[str] | None = None
    executed: bool = False
    failure_reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "op_index": self.op_index,
            "gate": self.gate,
            "qubits": list(self.qubits),
            "control_qubit": self.control_qubit,
            "target_qubit": self.target_qubit,
            "source_node": self.source_node,
            "target_node": self.target_node,
            "protocol": self.protocol,
            "ebits_required": self.ebits_required,
            "classical_messages": self.classical_messages,
            "ebit_fidelity": self.ebit_fidelity,
            "ebit_latency_ns": self.ebit_latency_ns,
            "ebit_attempts": self.ebit_attempts,
            "ebit_fidelity_applied": self.ebit_fidelity_applied,
            "ebit_noise": list(self.ebit_noise) if self.ebit_noise is not None else None,
            "executed": self.executed,
            "failure_reason": self.failure_reason,
        }


@dataclass
class EbitGrant:
    """One shared entangled pair granted (or refused) by the network layer."""

    node_a: str
    node_b: str
    success: bool
    fidelity: float | None = None
    latency_ns: float | None = None
    attempts: int | None = None
    route: list[str] | None = None
    model: str = "ideal"
    failure_reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "node_a": self.node_a,
            "node_b": self.node_b,
            "success": self.success,
            "fidelity": self.fidelity,
            "latency_ns": self.latency_ns,
            "attempts": self.attempts,
            "route": list(self.route) if self.route else None,
            "model": self.model,
            "failure_reason": self.failure_reason,
        }


@dataclass
class ClassicalMessage:
    """A classical message exchanged between nodes during a remote operation."""

    source_node: str
    target_node: str
    bits: int
    remote_op_index: int
    order: int
    kind: str = "correction"

    def to_dict(self) -> dict:
        return {
            "source_node": self.source_node,
            "target_node": self.target_node,
            "bits": self.bits,
            "remote_op_index": self.remote_op_index,
            "order": self.order,
            "kind": self.kind,
        }


@dataclass
class PartitionMetrics:
    """Quantitative partition quality indicators (directive §PARTITION QUALITY)."""

    local_gate_count: int = 0
    remote_gate_count: int = 0
    remote_cnot_count: int = 0
    cross_node_gate_count: int = 0
    ebit_consumption: int = 0
    classical_message_count: int = 0
    communication_cost: int = 0
    node_count: int = 0
    qubit_count: int = 0
    objective: str = "explicit"

    def to_dict(self) -> dict:
        return {
            "local_gate_count": self.local_gate_count,
            "remote_gate_count": self.remote_gate_count,
            "remote_cnot_count": self.remote_cnot_count,
            "cross_node_gate_count": self.cross_node_gate_count,
            "ebit_consumption": self.ebit_consumption,
            "classical_message_count": self.classical_message_count,
            "communication_cost": self.communication_cost,
            "node_count": self.node_count,
            "qubit_count": self.qubit_count,
            "objective": self.objective,
        }


@dataclass
class DistributedResult:
    """Consolidated result of a distributed execution (directive §RESULT MODEL)."""

    schema: str = "quantumlab.distributed-result"
    version: int = 1
    status: str = "success"
    protocol: str = "single_ebit"
    node_count: int = 0
    qubit_count: int = 0
    local_gate_count: int = 0
    remote_gate_count: int = 0
    remote_cnot_count: int = 0
    ebit_consumption: int = 0
    classical_message_count: int = 0
    communication_cost: int = 0
    partition_metrics: PartitionMetrics | None = None
    node_assignments: dict[int, str] = field(default_factory=dict)
    nodes: list[NodeSpec] = field(default_factory=list)
    local_operations: list[LocalOp] = field(default_factory=list)
    remote_operations: list[RemoteOp] = field(default_factory=list)
    entanglement_operations: list[EbitGrant] = field(default_factory=list)
    classical_messages: list[ClassicalMessage] = field(default_factory=list)
    equivalence: dict | None = None
    output_state: dict | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    reproducibility: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {
            "schema": self.schema,
            "version": self.version,
            "status": self.status,
            "protocol": self.protocol,
            "node_count": self.node_count,
            "qubit_count": self.qubit_count,
            "local_gate_count": self.local_gate_count,
            "remote_gate_count": self.remote_gate_count,
            "remote_cnot_count": self.remote_cnot_count,
            "ebit_consumption": self.ebit_consumption,
            "classical_message_count": self.classical_message_count,
            "communication_cost": self.communication_cost,
            "node_assignments": {str(k): v for k, v in self.node_assignments.items()},
            "nodes": [n.to_dict() for n in self.nodes],
            "local_operations": [o.to_dict() for o in self.local_operations],
            "remote_operations": [o.to_dict() for o in self.remote_operations],
            "entanglement_operations": [e.to_dict() for e in self.entanglement_operations],
            "classical_messages": [m.to_dict() for m in self.classical_messages],
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "reproducibility": dict(self.reproducibility),
            "notes": list(self.notes),
        }
        if self.partition_metrics is not None:
            d["partition_metrics"] = self.partition_metrics.to_dict()
        if self.equivalence is not None:
            d["equivalence"] = dict(self.equivalence)
        if self.output_state is not None:
            d["output_state"] = dict(self.output_state)
        return d
