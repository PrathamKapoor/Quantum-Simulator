"""API tests via TestClient: endpoints, validation, health, experiment flow."""
import time

import pytest
from fastapi.testclient import TestClient

from app.api.main import app, STATE


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def bell_document():
    from app.circuits import Circuit, circuit_to_dict

    c = Circuit(num_qubits=2, num_clbits=2)
    c.add_gate("H", [0]).add_gate("CX", [0, 1])
    c.add_measure([0, 1], [0, 1])
    return circuit_to_dict(c)


class TestHealth:
    def test_health_endpoint_reports_all_subsystems(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        for name in ("database", "quantum_engine", "network_engine", "worker"):
            assert name in body["checks"]
            assert body["checks"][name]["status"] == "ok"


class TestCircuitEndpoints:
    def test_execute_bell(self, client):
        r = client.post("/api/circuits/execute", json={
            "circuit": bell_document(), "shots": 500, "seed": 3,
        })
        assert r.status_code == 200
        body = r.json()
        assert set(body["counts"]) <= {"00", "11"}
        assert sum(body["counts"].values()) == 500

    def test_validate_rejects_bad_circuit(self, client):
        doc = bell_document()
        doc["operations"][0]["qubits"] = [77]
        r = client.post("/api/circuits/validate", json={"circuit": doc})
        body = r.json()
        assert body["valid"] is False
        codes = {i["code"] for i in body["issues"]}
        assert "BAD_QUBIT" in codes

    def test_rejects_invalid_shots(self, client):
        r = client.post("/api/circuits/execute", json={
            "circuit": bell_document(), "shots": -1,
        })
        assert r.status_code == 422

    def test_statevector_response_includes_amplitudes(self, client):
        r = client.post("/api/circuits/execute", json={
            "circuit": bell_document(), "shots": None,
        })
        body = r.json()
        assert "statevector" in body
        keys = sorted(body["statevector"])
        assert keys == ["00", "11"]


class TestAlgorithmEndpoints:
    def test_grover(self, client):
        r = client.post("/api/algorithms/grover",
                        json={"n_qubits": 3, "marked_index": 5, "shots": 512})
        assert r.status_code == 200
        body = r.json()
        assert body["success_probability"] > 0.8

    def test_bv(self, client):
        r = client.post("/api/algorithms/bv", json={"secret": "101"})
        body = r.json()
        assert body["correct"]

    def test_superdense(self, client):
        r = client.post("/api/algorithms/superdense", json={"bits": "10"})
        body = r.json()
        assert body["success_rate"] == 1.0

    def test_order_finding(self, client):
        r = client.post("/api/algorithms/order-finding", json={"a": 7, "N": 15})
        body = r.json()
        assert body["true_order"] == 4

    def test_order_finding_rejects_noncoprime(self, client):
        r = client.post("/api/algorithms/order-finding", json={"a": 5, "N": 15})
        assert r.status_code == 400


class TestProtocolEndpoints:
    def test_bb84_no_eve_low_qber(self, client):
        r = client.post("/api/protocols/bb84", json={"n_qubits": 512, "seed": 5})
        body = r.json()
        assert body["qber"] == 0.0

    def test_bb84_eve_raises_qber(self, client):
        r = client.post("/api/protocols/bb84", json={
            "n_qubits": 1024, "eve_intercept_probability": 1.0, "seed": 6})
        body = r.json()
        assert 0.15 < body["qber"] < 0.35

    def test_chsh_violation(self, client):
        r = client.post("/api/protocols/chsh", json={"state_fidelity": 1.0})
        body = r.json()
        assert abs(body["chsh_S"]) > 2.5

    def test_qrng_stats(self, client):
        r = client.post("/api/protocols/qrng", json={"n_bits": 2048})
        body = r.json()
        assert abs(body["fraction_of_ones"] - 0.5) < 0.05


class TestQECEndpoints:
    def test_codes_listed(self, client):
        r = client.get("/api/qec/codes")
        names = {c["name"] for c in r.json()}
        assert {"bit-flip-3", "shor-9", "steane-7", "five-qubit"} <= names

    def test_sweep_returns_table(self, client):
        r = client.post("/api/qec/sweep", json={
            "code": "bit-flip-3",
            "physical_error_rates": [0.001, 0.05],
            "trials": 1500,
        })
        table = r.json()["table"]
        assert len(table) == 2
        assert table[0]["logical_error_rate"] < table[1]["logical_error_rate"]

    def test_surface_code_layout(self, client):
        r = client.post("/api/qec/surface-code", json={"d": 3, "trials": 800})
        body = r.json()
        assert body["layout"]["d"] == 3
        assert len(body["layout"]["edges"]) == 18


class TestNetworkEndpoint:
    def _topology(self):
        return {
            "nodes": [
                {"name": "Alice", "type": "end", "memory_slots": 8},
                {"name": "R1", "type": "repeater", "memory_slots": 8},
                {"name": "Bob", "type": "end", "memory_slots": 8},
            ],
            "links": [
                {"source": "Alice", "destination": "R1", "distance_km": 20},
                {"source": "R1", "destination": "Bob", "distance_km": 20},
            ],
        }

    def test_simulate_chain_with_swap(self, client):
        payload = {
            **self._topology(),
            "requests": [{"source": "Alice", "destination": "Bob"}],
            "sim_time_ms": 100,
            "seed": 9,
        }
        r = client.post("/api/network/simulate", json=payload)
        assert r.status_code == 200
        body = r.json()
        assert body["success_count"] >= 1
        assert body["stats"]["swaps_performed"] >= 1
        assert any("request_completed" in line for line in body["event_log"])

    def test_route_explanation(self, client):
        payload = {
            **self._topology(),
            "requests": [{"source": "Alice", "destination": "Bob"}],
        }
        r = client.post("/api/network/route", json=payload)
        routes = r.json()["routes"]
        assert routes[0]["route"][0] == "Alice"
        assert "Route" in routes[0]["explanation"]

    def test_unknown_node_rejected(self, client):
        payload = dict(self._topology())
        payload["nodes"] = self._topology()["nodes"][:1]
        r = client.post("/api/network/simulate", json=payload)
        assert r.status_code == 400


class TestExperimentFlow:
    def test_full_experiment_lifecycle_over_api(self, client):
        # create
        r = client.post("/api/experiments", json={
            "name": "API Bell study",
            "module": "circuit_shots",
            "config": {"circuit": bell_document(), "shots": 256},
            "seed": 21,
            "objective": "verify API flow",
        })
        assert r.status_code == 200
        exp_id = r.json()["experiment_id"]
        run_id = r.json()["run_ids"][0]
        # execute (background job)
        r = client.post(f"/api/runs/{run_id}/execute")
        assert r.status_code == 200
        job_id = r.json()["job_id"]
        # poll until done
        for _ in range(120):
            jobs = {j["job_id"]: j for j in client.get("/api/jobs").json()}
            if jobs[job_id]["status"] in ("COMPLETED", "FAILED"):
                break
            time.sleep(0.1)
        assert jobs[job_id]["status"] == "COMPLETED"
        # result retrieval
        res = client.get(f"/api/runs/{run_id}/result")
        assert res.status_code == 200
        assert res.json()["document"]["metrics"]["shots"] == 256
        # listed in experiments
        listing = client.get("/api/experiments").json()
        assert any(e["id"] == exp_id for e in listing)

    def test_unknown_module_rejected(self, client):
        r = client.post("/api/experiments", json={
            "name": "bad", "module": "cold_fusion", "config": {}, "seed": 1,
        })
        assert r.status_code == 400


class TestQuantumInfoEndpoint:
    def test_bell_state_report(self, client):
        doc = bell_document()  # H + CX -> Bell state (measure ops ignored for pure evolution? they are terminal)
        r = client.post("/api/quantum-info/state-report", json={"circuit": doc})
        assert r.status_code == 200
        rep = r.json()["report"]
        # Terminal measurements don't collapse in no-shot mode: Bell state.
        assert rep["concurrence"] == pytest.approx(1.0, abs=1e-6)
        assert rep["negativity"] == pytest.approx(0.5, abs=1e-6)
        assert rep["mutual_information_bits"] == pytest.approx(2.0, abs=1e-6)
        assert rep["conditional_entropy_bits"] == pytest.approx(-1.0, abs=1e-6)

    def test_product_state_report(self, client):
        doc = {"schema": "quantumlab.circuit", "version": 1, "name": "prod",
               "num_qubits": 2, "num_clbits": 0, "metadata": {},
               "operations": [
                   {"kind": "gate", "gate": "X", "params": [], "qubits": [0], "clbits": [], "condition": None}]}
        rep = client.post("/api/quantum-info/state-report", json={"circuit": doc}).json()["report"]
        assert rep["concurrence"] == pytest.approx(0.0, abs=1e-9)
        assert rep["separability"]["verdict"] == "separable"

    def test_rejects_too_large(self, client):
        doc = {"schema": "quantumlab.circuit", "version": 1, "name": "big",
               "num_qubits": 12, "num_clbits": 0, "metadata": {}, "operations": []}
        r = client.post("/api/quantum-info/state-report", json={"circuit": doc})
        assert r.status_code == 400


class TestHardwareEndpoints:
    def test_profiles_listed(self, client):
        r = client.get("/api/hardware/profiles")
        names = {p["name"] for p in r.json()}
        assert {"Ideal-8Q", "NoisyGeneric-8Q", "SuperconductingInspired-16Q"} <= names
        for p in r.json():
            assert "MODEL" in p["model_label"].upper()

    def _bell(self):
        return bell_document()

    def test_transpile_inserts_swaps_on_line(self, client):
        doc = self._bell()
        # Force long-range CX by using qubits 0 and 4 on a 5-qubit circuit.
        doc = dict(doc)
        doc.update(num_qubits=5, num_clbits=0, operations=[
            {"kind": "gate", "gate": "H", "params": [], "qubits": [0], "clbits": [], "condition": None},
            {"kind": "gate", "gate": "CX", "params": [], "qubits": [0, 4], "clbits": [], "condition": None},
        ])
        r = client.post("/api/hardware/transpile", json={
            "circuit": doc, "profile_name": "NoisyGeneric-8Q"})
        body = r.json()
        assert body["metrics"]["swap_count"] >= 3
        assert body["verification"]["verified"]

    def test_analyze_endpoint(self, client):
        r = client.post("/api/circuits/analyze", json={"circuit": self._bell()})
        d = r.json()
        assert d["two_qubit_gate_count"] == 1
        assert d["depth"] == 3  # H -> CX -> measure layers

    def test_unknown_profile_rejected(self, client):
        r = client.post("/api/hardware/transpile", json={
            "circuit": self._bell(), "profile_name": "QuantumDot-99"})
        assert r.status_code == 400


class TestMitigationEndpoints:
    def test_readout_mitigation(self, client):
        r = client.post("/api/mitigation/readout", json={
            "counts": {"00": 470, "01": 20, "10": 8, "11": 502},
            "p_read1_given_0": 0.04, "p_read0_given_1": 0.03})
        body = r.json()
        leak_raw = sum(v for k, v in body["raw_probabilities"].items() if k in ("01", "10"))
        leak_mit = sum(v for k, v in body["mitigated_probabilities"].items() if k in ("01", "10"))
        assert leak_mit < leak_raw

    def test_zne_endpoint_flags_unstable_fit(self, client):
        r = client.post("/api/mitigation/zne", json={
            "scale_factors": [1, 3], "estimates": [0.2, 0.19]})
        body = r.json()
        assert body["extrapolated_value"] > 0.2
