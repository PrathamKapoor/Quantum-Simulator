"""API tests for the distributed quantum-computing endpoints."""
import pytest
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


# ---------------------------------------------------------------------------
# Distributed experiments through the existing experiment API
# ---------------------------------------------------------------------------

CIRCUIT_GHZ = {
    "schema": "quantumlab.circuit", "version": 1, "name": "ghz",
    "num_qubits": 3, "num_clbits": 0, "metadata": {},
    "operations": [
        {"kind": "gate", "gate": "H", "params": [], "qubits": [0], "clbits": [], "condition": None},
        {"kind": "gate", "gate": "CX", "params": [], "qubits": [0, 1], "clbits": [], "condition": None},
        {"kind": "gate", "gate": "CX", "params": [], "qubits": [1, 2], "clbits": [], "condition": None},
    ],
}


@pytest.fixture()
def exp_client():
    """Lifespan-enabled client so STATE.service / job queue are available."""
    with TestClient(app) as c:
        yield c


def _create_distributed_experiment(c):
    return c.post("/api/experiments", json={
        "name": "distributed ghz study",
        "module": "distributed_circuit",
        "config": {
            "circuit": CIRCUIT_GHZ,
            "qubit_to_node": {0: "node_0", 1: "node_1", 2: "node_1"},
            "protocol": "single_ebit",
        },
        "seed": 13,
    })


def _wait_completed(c, run_id, timeout_s=15.0):
    """Poll until the run reaches a terminal state (worker is async)."""
    import time
    for _ in range(int(timeout_s * 10)):
        run = c.get(f"/api/runs/{run_id}").json()
        if run["status"] in ("COMPLETED", "FAILED", "CANCELLED"):
            return run
        time.sleep(0.1)
    return c.get(f"/api/runs/{run_id}").json()


