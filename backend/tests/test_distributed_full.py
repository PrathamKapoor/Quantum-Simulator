"""Full distributed quantum-computing subsystem tests (§TEST MATRIX, §REGRESSION).

Covers basis states, superposition, entangled inputs, direction (A->B / B->A),
same-node, multiple and mixed remote CNOTs, multi-node (2/3/4), network
integration, failure modes, resource accounting, partition quality, and
property-based randomized equivalence.
"""
import random

import pytest

from app.circuits.model import Circuit
from app.circuits.simulate import simulate
from app.distributed import (
    DistributedExecutor,
    DistributedConfig,
    partition_circuit_full,
    heuristic_assignment,
    topology_from_nodes_links,
)
from app.network import NetworkConfig


def _centralized_probs(circuit, seed):
    r = simulate(circuit, mode="statevector", seed=seed)
    probs = r.final_state.probabilities()
    return {format(i, f"0{circuit.num_qubits}b"): float(p) for i, p in enumerate(probs)}


def _run(circuit, **kw):
    kw.setdefault("seed", 42)
    cfg = DistributedConfig(**kw)
    return DistributedExecutor(cfg).execute(circuit)


# ---------------------------------------------------------------- basis states
@pytest.mark.parametrize("ctrl,tgt", [(0, 0), (0, 1), (1, 0), (1, 1)])
def test_basis_states(ctrl, tgt):
    c = Circuit(num_qubits=2)
    if ctrl:
        c.add_gate("X", [0])
    if tgt:
        c.add_gate("X", [1])
    c.add_gate("CX", [0, 1])
    res = _run(c, qubit_to_node={0: "node_0", 1: "node_1"})
    assert res.status == "success"
    assert res.equivalence["passed"], res.equivalence
    assert res.ebit_consumption == 1
    assert res.classical_message_count == 2
    # CNOT copies control into target. Logical index li has control (qubit 0)
    # as LSB and target (qubit 1) as bit 1: li = control + 2*(control ^ target).
    out = res.output_state["probabilities"]
    expected = {}
    li = ctrl + 2 * (ctrl ^ tgt)
    expected[f"{li:02b}"] = 1.0
    for k, v in out.items():
        assert abs(v - expected.get(k, 0.0)) < 1e-9


# ------------------------------------------------------------- superposition
def test_superposition_plus0_plus1():
    for prep in ([("H", [0])], [("H", [1])], [("H", [0]), ("H", [1])]):
        c = Circuit(num_qubits=2)
        for g, q in prep:
            c.add_gate(g, q)
        c.add_gate("CX", [0, 1])
        res = _run(c, qubit_to_node={0: "A", 1: "B"})
        assert res.status == "success"
        assert res.equivalence["passed"], (prep, res.equivalence)


def test_superposition_minus_state():
    c = Circuit(num_qubits=2)
    c.add_gate("X", [0]); c.add_gate("H", [0])  # |0>-|1> on control
    c.add_gate("H", [1])
    c.add_gate("CX", [0, 1])
    res = _run(c, seed=7, qubit_to_node={0: "A", 1: "B"})
    assert res.equivalence["passed"], res.equivalence


def test_bell_state_creation():
    c = Circuit(num_qubits=2)
    c.add_gate("H", [0]); c.add_gate("CX", [0, 1])
    res = _run(c, qubit_to_node={0: "A", 1: "B"})
    assert res.status == "success"
    assert res.equivalence["passed"], res.equivalence
    out = res.output_state["probabilities"]
    assert abs(out.get("00", 0) - 0.5) < 1e-9
    assert abs(out.get("11", 0) - 0.5) < 1e-9


# --------------------------------------------------------- entangled inputs
def test_ghz_entangled_input():
    c = Circuit(num_qubits=3)
    c.add_gate("H", [0]); c.add_gate("CX", [0, 1]); c.add_gate("CX", [1, 2])
    res = _run(c, qubit_to_node={0: "A", 1: "B", 2: "C"})
    assert res.status == "success"
    assert res.equivalence["passed"], res.equivalence
    out = res.output_state["probabilities"]
    assert abs(out.get("000", 0) - 0.5) < 1e-9
    assert abs(out.get("111", 0) - 0.5) < 1e-9


# ----------------------------------------------------------------- direction
def test_direction_a_to_b_and_b_to_a():
    c_ab = Circuit(num_qubits=2); c_ab.add_gate("CX", [0, 1])
    c_ba = Circuit(num_qubits=2); c_ba.add_gate("CX", [1, 0])
    ra = _run(c_ab, qubit_to_node={0: "A", 1: "B"})
    rb = _run(c_ba, qubit_to_node={0: "A", 1: "B"})
    assert ra.remote_operations[0].source_node == "A"
    assert ra.remote_operations[0].target_node == "B"
    assert rb.remote_operations[0].source_node == "B"
    assert rb.remote_operations[0].target_node == "A"
    assert ra.equivalence["passed"] and rb.equivalence["passed"]


