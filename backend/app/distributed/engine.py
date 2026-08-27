"""Distributed execution engine (§REMOTE CNOT, §RESULT MODEL, §RESOURCE ACCOUNTING).

This is the orchestration layer. It:

  1. validates the circuit,
  2. assigns logical qubits to nodes (explicit or deterministic heuristic),
  3. partitions the circuit into local + remote operations,
  4. expands every cross-node CNOT into its genuine protocol circuit
     (teleportation / entanglement / measurement / Pauli correction),
  5. requests the required shared entanglement from the network bridge,
  6. simulates the expanded circuit on the ordinary quantum engine,
  7. compares the distributed logical output to a centralized reference,
  8. records every resource, message, and failure.

The distributed circuit is executed *through* the protocol abstraction — it is
never a centralized CNOT relabeled as remote (§NO FAKE DISTRIBUTION).
"""
from __future__ import annotations

import numpy as np
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .partition import PartitionPlan

from ..circuits.model import Circuit, Operation
from ..circuits.validate import validate_circuit
from ..circuits.simulate import simulate
from ..quantum.density import DensityMatrix
from ..quantum.states import QuantumCoreError
from .partition import partition_circuit_full, heuristic_assignment
from .remote_cnot import expand_remote_cnot
from .network_bridge import NetworkBridge
from .model import DistributedResult, ClassicalMessage


@dataclass
class DistributedConfig:
    protocol: str = "single_ebit"
    seed: int | None = None
    qubit_to_node: dict[int, str] | None = None
    num_nodes: int = 2
    node_names: list[str] | None = None
    objective: str = "minimize_cross_node"
    topology: object | None = None
    network_config: object | None = None
    fallback: str = "error"  # "error" (default) or "centralized"
    max_remote_operations: int = 64
    max_ancillas: int = 512

    def validated_node_names(self) -> list[str]:
        if self.node_names is not None:
            return list(self.node_names)
        if self.qubit_to_node:
            names = sorted(set(self.qubit_to_node.values()))
            if names:
                return names
        if self.num_nodes < 2:
            return ["node_0"]
        return [f"node_{i}" for i in range(max(2, self.num_nodes))]


