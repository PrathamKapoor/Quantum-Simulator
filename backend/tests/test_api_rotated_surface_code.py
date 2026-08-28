"""API + experiment tests for the rotated planar surface code (§97-§99)."""
import pytest
from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Decode endpoint
# ---------------------------------------------------------------------------

class TestDecodeEndpoint:
    def test_sampled_error_decodes(self):
        r = client.post("/api/qec/rotated-surface-code/decode", json={
            "d": 3, "physical_error_rate": 0.05, "seed": 11})
        assert r.status_code == 200
        body = r.json()
        assert body["outcome"] in ("CORRECTED", "LOGICAL_X", "LOGICAL_Z",
                                   "LOGICAL_Y")
        assert body["decoder"] == "mwpm"
        assert body["seed"] == 11
        assert len(body["layout"]["data_qubits"]) == 9
        assert len(body["layout"]["checks"]) == 8

    def test_explicit_single_error_corrected(self):
        r = client.post("/api/qec/rotated-surface-code/decode", json={
            "d": 3, "error": "XIIIIIIII"})
        assert r.status_code == 200
        assert r.json()["outcome"] == "CORRECTED"
        assert r.json()["error_support"]["X"] == [8]  # leftmost char = qubit 8

    def test_explicit_logical_error_flagged(self):
        # Logical X column x=3 for d=3: data qubits (3,1),(3,3),(3,5) ->
        # indices 1, 4, 7 -> string positions 9-1-idx.
        col = [1, 4, 7]
        chars = ["I"] * 9
        for q in col:
            chars[9 - 1 - q] = "X"
        r = client.post("/api/qec/rotated-surface-code/decode", json={
            "d": 3, "error": "".join(chars)})
        assert r.status_code == 200
        body = r.json()
        assert body["outcome"] == "LOGICAL_X"
        assert body["success"] is False
        assert all(v == 0 for v in body["syndrome_z"])  # zero syndrome...

    def test_result_carries_matching_and_correction(self):
        r = client.post("/api/qec/rotated-surface-code/decode", json={
            "d": 5, "physical_error_rate": 0.2, "seed": 2})
        body = r.json()
        for m in body["matching"]:
            assert m["kind"] in ("pair", "boundary")
            assert m["pauli"] in ("X", "Z")
            assert m["weight"] >= 1
            assert len(m["chain"]) >= 1
        if body["outcome"] != "DECODER_ERROR":
            assert body["matching_weight"] == sum(
                m["weight"] for m in body["matching"])

    def test_invalid_distance_rejected(self):
        r = client.post("/api/qec/rotated-surface-code/decode", json={"d": 4})
        assert r.status_code == 400

    def test_invalid_error_length_rejected(self):
        r = client.post("/api/qec/rotated-surface-code/decode", json={
            "d": 5, "error": "XXXXX"})
        assert r.status_code == 400

    def test_invalid_pauli_chars_rejected_by_schema(self):
        r = client.post("/api/qec/rotated-surface-code/decode", json={
            "d": 3, "error": "XXXQXXXXX"})
        assert r.status_code == 422

    def test_invalid_probability_rejected(self):
        r = client.post("/api/qec/rotated-surface-code/decode", json={
            "d": 3, "physical_error_rate": 2.0})
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# Simulate endpoint
# ---------------------------------------------------------------------------

class TestSimulateEndpoint:
    def test_simulate_reproducible(self):
        payload = {"d": 3, "physical_error_rate": 0.05, "trials": 300,
                   "seed": 42}
        a = client.post("/api/qec/rotated-surface-code/simulate",
                        json=payload).json()
        b = client.post("/api/qec/rotated-surface-code/simulate",
                        json=payload).json()
        assert a == b
        assert a["trials"] == 300
        assert a["ci95"][0] <= a["logical_error_rate"] <= a["ci95"][1]

    def test_simulate_invalid_trials(self):
        r = client.post("/api/qec/rotated-surface-code/simulate", json={
            "d": 3, "physical_error_rate": 0.05, "trials": 10})
        assert r.status_code == 422

    def test_simulate_note_is_honest(self):
        body = client.post("/api/qec/rotated-surface-code/simulate", json={
            "d": 3, "physical_error_rate": 0.05, "trials": 200}).json()
        assert "PERFECT syndrome" in body["note"]
        assert "not a hardware threshold" in body["note"]


