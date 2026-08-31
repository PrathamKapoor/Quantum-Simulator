"""API + experiment tests for repeated-round (space-time) surface-code decoding
(§57-§66)."""
import pytest
from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


class TestRepeatedRoundEndpoints:
    def test_decode_endpoint(self):
        r = client.post("/api/qec/rotated-surface-code/repeated-round/decode",
                        json={"d": 3, "rounds": 4, "p_data": 0.05,
                              "p_measurement": 0.05, "seed": 11})
        assert r.status_code == 200
        body = r.json()
        assert body["outcome"] in ("CORRECTED", "LOGICAL_X", "LOGICAL_Z",
                                   "LOGICAL_Y")
        assert body["rounds"] == 4
        assert len(body["observed_syndromes"]) == 4
        assert "layout" in body and body["layout"]["d"] == 3

    def test_simulate_endpoint_reproducible(self):
        payload = {"d": 3, "rounds": 3, "p_data": 0.03, "p_measurement": 0.03,
                   "trials": 300, "seed": 42}
        a = client.post("/api/qec/rotated-surface-code/repeated-round/simulate",
                        json=payload).json()
        b = client.post("/api/qec/rotated-surface-code/repeated-round/simulate",
                        json=payload).json()
        assert a == b
        assert a["ci95"][0] <= a["logical_error_rate"] <= a["ci95"][1]
        assert "PERFECT stabilizer" in a["note"] or "ideal" in a["note"]

    def test_invalid_rounds_rejected(self):
        r = client.post("/api/qec/rotated-surface-code/repeated-round/decode",
                        json={"d": 3, "rounds": 0})
        assert r.status_code == 422

    def test_invalid_probability_rejected(self):
        r = client.post("/api/qec/rotated-surface-code/repeated-round/simulate",
                        json={"d": 3, "rounds": 3, "p_data": 2.0, "trials": 100})
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


def test_repeated_round_experiment_end_to_end(exp_client):
    """Experiment through the real process-isolated worker path (§60-§61)."""
    r = exp_client.post("/api/experiments", json={
        "name": "rr qec study", "module": "repeated_round_surface_code",
        "config": {"distances": [3], "rounds": 3, "p_data": 0.03,
                   "p_measurement": 0.03, "trials_per_point": 400},
        "seed": 17})
    assert r.status_code == 200, r.text
    rid = r.json()["run_ids"][0]
    exp_client.post(f"/api/runs/{rid}/execute")
    run = _wait(exp_client, rid)
    assert run["status"] == "COMPLETED", run.get("error_message", run)

    res = exp_client.get(f"/api/runs/{rid}/result").json()
    doc = res["document"]
    assert doc["module"] == "repeated_round_surface_code"
    assert doc["metrics"]["rounds"] == 3
    assert doc["metrics"]["distances"] == [3]
    art = doc["artifacts"]["table"][0]
    assert art["d"] == 3 and art["rounds"] == 3
    assert art["ci95_low"] <= art["logical_error_rate"] <= art["ci95_high"]

    # reproduction (process boundary): EXACT_MATCH, original immutable
    rep = exp_client.post(f"/api/runs/{rid}/reproduce")
    assert rep.status_code == 200, rep.text
    assert rep.json()["status"] == "EXACT_MATCH"
    assert rep.json()["reproduced_run_id"] != rid
    assert exp_client.get(f"/api/runs/{rid}").json()["status"] == "COMPLETED"


def test_repeated_round_invalid_config_fails(exp_client):
    r = exp_client.post("/api/experiments", json={
        "name": "rr qec bad", "module": "repeated_round_surface_code",
        "config": {"distances": [3], "rounds": 0, "p_data": 0.03,
                   "p_measurement": 0.03, "trials_per_point": 100},
        "seed": 1})
    if r.status_code != 200:
        return  # validation may reject at create time
    rid = r.json()["run_ids"][0]
    exp_client.post(f"/api/runs/{rid}/execute")
    run = _wait(exp_client, rid)
    assert run["status"] == "FAILED"
    assert run["error_code"] or run["error_message"]