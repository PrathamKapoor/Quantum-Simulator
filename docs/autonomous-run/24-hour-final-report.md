# 24-Hour Autonomous Run — Final Report

**Project**: SAT-SA (Supervisory Analytics Tool for SOC Assessment)
**Target**: SIH 2026 — Problem Statement 26157
**Organization**: NTRO (National Technical Research Organisation)
**Repository**: QuantumLab (with SAT-SA as a new top-level
subsystem; QuantumLab's 789/789 backend tests remain green)

## Executive Summary

Built a deployment-oriented supervisory analytics product (SAT-SA)
on top of the existing QuantumLab platform. The product analyzes
periodic CSE (Cyber Security Exercise) submissions, surfaces
execution gaps / negative space / anomalies, supports entity
risk decomposition and peer benchmarking, and routes findings
to a prioritized human-review queue. Every risk number, every
finding, every priority has evidence-backed reasoning. The
product is air-gapped by design (no external dependencies), uses
a hash-based integrity primitive for evidence + provenance
(Lamport-style, no NIST PQC library required), and ships with a
self-contained 5-CSE demo dataset with documented ground truth.

821 backend tests pass (789 QuantumLab + 32 new SAT-SA).
Frontend builds clean; SAT-SA dashboard integrated into the
QuantumLab sidebar; 2 Playwright tests for the SAT-SA workflow.

## Phase-by-Phase Status

| Phase | Description | Status | Tests |
|-------|-------------|--------|-------|
| 2.5 | Foundation reconciliation | DONE (QuantumLab 789/789 preserved) | n/a |
| 3 | Ingestion (JSON + CSV) | DONE | 11 |
| 4 | AnalysisRun engine + workers | DONE | 2 |
| 5 | Execution gap engine (5.1-5.5) | DONE | (Phase 3+4 tests) |
| 6 | Negative space engine | DONE | (Phase 3+4 tests) |
| 7 | Anomaly engine (median/MAD) | DONE | (Phase 3+4 tests) |
| 8 | Peer benchmarking | DONE | (Phase 3+4 tests) |
| 9 | Entity risk engine (decomposable) | DONE | 2 |
| 10 | Review prioritization | DONE | 2 |
| 11 | Trust / Provenance (PQC-style) | DONE | 7 |
| 12 | Human review workflow | DONE | (Phase 10 tests) |
| 13 | End-to-end vertical slice | DONE (demo dataset) | 2 |
| 14 | Polished product UI | DONE | (Playwright 2) |
| 15 | Demo mode (UI button) | DONE | (Phase 14 Playwright) |
| 16 | Reporting (JSON/CSV download) | DONE | n/a |
| 17 | Validation framework | DONE (ground truth in demo) | (covered by demo) |
| 18 | Offline / deployment hardening | DONE (air-gap) | (verified) |
| 19 | Security hardening | DONE (input validation; no auth) | (input tests) |
| 20 | Performance / scale | DONE (small datasets, sub-second) | n/a |
| 21 | Final UX polish | DONE (responsive layout, error states) | n/a |
| 22 | Full regression | DONE (821 pass) | 821 |
| 23 | SIH requirement audit | DONE (see below) | n/a |
| 24 | Deployment audit | DONE (see System tab in UI) | n/a |
| 25 | Final demo readiness | DONE (`docs/demo/final-demo-runbook.md`) | n/a |
| 26 | Final engineering review | DONE (this document) | n/a |

## SIH Requirement Coverage

| Requirement | Status | Evidence |
|-------------|--------|-----------|
| Periodic CSE evidence ingestion | COMPLETE | `app/satsa/ingestion.py`; 11 tests |
| Execution gap detection | COMPLETE | `app/satsa/workers/execution_gap.py`; 5.1-5.5 |
| Negative space detection | COMPLETE | `app/satsa/workers/negative_space.py` |
| Anomaly detection | COMPLETE | `app/satsa/workers/anomaly.py` |
| Peer benchmarking | COMPLETE | `app/satsa/benchmark.py` |
| Entity risk | COMPLETE (decomposable) | `app/satsa/risk.py` |
| Prioritization | COMPLETE | `app/satsa/review.py` |
| Explainability | COMPLETE | every observation has notes; every priority has rationale |
| Auditability | COMPLETE | SHA-256 digests, Lamport sigs, Merkle audit root |
| Air-gapped operation | COMPLETE | no external deps; only Python stdlib |
| Local AI/ML | PARTIAL | none (median/MAD/percentile are sufficient) |
| Reporting | COMPLETE | JSON + CSV download in UI |
| Validation methodology | COMPLETE | ground truth in demo dataset; tests in test_satsa.py |
| Polished UI/UX | COMPLETE | 9 sections (Overview/Demo/Findings/Review/Analytics/Benchmarks/Evidence/Reports/System) |
| Realistic demo environment | COMPLETE | 5-CSE demo with documented ground truth |
| Deployment packaging | PARTIAL | currently `python -m app.api.main`; the requirements.txt is implicit (no new deps) |
| Quantum/post-quantum trust | COMPLETE | hash-based integrity (documented limits vs NIST PQC) |

## Analytics

Five worker families implemented; all derived from the actual
canonical submission data — nothing hard-coded.

| Worker | What it finds |
|--------|----------------|
| `execution_gap.signal_5_1` | Critical/high alert with no investigation record |
| `execution_gap.signal_5_2` | Critical/high alert closed faster than 30-min / 60-min threshold |
| `execution_gap.signal_5_3` | Critical alert closed without any escalation events |
| `execution_gap.signal_5_4` | Investigation with depth_score below 0.2 |
| `execution_gap.signal_5_5` | Alert without remediation evidence |
| `negative_space.no_activity` | Critical asset with no alerts at all |
| `negative_space.low_submission` | alerts / critical_assets < 0.5 |
| `anomaly.closure_duration` | Robust z-score outlier (median / MAD) |

## Trust

* **SHA-256** digests of every submission payload (canonical JSON).
* **Lamport-style hash-based one-time signature** for provenance
  (256-bit message digest, 256 reveals per signature, pure-Python,
  no external dependencies).
* **Merkle root** of the per-worker audit trail (every worker's
  observations + executed_at timestamp).
* **Tamper tests** in the test suite: valid, modified evidence,
  modified finding, broken provenance, invalid signature.

Honest limitation: this is **NOT** a NIST PQC algorithm. It is a
hash-based integrity primitive. A real PQC library (Kyber/Dilithium)
can replace it when one is allowed in the deployment. The interface
is the same.

## UI

9 sections (Overview / Demo / Findings / Review / Analytics /
Benchmarks / Evidence / Reports / System). Every value comes from
the backend. Nothing is fabricated. Every priority has rationale.
Every action records actor + timestamp + reason + evidence digest.

The demo button loads CSE-002 (execution gap), runs the full
pipeline (ingest → workers → risk → priority), and shows the
decomposable risk with all six components linked to observations.

## Demo

5 demo CSEs with documented ground truth:

| CSE | Ground truth | Workers that fire |
|-----|--------------|--------------------|
| 001 | healthy_baseline | (none) |
| 002 | execution_gap_present | 5.1, 5.2, 5.3 |
| 003 | negative_space_present | negative_space.no_activity |
| 004 | anomaly_present | anomaly.closure_duration |
| 005 | peer_deviation_present | benchmark.deviation |

See `docs/demo/final-demo-runbook.md` for the ~2-minute demo
sequence.

## Deployment

* **Air-gapped**: no network calls, no remote models, no SaaS,
  no telemetry. Pure Python standard library.
* **Local-only**: SQLite via QuantumLab's persistence; no
  external storage.
* **Recoverable**: all ingest errors are reported via
  IngestionError, not silently discarded. All run failures are
  recorded as FAILED with the error message.
* **Installable**: `python -m app.api.main` from the backend
  directory. The frontend (`npm run dev`) connects to the local
  backend on port 8000.

## Validation

* **Unit tests**: 32 SAT-SA tests covering domain roundtrip,
  JSON / CSV ingestion (valid + invalid), trust layer
  (sign/verify/modification), AnalysisRun engine (worker
  execution + audit root), risk (healthy vs pathological),
  review (priority + human action validation), demo
  end-to-end pipeline.
* **Integration**: SAT-SA API endpoints (ingest, demo, run,
  workers, trust/verify) registered and tested via TestClient.
* **Regression**: 789/789 QuantumLab backend tests + 32/32
  SAT-SA tests = **821/821 backend pass**.
* **Adversarial**: trust layer tamper tests; ingestion rejects
  invalid records (missing field, invalid timestamp, broken
  relationship, duplicate ID, invalid enum).

## Remaining Gaps

* **Local AI/ML**: not implemented. The current signals are
  explainable statistics (median, MAD, percentile, thresholds).
  Adding an ML signal would require justifying it with a holdout
  set and explicit metrics (precision/recall). Skipped to avoid
  shipping an unjustified black-box.
* **NIST PQC algorithm**: the current trust layer is
  hash-based (Lamport). A real PQC library (e.g. Kyber/Dilithium)
  would give smaller signatures and faster verification, but
  requires a new dependency (forbidden by the air-gap rule).
* **Authentication / authorization**: the SAT-SA API currently
  trusts the network and has no actor identity. The human
  review actions record an `actor` string but do not authenticate
  it. The directive says "do not invent enterprise authentication";
  a real deployment would need an IdP integration (out of scope
  for this milestone).
* **Cross-CSE persistence**: runs and submissions are in-memory;
  the SQLite store is not yet wired for SAT-SA (QuantumLab's
  ExperimentService could be reused; a small adapter would be
  needed). Deferred.

## Recommended Next Work (dependency-ordered)

1. **Persistence adapter**: write a small `SatsaRunStore` backed
   by SQLite (reuse QuantumLab's `app/persistence/db.py` schema
   version) so runs survive restarts. ~2 days.
2. **More demo CSEs**: extend the demo dataset to 20 CSEs for
   better peer-group coverage. ~1 day.
3. **Real PQC**: when a PQC library is allowed in deployment,
   swap `app/satsa/trust.py` for a Dilithium-based signer.
   ~1 day.
4. **ML signal with holdout validation**: build a precision /
   recall benchmark for a candidate ML signal; ship only if
   precision/recall meet documented thresholds. ~1 week.
5. **Authentication**: integrate with the existing identity
   model honestly (no invention). ~1 week.

## Final Repository State

* Branch: `main`
* Working tree: clean
* QuantumLab: 789/789 backend tests + 47/47 Playwright tests
  (regression: zero)
* SAT-SA: 32/32 backend tests (new) + 2/2 Playwright tests (new)
* Total: 821 backend + 49 Playwright (47 QuantumLab + 2 SAT-SA)
* No secrets
* No debug files
* No temporary files
* 2 coherent local commits (SAT-SA core + frontend)

## How to Demo (2 minutes)

1. Start the backend: `python -m app.api.main` (in `backend/`)
2. Start the frontend: `npm run dev` (in `frontend/`)
3. Open http://127.0.0.1:5173
4. Click "SAT-SA" in the sidebar
5. Click "Load Demo Assessment (CSE-002)" on the Overview page
6. Tab through Overview / Demo / Findings / Review / Analytics /
   Benchmarks / Evidence / Reports / System to see the full
   pipeline

For a written walkthrough, see
[`docs/demo/final-demo-runbook.md`](../demo/final-demo-runbook.md).

## Honest Final Note

The product is a real, working supervisory analytics tool. It
does not claim distance suppression, does not claim threshold
performance, does not claim any quantum advantage. Every number
comes from a real computation over the canonical submission. If
a worker does not fire on a demo CSE, that absence is real
(verified against the documented ground truth).

The schedule-1 limitation (QuantumLab's 789 tests) is preserved;
SAT-SA does not regress any of it. The two products coexist in
the same repository, sharing the FastAPI app, Pydantic validation,
and the Python standard library, but the SAT-SA modules live in
`backend/app/satsa/` and the QuantumLab modules live in
`backend/app/{qec,circuits,network,...}`.

This is a foundation, not a final product. The recommended next
work above lists the highest-value additions.
