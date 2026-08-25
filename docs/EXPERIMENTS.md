# Experiments & Reproducibility

Implementation: `backend/app/experiments/*`, `backend/app/workers/*`,
`backend/app/persistence/db.py`. Validation: `test_experiments.py`.

## Model

- **Experiment** = definition (name, module, base config, sweep, seed,
  objective, hypothesis). **Run** = one execution with resolved config.
  Immutable once COMPLETED (§98, §127).
- Statuses: CREATED → RUNNING → COMPLETED | FAILED | CANCELLED. Failed runs
  keep `error_code`/`error_message`; a failed run is never reported complete.
- Result documents carry `schema: quantumlab.run-result` v1 with metrics,
  summary, artifacts, and per-study notes.

## Runner registry

circuit_shots · qec_sweep · bb84_study · network_study · vqe · grover_study ·
purification_study · repeater_study · network_bb84

Each runner is a pure function of (resolved_config, seed): identical inputs
reproduce identical outputs bit-for-bit.

## Sweeps

Cartesian expansion of declared sweep parameters over the base config;
grid capped at 256 runs; each combination becomes an independent run with a
deterministically derived seed (`seed + 7919·index`).

## Execution & jobs

Runs execute on the threaded JobQueue (bounded workers); progress callbacks
persist fraction+detail to the runs table and broadcast over
`/ws/jobs`. Cancellation is cooperative at progress boundaries; cancelled
runs are CANCELLED, never silently completed.

## Reproducibility

`POST /api/runs/{id}/reproduce` re-executes the stored resolved config + seed
as a NEW run (original untouched) and compares result documents:

| Status | Meaning |
|--------|---------|
| EXACT_MATCH | every flattened scalar identical |
| TOLERANCE_MATCH | numerics within 1e−9 relative only |
| MISMATCH | structural difference or numeric drift beyond tolerance |

Deterministic modules reproduce EXACT_MATCH (regression-tested).

## Comparison

Multi-run comparison reports differing parameters, per-run metrics, seeds —
without claiming statistical significance unless a test was actually applied.

## Export

`GET /api/runs/{id}/export.csv` emits the artifacts table with provenance
columns: experiment_id, run_id, seed, then data columns.

## Statistics subsystem

`app.analytics.statistics`: mean/std/SEM, normal-approximation CI (documented:
normal quantile, CLT assumption), percentile bootstrap (seeded), Wilson
proportion intervals. Every stochastic summary exposes N explicitly.

## Preflight validation (§130, §238)

Experiment creation validates module existence, seed type, sweep values.
Execution-time validation rejects oversized circuits (e.g. quantum-info
reports >10 qubits), invalid probabilities, and malformed topologies with
actionable messages before any compute starts.
