"""SAT-SA AnalysisRun engine.

A thin orchestration layer (reusing the existing `app.experiments`
infrastructure where it makes sense, but a dedicated `AnalysisRun`
data class for clarity).

An `AnalysisRun` represents one execution of the analytical pipeline
over a normalized CSE submission. The run has:
  - run_id
  - cse_id
  - submission_id
  - started_at / completed_at
  - status (CREATED, RUNNING, COMPLETED, FAILED)
  - observations: list of (worker_id, observation_dict)
  - findings: list of Finding
  - provenance: provenance dict (signed by the trust layer)

Workers are registered through `satsa.workers.registry` and
executed sequentially. A worker is a callable:

  def worker(submission: CSESubmission) -> list[Observation]

The run is persisted to an in-memory store by default; a SQLite
backend can be added by re-implementing the store (the interface
is the same).
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from .domain import CSESubmission
from .trust import audit_root, verify_signature


# ---------------------------------------------------------------------------
# Findings and observations.
# ---------------------------------------------------------------------------

@dataclass
class Observation:
    worker_id: str
    worker_version: str
    target: str                    # e.g. asset_id, alert_id, cse_id
    metric: str                    # e.g. "closure_duration_minutes"
    value: float
    baseline: Optional[float] = None
    deviation: Optional[float] = None
    evidence_refs: list = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "worker_id": self.worker_id,
            "worker_version": self.worker_version,
            "target": self.target,
            "metric": self.metric,
            "value": self.value,
            "baseline": self.baseline,
            "deviation": self.deviation,
            "evidence_refs": list(self.evidence_refs),
            "notes": self.notes,
        }


@dataclass
class Finding:
    finding_id: str
    cse_id: str
    worker_id: str
    severity: str                # "info" | "low" | "medium" | "high" | "critical"
    confidence: float            # 0..1
    what: str                     # WHAT happened
    why: str                      # WHY is it unusual
    evidence: list               # refs to observations, source records
    recommendation: str
    rationale: str = ""

    def to_dict(self) -> dict:
        return {
            "finding_id": self.finding_id,
            "cse_id": self.cse_id,
            "worker_id": self.worker_id,
            "severity": self.severity,
            "confidence": self.confidence,
            "what": self.what,
            "why": self.why,
            "evidence": list(self.evidence),
            "recommendation": self.recommendation,
            "rationale": self.rationale,
        }


# ---------------------------------------------------------------------------
# AnalysisRun.
# ---------------------------------------------------------------------------

RUN_STATUSES = ("CREATED", "RUNNING", "COMPLETED", "FAILED")


@dataclass
class AnalysisRun:
    run_id: str
    cse_id: str
    submission_id: str
    status: str = "CREATED"
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    observations: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    error: str = ""
    audit_trail: list = field(default_factory=list)
    provenance_signature: Optional[dict] = None

    @property
    def audit_root(self) -> str:
        """Merkle root of the audit trail (computed on demand)."""
        return audit_root(self.audit_trail)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "cse_id": self.cse_id,
            "submission_id": self.submission_id,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "observations": [o.to_dict() if isinstance(o, Observation)
                              else o for o in self.observations],
            "findings": [f.to_dict() if isinstance(f, Finding)
                          else f for f in self.findings],
            "error": self.error,
            "audit_root": self.audit_root,
            "provenance_signature": self.provenance_signature,
        }


# ---------------------------------------------------------------------------
# Run store (in-memory, thread-safe).
# ---------------------------------------------------------------------------

class _RunStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._runs: dict[str, AnalysisRun] = {}

    def add(self, run: AnalysisRun) -> None:
        with self._lock:
            self._runs[run.run_id] = run

    def get(self, run_id: str) -> Optional[AnalysisRun]:
        with self._lock:
            return self._runs.get(run_id)

    def list(self) -> list:
        with self._lock:
            return list(self._runs.values())


_STORE = _RunStore()


def get_run(run_id: str) -> Optional[AnalysisRun]:
    return _STORE.get(run_id)


def list_runs() -> list:
    return _STORE.list()


# ---------------------------------------------------------------------------
# Worker registry.
# ---------------------------------------------------------------------------

WorkerFn = Callable[[CSESubmission], list[Observation]]
_REGISTRY: dict[str, tuple[str, WorkerFn]] = {}


def register_worker(worker_id: str, version: str,
                     fn: WorkerFn) -> None:
    _REGISTRY[worker_id] = (version, fn)


def get_worker(worker_id: str) -> tuple[str, WorkerFn]:
    if worker_id not in _REGISTRY:
        raise KeyError(f"unknown worker: {worker_id}")
    return _REGISTRY[worker_id]


def list_workers() -> list[dict]:
    return [
        {"worker_id": wid, "version": ver}
        for wid, (ver, _) in _REGISTRY.items()
    ]


# ---------------------------------------------------------------------------
# Run execution.
# ---------------------------------------------------------------------------

def execute_run(submission: CSESubmission,
                 worker_ids: Optional[list[str]] = None,
                 keypair: Optional[object] = None,
                 ) -> AnalysisRun:
    """Execute an AnalysisRun over the given submission.

    If worker_ids is None, runs ALL registered workers. If keypair
    is given (a `KeyPair` from `satsa.trust`), signs the run's
    provenance.
    """
    run = AnalysisRun(
        run_id=str(uuid.uuid4()),
        cse_id=submission.cse_id,
        submission_id=submission.submission_id,
    )
    _STORE.add(run)
    run.status = "RUNNING"
    run.started_at = datetime.utcnow().isoformat() + "Z"
    try:
        ids = worker_ids if worker_ids is not None else list(_REGISTRY.keys())
        for wid in ids:
            version, fn = get_worker(wid)
            obs = fn(submission)
            run.observations.extend(obs)
            # Audit trail: append one record per worker per run.
            run.audit_trail.append({
                "worker_id": wid,
                "worker_version": version,
                "cse_id": submission.cse_id,
                "submission_id": submission.submission_id,
                "n_observations": len(obs),
                "executed_at": datetime.utcnow().isoformat() + "Z",
            })
        # Derive findings from observations in a separate phase
        # (the analytical-engine files do this in Phase 5+).
        run.status = "COMPLETED"
    except Exception as e:
        run.status = "FAILED"
        run.error = str(e)
    finally:
        run.completed_at = datetime.utcnow().isoformat() + "Z"
    if keypair is not None:
        from .trust import sign_submission as _sign
        run.provenance_signature = _sign(run.to_dict(), keypair).to_dict()
    return run


__all__ = [
    "Observation", "Finding", "AnalysisRun",
    "get_run", "list_runs",
    "register_worker", "get_worker", "list_workers",
    "execute_run",
]