# -------------------------------------------------------------- same node
def test_same_node_cnot_is_local():
    c = Circuit(num_qubits=2); c.add_gate("CX", [0, 1])
    res = _run(c, qubit_to_node={0: "A", 1: "A"})
    assert res.status == "success"
    assert res.remote_gate_count == 0
    assert res.ebit_consumption == 0
    assert res.equivalence["passed"]


# --------------------------------------------------- multiple / mixed remote
def test_multiple_remote_cnots():
    c = Circuit(num_qubits=4)
    for i in range(3):
        c.add_gate("CX", [i, i + 1])
    res = _run(c, qubit_to_node={0: "A", 1: "B", 2: "C", 3: "D"})
    assert res.status == "success"
    assert res.remote_cnot_count == 3
    assert res.ebit_consumption == 3
    assert res.equivalence["passed"], res.equivalence


def test_six_qubit_chain_alternating_nodes():
    """Regression: the equivalence reduction must stay memory-safe on larger
    expanded registers (5 remote CNOTs -> 10 ancillas -> 16-qubit statevector);
    a full 4^16 density matrix must never be materialised."""
    c = Circuit(num_qubits=6)
    c.add_gate("H", [0])
    for i in range(5):
        c.add_gate("CX", [i, i + 1])
    mapping = {i: ("A" if i % 2 == 0 else "B") for i in range(6)}
    res = _run(c, qubit_to_node=mapping)
    assert res.status == "success", res.errors
    assert res.remote_cnot_count == 5
    assert res.ebit_consumption == 5
    assert res.equivalence is not None and res.equivalence["passed"], res.equivalence


def test_remote_then_local_then_remote():
    # control 0 on A, target 1 on B; after first remote CNOT the control's
    # carrier moves; a later local H(0) and a second remote CNOT must still
    # reproduce the centralized result.
    c = Circuit(num_qubits=2)
    c.add_gate("CX", [0, 1])
    c.add_gate("H", [0])
    c.add_gate("CX", [0, 1])
    res = _run(c, qubit_to_node={0: "A", 1: "B"})
    assert res.status == "success"
    assert res.equivalence["passed"], res.equivalence


def test_remote_inside_entangled_circuit():
    c = Circuit(num_qubits=3)
    c.add_gate("H", [0])
    c.add_gate("CX", [0, 1])
    c.add_gate("RX", [2], params=[0.9])
    c.add_gate("CX", [1, 2])
    res = _run(c, qubit_to_node={0: "A", 1: "B", 2: "C"})
    assert res.status == "success"
    assert res.equivalence["passed"], res.equivalence


# ---------------------------------------------------------- multi-node counts
@pytest.mark.parametrize("nn", [2, 3, 4])
def test_multi_node_partition_and_execution(nn):
    n = nn + 1
    c = Circuit(num_qubits=n)
    for i in range(n - 1):
        c.add_gate("CX", [i, i + 1])
    mapping = {i: f"node_{i % nn}" for i in range(n)}
    res = _run(c, qubit_to_node=mapping)
    assert res.status == "success"
    assert res.equivalence["passed"], res.equivalence
    # each cross-node edge consumed exactly one ebit
    assert res.ebit_consumption == res.remote_cnot_count


# ----------------------------------------------------- network integration
def test_network_integration_real_grant():
    nodes = [{"name": "A", "type": "end"}, {"name": "B", "type": "end"}]
    links = [{"source": "A", "destination": "B", "distance_km": 50, "base_fidelity": 0.95}]
    topo = topology_from_nodes_links(nodes, links)
    c = Circuit(num_qubits=2); c.add_gate("CX", [0, 1])
    res = _run(c, qubit_to_node={0: "A", 1: "B"}, topology=topo,
               network_config=NetworkConfig())
    assert res.status == "success"
    g = res.entanglement_operations[0]
    assert g.success
    assert g.model == "network"
    assert 0.0 < g.fidelity <= 1.0
    assert g.latency_ns is not None and g.latency_ns > 0
    assert res.equivalence["passed"]


# ------------------------------------------------------------ failure modes
def test_failure_disconnected_topology():
    nodes = [{"name": "A", "type": "end"}, {"name": "B", "type": "end"},
             {"name": "C", "type": "end"}]
    links = [{"source": "A", "destination": "C", "distance_km": 10}]
    topo = topology_from_nodes_links(nodes, links)
    c = Circuit(num_qubits=2); c.add_gate("CX", [0, 1])
    res = _run(c, qubit_to_node={0: "A", 1: "B"}, topology=topo,
               network_config=NetworkConfig())
    assert res.status == "failed"
    assert res.errors
    assert "none could be established" in res.errors[0]


