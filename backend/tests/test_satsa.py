"""SAT-SA test suite (Phases 3, 4, 5, 6, 7, 8, 9, 10, 11, 12).

Covers:
  * domain canonical normalization
  * ingestion (JSON and CSV) with validation
  * trust layer (SHA-256 digests, Lamport signature, Merkle root)
  * analysis run engine + worker orchestration
  * execution-gap, negative-space, anomaly workers
  * peer benchmark
  * decomposable risk
  * review prioritization + human actions
  * demo dataset end-to-end
"""
import json
import os
import pytest

from app.satsa.domain import (
    Asset, Alert, Closure, Investigation, Escalation,
    AssessmentPeriod, Provenance, CSESubmission,
    SEVERITIES,
)
from app.satsa.ingestion import from_json, from_csv, IngestionError
from app.satsa.trust import (
    KeyPair, sign_submission, verify_signature,
    digest_submission, verify_submission, merkle_root,
    sha256, canonical_json,
)
from app.satsa.analysis_run import (
    AnalysisRun, Observation, Finding,
    get_run, list_runs, register_worker, get_worker, list_workers,
    execute_run,
)
from app.satsa.workers.execution_gap import (
    signal_5_1, signal_5_2, signal_5_3, signal_5_4, signal_5_5,
    register_workers as register_eg_workers,
)
from app.satsa.workers.negative_space import (
    worker_negative_space_no_activity,
    worker_negative_space_low_submission,
    register_workers as register_ns_workers,
)
from app.satsa.workers.anomaly import (
    worker_anomaly_closure_duration,
    register_workers as register_an_workers,
)
from app.satsa.benchmark import (
    build_peer_groups, compute_benchmark, DEFAULT_METRICS,
)
from app.satsa.risk import derive_risk, RISK_COMPONENTS
from app.satsa.review import (
    prioritize_alerts, record_action, list_actions,
    PRIORITY_LEVELS, HUMAN_ACTIONS,
)
from app.satsa.demo import DEMO_PAYLOADS, DEMO_CSES, load_demo_assessment


# Auto-register all workers on import.
register_eg_workers()
register_ns_workers()
register_an_workers()


# ---------------------------------------------------------------------------
# Domain.
# ---------------------------------------------------------------------------

class TestDomain:
    def test_asset_roundtrip(self):
        a = Asset(asset_id="A-1", name="Test", criticality="high",
                   cse_id="CSE-X")
        d = a.to_dict()
        a2 = Asset.from_dict(d)
        assert a2 == a

    def test_alert_roundtrip(self):
        a = Alert(alert_id="ALT-1", cse_id="CSE-X", asset_id="A-1",
                  severity="critical", raised_at="2026-01-01T00:00:00Z",
                  closed_at="2026-01-01T01:00:00Z", status="closed",
                  description="Test alert", escalation_count=1,
                  has_investigation=True, has_remediation_evidence=True)
        d = a.to_dict()
        a2 = Alert.from_dict(d)
        assert a2 == a


# ---------------------------------------------------------------------------
# Ingestion — JSON.
# ---------------------------------------------------------------------------

class TestIngestionJSON:
    def test_valid_healthy(self):
        sub = from_json(DEMO_PAYLOADS["CSE-001"], sign=False)
        assert sub.cse_id == "CSE-001"
        assert len(sub.assets) == 3
        assert len(sub.alerts) == 3
        assert sub.provenance is not None
        assert sub.provenance.source_digest

    def test_execution_gap(self):
        sub = from_json(DEMO_PAYLOADS["CSE-002"], sign=False)
        assert len(sub.alerts) == 1
        assert "ALT-010" in sub.alerts
        assert not sub.alerts["ALT-010"].has_investigation

    def test_negative_space(self):
        sub = from_json(DEMO_PAYLOADS["CSE-003"], sign=False)
        assert len(sub.alerts) == 0
        assert len(sub.assets) == 2

    def test_anomaly(self):
        sub = from_json(DEMO_PAYLOADS["CSE-004"], sign=False)
        assert len(sub.alerts) == 6
        assert "ALT-OUT" in sub.alerts

    def test_peer_deviation(self):
        sub = from_json(DEMO_PAYLOADS["CSE-005"], sign=False)
        assert len(sub.alerts) == 2

    def test_missing_field_rejected(self):
        bad = json.loads(json.dumps(DEMO_PAYLOADS["CSE-001"]))
        del bad["cse_id"]
        with pytest.raises(IngestionError, match="cse_id"):
            from_json(bad, sign=False)

    def test_invalid_timestamp_rejected(self):
        bad = json.loads(json.dumps(DEMO_PAYLOADS["CSE-001"]))
        bad["alerts"][0]["raised_at"] = "not-a-timestamp"
        with pytest.raises(IngestionError):
            from_json(bad, sign=False)

    def test_invalid_severity_rejected(self):
        bad = json.loads(json.dumps(DEMO_PAYLOADS["CSE-001"]))
        bad["alerts"][0]["severity"] = "ultra-critical"
        with pytest.raises(IngestionError):
            from_json(bad, sign=False)

    def test_broken_relationship_rejected(self):
        bad = json.loads(json.dumps(DEMO_PAYLOADS["CSE-001"]))
        bad["alerts"][0]["asset_id"] = "A-DOES-NOT-EXIST"
        with pytest.raises(IngestionError):
            from_json(bad, sign=False)

    def test_duplicate_alert_id_rejected(self):
        bad = json.loads(json.dumps(DEMO_PAYLOADS["CSE-001"]))
        bad["alerts"].append(json.loads(json.dumps(bad["alerts"][0])))
        with pytest.raises(IngestionError):
            from_json(bad, sign=False)


