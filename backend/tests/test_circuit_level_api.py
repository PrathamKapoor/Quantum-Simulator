"""API + experiment tests for circuit-level surface-code decoding."""
import pytest
from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


class TestCircuitLevelEndpoints:
    def test_decode_endpoint(self):
        r = client.post("/api/qec/rotated-surface-code/circuit-level/decode",
                        json={"d": 3, "rounds": 3, "p_gate": 0.005,
                              "p_readout": 0.005, "p_reset": 0.003,
                              "p_prep": 0.003, "seed": 11})
        assert r.status_code == 200
        body = r.json()
        assert body["outcome"] in ("CORRECTED", "LOGICAL_X", "LOGICAL_Z", "LOGICAL_Y")
        assert body["rounds"] == 3
        assert "layout" in body
        assert "decoder" in body and body["decoder"] == "mwpm"

    def test_simulate_endpoint_reproducible(self):
        payload = {"d": 3, "rounds": 3, "p_gate": 0.005, "p_readout": 0.005,
                   "p_reset": 0.003, "p_prep": 0.003, "trials": 300, "seed": 42}
        a = client.post("/api/qec/rotated-surface-code/circuit-level/simulate",
                        json=payload).json()
        b = client.post("/api/qec/rotated-surface-code/circuit-level/simulate",
                        json=payload).json()
        assert a == b
        assert a["ci95"][0] <= a["logical_error_rate"] <= a["ci95"][1]
        assert "hook_error_events" in a

    def test_invalid_probability_rejected(self):
        r = client.post("/api/qec/rotated-surface-code/circuit-level/simulate",
                        json={"d": 3, "rounds": 3, "p_gate": 2.0, "trials": 100})
        assert r.status_code == 422

    def test_decode_with_correlation_decoder(self):
        r = client.post("/api/qec/rotated-surface-code/circuit-level/decode",
                        json={"d": 3, "rounds": 2, "p_gate": 0.01,
                              "p_readout": 0.005, "p_reset": 0.003,
                              "p_prep": 0.003, "seed": 9,
                              "extraction_model": "fitted_pair",
                              "decoder": "correlation_aware"})
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["decoder"] == "correlation_aware"
        assert b["decoder_requested"] == "correlation_aware"
        assert b["outcome"] in ("CORRECTED", "LOGICAL_X", "LOGICAL_Z",
                                "LOGICAL_Y")
        assert b["best_source"] in ("phenomenological", "signature")
        assert "n_candidates" in b and "attributed_signature" in b

    def test_simulate_with_correlation_decoder_reproducible(self):
        payload = {"d": 3, "rounds": 2, "p_gate": 0.005, "p_readout": 0.005,
                   "p_reset": 0.003, "p_prep": 0.003, "trials": 100,
                   "seed": 3, "extraction_model": "fitted_pair",
                   "decoder": "correlation_aware"}
        a = client.post("/api/qec/rotated-surface-code/circuit-level/simulate",
                        json=payload)
        b = client.post("/api/qec/rotated-surface-code/circuit-level/simulate",
                        json=payload)
        assert a.status_code == b.status_code == 200
        ra, rb = a.json(), b.json()
        assert ra["decoder"] == "correlation_aware"
        assert ra["logical_failures"] == rb["logical_failures"]
        assert ra["signature_attributions"] == rb["signature_attributions"]

    def test_invalid_decoder_rejected(self):
        r = client.post("/api/qec/rotated-surface-code/circuit-level/decode",
                        json={"d": 3, "decoder": "magic_decoder"})
        assert r.status_code == 422


@pytest.fixture()
def exp_client():
    with TestClient(app) as c:
        yield c


def _wait(c, rid, timeout=90.0):
    import time
    for _ in range(int(timeout * 10)):
        run = c.get(f"/api/runs/{rid}").json()
        if run["status"] in ("COMPLETED", "FAILED", "CANCELLED"):
            return run
        time.sleep(0.1)
    return c.get(f"/api/runs/{rid}").json()

def test_circuit_level_experiment_end_to_end(exp_client):
    r = exp_client.post("/api/experiments", json={
        "name": "cl qec study", "module": "surface_code_circuit_level",
        "config": {"distances": [3], "rounds": 3, "p_gate": 0.005,
                   "p_readout": 0.005, "p_reset": 0.003, "p_prep": 0.003,
                   "trials_per_point": 400},
        "seed": 17})
    assert r.status_code == 200, r.text
    rid = r.json()["run_ids"][0]
    exp_client.post(f"/api/runs/{rid}/execute")
    run = _wait(exp_client, rid)
    assert run["status"] == "COMPLETED", run.get("error_message", run)

    doc = exp_client.get(f"/api/runs/{rid}/result").json()["document"]
    assert doc["module"] == "surface_code_circuit_level"
    art = doc["artifacts"]["table"][0]
    assert art["d"] == 3 and "hook_error_events" in art
    assert art["ci95_low"] <= art["logical_error_rate"] <= art["ci95_high"]

    rep = exp_client.post(f"/api/runs/{rid}/reproduce")
    assert rep.status_code == 200, rep.text
    assert rep.json()["status"] == "EXACT_MATCH"

def test_circuit_level_experiment_correlation_decoder(exp_client):
    """The decoder option passes through the process-isolated worker
    boundary (directive §36) and reproduces exactly."""
    r = exp_client.post("/api/experiments", json={
        "name": "cl qec corr decoder", "module": "surface_code_circuit_level",
        "config": {"distances": [3], "rounds": 3, "p_gate": 0.005,
                   "p_readout": 0.005, "p_reset": 0.003, "p_prep": 0.003,
                   "trials_per_point": 200, "extraction_model": "fitted_pair",
                   "decoder": "correlation_aware"},
        "seed": 21})
    assert r.status_code == 200, r.text
    rid = r.json()["run_ids"][0]
    exp_client.post(f"/api/runs/{rid}/execute")
    run = _wait(exp_client, rid)
    assert run["status"] == "COMPLETED", run.get("error_message", run)
    doc = exp_client.get(f"/api/runs/{rid}/result").json()["document"]
    assert doc["metrics"]["decoder"] == "correlation_aware"
    art = doc["artifacts"]["table"][0]
    assert art["ci95_low"] <= art["logical_error_rate"] <= art["ci95_high"]
    rep = exp_client.post(f"/api/runs/{rid}/reproduce")
    assert rep.status_code == 200, rep.text
    assert rep.json()["status"] == "EXACT_MATCH"
