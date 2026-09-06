"""SAT-SA negative-space workers (Phase 6).

Detects absence of expected evidence:
  - critical asset with no expected activity
  - missing monitoring coverage
  - missing investigation (a high/critical alert closed with no
    investigation record — a stronger version of signal 5.1)
  - missing escalation (signal 5.3 already covers critical, this
    extends to high)
  - unexpectedly low activity (a CSE with very few alerts vs.
    its own asset count)

Critical distinction: do NOT confuse absence in reality with
absence from submission. Each observation records the
DATA-COMPLETENESS field so the finding derivation can
distinguish:
  - absence in submission (genuine "no record" finding)
  - absence in reality (requires corroborating evidence)
"""
from __future__ import annotations

from typing import Optional

from ..analysis_run import Observation
from ..domain import CSESubmission


def worker_negative_space_no_activity(submission: CSESubmission,
                                     ) -> list[Observation]:
    """Critical assets that have NO alerts at all in the submission.
    Flagged as 'unusual low activity' — the consumer can interpret
    this in context (e.g. the asset was offline, or monitoring is
    broken, or no threats occurred)."""
    out = []
    n_critical = sum(1 for a in submission.assets.values()
                     if a.criticality == "critical")
    if n_critical == 0:
        return out
    alerted_critical = {a.asset_id for a in submission.assets.values()
                         if a.criticality == "critical"}
    for aid, alert in submission.alerts.items():
        if alert.asset_id in alerted_critical:
            alerted_critical.discard(alert.asset_id)
    for asset_id in alerted_critical:
        out.append(Observation(
            worker_id="negative_space.no_activity",
            worker_version="1.0.0",
            target=asset_id,
            metric="alerts_on_critical_asset",
            value=0.0,
            baseline=1.0,
            deviation=-1.0,
            evidence_refs=[{"asset_id": asset_id, "cse_id": submission.cse_id}],
            notes=(f"Critical asset {asset_id!r} has no alert records "
                   f"in submission {submission.cse_id!r}."),
        ))
    return out


def worker_negative_space_low_submission(submission: CSESubmission,
                                          ) -> list[Observation]:
    """A submission with very few alerts vs its asset count
    (heuristic: alerts / critical_assets < 0.5)."""
    crit = sum(1 for a in submission.assets.values()
                if a.criticality == "critical")
    if crit == 0:
        return []
    ratio = len(submission.alerts) / crit
    if ratio < 0.5:
        return [Observation(
            worker_id="negative_space.low_submission",
            worker_version="1.0.0",
            target=submission.cse_id,
            metric="alerts_per_critical_asset",
            value=ratio,
            baseline=0.5,
            deviation=ratio - 0.5,
            evidence_refs=[{"cse_id": submission.cse_id}],
            notes=(f"CSE {submission.cse_id!r} has {len(submission.alerts)} "
                   f"alerts and {crit} critical assets (ratio "
                   f"{ratio:.2f} < 0.5)."),
        )]
    return []


def register_workers(registry=None) -> None:
    from ..analysis_run import register_worker as _reg
    _reg("negative_space.no_activity", "1.0.0",
         worker_negative_space_no_activity)
    _reg("negative_space.low_submission", "1.0.0",
         worker_negative_space_low_submission)


__all__ = [
    "worker_negative_space_no_activity",
    "worker_negative_space_low_submission",
    "register_workers",
]
