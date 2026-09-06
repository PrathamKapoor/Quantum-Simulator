"""SAT-SA demo dataset (Phase 13, Phase 15).

A controlled, multi-CSE demo set that exercises every analytical
worker in the pipeline. Each CSE has known ground truth:
  - CSE-001: healthy baseline
  - CSE-002: execution gap (fast critical closure, no
    investigation, no escalation)
  - CSE-003: negative space (critical asset with no activity)
  - CSE-004: anomaly (outlier closure duration)
  - CSE-005: peer deviation (median critical closure very
    different from peers)

The dataset is used by Phase 13 (end-to-end vertical slice),
Phase 15 (demo mode), and Phase 17 (validation framework).
"""
from __future__ import annotations

from .domain import (
    Asset, Alert, Closure, Investigation, Escalation,
    AssessmentPeriod, Provenance, CSESubmission,
)
from .ingestion import from_json
from datetime import datetime, timedelta


_BASE_TIME = datetime(2026, 1, 1, 12, 0, 0)


def _iso(dt):
    return dt.isoformat() + "Z"


def _ts(minutes_offset: int) -> str:
    return _iso(_BASE_TIME + timedelta(minutes=minutes_offset))


def _healthy_cse() -> dict:
    """A CSE with normal activity, full investigation, escalation,
    remediation evidence."""
    assets = [
        {"asset_id": "A-001", "name": "Auth server", "criticality": "critical"},
        {"asset_id": "A-002", "name": "DB primary", "criticality": "high"},
        {"asset_id": "A-003", "name": "Web frontend", "criticality": "medium"},
    ]
    alerts = [
        {"alert_id": "ALT-001", "cse_id": "CSE-001", "asset_id": "A-001",
         "severity": "high", "raised_at": _ts(0), "closed_at": _ts(180),
         "status": "closed", "description": "Brute-force attempt",
         "escalation_count": 1, "has_investigation": True,
         "has_remediation_evidence": True},
        {"alert_id": "ALT-002", "cse_id": "CSE-001", "asset_id": "A-002",
         "severity": "medium", "raised_at": _ts(60), "closed_at": _ts(300),
         "status": "closed", "description": "Anomalous query",
         "escalation_count": 0, "has_investigation": True,
         "has_remediation_evidence": True},
        {"alert_id": "ALT-003", "cse_id": "CSE-001", "asset_id": "A-003",
         "severity": "low", "raised_at": _ts(120), "closed_at": _ts(180),
         "status": "closed", "description": "Cosmetic",
         "escalation_count": 0, "has_investigation": True,
         "has_remediation_evidence": True},
    ]
    investigations = [
        {"investigation_id": "INV-001", "alert_id": "ALT-001",
         "cse_id": "CSE-001", "started_at": _ts(5), "completed_at": _ts(150),
         "notes_count": 6, "evidence_count": 4, "depth_score": 0.85},
        {"investigation_id": "INV-002", "alert_id": "ALT-002",
         "cse_id": "CSE-001", "started_at": _ts(70), "completed_at": _ts(280),
         "notes_count": 4, "evidence_count": 3, "depth_score": 0.7},
        {"investigation_id": "INV-003", "alert_id": "ALT-003",
         "cse_id": "CSE-001", "started_at": _ts(125), "completed_at": _ts(170),
         "notes_count": 2, "evidence_count": 1, "depth_score": 0.5},
    ]
    escalations = [
        {"escalation_id": "ESC-001", "alert_id": "ALT-001",
         "cse_id": "CSE-001", "escalated_at": _ts(15),
         "from_level": "tier_2", "to_level": "tier_3"},
    ]
    closures = [
        {"closure_id": "CLO-001", "alert_id": "ALT-001",
         "cse_id": "CSE-001", "closed_at": _ts(180),
         "reason": "resolved", "raised_at": _ts(0), "had_escalation": True},
        {"closure_id": "CLO-002", "alert_id": "ALT-002",
         "cse_id": "CSE-001", "closed_at": _ts(300),
         "reason": "resolved", "raised_at": _ts(60), "had_escalation": False},
        {"closure_id": "CLO-003", "alert_id": "ALT-003",
         "cse_id": "CSE-001", "closed_at": _ts(180),
         "reason": "false_positive", "raised_at": _ts(120),
         "had_escalation": False},
    ]
    return {
        "submission_id": "SUB-001",
        "cse_id": "CSE-001",
        "period": {"period_id": "P-001", "start_at": _ts(0),
                   "end_at": _ts(60 * 24), "description": "Q1"},
        "assets": assets, "alerts": alerts,
        "investigations": investigations,
        "escalations": escalations, "closures": closures,
    }


