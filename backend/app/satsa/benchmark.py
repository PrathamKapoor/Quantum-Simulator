"""SAT-SA peer benchmarking (Phase 8).

Compare comparable CSEs. Peers are grouped by:
  - criticality profile (counts of critical vs high assets)
  - asset count bucket (small / medium / large)

The benchmark for a metric M is the median of M over the peers.
A target CSE is flagged if its metric deviates by more than the
configurable threshold (default ±50% from peer median).
"""
from __future__ import annotations

from statistics import median
from typing import Optional

from .domain import CSESubmission


# Default metric registry: each metric is a function
# (CSESubmission) -> float. Submissions return None to opt out.
DEFAULT_METRICS = {
    "median_critical_closure_minutes":
        lambda s: _median_critical_closure(s),
    "n_alerts": lambda s: float(len(s.alerts)),
    "n_critical_alerts": lambda s: float(sum(1 for a in s.alerts.values()
                                            if a.severity == "critical")),
    "critical_alert_escalation_rate":
        lambda s: _critical_alert_escalation_rate(s),
    "investigation_coverage":
        lambda s: _investigation_coverage(s),
}


def _median_critical_closure(submission: CSESubmission) -> Optional[float]:
    durations = []
    for aid, alert in submission.alerts.items():
        if alert.severity != "critical":
            continue
        closure = submission.closures.get(aid)
        if closure is None or not alert.raised_at or not closure.closed_at:
            continue
        from datetime import datetime
        try:
            a = datetime.fromisoformat(alert.raised_at.replace("Z", "+00:00"))
            c = datetime.fromisoformat(closure.closed_at.replace("Z", "+00:00"))
            durations.append((c - a).total_seconds() / 60.0)
        except ValueError:
            continue
    if not durations:
        return None
    return float(median(durations))


def _critical_alert_escalation_rate(submission: CSESubmission) -> float:
    crit = [a for a in submission.alerts.values() if a.severity == "critical"]
    if not crit:
        return 0.0
    esc = sum(1 for a in crit if a.escalation_count > 0)
    return esc / len(crit)


def _investigation_coverage(submission: CSESubmission) -> float:
    if not submission.alerts:
        return 1.0
    n_inv = sum(1 for a in submission.alerts.values() if a.has_investigation)
    return n_inv / len(submission.alerts)


def build_peer_groups(cses: list[CSESubmission]
                      ) -> dict[str, list[CSESubmission]]:
    """Build a deterministic peer group per CSE based on critical
    asset count bucket. The buckets are: small (1-2), medium (3-9),
    large (>=10)."""
    groups: dict[str, list[CSESubmission]] = {"small": [], "medium": [],
                                              "large": []}
    for s in cses:
        n_crit = sum(1 for a in s.assets.values() if a.criticality == "critical")
        if n_crit <= 2:
            groups["small"].append(s)
        elif n_crit <= 9:
            groups["medium"].append(s)
        else:
            groups["large"].append(s)
    return groups


def compute_benchmark(target: CSESubmission,
                      peers: list[CSESubmission],
                      metric: str,
                      deviation_threshold: float = 0.5,
                      ) -> Optional[dict]:
    """Compute the peer benchmark for one metric.

    Returns a dict with the target's value, the peer median, and
    the deviation, or None if the metric is not available.
    """
    fn = DEFAULT_METRICS.get(metric)
    if fn is None:
        return None
    target_val = fn(target)
    if target_val is None:
        return None
    peer_vals = [fn(p) for p in peers if p.cse_id != target.cse_id]
    peer_vals = [v for v in peer_vals if v is not None]
    if len(peer_vals) < 3:
        return None
    peer_med = float(median(peer_vals))
    if peer_med == 0:
        deviation = 0.0 if target_val == 0 else float("inf")
    else:
        deviation = (target_val - peer_med) / peer_med
    return {
        "metric": metric,
        "target_value": target_val,
        "peer_median": peer_med,
        "deviation": deviation,
        "exceeds_threshold": abs(deviation) > deviation_threshold,
        "n_peers": len(peer_vals),
    }


__all__ = [
    "DEFAULT_METRICS", "build_peer_groups", "compute_benchmark",
]
