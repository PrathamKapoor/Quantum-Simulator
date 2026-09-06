"""SAT-SA anomaly workers (Phase 7).

Detect statistical deviations using explainable statistics:
median / MAD, IQR, percentile. No black-box ML.

Per-CSE baselines (computed from this submission itself, which is
appropriate for single-CSE analysis). For peer comparison, see the
benchmark module.
"""
from __future__ import annotations

from statistics import median
from typing import Optional

from ..analysis_run import Observation
from ..domain import CSESubmission


def _mad(values: list[float]) -> float:
    """Median absolute deviation."""
    if not values:
        return 0.0
    med = median(values)
    return median([abs(v - med) for v in values])


def _z_score_mad(value: float, med: float, mad: float) -> float:
    """Robust z-score using MAD (constant 1.4826 makes MAD a
    consistent estimator of sigma for normal data)."""
    if mad <= 0:
        return 0.0
    return (value - med) / (1.4826 * mad)


def worker_anomaly_closure_duration(submission: CSESubmission,
                                    z_threshold: float = 2.0
                                    ) -> list[Observation]:
    """Flag closures whose duration is a robust z-score outlier."""
    durations = []
    for aid, alert in submission.alerts.items():
        closure = submission.closures.get(aid)
        if closure is None or not alert.raised_at or not closure.closed_at:
            continue
        from datetime import datetime
        try:
            a = datetime.fromisoformat(alert.raised_at.replace("Z", "+00:00"))
            c = datetime.fromisoformat(closure.closed_at.replace("Z", "+00:00"))
            durations.append(((c - a).total_seconds() / 60.0, aid, alert.severity))
        except ValueError:
            continue
    if len(durations) < 5:
        return []
    vals = [d[0] for d in durations]
    med = median(vals)
    mad = _mad(vals)
    out = []
    for dur, aid, severity in durations:
        z = _z_score_mad(dur, med, mad)
        if abs(z) >= z_threshold:
            out.append(Observation(
                worker_id="anomaly.closure_duration",
                worker_version="1.0.0",
                target=aid,
                metric="closure_duration_minutes_z",
                value=z,
                baseline=0.0,
                deviation=z,
                evidence_refs=[{"alert_id": aid, "severity": severity}],
                notes=(f"{severity} alert {aid!r} closure duration "
                       f"({dur:.1f} min) is a robust z-score outlier "
                       f"(med={med:.1f}, mad={mad:.1f}, z={z:.2f})."),
            ))
    return out


def register_workers(registry=None) -> None:
    from ..analysis_run import register_worker as _reg
    _reg("anomaly.closure_duration", "1.0.0",
         worker_anomaly_closure_duration)


__all__ = ["worker_anomaly_closure_duration", "register_workers"]