class DistributedExecutor:
    def __init__(self, config: DistributedConfig | None = None):
        self.config = config or DistributedConfig()

    # ---- public API -------------------------------------------------------

    def plan(self, circuit: Circuit) -> PartitionPlan:
        """Compute the partition plan without executing (analysis only)."""
        from .partition import partition_circuit_full, heuristic_assignment

        node_names = self.config.validated_node_names()
        assignment = heuristic_assignment(
            circuit, num_nodes=self.config.num_nodes,
            qubit_to_node=self.config.qubit_to_node, node_names=node_names,
            objective=self.config.objective,
        )
        if self.config.topology is not None:
            topo_nodes = set(self.config.topology.nodes)
            unknown = [n for n in set(assignment.values()) if n not in topo_nodes]
            if unknown:
                raise ValueError(
                    f"Assignment references unknown node(s) {unknown} not present "
                    f"in the supplied topology."
                )
        return partition_circuit_full(circuit, assignment, objective=self.config.objective)

    def execute(self, circuit: Circuit) -> DistributedResult:
        result = DistributedResult(
            protocol=self.config.protocol,
            qubit_count=circuit.num_qubits,
        )
        try:
            return self._execute_inner(circuit, result)
        except Exception as e:  # surface as a structured failure, never silent
            result.status = "failed"
            result.errors.append(f"{type(e).__name__}: {e}")
            return result

    def analyze_single_remote_cnot(
        self, control_qubit: int, target_qubit: int,
        assignment: dict[int, str] | None = None,
    ) -> DistributedResult:
        """Build a minimal 2-qubit CNOT(control, target) and run it distributed."""
        if assignment is None:
            assignment = {control_qubit: "node_0", target_qubit: "node_1"}
        if control_qubit == target_qubit:
            raise ValueError("control and target must be distinct qubits.")
        sub = Circuit(num_qubits=max(control_qubit, target_qubit) + 1)
        sub.add_gate("CX", [control_qubit, target_qubit])
        cfg = DistributedConfig(
            protocol=self.config.protocol, seed=self.config.seed,
            qubit_to_node=assignment, topology=self.config.topology,
            network_config=self.config.network_config, fallback=self.config.fallback,
        )
        return DistributedExecutor(cfg).execute(sub)

    # ---- internals --------------------------------------------------------

    def _execute_inner(self, circuit: Circuit, result: DistributedResult) -> DistributedResult:
        issues = validate_circuit(circuit)
        if issues:
            raise ValueError("; ".join(i.message for i in issues))

        node_names = self.config.validated_node_names()
        assignment = heuristic_assignment(
            circuit, num_nodes=self.config.num_nodes,
            qubit_to_node=self.config.qubit_to_node, node_names=node_names,
            objective=self.config.objective,
        )
        # Fail loudly on nodes that do not exist in a supplied topology.
        if self.config.topology is not None:
            topo_nodes = set(self.config.topology.nodes)
            unknown = [n for n in set(assignment.values()) if n not in topo_nodes]
            if unknown:
                raise ValueError(
                    f"Assignment references unknown node(s) {unknown} not present "
                    f"in the supplied topology."
                )

        plan = partition_circuit_full(circuit, assignment, objective=self.config.objective)

        result.node_assignments = {int(k): v for k, v in assignment.items()}
        result.nodes = plan.nodes
        result.local_operations = plan.local_operations
        result.remote_operations = plan.remote_operations
        result.partition_metrics = plan.metrics
        result.node_count = plan.metrics.node_count
        result.local_gate_count = plan.metrics.local_gate_count
        result.remote_gate_count = plan.metrics.remote_gate_count
        result.remote_cnot_count = plan.metrics.remote_cnot_count

        # Cap enforcement (§RESOURCE ACCOUNTING / failure modes).
        if len(plan.remote_operations) > self.config.max_remote_operations:
            raise ValueError(
                f"Circuit has {len(plan.remote_operations)} remote operations; "
                f"exceeds cap {self.config.max_remote_operations}."
            )

        bridge = NetworkBridge(
            topology=self.config.topology, config=self.config.network_config,
            seed=self.config.seed if self.config.seed is not None else 7,
        )

        # Expand remote CNOTs into protocol circuits while tracking the
        # logical->physical carrier remapping.
        remote_by_index = {r.op_index: r for r in plan.remote_operations}
        physical_of = {q: q for q in range(circuit.num_qubits)}
        next_ancilla = circuit.num_qubits
        next_clbit = circuit.num_clbits
        expanded_ops: list[Operation] = []

        def get_ancilla():
            nonlocal next_ancilla
            a = next_ancilla
            next_ancilla += 1
            if next_ancilla > circuit.num_qubits + self.config.max_ancillas:
                raise ValueError("Exceeded maximum ancilla budget for remote operations.")
            return a

        def get_clbit():
            nonlocal next_clbit
            c = next_clbit
            next_clbit += 1
            return c

        # First pass: build the expanded operation list, requesting ebits.
        for idx, op in enumerate(circuit.operations):
            if idx in remote_by_index:
                rop = remote_by_index[idx]
                if rop.control_qubit == rop.target_qubit:
                    raise ValueError("control and target must be distinct qubits.")
                c_phys = physical_of[rop.control_qubit]
                t_phys = physical_of[rop.target_qubit]
                expansion = expand_remote_cnot(
                    c_phys, t_phys, rop.source_node, rop.target_node,
                    self.config.protocol, get_ancilla, get_clbit,
                )
                # Request the real entanglement resource from the network.
                grant = bridge.request_ebit(rop.source_node, rop.target_node,
                                            protocol=self.config.protocol)
                result.entanglement_operations.append(grant)
                if not grant.success:
                    if self.config.fallback == "centralized":
                        result.warnings.append(
                            f"Remote CNOT {idx} ebit unavailable; falling back to "
                            f"centralized execution (explicit fallback requested)."
                        )
                        # EXPLICIT centralized fallback: emit a single local CNOT
                        # on the current carriers and do NOT run the distributed
                        # protocol (no ebit is consumed, carriers stay put).
                        remapped = Operation(
                            kind="gate", gate="CX",
                            qubits=(physical_of[rop.control_qubit],
                                    physical_of[rop.target_qubit]),
                        )
                        expanded_ops.append(remapped)
                        rop.executed = False
                        rop.ebits_required = 0
                        rop.classical_messages = 0
                        rop.failure_reason = grant.failure_reason or "ebit unavailable"
                        continue
                    result.status = "failed"
                    result.errors.append(
                        f"Remote CNOT at op {idx} ({rop.source_node}->{rop.target_node}) "
                        f"requires entanglement but none could be established: "
                        f"{grant.failure_reason}"
                    )
                    rop.executed = False
                    rop.failure_reason = grant.failure_reason
                    rop.ebit_fidelity = grant.fidelity
                    rop.ebit_latency_ns = grant.latency_ns
                    rop.ebit_attempts = grant.attempts
                    return result
                # Grant succeeded: run the genuine protocol expansion and record
                # ACTUAL resource consumption (protocol-dependent, e.g. double
                # teleportation consumes 2 ebits + 4 cbits, not the partition
                # plan's single-ebit estimate).
                rop.executed = True
                rop.ebits_required = expansion.ebits
                rop.classical_messages = expansion.classical_bits
                rop.ebit_fidelity = grant.fidelity
                rop.ebit_latency_ns = grant.latency_ns
                rop.ebit_attempts = grant.attempts
                order = 0
                for (sender, receiver, bits) in expansion.classical_messages:
                    result.classical_messages.append(
                        ClassicalMessage(source_node=sender, target_node=receiver,
                                         bits=bits, remote_op_index=idx, order=order)
                    )
                    order += 1
                expanded_ops.extend(expansion.operations)
                physical_of[rop.control_qubit] = expansion.control_output_qubit
                physical_of[rop.target_qubit] = expansion.target_output_qubit
            else:
                # Local op: remap qubit operands to their current carriers.
                remapped = Operation(
                    kind=op.kind, gate=op.gate, params=op.params,
                    qubits=tuple(physical_of[q] for q in op.qubits),
                    clbits=op.clbits, condition=op.condition, label=op.label,
                )
                expanded_ops.append(remapped)

        if result.status == "failed":
            return result

        expanded = Circuit(
            num_qubits=next_ancilla, num_clbits=next_clbit,
            operations=expanded_ops, name=circuit.name,
            metadata=dict(circuit.metadata),
        )

        sim = simulate(expanded, mode="statevector", seed=self.config.seed)
        central = simulate(circuit, mode="statevector", seed=self.config.seed)

        # Resource accounting.
        result.ebit_consumption = sum(r.ebits_required for r in result.remote_operations if r.executed)
        result.classical_message_count = sum(cm.bits for cm in result.classical_messages)
        result.communication_cost = result.classical_message_count

        # Equivalence: reduce both states to the logical qubits and compare.
        # The reduction is computed directly from the amplitudes via axis
        # permutation, so no full 4^N density matrix of the expanded register
        # is ever materialised (that would explode for large remote circuits).
        n = circuit.num_qubits

        def reduced(amps: np.ndarray, phys_positions: list[int]) -> DensityMatrix:
            N = int(round(np.log2(amps.size)))
            tensor = amps.reshape([2] * N)
            # C-order reshape puts the most-significant index bit on axis 0,
            # i.e. axis p corresponds to physical qubit N-1-p.
            logical_axes = [N - 1 - q for q in phys_positions]
            remaining = [p for p in range(N) if p not in set(logical_axes)]
            moved = np.transpose(tensor, logical_axes + remaining)
            m = moved.reshape(1 << len(phys_positions), -1)
            rho = m @ m.conj().T
            tr = float(np.real(np.trace(rho)))
            if tr <= 0 or abs(tr - 1.0) > 1e-6:
                raise QuantumCoreError(
                    f"Reduced-state trace {tr:.6f}; numerical failure."
                )
            return DensityMatrix(rho / tr, len(phys_positions))

        rho_d = reduced(sim.final_state.amplitudes,
                        [physical_of[q] for q in range(n)])
        rho_c = reduced(central.final_state.amplitudes, list(range(n)))
        fid = float(rho_d.fidelity_with(rho_c))
        equiv_passed = bool(fid >= 1 - 1e-8)
        result.equivalence = {
            "fidelity": round(fid, 12),
            "passed": equiv_passed,
            "method": "Uhlmann fidelity of reduced logical states",
            "tolerance": 1e-8,
        }
        if not equiv_passed and self.config.fallback != "centralized":
            result.warnings.append(
                "Distributed output did not match centralized reference within tolerance."
            )

        # Output state: canonical logical-basis probabilities. We marginalise
        # the post-protocol state over the logical physical carriers directly
        # (robust to the partial_trace qubit-ordering convention). Bit L of the
        # logical index is taken from physical carrier physical_of[L].
        full_probs = np.abs(sim.final_state.amplitudes) ** 2
        logical_probs = np.zeros(1 << n, dtype=float)
        for i, p in enumerate(full_probs):
            if p <= 0.0:
                continue
            li = 0
            for L in range(n):
                if (i >> physical_of[L]) & 1:
                    li |= (1 << L)
            logical_probs[li] += p
        out_probs = {
            format(i, f"0{n}b"): round(float(p), 9)
            for i, p in enumerate(logical_probs) if p > 1e-12
        }
        result.output_state = {
            "probabilities": out_probs,
            "logical_qubits": n,
            "note": "Reduced state over the original logical qubits (ancillas traced out).",
        }

        result.reproducibility = {
            "seed": self.config.seed,
            "protocol": self.config.protocol,
            "objective": self.config.objective,
            "assignment": {str(k): v for k, v in assignment.items()},
            "fallback": self.config.fallback,
            "network_model": "ideal" if self.config.topology is None else "network_engine",
        }
        result.notes = [
            "Remote CNOTs are executed through the genuine protocol expansion "
            "(entanglement + teleportation + Pauli corrections), not a relabeled "
            "centralized CNOT.",
            "Simulation runtime is NOT physical hardware performance; modelled "
            "network latency (where a topology is supplied) is reported separately "
            "under entanglement_operations[].latency_ns.",
        ]
        result.status = "success"
        return result