def test_create_distributed_experiment_and_run(exp_client):
    r = _create_distributed_experiment(exp_client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["experiment_id"]
    run_ids = body["run_ids"]
    assert len(run_ids) >= 1

    # execute the single run and wait for the async worker to finish
    rid = run_ids[0]
    rr = exp_client.post(f"/api/runs/{rid}/execute")
    assert rr.status_code == 200
    assert rr.json()["job_id"]
    run = _wait_completed(exp_client, rid)
    assert run["status"] == "COMPLETED", run.get("error_message", run)

    # result endpoint serves the run-result document with distributed payload
    res = exp_client.get(f"/api/runs/{rid}/result")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["schema"] == "quantumlab.run-result"
    assert body["document"]["module"] == "distributed_circuit"
    assert body["document"]["metrics"]["status"] == "success"
    assert body["document"]["summary"]["equivalence"]["passed"]
    assert body["document"]["artifacts"]["distributed_result"]["schema"] == \
        "quantumlab.distributed-result"


def test_distributed_experiment_reproduce_immutable(exp_client):
    r = _create_distributed_experiment(exp_client)
    rid = r.json()["run_ids"][0]
    exp_client.post(f"/api/runs/{rid}/execute")
    _wait_completed(exp_client, rid)
    rep = exp_client.post(f"/api/runs/{rid}/reproduce")
    assert rep.status_code == 200, rep.text
    report = rep.json()
    assert report["reproduced_run_id"] != rid
    assert report["status"] == "EXACT_MATCH"
    # original run status left COMPLETED (immutable)
    orig_run = exp_client.get(f"/api/runs/{rid}").json()
    assert orig_run["status"] == "COMPLETED"


# ---------------------------------------------------------------------------
# Noisy ebits / Werner-model entanglement injection (AD-012)
# ---------------------------------------------------------------------------

NOISY_TOPO = {
    "nodes": [{"name": "A", "type": "end"}, {"name": "B", "type": "end"}],
    "links": [{"source": "A", "destination": "B", "distance_km": 0,
               "base_fidelity": 0.7}],
}


def test_simulate_network_fidelity_mode():
    r = client.post("/api/distributed/simulate", json={
        "circuit": CIRCUIT, "qubit_to_node": {0: "A", 1: "B"},
        "topology": NOISY_TOPO, "seed": 5, "ebit_noise": "network_fidelity"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    rop = body["remote_operations"][0]
    assert rop["ebit_fidelity"] == pytest.approx(0.7)
    assert rop["ebit_fidelity_applied"] == pytest.approx(0.7)
    assert len(rop["ebit_noise"]) == 1
    assert rop["ebit_noise"][0] in ("I", "X", "Y", "Z")
    assert body["reproducibility"]["ebit_noise"] == "network_fidelity"


def test_simulate_fixed_fidelity_F1_matches_legacy():
    legacy = client.post("/api/distributed/simulate", json={
        "circuit": CIRCUIT, "qubit_to_node": {0: "node_0", 1: "node_1"},
        "seed": 21}).json()
    f1 = client.post("/api/distributed/simulate", json={
        "circuit": CIRCUIT, "qubit_to_node": {0: "node_0", 1: "node_1"},
        "seed": 21, "ebit_noise": "fixed", "ebit_noise_fidelity": 1.0}).json()
    assert f1["status"] == "success"
    assert f1["output_state"]["probabilities"] == legacy["output_state"]["probabilities"]
    assert f1["equivalence"]["fidelity"] == 1.0


def test_simulate_fixed_fidelity_degrades():
    fids = []
    saw_noise = False
    for seed in range(5, 25):
        r = client.post("/api/distributed/simulate", json={
            "circuit": CIRCUIT, "qubit_to_node": {0: "node_0", 1: "node_1"},
            "seed": seed, "ebit_noise": "fixed", "ebit_noise_fidelity": 0.5})
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "success"
        fids.append(body["equivalence"]["fidelity"])
        if body["remote_operations"][0]["ebit_noise"] != ["I"]:
            saw_noise = True
    assert saw_noise
    assert sum(fids) / len(fids) < 1.0


def test_simulate_invalid_noise_mode_rejected():
    r = client.post("/api/distributed/simulate", json={
        "circuit": CIRCUIT, "qubit_to_node": {0: "node_0", 1: "node_1"},
        "ebit_noise": "bogus"})
    assert r.status_code == 422


def test_simulate_invalid_noise_fidelity_rejected():
    r = client.post("/api/distributed/simulate", json={
        "circuit": CIRCUIT, "qubit_to_node": {0: "node_0", 1: "node_1"},
        "ebit_noise": "fixed", "ebit_noise_fidelity": 1.5})
    assert r.status_code == 422


def test_noisy_distributed_experiment_run_and_reproduce(exp_client):
    r = exp_client.post("/api/experiments", json={
        "name": "noisy distributed ghz study",
        "module": "distributed_circuit",
        "config": {
            "circuit": CIRCUIT_GHZ,
            "qubit_to_node": {0: "node_0", 1: "node_1", 2: "node_1"},
            "protocol": "single_ebit",
            "ebit_noise": "fixed",
            "ebit_noise_fidelity": 0.9,
        },
        "seed": 13,
    })
    assert r.status_code == 200, r.text
    rid = r.json()["run_ids"][0]
    exp_client.post(f"/api/runs/{rid}/execute")
    run = _wait_completed(exp_client, rid)
    assert run["status"] == "COMPLETED", run.get("error_message", run)

    res = exp_client.get(f"/api/runs/{rid}/result").json()
    doc = res["document"]
    assert doc["metrics"]["ebit_noise"] == "fixed"
    assert doc["metrics"]["mean_ebit_fidelity"] == pytest.approx(0.9)
    dist = doc["artifacts"]["distributed_result"]
    assert dist["reproducibility"]["ebit_noise"] == "fixed"
    assert all(
        rop["ebit_fidelity_applied"] == pytest.approx(0.9)
        for rop in dist["remote_operations"] if rop["executed"]
    )
    # A noisy run is not expected to match the ideal centralized reference,
    # unless every sampled Werner component happened to be the ideal one
    # (probability F^(#ebits) for a fixed seed).
    components = [rop["ebit_noise"] for rop in dist["remote_operations"] if rop["executed"]]
    if all(c == ["I"] for c in components):
        assert doc["summary"]["equivalence"]["fidelity"] == 1.0
    else:
        assert doc["summary"]["equivalence"]["fidelity"] < 1.0

    # Reproduction: same noisy behavior, new run, original immutable.
    rep = exp_client.post(f"/api/runs/{rid}/reproduce")
    assert rep.status_code == 200, rep.text
    report = rep.json()
    assert report["reproduced_run_id"] != rid
    rep_run = exp_client.get(
        f"/api/runs/{report['reproduced_run_id']}/result").json()
    rep_dist = rep_run["document"]["artifacts"]["distributed_result"]
    assert rep_dist["reproducibility"]["ebit_noise"] == "fixed"
    assert (rep_dist["remote_operations"][0]["ebit_noise"]
            == dist["remote_operations"][0]["ebit_noise"])
    orig = exp_client.get(f"/api/runs/{rid}").json()
    assert orig["status"] == "COMPLETED"