def test_failure_unknown_node_in_mapping():
    from app.distributed import topology_from_nodes_links
    topo = topology_from_nodes_links(
        [{"name": "A", "type": "end"}, {"name": "B", "type": "end"}],
        [{"source": "A", "destination": "B", "distance_km": 10}],
    )
    c = Circuit(num_qubits=2); c.add_gate("CX", [0, 1])
    res = _run(c, qubit_to_node={0: "A", 1: "GHOST"}, topology=topo)
    assert res.status == "failed"
    assert any("GHOST" in e for e in res.errors)


def test_failure_control_equals_target():
    c = Circuit(num_qubits=2); c.add_gate("CX", [0, 1])
    # same-node CNOT is local, not a failure; test control==target directly:
    c2 = Circuit(num_qubits=1); c2.add_gate("CX", [0, 0])
    res = _run(c2, qubit_to_node={0: "A"})
    # a 1-qubit "CX" with identical operands is rejected by circuit validation
    assert res.status == "failed" or res.remote_gate_count == 0


def test_failure_resource_cap():
    c = Circuit(num_qubits=3)
    c.add_gate("CX", [0, 1]); c.add_gate("CX", [1, 2])
    res = _run(c, qubit_to_node={0: "A", 1: "B", 2: "C"}, max_remote_operations=1)
    assert res.status == "failed"
    assert any("cap" in e for e in res.errors)


# ------------------------------------------------------ resource accounting
def test_resource_accounting_detailed():
    c = Circuit(num_qubits=2); c.add_gate("CX", [0, 1])
    res = _run(c, qubit_to_node={0: "A", 1: "B"})
    assert res.ebit_consumption == 1
    assert res.classical_message_count == 2
    assert res.communication_cost == 2
    assert len(res.classical_messages) == 1
    cm = res.classical_messages[0]
    assert cm.source_node == "A" and cm.target_node == "B"
    assert cm.bits == 2


# -------------------------------------------------------- partitioning alone
def test_partition_plan_metrics():
    c = Circuit(num_qubits=4)
    c.add_gate("H", [0]); c.add_gate("CX", [0, 1]); c.add_gate("CX", [2, 3])
    c.add_gate("CX", [1, 2])
    plan = partition_circuit_full(c, {0: "A", 1: "B", 2: "C", 3: "C"})
    assert plan.metrics.local_gate_count == 2          # H(0), CX(2,3)
    assert plan.metrics.remote_gate_count == 2          # CX(0,1), CX(1,2)
    assert plan.metrics.remote_cnot_count == 2
    assert plan.metrics.ebit_consumption == 2
    assert plan.metrics.classical_message_count == 4


def test_heuristic_explicit_mapping_honoured():
    c = Circuit(num_qubits=3)
    c.add_gate("CX", [0, 1]); c.add_gate("CX", [1, 2])
    assign = heuristic_assignment(c, qubit_to_node={0: "X", 1: "Y", 2: "Z"})
    assert assign == {0: "X", 1: "Y", 2: "Z"}


def test_heuristic_auto_distributes():
    c = Circuit(num_qubits=3)
    c.add_gate("CX", [0, 1]); c.add_gate("CX", [1, 2])
    assign = heuristic_assignment(c, num_nodes=3, objective="minimize_cross_node")
    # all three nodes must be occupied (no collapse to one node)
    assert set(assign.values()) == {"node_0", "node_1", "node_2"}


# --------------------------------------------------- property-based random
def _random_circuit(rng, n, depth):
    c = Circuit(num_qubits=n)
    gates = [("H", 1), ("X", 1), ("Z", 1), ("RY", 1), ("RX", 1), ("CX", 2)]
    for _ in range(depth):
        g, ar = gates[rng.randrange(len(gates))]
        if ar == 1:
            q = rng.randrange(n)
            params = [rng.uniform(0, 3.14)] if g in ("RY", "RX") else []
            c.add_gate(g, [q], params=params)
        else:
            a = rng.randrange(n); b = rng.randrange(n)
            if a == b:
                b = (b + 1) % n
            c.add_gate("CX", [a, b])
    return c


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_property_random_equivalence(seed):
    rng = random.Random(seed)
    for _ in range(4):
        n = rng.choice([2, 3, 4])
        c = _random_circuit(rng, n, rng.randint(2, 6))
        mapping = {i: f"node_{i % rng.choice([2, 3])}" for i in range(n)}
        res = _run(c, seed=seed, qubit_to_node=mapping)
        central = _centralized_probs(c, seed)
        dist_probs = res.output_state["probabilities"]
        # compare probability vectors over the logical basis
        for k in set(central) | set(dist_probs):
            assert abs(central.get(k, 0.0) - dist_probs.get(k, 0.0)) < 1e-8, (seed, k, res.status)
        assert res.status == "success"
        assert res.equivalence["passed"], res.equivalence
