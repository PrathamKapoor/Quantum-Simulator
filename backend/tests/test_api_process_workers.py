"""API-level acceptance for process-isolated execution (directive §101, §151).

The API contract must be unchanged: create -> queue -> worker process ->
progress -> completion -> result; plus failure and cancellation paths.
"""
import time

import pytest
from fastapi.testclient import TestClient

from app.api.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _wait_run(c, run_id, statuses=("COMPLETED", "FAILED", "CANCELLED"),
              timeout_s=90.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        run = c.get(f"/api/runs/{run_id}").json()
        if run["status"] in statuses:
            return run
        time.sleep(0.1)
    return c.get(f"/api/runs/{run_id}").json()


def _probe_experiment(c, action, name="api probe"):
    r = c.post("/api/experiments", json={
        "name": name,
        "module": "process_probe",
        "config": {"action": action},
        "seed": 3,
    })
    assert r.status_code == 200, r.text
    return r.json()["run_ids"][0]


class TestApiLifecycle:
    def test_success_lifecycle_through_process(self, client):
        rid = _probe_experiment(client, "succeed", "api success")
        r = client.post(f"/api/runs/{rid}/execute")
        assert r.status_code == 200
        assert r.json()["job_id"]
        run = _wait_run(client, rid)
        assert run["status"] == "COMPLETED"
        res = client.get(f"/api/runs/{rid}/result").json()
        assert res["document"]["metrics"]["action"] == "succeed"

    def test_worker_exception_records_failed(self, client):
        rid = _probe_experiment(client, "fail", "api failure")
        client.post(f"/api/runs/{rid}/execute")
        run = _wait_run(client, rid)
        assert run["status"] == "FAILED"
        assert "intentional probe failure" in run["error_message"]
        r = client.get(f"/api/runs/{rid}/result")
        assert r.status_code == 404  # no fabricated result
        # API remains healthy after the failure
        assert client.get("/api/qec/codes").status_code == 200

    def test_worker_hard_exit_records_failed_and_api_survives(self, client):
        """§24/§156: the central crash demonstration over the real API."""
        rid = _probe_experiment(client, "hard_exit", "api crash")
        client.post(f"/api/runs/{rid}/execute")
        run = _wait_run(client, rid)
        assert run["status"] == "FAILED"
        assert run["error_code"] == "WorkerAborted"
        # next experiment executes successfully afterwards
        rid2 = _probe_experiment(client, "succeed", "api after crash")
        client.post(f"/api/runs/{rid2}/execute")
        run2 = _wait_run(client, rid2)
        assert run2["status"] == "COMPLETED"

    def test_running_cancellation_via_api(self, client):
        # long-running probe; give the child time to spawn
        r = client.post("/api/experiments", json={
            "name": "api cancel", "module": "process_probe",
            "config": {"action": "slow", "seconds": 60}, "seed": 3})
        rid = r.json()["run_ids"][0]
        client.post(f"/api/runs/{rid}/execute")
        deadline = time.monotonic() + 60
        job_id = None
        while time.monotonic() < deadline:
            jobs = client.get("/api/jobs").json()
            mine = [j for j in jobs if j["payload"].get("run_id") == rid]
            if mine and mine[0]["status"] == "RUNNING":
                job_id = mine[0]["job_id"]
                break
            time.sleep(0.1)
        assert job_id is not None, "job never reached RUNNING"
        r = client.post(f"/api/jobs/{job_id}/cancel")
        assert r.status_code == 200
        run = _wait_run(client, rid, statuses=("CANCELLED", "COMPLETED",
                                               "FAILED"))
        assert run["status"] == "CANCELLED"

    def test_reproduction_endpoint_through_process(self, client):
        rid = _probe_experiment(client, "succeed", "api repro")
        client.post(f"/api/runs/{rid}/execute")
        _wait_run(client, rid)
        rep = client.post(f"/api/runs/{rid}/reproduce")
        assert rep.status_code == 200
        report = rep.json()
        assert report["status"] == "EXACT_MATCH"
        assert report["reproduced_run_id"] != rid
