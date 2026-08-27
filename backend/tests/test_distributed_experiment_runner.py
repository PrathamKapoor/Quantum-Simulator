"""Tests for the distributed circuit experiment runner integration."""
import pytest

from app.experiments.runner import run_distributed_circuit, ExperimentSpec
from app.experiments.service import ExperimentService
from app.circuits.model import Circuit
from app.circuits import circuit_to_dict


def make_cnot_circuit():
    """Create a simple 2-qubit CNOT circuit for testing (no measurements)."""
    c = Circuit(num_qubits=2, name="cnot-test")
    c.add_gate("H", [0])
    c.add_gate("CX", [0, 1])
    return c


def test_run_distributed_circuit_basic():
    """Test basic distributed circuit execution through the runner."""
    circuit = make_cnot_circuit()

    config = {
        "circuit": circuit_to_dict(circuit),
        "qubit_to_node": {0: "node_0", 1: "node_1"},
        "protocol": "single_ebit",
    }

    result = run_distributed_circuit(config, seed=42)

    assert result["schema"] == "quantumlab.run-result"
    assert result["version"] == 1
    assert result["module"] == "distributed_circuit"
    assert result["metrics"]["status"] == "success"
    assert result["metrics"]["ebit_consumption"] == 1
    assert result["metrics"]["remote_cnot_count"] == 1
    assert result["summary"]["equivalence"]["passed"]
    assert result["summary"]["equivalence"]["fidelity"] == 1.0
    # full distributed result preserved
    assert result["artifacts"]["distributed_result"]["schema"] == "quantumlab.distributed-result"
    assert result["artifacts"]["distributed_result"]["version"] == 1


def test_run_distributed_circuit_with_topology():
    """Test distributed circuit with network topology."""
    circuit = make_cnot_circuit()

    config = {
        "circuit": circuit_to_dict(circuit),
        "qubit_to_node": {0: "A", 1: "B"},
        "protocol": "single_ebit",
        "topology": {
            "nodes": [
                {"name": "A", "type": "end", "memory_slots": 4},
                {"name": "B", "type": "end", "memory_slots": 4},
            ],
            "links": [
                {"source": "A", "destination": "B", "distance_km": 50, "base_fidelity": 0.95}
            ],
        },
    }

    result = run_distributed_circuit(config, seed=42)

    assert result["metrics"]["status"] == "success"
    assert result["summary"]["equivalence"]["passed"]
    # Should have network-mode entanglement grants
    grants = result["artifacts"]["entanglement_operations"]
    assert len(grants) == 1
    assert grants[0]["model"] == "network"
    assert grants[0]["fidelity"] is not None
    assert grants[0]["fidelity"] < 1.0  # lossy channel
    # modelled latency reported separately from simulator runtime
    assert result["metrics"]["modeled_network_latency_ms"] is not None
    assert result["metrics"]["modeled_network_latency_ms"] > 0


def test_run_distributed_circuit_double_teleport():
    """Test distributed circuit with double teleport protocol."""
    circuit = make_cnot_circuit()

    config = {
        "circuit": circuit_to_dict(circuit),
        "qubit_to_node": {0: "node_0", 1: "node_1"},
        "protocol": "double_teleport",
    }

    result = run_distributed_circuit(config, seed=42)

    assert result["metrics"]["status"] == "success"
    assert result["metrics"]["ebit_consumption"] == 2  # 2 ebits for double teleport
    assert result["metrics"]["classical_message_count"] == 4  # 4 cbits
    assert result["metrics"]["protocol"] == "double_teleport"


def test_run_distributed_circuit_missing_mapping():
    """No mapping and no num_nodes -> rejected; num_nodes auto-assign works."""
    circuit = make_cnot_circuit()

    config = {
        "circuit": circuit_to_dict(circuit),
        "protocol": "single_ebit",
    }

    with pytest.raises(ValueError, match="qubit_to_node mapping or num_nodes"):
        run_distributed_circuit(config, seed=42)

    config["num_nodes"] = 2
    result = run_distributed_circuit(config, seed=42)
    assert result["metrics"]["status"] == "success"
    assert result["summary"]["equivalence"]["passed"]
    # effective assignment must be recorded (NO hidden defaults)
    assert result["summary"]["reproducibility"]["assignment"]
    assert result["metrics"]["node_count"] == 2


def test_run_distributed_circuit_num_nodes_below_two():
    circuit = make_cnot_circuit()
    config = {
        "circuit": circuit_to_dict(circuit),
        "num_nodes": 1,
    }
    with pytest.raises(ValueError, match="num_nodes must be >= 2"):
        run_distributed_circuit(config, seed=42)


def test_run_distributed_circuit_invalid_circuit():
    """Test that invalid circuit is rejected."""
    with pytest.raises(ValueError, match="quantumlab.circuit"):
        run_distributed_circuit({"circuit": {"foo": "bar"}, "qubit_to_node": {0: "A"}}, seed=42)