def _execution_gap_cse() -> dict:
    """Critical alert closed in 5 minutes (well under the 30-min
    threshold), no investigation, no escalation."""
    return {
        "submission_id": "SUB-002",
        "cse_id": "CSE-002",
        "period": {"period_id": "P-002", "start_at": _ts(0),
                   "end_at": _ts(60 * 24)},
        "assets": [
            {"asset_id": "A-010", "name": "Payments", "criticality": "critical"},
        ],
        "alerts": [
            {"alert_id": "ALT-010", "cse_id": "CSE-002", "asset_id": "A-010",
             "severity": "critical", "raised_at": _ts(0), "closed_at": _ts(5),
             "status": "closed", "description": "Suspicious transaction",
             "escalation_count": 0, "has_investigation": False,
             "has_remediation_evidence": False},
        ],
        "investigations": [],
        "escalations": [],
        "closures": [
            {"closure_id": "CLO-010", "alert_id": "ALT-010",
             "cse_id": "CSE-002", "closed_at": _ts(5),
             "reason": "false_positive", "raised_at": _ts(0),
             "had_escalation": False},
        ],
    }


def _negative_space_cse() -> dict:
    """Critical asset with NO alerts at all."""
    return {
        "submission_id": "SUB-003",
        "cse_id": "CSE-003",
        "period": {"period_id": "P-003", "start_at": _ts(0),
                   "end_at": _ts(60 * 24)},
        "assets": [
            {"asset_id": "A-020", "name": "Authentication proxy",
             "criticality": "critical"},
            {"asset_id": "A-021", "name": "Backup server",
             "criticality": "critical"},
        ],
        "alerts": [],
        "investigations": [],
        "escalations": [],
        "closures": [],
    }


def _anomaly_cse() -> dict:
    """A single closure with extreme outlier duration (one among
    several normal ones)."""
    return {
        "submission_id": "SUB-004",
        "cse_id": "CSE-004",
        "period": {"period_id": "P-004", "start_at": _ts(0),
                   "end_at": _ts(60 * 24)},
        "assets": [
            {"asset_id": "A-030", "name": "API gateway",
             "criticality": "high"},
        ],
        "alerts": [
            {"alert_id": f"ALT-04{i}", "cse_id": "CSE-004", "asset_id": "A-030",
             "severity": "high" if i < 4 else "critical",
             "raised_at": _ts(10 * i), "closed_at": _ts(10 * i + 60),
             "status": "closed", "description": "Anomaly",
             "escalation_count": 0, "has_investigation": True,
             "has_remediation_evidence": True}
            for i in range(5)
        ] + [
            # The outlier: very fast critical closure.
            {"alert_id": "ALT-OUT", "cse_id": "CSE-004", "asset_id": "A-030",
             "severity": "critical", "raised_at": _ts(200),
             "closed_at": _ts(201),  # 1 minute!
             "status": "closed", "description": "Critical outlier",
             "escalation_count": 0, "has_investigation": False,
             "has_remediation_evidence": False},
        ],
        "investigations": [
            {"investigation_id": f"INV-04{i}", "alert_id": f"ALT-04{i}",
             "cse_id": "CSE-004", "started_at": _ts(10 * i + 1),
             "completed_at": _ts(10 * i + 55), "notes_count": 3,
             "evidence_count": 2, "depth_score": 0.6}
            for i in range(5)
        ],
        "escalations": [],
        "closures": [
            {"closure_id": f"CLO-04{i}", "alert_id": f"ALT-04{i}",
             "cse_id": "CSE-004", "closed_at": _ts(10 * i + 60),
             "reason": "resolved", "raised_at": _ts(10 * i),
             "had_escalation": False}
            for i in range(5)
        ] + [
            {"closure_id": "CLO-OUT", "alert_id": "ALT-OUT",
             "cse_id": "CSE-004", "closed_at": _ts(201),
             "reason": "false_positive", "raised_at": _ts(200),
             "had_escalation": False},
        ],
    }


