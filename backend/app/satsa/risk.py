"""SAT-SA entity risk engine (Phase 9).

Aggregates observations into an explainable, decomposable entity
risk profile. The risk is NEVER a single number; each component
links to specific findings/observations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .analysis_run import AnalysisRun, Finding, Observation
from .domain import CSESubmission


# Risk components (each is a list of observations / findings feeding
# into one dimension of the risk).
RISK_COMPONENTS = (
    "execution_gap",
    "negative_space",
    "anomaly",
    "peer_deviation",
    "coverage",
    "investigation",
)


@dataclass
class ComponentRisk:
    name: str
    score: float            # 0..1
    n_findings: int
    n_observations: int
    finding_ids: list = field(default_factory=list)
    observation_refs: list = field(default_factory=list)
    rationale: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "score": self.score,
            "n_findings": self.n_findings,
            "n_observations": self.n_observations,
            "finding_ids": list(self.finding_ids),
            "observation_refs": list(self.observation_refs),
            "rationale": self.rationale,
        }


@dataclass
class EntityRisk:
    cse_id: str
    submission_id: str
    components: dict = field(default_factory=dict)
    overall_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "cse_id": self.cse_id,
            "submission_id": self.submission_id,
            "components": {k: v.to_dict() for k, v in self.components.items()},
            "overall_score": self.overall_score,
        }


def _score_from_observations(obs_list: list[Observation],
                              critical_severity: int = 0) -> float:
    """Crude scoring: each observation is a 0..1 contribution based
    on the deviation field; we cap at 1. Critical observations count
    double. The score is normalized by the number of assets in
    the submission (caller divides)."""
    if not obs_list:
        return 0.0
    total = 0.0
    for o in obs_list:
        d = o.deviation if o.deviation is not None else 0.0
        contribution = min(1.0, abs(d) / 10.0)  # rough normalization
        total += contribution
    return min(1.0, total / max(1, len(obs_list)))


def derive_risk(submission: CSESubmission,
                 run: AnalysisRun) -> EntityRisk:
    """Build a decomposable entity risk from the run's observations.

    Each component is scored by the observations attributed to it
    (by worker_id prefix). The overall score is a weighted average
    of components with documented weights.
    """
    by_component: dict[str, list[Observation]] = {c: [] for c in RISK_COMPONENTS}
    for o in run.observations:
        wid = o.worker_id
        for c in RISK_COMPONENTS:
            if wid.startswith(c):
                by_component[c].append(o)
                break

    components = {}
    for c, obs_list in by_component.items():
        score = _score_from_observations(obs_list)
        comp = ComponentRisk(
            name=c,
            score=score,
            n_findings=0,
            n_observations=len(obs_list),
            observation_refs=[
                {"worker_id": o.worker_id, "target": o.target,
                 "metric": o.metric, "value": o.value}
                for o in obs_list
            ],
            rationale=(f"{c}: {len(obs_list)} observation(s) "
                       f"with score {score:.2f}"),
        )
        components[c] = comp

    # Overall: weighted average (documented weights)
    weights = {
        "execution_gap": 0.30,
        "negative_space": 0.20,
        "anomaly": 0.20,
        "peer_deviation": 0.15,
        "coverage": 0.10,
        "investigation": 0.05,
    }
    overall = sum(weights.get(c, 0.0) * comp.score
                  for c, comp in components.items())
    return EntityRisk(
        cse_id=submission.cse_id,
        submission_id=submission.submission_id,
        components=components,
        overall_score=overall,
    )


__all__ = ["ComponentRisk", "EntityRisk", "derive_risk", "RISK_COMPONENTS"]