def test_run_distributed_circuit_control_equals_target():
    """Test that a CX with control == target is rejected at circuit validation."""
    c = Circuit(num_qubits=1, name="bad-cnot")
    c.add_gate("CX", [0, 0])

    config = {
        "circuit": circuit_to_dict(c),
        "qubit_to_node": {0: "A"},
    }

    with pytest.raises(ValueError, match="Duplicate qubit"):
        run_distributed_circuit(config, seed=42)


def test_run_distributed_circuit_disconnected_fails():
    """Distributed failure must raise (run is marked FAILED, no fake success)."""
    topo = {
        "nodes": [
            {"name": "A", "type": "end", "memory_slots": 4},
            {"name": "B", "type": "end", "memory_slots": 4},
            {"name": "C", "type": "end", "memory_slots": 4},
        ],
        "links": [{"source": "A", "destination": "C", "distance_km": 10}],
    }

    circuit = make_cnot_circuit()
    config = {
        "circuit": circuit_to_dict(circuit),
        "qubit_to_node": {0: "A", 1: "B"},
        "topology": topo,
        "protocol": "single_ebit",
    }

    with pytest.raises(ValueError, match="Distributed execution failed"):
        run_distributed_circuit(config, seed=42)


def test_run_distributed_circuit_fallback_centralized():
    """Explicit fallback to centralized is recorded, not silent."""
    topo = {
        "nodes": [
            {"name": "A", "type": "end", "memory_slots": 4},
            {"name": "B", "type": "end", "memory_slots": 4},
            {"name": "C", "type": "end", "memory_slots": 4},
        ],
        "links": [{"source": "A", "destination": "C", "distance_km": 10}],
    }

    circuit = make_cnot_circuit()
    config = {
        "circuit": circuit_to_dict(circuit),
        "qubit_to_node": {0: "A", 1: "B"},
        "topology": topo,
        "protocol": "single_ebit",
        "fallback": "centralized",
    }

    result = run_distributed_circuit(config, seed=42)
    assert result["metrics"]["status"] == "success"
    assert result["summary"]["equivalence"]["passed"]
    assert any("falling back" in n.lower() for n in result["notes"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

# ---------------------------------------------------------------------------
# Full experiment lifecycle through ExperimentService + database
# ---------------------------------------------------------------------------

@pytest.fixture()
def svc(tmp_path):
    from app.persistence.db import Database
    db = Database(str(tmp_path / "dist.db"))
    yield ExperimentService(db)
    db.close()


def _dist_spec(n_nodes: int = 2) -> ExperimentSpec:
    return ExperimentSpec(
        name="distributed cnot study",
        module="distributed_circuit",
        config={
            "circuit": circuit_to_dict(make_cnot_circuit()),
            "qubit_to_node": {0: "node_0", 1: "node_1"},
            "protocol": "single_ebit",
        },
        seed=5,
    )


def test_experiment_lifecycle_create_execute_result(svc):
    """CREATE -> RUNNING -> COMPLETED with persisted result document."""
    exp_id = svc.create_experiment(_dist_spec())
    run_ids = svc.create_runs_for_experiment(exp_id)
    assert len(run_ids) == 1
    assert svc.get_run(run_ids[0])["status"] == "CREATED"

    doc = svc.execute_run_now(run_ids[0])
    run = svc.get_run(run_ids[0])
    assert run["status"] == "COMPLETED"
    assert run["seed"] is not None
    # result persisted with the standard run-result schema
    res = svc.get_result(run_ids[0])
    assert res["schema"] == "quantumlab.run-result"
    assert res["document"]["module"] == "distributed_circuit"
    assert res["document"]["metrics"]["status"] == "success"
    # full distributed result preserved inside artifacts
    dist = res["document"]["artifacts"]["distributed_result"]
    assert dist["schema"] == "quantumlab.distributed-result"
    assert dist["equivalence"]["passed"]
    assert doc["metrics"]["remote_cnot_count"] == 1


def test_experiment_seed_effective_and_persisted(svc):
    spec = _dist_spec()
    exp_id = svc.create_experiment(spec)
    run_ids = svc.create_runs_for_experiment(exp_id)
    svc.execute_run_now(run_ids[0])
    run = svc.get_run(run_ids[0])
    # run seed convention: spec.seed + 7919 * run_index
    assert run["seed"] == 5


def test_experiment_failed_run_semantics(svc):
    """A disconnected distributed run must be FAILED, never COMPLETED."""
    topo = {
        "nodes": [
            {"name": "A", "type": "end", "memory_slots": 4},
            {"name": "B", "type": "end", "memory_slots": 4},
            {"name": "C", "type": "end", "memory_slots": 4},
        ],
        "links": [{"source": "A", "destination": "C", "distance_km": 10}],
    }
    spec = ExperimentSpec(
        name="disconnected", module="distributed_circuit",
        config={
            "circuit": circuit_to_dict(make_cnot_circuit()),
            "qubit_to_node": {0: "A", 1: "B"},
            "topology": topo,
            "protocol": "single_ebit",
        },
        seed=5,
    )
    exp_id = svc.create_experiment(spec)
    rid = svc.create_runs_for_experiment(exp_id)[0]
    with pytest.raises(ValueError, match="Distributed execution failed"):
        svc.execute_run_now(rid)
    run = svc.get_run(rid)
    assert run["status"] == "FAILED"
    assert run["error_code"]
    assert run["error_message"]
    # no fabricated result
    assert svc.get_result(rid) is None


def test_experiment_reproduction_immutability(svc):
    """Reproduction creates a NEW run matching original; original unchanged."""
    exp_id = svc.create_experiment(_dist_spec())
    rid = svc.create_runs_for_experiment(exp_id)[0]
    svc.execute_run_now(rid)
    report = svc.reproduce_run(rid)
    assert report.reproduced_run_id != rid
    assert report.status == "EXACT_MATCH", report.differences
    # original immutable
    assert svc.get_run(rid)["status"] == "COMPLETED"
    assert svc.get_run(rid)["completed_at"] is not None


def test_experiment_sweep_runs(svc):
    """Sweep across num_nodes (an engine-supported numeric dimension) must
    materialize one run per combo and never mutate the source config."""
    chain = Circuit(num_qubits=3, name="chain")
    chain.add_gate("H", [0]); chain.add_gate("CX", [0, 1]); chain.add_gate("CX", [1, 2])
    spec = ExperimentSpec(
        name="distributed chain", module="distributed_circuit",
        config={"circuit": circuit_to_dict(chain), "protocol": "single_ebit"},
        seed=8,
    )
    from app.experiments.runner import SweepParameter
    spec.sweep = [SweepParameter("num_nodes", [2, 3])]
    exp_id = svc.create_experiment(spec)
    run_ids = svc.create_runs_for_experiment(exp_id)
    assert len(run_ids) == 2
    for rid in run_ids:
        doc = svc.execute_run_now(rid)
        assert doc["metrics"]["status"] == "success"
        assert doc["summary"]["equivalence"]["passed"]
    # seeds must differ per run index
    seeds = {svc.get_run(rid)["seed"] for rid in run_ids}
    assert len(seeds) == 2
    # the two runs use different numbers of nodes (observable resource change)
    node_counts = {svc.get_result(rid)["document"]["metrics"]["node_count"] for rid in run_ids}
    assert node_counts == {2, 3}
    # sweep does not mutate the source experiment config (per-run sweep values
    # are resolved into runs, never baked into the experiment definition)
    exp = svc.get_experiment(exp_id)
    from app.persistence.db import Database
    base = Database.loads(exp["base_config"])
    assert "num_nodes" not in base["config"]


def test_experiment_compare_runs(svc):
    """Comparison surfaces differing parameters/resource metrics."""
    spec_a = _dist_spec()
    exp_a = svc.create_experiment(spec_a)
    rid_a = svc.create_runs_for_experiment(exp_a)[0]
    svc.execute_run_now(rid_a)

    spec_b = ExperimentSpec(
        name="distributed protocol compare", module="distributed_circuit",
        config={
            "circuit": circuit_to_dict(make_cnot_circuit()),
            "qubit_to_node": {0: "node_0", 1: "node_1"},
            "protocol": "double_teleport",
        },
        seed=6,
    )
    exp_b = svc.create_experiment(spec_b)
    rid_b = svc.create_runs_for_experiment(exp_b)[0]
    svc.execute_run_now(rid_b)

    cmp = svc.compare_runs([rid_a, rid_b])
    assert "protocol" in cmp["differing_parameters"]
    rows = {r["run_id"]: r for r in cmp["runs"]}
    assert rows[rid_a]["metrics"]["ebit_consumption"] == 1
    assert rows[rid_b]["metrics"]["ebit_consumption"] == 2
    assert rows[rid_b]["metrics"]["protocol"] == "double_teleport"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


def test_experiment_cancellation_queued_job(svc):
    """Cancelling a QUEUED distributed job yields CANCELLED, never COMPLETED.

    Note: cancellation is cooperative (§288-291). The in-process engine executes
    atomically, so cancellation is guaranteed only while the job is queued; a
    RUNNING job finishes and reports unless it checks the flag at a progress
    boundary. This limitation is documented in LIMITATIONS.md.
    """
    from app.workers.jobs import JobQueue

    exp_id = svc.create_experiment(_dist_spec())
    rid = svc.create_runs_for_experiment(exp_id)[0]
    jq = JobQueue(db=svc.db, workers=1)
    job = jq.submit_run_job(rid, lambda r, cb=None: svc.execute_run_now(r, cb))
    assert jq.cancel_job(job.id)
    jq.start()
    import time
    for _ in range(40):
        if job.status == "CANCELLED":
            break
        time.sleep(0.05)
    assert job.status == "CANCELLED"
    assert job.status != "COMPLETED"
    jq.shutdown()