# ---------------------------------------------------------------------------
# Experiment runner integration (§63-§65, §97-§99)
# ---------------------------------------------------------------------------

@pytest.fixture()
def exp_client():
    with TestClient(app) as c:
        yield c


def _wait_completed(c, run_id, timeout_s=20.0):
    import time
    for _ in range(int(timeout_s * 10)):
        run = c.get(f"/api/runs/{run_id}").json()
        if run["status"] in ("COMPLETED", "FAILED", "CANCELLED"):
            return run
        time.sleep(0.1)
    return c.get(f"/api/runs/{run_id}").json()


def _create_surface_experiment(c, distances=(3, 5),
                               name="surface code mwpm study"):
    return c.post("/api/experiments", json={
        "name": name,
        "module": "surface_code_mwpm",
        "config": {
            "distances": distances,
            "physical_error_permille": [20, 50],
            "trials_per_point": 300,
            "error_model": "depolarizing",
        },
        "seed": 17,
    })


def test_surface_code_experiment_end_to_end(exp_client):
    r = _create_surface_experiment(exp_client)
    assert r.status_code == 200, r.text
    rid = r.json()["run_ids"][0]
    exp_client.post(f"/api/runs/{rid}/execute")
    run = _wait_completed(exp_client, rid)
    assert run["status"] == "COMPLETED", run.get("error_message", run)

    res = exp_client.get(f"/api/runs/{rid}/result").json()
    doc = res["document"]
    assert doc["module"] == "surface_code_mwpm"
    assert doc["metrics"]["trials_total"] == 1200
    table = doc["artifacts"]["table"]
    assert len(table) == 4
    for row in table:
        assert {"d", "physical_error_rate", "logical_error_rate",
                "ci95_low", "ci95_high", "trials", "seed"} <= set(row)
        assert row["ci95_low"] <= row["logical_error_rate"] <= row["ci95_high"]
    # physical p and logical p_L are distinct, explicitly named fields
    assert any(row["physical_error_rate"] != row["logical_error_rate"]
               for row in table)

    # reproduction: new run, identical aggregate results, original immutable
    rep = exp_client.post(f"/api/runs/{rid}/reproduce")
    assert rep.status_code == 200, rep.text
    report = rep.json()
    assert report["reproduced_run_id"] != rid
    assert report["status"] == "EXACT_MATCH"
    orig = exp_client.get(f"/api/runs/{rid}").json()
    assert orig["status"] == "COMPLETED"


def test_surface_code_comparison_d3_vs_d5(exp_client):
    r3 = _create_surface_experiment(exp_client, [3], name="surface d3")
    r5 = _create_surface_experiment(exp_client, [5], name="surface d5")
    assert r3.status_code == 200 and r5.status_code == 200
    rid3, rid5 = r3.json()["run_ids"][0], r5.json()["run_ids"][0]
    exp_client.post(f"/api/runs/{rid3}/execute")
    exp_client.post(f"/api/runs/{rid5}/execute")
    run3 = _wait_completed(exp_client, rid3)
    run5 = _wait_completed(exp_client, rid5)
    assert run3["status"] == "COMPLETED"
    assert run5["status"] == "COMPLETED"

    doc3 = exp_client.get(f"/api/runs/{rid3}/result").json()["document"]
    doc5 = exp_client.get(f"/api/runs/{rid5}/result").json()["document"]
    assert doc3["metrics"]["distances"] == [3]
    assert doc5["metrics"]["distances"] == [5]
    # same physical p, and at p=0.02 the larger code should do at least as
    # well in this bounded study (statistical comparison, not a threshold)
    t3 = {round(row["physical_error_rate"], 4): row
          for row in doc3["artifacts"]["table"]}
    t5 = {round(row["physical_error_rate"], 4): row
          for row in doc5["artifacts"]["table"]}
    assert set(t3) == set(t5)
    assert t5[0.02]["logical_error_rate"] <= t3[0.02]["logical_error_rate"]

    cmp = exp_client.post("/api/experiments/compare", json={
        "run_ids": [rid3, rid5]})
    assert cmp.status_code == 200, cmp.text