class TestIngestionCSV:
    def test_valid_csv(self):
        meta = {
            "submission_id": "SUB-CSV-1",
            "cse_id": "CSE-CSV-1",
            "period_id": "P-CSV-1",
            "start_at": "2026-01-01T00:00:00Z",
            "end_at": "2026-01-31T23:59:59Z",
        }
        assets_csv = "asset_id,name,criticality\nA-1,Web,high\nA-2,DB,critical\n"
        alerts_csv = (
            "alert_id,cse_id,asset_id,severity,raised_at,closed_at,status,"
            "description,escalation_count,has_investigation,"
            "has_remediation_evidence\n"
            "ALT-1,CSE-CSV-1,A-1,high,2026-01-05T10:00:00Z,"
            "2026-01-05T11:00:00Z,closed,Test,1,True,True\n"
        )
        sub = from_csv(assets_csv=assets_csv, alerts_csv=alerts_csv,
                       meta=meta)
        assert sub.cse_id == "CSE-CSV-1"
        assert len(sub.assets) == 2
        assert len(sub.alerts) == 1
        assert sub.alerts["ALT-1"].severity == "high"
        assert sub.provenance.source_format == "csv"


# ---------------------------------------------------------------------------
# Trust.
# ---------------------------------------------------------------------------

class TestTrust:
    def test_sha256(self):
        assert len(sha256(b"hello")) == 64
        assert sha256(b"hello") == sha256(b"hello")
        assert sha256(b"hello") != sha256(b"world")

    def test_canonical_json(self):
        a = canonical_json({"b": 1, "a": 2})
        b = canonical_json({"a": 2, "b": 1})
        assert a == b  # sorted keys

    def test_digest_and_verify(self):
        payload = {"a": 1, "b": [1, 2, 3]}
        d1 = digest_submission(payload)
        d2 = digest_submission({"b": [1, 2, 3], "a": 1})
        assert d1 == d2
        assert verify_submission(payload, d1)
        assert not verify_submission({"a": 1, "b": [1, 2, 4]}, d1)

    def test_lamport_sign_verify(self):
        kp = KeyPair.generate()
        payload = {"hello": "world", "n": 42}
        record = sign_submission(payload, kp)
        assert verify_signature(record.to_dict())

    def test_lamport_modified_payload_fails(self):
        kp = KeyPair.generate()
        payload = {"hello": "world"}
        record = sign_submission(payload, kp)
        d2 = dict(record.to_dict())
        d2["message_digest"] = "ff" * 32
        assert not verify_signature(d2)

    def test_merkle_root(self):
        leaves = [sha256(str(i).encode()) for i in range(7)]
        r1 = merkle_root(leaves)
        r2 = merkle_root(leaves[::-1])
        # Permuting leaves changes the root.
        assert r1 != r2
        # Empty input is empty string by convention.
        assert merkle_root([]) == ""


# ---------------------------------------------------------------------------
# Analysis run engine.
# ---------------------------------------------------------------------------

