"""Multi-node circuit partitioner tests (§28-29)."""
import pytest

from app.circuits.model import Circuit
from app.distributed import partition_circuit, remote_gate_cost


def _sample_circuit() -> Circuit:
    """4-qubit circuit: two intra-node CXs, one cross-node CX, one
    three-qubit gate spanning two nodes (requires decomposition)."""
    c = Circuit(num_qubits=4, operations=[])
    c.add_gate("H", [0])
    c.add_gate("CX", [0, 1])      # node A local
    c.add_gate("CX", [2, 3])      # node B local
    c.add_gate("CX", [1, 2])      # cross node A <-> B
    c.add_gate("RY", [2], params=[0.3])
    c.add_gate("TOFFOLI", [0, 2, 3])  # spans nodes A, B, B -> 2 nodes but 3 qubits
    c.add_measure([3], [0])
    c.add_gate("X", [0])          # node A local
    return c


PARTITION_2NODE = {0: "NA", 1: "NA", 2: "NB", 3: "NB"}


def test_local_remote_split():
    c = _sample_circuit()
    res = partition_circuit(c, PARTITION_2NODE)
    assert set(res.node_ids) == {"NA", "NB"}
    # node A local gates: H(0), CX(0,1), X(0)
    na = [op.gate for op in res.local_operations["NA"]]
    assert "H" in na and "CX" in na and "X" in na
    # node B local: CX(2,3), RY(2), measure(3)
    nb_gates = [op.gate for op in res.local_operations["NB"]]
    nb_kinds = [op.kind for op in res.local_operations["NB"]]
    assert "CX" in nb_gates and "RY" in nb_gates and "measure" in nb_kinds


def test_cross_node_gate_detected():
    c = _sample_circuit()
    res = partition_circuit(c, PARTITION_2NODE)
    cross = [rg for rg in res.remote_gates if rg.gate == "CX" and set(rg.qubits) == {1, 2}]
    assert len(cross) == 1
    assert set(cross[0].nodes) == {"NA", "NB"}
    assert cross[0].supported_as_single_remote_cnot is True


def test_unsupported_requires_decomposition():
    c = _sample_circuit()
    res = partition_circuit(c, PARTITION_2NODE)
    # TOFFOLI(0,2,3) spans 2 nodes but is 3-qubit -> needs decomposition.
    tof = [rg for rg in res.remote_gates if rg.gate == "TOFFOLI"]
    assert len(tof) == 1
    assert tof[0].supported_as_single_remote_cnot is False
    assert tof[0] in res.requires_decomposition
    assert res.unsupported_remote_gate_count == 1


def test_cost_accounting():
    c = _sample_circuit()
    res = partition_circuit(c, PARTITION_2NODE)
    # Only one supported remote gate (CX 1<->2) -> single-ebit: 1 ebit, 2 cbits.
    assert res.supported_remote_gate_count == 1
    assert res.ebits_single_ebit == 1
    assert res.classical_bits_single_ebit == 2
    assert res.ebits_double_teleport == 2
    assert res.classical_bits_double_teleport == 4


def test_remote_gate_cost_convenience():
    c = _sample_circuit()
    single = remote_gate_cost(c, PARTITION_2NODE, protocol="single_ebit")
    assert single["ebits"] == 1 and single["classical_bits"] == 2
    assert single["unsupported_remote_gates"] == 1
    assert single["requires_decomposition"][0]["gate"] == "TOFFOLI"
    double = remote_gate_cost(c, PARTITION_2NODE, protocol="double_teleport")
    assert double["ebits"] == 2 and double["classical_bits"] == 4


def test_partition_must_cover_all_qubits():
    c = Circuit(num_qubits=3)
    c.add_gate("CX", [0, 1])
    with pytest.raises(ValueError):
        partition_circuit(c, {0: "NA", 1: "NA"})  # qubit 2 unassigned


def test_unassigned_partition_rejected():
    c = Circuit(num_qubits=2)
    with pytest.raises(ValueError):
        partition_circuit(c, {})
