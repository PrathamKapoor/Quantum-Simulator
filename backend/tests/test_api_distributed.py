"""API tests for the distributed quantum-computing endpoints."""
from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)

CIRCUIT = {
    "schema": "quantumlab.circuit", "version": 1, "name": "cnot",
    "num_qubits": 2, "num_clbits": 0, "metadata": {},
    "operations": [
        {"kind": "gate", "gate": "H", "params": [], "qubits": [0], "clbits": [], "condition": None},
        {"kind": "gate", "gate": "CX", "params": [], "qubits": [0, 1], "clbits": [], "condition": None},
    ],
}
TOPO = {
    "nodes": [{"name": "A", "type": "end"}, {"name": "B", "type": "end"}],
    "links": [{"source": "A", "destination": "B", "distance_km": 50, "base_fidelity": 0.95}],
}


def test_partition_endpoint():
    r = client.post("/api/distributed/partition", json={
        "circuit": CIRCUIT, "qubit_to_node": {0: "node_0", 1: "node_1"}})
    assert r.status_code == 200
    body = r.json()
    assert body["remote_operations"][0]["gate"] == "CX"
    assert body["metrics"]["remote_cnot_count"] == 1


def test_simulate_endpoint_success():
    r = client.post("/api/distributed/simulate", json={
        "circuit": CIRCUIT, "protocol": "single_ebit",
        "qubit_to_node": {0: "node_0", 1: "node_1"}, "seed": 11})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["equivalence"]["passed"]
    assert body["ebit_consumption"] == 1


def test_remote_cnot_endpoint():
    r = client.post("/api/distributed/remote-cnot", json={
        "control_qubit": 0, "target_qubit": 1,
        "qubit_to_node": {0: "A", 1: "B"}, "protocol": "single_ebit"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["equivalence"]["fidelity"] == 1.0


def test_simulate_networked_endpoint():
    r = client.post("/api/distributed/simulate", json={
        "circuit": CIRCUIT, "qubit_to_node": {0: "A", 1: "B"},
        "topology": TOPO, "seed": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["entanglement_operations"][0]["fidelity"] > 0.0
    assert body["entanglement_operations"][0]["model"] == "network"


def test_simulate_disconnected_failure():
    topo = {
        "nodes": [{"name": "A", "type": "end"}, {"name": "B", "type": "end"}, {"name": "C", "type": "end"}],
        "links": [{"source": "A", "destination": "C", "distance_km": 10}],
    }
    r = client.post("/api/distributed/simulate", json={
        "circuit": CIRCUIT, "qubit_to_node": {0: "A", 1: "B"},
        "topology": topo})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "failed"
    assert body["errors"]


def test_invalid_circuit_schema_rejected():
    r = client.post("/api/distributed/simulate", json={"circuit": {"foo": 1}})
    assert r.status_code in (400, 422)
