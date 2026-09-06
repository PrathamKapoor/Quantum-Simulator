"""SAT-SA review prioritization (Phase 10) + human review workflow
(Phase 12).

Prioritization orders entities, controls, processes, cases, alerts
by evidence-backed reason. Every priority has a rationale; nothing
is fabricated.

The human review state machine supports:
  - confirm  (examiner accepts the finding)
  - dismiss  (examiner rejects the finding, with reason)
  - escalate (examiner escalates; re-prioritizes)
  - annotate (examiner adds a note)
  - request_manual_review (examiner requests a deeper review)
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .analysis_run import AnalysisRun
from .risk import EntityRisk


# ---------------------------------------------------------------------------
# Priorities.
# ---------------------------------------------------------------------------

PRIORITY_LEVELS = ("low", "medium", "high", "critical")
HUMAN_ACTIONS = ("confirm", "dismiss", "escalate", "annotate",
                  "request_manual_review")


@dataclass
class Priority:
    target_id: str                # entity or alert id
    target_kind: str              # "cse" | "alert" | "case" | "asset" | "process"
    level: str                    # PRIORITY_LEVELS
    score: float                  # 0..1
    rationale: str
    evidence_refs: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "target_id": self.target_id,
            "target_kind": self.target_kind,
            "level": self.level,
            "score": self.score,
            "rationale": self.rationale,
            "evidence_refs": list(self.evidence_refs),
        }


def prioritize_alerts(run: AnalysisRun,
                       risk: EntityRisk,
                       top_n: int = 20) -> list[Priority]:
    """Produce a priority list of alerts based on the entity risk and
    the run's observations."""
    priorities: list[Priority] = []
    for obs in run.observations:
        if obs.target not in run.observations:
            pass
        d = obs.deviation if obs.deviation is not None else 0.0
        # Crude mapping: abs(deviation) -> level
        ad = abs(d)
        if ad >= 8:
            level = "critical"
        elif ad >= 4:
            level = "high"
        elif ad >= 1:
            level = "medium"
        else:
            level = "low"
        rationale = (
            f"Alert {obs.target!r} flagged by worker "
            f"{obs.worker_id!r} with metric {obs.metric!r} (value="
            f"{obs.value:.2f}, deviation={d:.2f})."
        )
        priorities.append(Priority(
            target_id=obs.target,
            target_kind="alert",
            level=level,
            score=min(1.0, ad / 10.0),
            rationale=rationale,
            evidence_refs=[obs.to_dict()],
        ))
    # Sort by level then score.
    level_order = {l: i for i, l in enumerate(reversed(PRIORITY_LEVELS))}
    priorities.sort(key=lambda p: (level_order[p.level], -p.score))
    return priorities[:top_n]


# ---------------------------------------------------------------------------
# Human review state machine.
# ---------------------------------------------------------------------------

@dataclass
class ReviewAction:
    action_id: str
    run_id: str
    target_id: str
    actor: str
    action: str                    # HUMAN_ACTIONS
    reason: str = ""
    note: str = ""
    timestamp: str = ""
    evidence_digest: str = ""

    def to_dict(self) -> dict:
        return {
            "action_id": self.action_id,
            "run_id": self.run_id,
            "target_id": self.target_id,
            "actor": self.actor,
            "action": self.action,
            "reason": self.reason,
            "note": self.note,
            "timestamp": self.timestamp,
            "evidence_digest": self.evidence_digest,
        }


class _ReviewStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._actions: list[ReviewAction] = []

    def add(self, a: ReviewAction) -> None:
        with self._lock:
            self._actions.append(a)

    def for_run(self, run_id: str) -> list[ReviewAction]:
        with self._lock:
            return [a for a in self._actions if a.run_id == run_id]

    def for_target(self, run_id: str, target_id: str) -> list[ReviewAction]:
        with self._lock:
            return [a for a in self._actions
                    if a.run_id == run_id and a.target_id == target_id]


_REVIEW = _ReviewStore()


def record_action(run_id: str, target_id: str, actor: str,
                   action: str, reason: str = "", note: str = "",
                   evidence_digest: str = "") -> ReviewAction:
    if action not in HUMAN_ACTIONS:
        raise ValueError(f"action must be one of {HUMAN_ACTIONS}, got "
                          f"{action!r}")
    a = ReviewAction(
        action_id=str(uuid.uuid4()),
        run_id=run_id,
        target_id=target_id,
        actor=actor,
        action=action,
        reason=reason,
        note=note,
        timestamp=datetime.utcnow().isoformat() + "Z",
        evidence_digest=evidence_digest,
    )
    _REVIEW.add(a)
    return a


def list_actions(run_id: Optional[str] = None,
                   target_id: Optional[str] = None) -> list:
    if run_id is None:
        with _REVIEW._lock:
            return list(_REVIEW._actions)
    if target_id is None:
        return _REVIEW.for_run(run_id)
    return _REVIEW.for_target(run_id, target_id)


__all__ = [
    "Priority", "PRIORITY_LEVELS", "HUMAN_ACTIONS",
    "prioritize_alerts",
    "ReviewAction", "record_action", "list_actions",
]