def _peer_deviation_cse() -> dict:
    """CSE with very fast median critical closure (peer deviation)."""
    return {
        "submission_id": "SUB-005",
        "cse_id": "CSE-005",
        "period": {"period_id": "P-005", "start_at": _ts(0),
                   "end_at": _ts(60 * 24)},
        "assets": [
            {"asset_id": "A-050", "name": "DNS", "criticality": "critical"},
            {"asset_id": "A-051", "name": "NTP", "criticality": "critical"},
        ],
        "alerts": [
            {"alert_id": "ALT-050", "cse_id": "CSE-005", "asset_id": "A-050",
             "severity": "critical", "raised_at": _ts(0), "closed_at": _ts(3),
             "status": "closed", "description": "DNS anomaly",
             "escalation_count": 0, "has_investigation": True,
             "has_remediation_evidence": True},
            {"alert_id": "ALT-051", "cse_id": "CSE-005", "asset_id": "A-051",
             "severity": "critical", "raised_at": _ts(10),
             "closed_at": _ts(12),
             "status": "closed", "description": "NTP drift",
             "escalation_count": 0, "has_investigation": True,
             "has_remediation_evidence": True},
        ],
        "investigations": [
            {"investigation_id": "INV-050", "alert_id": "ALT-050",
             "cse_id": "CSE-005", "started_at": _ts(0), "completed_at": _ts(3),
             "notes_count": 1, "evidence_count": 1, "depth_score": 0.1},
            {"investigation_id": "INV-051", "alert_id": "ALT-051",
             "cse_id": "CSE-005", "started_at": _ts(10), "completed_at": _ts(12),
             "notes_count": 1, "evidence_count": 1, "depth_score": 0.1},
        ],
        "escalations": [],
        "closures": [
            {"closure_id": "CLO-050", "alert_id": "ALT-050",
             "cse_id": "CSE-005", "closed_at": _ts(3),
             "reason": "false_positive", "raised_at": _ts(0),
             "had_escalation": False},
            {"closure_id": "CLO-051", "alert_id": "ALT-051",
             "cse_id": "CSE-005", "closed_at": _ts(12),
             "reason": "false_positive", "raised_at": _ts(10),
             "had_escalation": False},
        ],
    }


DEMO_PAYLOADS = {
    "CSE-001": _healthy_cse(),
    "CSE-002": _execution_gap_cse(),
    "CSE-003": _negative_space_cse(),
    "CSE-004": _anomaly_cse(),
    "CSE-005": _peer_deviation_cse(),
}


DEMO_CSES = {cse_id: from_json(p, sign=False)
              for cse_id, p in DEMO_PAYLOADS.items()}


def load_demo_assessment(cse_id: str = "CSE-002") -> dict:
    """Return a JSON-serializable dict for the demo assessment (the
    one CSE's CSESubmission plus ground truth labels)."""
    sub = DEMO_CSES[cse_id]
    gt = {
        "CSE-001": "healthy_baseline",
        "CSE-002": "execution_gap_present",
        "CSE-003": "negative_space_present",
        "CSE-004": "anomaly_present",
        "CSE-005": "peer_deviation_present",
    }
    return {
        "submission": sub.to_dict(),
        "ground_truth": gt[cse_id],
    }


__all__ = ["DEMO_PAYLOADS", "DEMO_CSES", "load_demo_assessment"]