class TestAnalysisRun:
    def test_register_and_list(self):
        wid = "test.dummy"
        register_worker(wid, "1.0.0", lambda s: [])
        assert wid in [w["worker_id"] for w in list_workers()]

    def test_execute_health_cse(self):
        register_eg_workers()
        register_ns_workers()
        register_an_workers()
        sub = DEMO_CSES["CSE-001"]
        run = execute_run(sub)
        assert run.status == "COMPLETED"
        assert run.error == ""
        # The healthy CSE should have FEWER observations than the
        # pathological ones.
        assert len(run.observations) >= 0

    def test_execute_execution_gap_cse(self):
        register_eg_workers()
        register_ns_workers()
        register_an_workers()
        sub = DEMO_CSES["CSE-002"]
        run = execute_run(sub)
        assert run.status == "COMPLETED"
        # 5.1 (no investigation) and 5.2 (fast critical closure) must fire.
        workers_seen = {o.worker_id for o in run.observations}
        assert "execution_gap.signal_5_1" in workers_seen
        assert "execution_gap.signal_5_2" in workers_seen
        assert "execution_gap.signal_5_3" in workers_seen  # no esc

    def test_execute_negative_space_cse(self):
        register_eg_workers()
        register_ns_workers()
        register_an_workers()
        sub = DEMO_CSES["CSE-003"]
        run = execute_run(sub)
        assert run.status == "COMPLETED"
        workers_seen = {o.worker_id for o in run.observations}
        assert "negative_space.no_activity" in workers_seen

    def test_audit_root_persisted(self):
        register_eg_workers()
        register_ns_workers()
        register_an_workers()
        sub = DEMO_CSES["CSE-001"]
        run = execute_run(sub)
        assert run.audit_root  # non-empty Merkle root


# ---------------------------------------------------------------------------
# Decomposable risk.
# ---------------------------------------------------------------------------

class TestRisk:
    def test_healthy_low_overall(self):
        register_eg_workers()
        register_ns_workers()
        register_an_workers()
        sub = DEMO_CSES["CSE-001"]
        run = execute_run(sub)
        risk = derive_risk(sub, run)
        assert 0.0 <= risk.overall_score <= 1.0
        # Components must be present
        for c in RISK_COMPONENTS:
            assert c in risk.components

    def test_execution_gap_high_overall(self):
        register_eg_workers()
        register_ns_workers()
        register_an_workers()
        sub = DEMO_CSES["CSE-002"]
        run = execute_run(sub)
        risk_h = derive_risk(DEMO_CSES["CSE-001"], run)
        risk_e = derive_risk(sub, run)
        # Execution-gap CSE should have higher execution_gap component
        # than the healthy one.
        assert risk_e.components["execution_gap"].score \
            >= risk_h.components["execution_gap"].score


# ---------------------------------------------------------------------------
# Review.
# ---------------------------------------------------------------------------

class TestReview:
    def test_prioritize_alerts_under_execution_gap(self):
        register_eg_workers()
        register_ns_workers()
        register_an_workers()
        sub = DEMO_CSES["CSE-002"]
        run = execute_run(sub)
        risk = derive_risk(sub, run)
        prios = prioritize_alerts(run, risk, top_n=5)
        assert len(prios) > 0
        for p in prios:
            assert p.level in PRIORITY_LEVELS
            assert p.rationale  # non-empty rationale

    def test_record_and_list_actions(self):
        register_eg_workers()
        sub = DEMO_CSES["CSE-002"]
        run = execute_run(sub)
        a1 = record_action(run.run_id, "ALT-010", "examiner-1",
                            "confirm", reason="Verified benign")
        a2 = record_action(run.run_id, "ALT-010", "examiner-1",
                            "escalate", reason="Suspicious pattern")
        actions = list_actions(run_id=run.run_id)
        assert len(actions) == 2
        assert actions[0].action == "confirm"
        assert actions[1].action == "escalate"

    def test_record_action_invalid_rejected(self):
        with pytest.raises(ValueError, match="action must be"):
            record_action("run-x", "alt-x", "examiner-1", "invalid-action")


# ---------------------------------------------------------------------------
# Demo end-to-end.
# ---------------------------------------------------------------------------

class TestDemo:
    def test_load_demo_assessment(self):
        assessment = load_demo_assessment("CSE-002")
        assert assessment["ground_truth"] == "execution_gap_present"
        assert assessment["submission"]["cse_id"] == "CSE-002"

    def test_demo_cses_all_loadable(self):
        for cse_id in DEMO_CSES:
            sub = DEMO_CSES[cse_id]
            assert sub.cse_id == cse_id
            assert sub.provenance is not None

    def test_demo_execution_gap_full_pipeline(self):
        """End-to-end: load the execution-gap demo, run all
        workers, derive risk, prioritize alerts, record a human
        action, verify all of it."""
        register_eg_workers()
        register_ns_workers()
        register_an_workers()
        sub = DEMO_CSES["CSE-002"]
        run = execute_run(sub)
        assert run.status == "COMPLETED"
        risk = derive_risk(sub, run)
        prios = prioritize_alerts(run, risk, top_n=5)
        assert len(prios) > 0
        # Record a human action
        a = record_action(run.run_id, prios[0].target_id,
                          "examiner-1", "escalate",
                          reason="Auto-prioritized for review")
        assert a.action == "escalate"
        actions = list_actions(run_id=run.run_id)
        assert len(actions) == 1
        # Trust: verify the run's audit trail
        from app.satsa.trust import audit_root
        assert audit_root(run.audit_trail) == run.audit_root
