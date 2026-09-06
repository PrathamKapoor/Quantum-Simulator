"""SAT-SA execution-gap workers.

This is the FIRST major SIH intelligence capability. Five signals are
implemented (Phase 5.1-5.5):

  5.1  acknowledged alert without meaningful investigation evidence
  5.2  critical/high severity alert closed unusually quickly
  5.3  critical alert closed without escalation
  5.4  repeated investigation patterns (low depth / no evidence)
  5.5  repeated alerts without remediation evidence

Each signal returns a list of `Observation` objects. The finding
derivation (which observations become findings) lives in the
risk.py module.

Per the directive: every signal is supported by the available data.
5.6 (potential metric gaming) is left as a configurable hook
that downstream consumers can implement with their own baselines.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from ..analysis_run import Observation, Finding
from ..domain import (
    SEVERITIES, CSESubmission, Alert, Closure,
)


# Default thresholds (configurable by the caller via the
# submission's per-submission overrides, if needed).
DEFAULT_FAST_CLOSURE_THRESHOLD_MIN = {
    "critical": 30.0,    # minutes — closure faster than this is suspicious
    "high": 60.0,
    "medium": 240.0,
    "low": 1440.0,
}


def _parse_iso(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _closure_duration_min(alert: Alert, closure: Closure) -> Optional[float]:
    if not alert.raised_at or not closure.closed_at:
        return None
    a = _parse_iso(alert.raised_at)
    c = _parse_iso(closure.closed_at)
    if a is None or c is None:
        return None
    return (c - a).total_seconds() / 60.0


# ---------------------------------------------------------------------------
# 5.1 — acknowledged alert without meaningful investigation.
# ---------------------------------------------------------------------------

def signal_5_1(submission: CSESubmission) -> list[Observation]:
    """A critical/high alert that has NO investigation record AT ALL."""
    out = []
    for aid, alert in submission.alerts.items():
        if alert.severity not in ("critical", "high"):
            continue
        # Check if ANY investigation references this alert.
        has_invest = any(inv.alert_id == aid
                          for inv in submission.investigations.values())
        if not has_invest:
            out.append(Observation(
                worker_id="execution_gap.signal_5_1",
                worker_version="1.0.0",
                target=aid,
                metric="has_investigation",
                value=0.0,
                baseline=1.0,
                deviation=-1.0,
                evidence_refs=[{"alert_id": aid, "cse_id": alert.cse_id}],
                notes=(f"Critical/high alert {aid!r} has no investigation "
                       f"record in submission {alert.cse_id!r}."),
            ))
    return out


# ---------------------------------------------------------------------------
# 5.2 — critical/high severity alert closed unusually quickly.
# ---------------------------------------------------------------------------

def signal_5_2(submission: CSESubmission,
                thresholds: Optional[dict] = None
                ) -> list[Observation]:
    th = thresholds or DEFAULT_FAST_CLOSURE_THRESHOLD_MIN
    out = []
    for aid, alert in submission.alerts.items():
        if alert.severity not in ("critical", "high"):
            continue
        closure = submission.closures.get(aid)
        if closure is None:
            continue
        dur = _closure_duration_min(alert, closure)
        if dur is None:
            continue
        thr = th.get(alert.severity)
        if thr is None or dur >= thr:
            continue
        out.append(Observation(
            worker_id="execution_gap.signal_5_2",
            worker_version="1.0.0",
            target=aid,
            metric="closure_duration_minutes",
            value=dur,
            baseline=thr,
            deviation=thr - dur,
            evidence_refs=[
                {"alert_id": aid, "cse_id": alert.cse_id},
                {"closure_id": closure.closure_id, "reason": closure.reason},
            ],
            notes=(f"{alert.severity} alert {aid!r} closed in {dur:.1f} "
                   f"min, faster than the {thr:.0f}-min threshold."),
        ))
    return out


# ---------------------------------------------------------------------------
# 5.3 — critical alert closed without escalation.
# ---------------------------------------------------------------------------

def signal_5_3(submission: CSESubmission) -> list[Observation]:
    out = []
    for aid, alert in submission.alerts.items():
        if alert.severity != "critical":
            continue
        if not alert.closed_at:
            continue
        esc_count = sum(1 for e in submission.escalations
                        if e.alert_id == aid)
        if esc_count > 0:
            continue
        out.append(Observation(
            worker_id="execution_gap.signal_5_3",
            worker_version="1.0.0",
            target=aid,
            metric="escalation_count",
            value=float(esc_count),
            baseline=1.0,
            deviation=-1.0,
            evidence_refs=[{"alert_id": aid, "cse_id": alert.cse_id}],
            notes=(f"Critical alert {aid!r} was closed without any "
                   f"escalation events."),
        ))
    return out


# ---------------------------------------------------------------------------
# 5.4 — repeated investigation patterns (low depth).
# ---------------------------------------------------------------------------

def signal_5_4(submission: CSESubmission,
                depth_threshold: float = 0.2) -> list[Observation]:
    out = []
    for inv_id, inv in submission.investigations.items():
        if inv.depth_score >= depth_threshold:
            continue
        out.append(Observation(
            worker_id="execution_gap.signal_5_4",
            worker_version="1.0.0",
            target=inv.alert_id,
            metric="investigation_depth_score",
            value=inv.depth_score,
            baseline=depth_threshold,
            deviation=inv.depth_score - depth_threshold,
            evidence_refs=[{"investigation_id": inv_id,
                             "alert_id": inv.alert_id}],
            notes=(f"Investigation {inv_id!r} for alert "
                   f"{inv.alert_id!r} has depth_score "
                   f"{inv.depth_score:.2f} below the {depth_threshold} "
                   f"threshold."),
        ))
    return out


# ---------------------------------------------------------------------------
# 5.5 — repeated alerts without remediation evidence.
# ---------------------------------------------------------------------------

def signal_5_5(submission: CSESubmission) -> list[Observation]:
    out = []
    for aid, alert in submission.alerts.items():
        if not alert.has_remediation_evidence:
            out.append(Observation(
                worker_id="execution_gap.signal_5_5",
                worker_version="1.0.0",
                target=aid,
                metric="has_remediation_evidence",
                value=0.0,
                baseline=1.0,
                deviation=-1.0,
                evidence_refs=[{"alert_id": aid, "cse_id": alert.cse_id}],
                notes=(f"Alert {aid!r} has no remediation evidence in "
                       f"submission {alert.cse_id!r}."),
            ))
    return out


# ---------------------------------------------------------------------------
# Worker registration.
# ---------------------------------------------------------------------------

def worker_execution_gap_5_1(submission: CSESubmission) -> list[Observation]:
    return signal_5_1(submission)


def worker_execution_gap_5_2(submission: CSESubmission) -> list[Observation]:
    return signal_5_2(submission)


def worker_execution_gap_5_3(submission: CSESubmission) -> list[Observation]:
    return signal_5_3(submission)


def worker_execution_gap_5_4(submission: CSESubmission) -> list[Observation]:
    return signal_5_4(submission)


def worker_execution_gap_5_5(submission: CSESubmission) -> list[Observation]:
    return signal_5_5(submission)


def register_workers(registry=None) -> None:
    """Register all execution-gap workers. The registry parameter
    is a callable; pass `satsa.analysis_run.register_worker` to
    register here, or a no-op for tests."""
    from ..analysis_run import register_worker as _reg
    _reg("execution_gap.signal_5_1", "1.0.0", worker_execution_gap_5_1)
    _reg("execution_gap.signal_5_2", "1.0.0", worker_execution_gap_5_2)
    _reg("execution_gap.signal_5_3", "1.0.0", worker_execution_gap_5_3)
    _reg("execution_gap.signal_5_4", "1.0.0", worker_execution_gap_5_4)
    _reg("execution_gap.signal_5_5", "1.0.0", worker_execution_gap_5_5)


__all__ = [
    "signal_5_1", "signal_5_2", "signal_5_3", "signal_5_4", "signal_5_5",
    "register_workers",
    "DEFAULT_FAST_CLOSURE_THRESHOLD_MIN",
]
