"""SAT-SA canonical domain entities.

The CSE (Cyber Security Exercise) submission is the input. SAT-SA
normalizes the records into a canonical representation used by all
downstream analytical workers.

Entities:
  CSE                  a Cyber Security Exercise submission
  AssessmentPeriod     the time range of the submission
  Asset                a system or asset under supervision
  Alert                an alert raised during the assessment
  Case                 a case-management record (one per alert)
  Investigation        investigation workflow
  Escalation           an escalation event
  Closure              a closure/closure-attempt event
  Provenance           submission identity + digests + processing version
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# Canonical enum-like string sets (no enum to keep JSON-friendly)
SEVERITIES = ("low", "medium", "high", "critical")
ALERT_STATUSES = ("open", "investigating", "escalated", "closed")
CLOSURE_REASONS = ("resolved", "duplicate", "false_positive",
                    "inconclusive", "other")


@dataclass
class Asset:
    asset_id: str
    name: str
    criticality: str         # "low" | "medium" | "high" | "critical"
    cse_id: str              # the CSE this asset belongs to

    def to_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "name": self.name,
            "criticality": self.criticality,
            "cse_id": self.cse_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Asset":
        return cls(
            asset_id=d["asset_id"],
            name=d.get("name", d["asset_id"]),
            criticality=d.get("criticality", "medium"),
            cse_id=d.get("cse_id", ""),
        )


@dataclass
class Alert:
    alert_id: str
    cse_id: str
    asset_id: str
    severity: str           # SEVERITIES
    raised_at: str          # ISO8601
    closed_at: Optional[str] = None
    status: str = "open"    # ALERT_STATUSES
    description: str = ""
    escalation_count: int = 0
    has_investigation: bool = False
    has_remediation_evidence: bool = False

    def to_dict(self) -> dict:
        return {
            "alert_id": self.alert_id,
            "cse_id": self.cse_id,
            "asset_id": self.asset_id,
            "severity": self.severity,
            "raised_at": self.raised_at,
            "closed_at": self.closed_at,
            "status": self.status,
            "description": self.description,
            "escalation_count": self.escalation_count,
            "has_investigation": self.has_investigation,
            "has_remediation_evidence": self.has_remediation_evidence,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Alert":
        return cls(
            alert_id=d["alert_id"],
            cse_id=d.get("cse_id", ""),
            asset_id=d.get("asset_id", ""),
            severity=d.get("severity", "low"),
            raised_at=d.get("raised_at", ""),
            closed_at=d.get("closed_at"),
            status=d.get("status", "open"),
            description=d.get("description", ""),
            escalation_count=int(d.get("escalation_count", 0)),
            has_investigation=bool(d.get("has_investigation", False)),
            has_remediation_evidence=bool(d.get("has_remediation_evidence", False)),
        )


@dataclass
class Closure:
    closure_id: str
    alert_id: str
    cse_id: str
    closed_at: str           # ISO8601
    reason: str             # CLOSURE_REASONS
    raised_at: Optional[str] = None   # alert's raised_at, for duration calc
    closure_duration_minutes: Optional[float] = None
    had_escalation: bool = False

    def to_dict(self) -> dict:
        return {
            "closure_id": self.closure_id,
            "alert_id": self.alert_id,
            "cse_id": self.cse_id,
            "closed_at": self.closed_at,
            "reason": self.reason,
            "raised_at": self.raised_at,
            "closure_duration_minutes": self.closure_duration_minutes,
            "had_escalation": self.had_escalation,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Closure":
        return cls(
            closure_id=d["closure_id"],
            alert_id=d["alert_id"],
            cse_id=d.get("cse_id", ""),
            closed_at=d.get("closed_at", ""),
            reason=d.get("reason", "other"),
            raised_at=d.get("raised_at"),
            closure_duration_minutes=d.get("closure_duration_minutes"),
            had_escalation=bool(d.get("had_escalation", False)),
        )


@dataclass
class Investigation:
    investigation_id: str
    alert_id: str
    cse_id: str
    started_at: str
    completed_at: Optional[str] = None
    notes_count: int = 0
    evidence_count: int = 0
    depth_score: float = 0.0  # 0..1, crude

    def to_dict(self) -> dict:
        return {
            "investigation_id": self.investigation_id,
            "alert_id": self.alert_id,
            "cse_id": self.cse_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "notes_count": self.notes_count,
            "evidence_count": self.evidence_count,
            "depth_score": self.depth_score,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Investigation":
        return cls(
            investigation_id=d["investigation_id"],
            alert_id=d["alert_id"],
            cse_id=d.get("cse_id", ""),
            started_at=d.get("started_at", ""),
            completed_at=d.get("completed_at"),
            notes_count=int(d.get("notes_count", 0)),
            evidence_count=int(d.get("evidence_count", 0)),
            depth_score=float(d.get("depth_score", 0.0)),
        )


@dataclass
class Escalation:
    escalation_id: str
    alert_id: str
    cse_id: str
    escalated_at: str
    from_level: str
    to_level: str

    def to_dict(self) -> dict:
        return {
            "escalation_id": self.escalation_id,
            "alert_id": self.alert_id,
            "cse_id": self.cse_id,
            "escalated_at": self.escalated_at,
            "from_level": self.from_level,
            "to_level": self.to_level,
        }


@dataclass
class AssessmentPeriod:
    period_id: str
    cse_id: str
    start_at: str          # ISO8601
    end_at: str            # ISO8601
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "period_id": self.period_id,
            "cse_id": self.cse_id,
            "start_at": self.start_at,
            "end_at": self.end_at,
            "description": self.description,
        }


@dataclass
class Provenance:
    submission_id: str
    cse_id: str
    period_id: str
    source_format: str      # "csv" | "json"
    source_digest: str      # SHA-256 hex of the raw source bytes
    ingested_at: str        # ISO8601
    processing_version: str

    def to_dict(self) -> dict:
        return {
            "submission_id": self.submission_id,
            "cse_id": self.cse_id,
            "period_id": self.period_id,
            "source_format": self.source_format,
            "source_digest": self.source_digest,
            "ingested_at": self.ingested_at,
            "processing_version": self.processing_version,
        }


@dataclass
class CSESubmission:
    """A complete Cyber Security Exercise submission."""
    cse_id: str
    submission_id: str
    period: AssessmentPeriod
    assets: dict = field(default_factory=dict)        # asset_id -> Asset
    alerts: dict = field(default_factory=dict)       # alert_id -> Alert
    investigations: dict = field(default_factory=dict)  # investigation_id -> Investigation
    escalations: list = field(default_factory=list)    # [Escalation]
    closures: dict = field(default_factory=dict)      # alert_id -> Closure
    provenance: Optional[Provenance] = None

    def to_dict(self) -> dict:
        return {
            "cse_id": self.cse_id,
            "submission_id": self.submission_id,
            "period": self.period.to_dict(),
            "assets": {k: v.to_dict() for k, v in self.assets.items()},
            "alerts": {k: v.to_dict() for k, v in self.alerts.items()},
            "investigations": {k: v.to_dict() for k, v in
                               self.investigations.items()},
            "escalations": [e.to_dict() for e in self.escalations],
            "closures": {k: v.to_dict() for k, v in self.closures.items()},
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "summary": {
                "n_assets": len(self.assets),
                "n_alerts": len(self.alerts),
                "n_investigations": len(self.investigations),
                "n_escalations": len(self.escalations),
                "n_closures": len(self.closures),
            },
        }


__all__ = [
    "SEVERITIES", "ALERT_STATUSES", "CLOSURE_REASONS",
    "Asset", "Alert", "Closure", "Investigation", "Escalation",
    "AssessmentPeriod", "Provenance", "CSESubmission",
]
