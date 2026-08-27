# QuantumLab — Handoff to Next Agent

Generated: 2026-08-26, end of autonomous session 4.
Read together with `docs/DEVELOPMENT_STATUS.md` (checkpoint) and
`docs/AUTONOMOUS_SESSION_LOG.md` (per-phase log). This file documents what
actually happened.

---

## 1. Current Phase

- **Project:** QuantumLab — integrated quantum computing / information /
  networking research platform. Python+FastAPI backend, React+TS frontend,
  SQLite persistence.
- **Session 4 of autonomous development.** Objective (roadmap priority #1):
  promote distributed quantum computation from a standalone subsystem into a
  first-class experiment type — full lifecycle, persistence, reproducibility,
  sweeps, comparison, cancellation, API, and Experiments-UI workflow.
- **Status: COMPLETE and validated.** Backend suite green at **437 tests**;
  frontend build clean. All work committed on `main`.

## 2. Work Completed (session 4)

- **Runner adapter** (`backend/app/experiments/runner.py`):
  `RUNNER_REGISTRY["distributed_circuit"] = run_distributed_circuit`. Wraps the
  existing `DistributedExecutor` output (`quantumlab.distributed-result` v1)
  in the standard `quantumlab.run-result` v1 document. Config: `circuit`
  (document), `protocol`, `qubit_to_node` (explicit) OR `num_nodes`
  (auto-assign), `topology`, `network_config`, `fallback`.
- **Engine correctness fixes** (`backend/app/distributed/engine.py`), all
  regression-covered:
  1. `ebit_consumption` now reflects actual protocol cost (double_teleport = 2
     ebits / 4 cbits) rather than the single-ebit partition estimate.
  2. Explicit `fallback="centralized"` now emits a single local CNOT and skips
     protocol expansion + carrier remapping (previously double-applied the gate
     and corrupted remapping).
  3. Classical-message records only attach to executed protocol expansions.
- **Sweep fix** (`expand_sweep` in runner.py): each combo now seeds from the
  base configuration (`rec(0, dict(spec.config), [])`). Sweeps over
  `num_nodes` (auto-assign) are supported, engine-backed, and recorded.
- **Lifecycle** (existing infra, no migration): create → runs (seed
  `spec.seed + 7919*i`) → threaded JobQueue → execute → persist `results`
  row → reproduce (new run, EXACT_MATCH, original immutable) → compare →
  cancel (cooperative; queued guaranteed, running is atomic — documented).
- **API**: no new routes required — the existing `/api/experiments` and
  `/api/runs/{id}/*` endpoints accept the new module. Two end-to-end API tests.
- **Frontend** (`frontend/src/pages/Experiments.tsx`): `DistributedResultView`
  component (resource cards, modelled-latency disclaimer, equivalence verdict,
  entanglement/remote-op/classical-message/probability tables, raw document
  `<details>`), "Distributed GHZ study" template, and a "Reproduce" button per
  completed run.
- **Docs**: DEVELOPMENT_STATUS (session 4 checkpoint), SCIENTIFIC_MODELS
  (experiment records + reproducibility + sweep semantics),
  LIMITATIONS (integration-specific), ARCHITECTURE_DECISIONS AD-011
  (adapter/orchestration rationale, ownership, persistence, seed, cancellation,
  large-result, sweep strategies), AUTONOMOUS_SESSION_LOG.

## 3. Files Changed

Backend: `app/experiments/runner.py`, `app/distributed/engine.py`,
`app/api/schemas.py` (removed transient unused experiment schema classes),
`tests/test_distributed_experiment_runner.py` (new, 16 tests),
`tests/test_api_distributed.py` (extended to 8 tests).
Frontend: `src/pages/Experiments.tsx`.
Docs: DEVELOPMENT_STATUS / SCIENTIFIC_MODELS / LIMITATIONS /
ARCHITECTURE_DECISIONS / AUTONOMOUS_SESSION_LOG / handoff.

## 4. Testing and Verification

- `.venv/Scripts/python.exe -m pytest backend/tests --timeout=300` → **437
  passed** (exit 0). Note: the tool/shell drops pytest's final "N passed" line;
  confirm via `--collect-only` count and exit code / FAILED counts.
- New coverage: config validation, topology, protocol accounting, auto-assign,
  failure→FAILED semantics, fallback-centralized, lifecycle
  (CREATE→RUNNING→COMPLETED), reproduction immutability (EXACT_MATCH),
  sweep materialization + source-config immutability, comparison, queued
  cancellation, and end-to-end API create→execute→result + reproduce.
- Frontend: `npx tsc -b && npm run build` clean (31 modules).
- Browser inspection NOT performed (no browser tooling); UI verified via
  TypeScript build + endpoint contracts only. Do not claim visual validation.

## 5. Decisions Made (new)

`docs/ARCHITECTURE_DECISIONS.md` → AD-011 (adapter over the engine, result
ownership = distributed-result v1, existing-tables persistence, existing seed
convention, cooperative cancellation with atomic-engine limitation, large-result
summary-in-runs/full-doc-in-results, float-only sweep with base-config fix).
Standing AD-001..AD-010 remain binding (ordering conventions AD-003/AD-004,
explicit-mapping honouring AD-010, no-silent-fallback AD-009).

## 6. Known Limitations

- RUNNING cancellation is cooperative and the in-process engine is atomic:
  queued jobs cancel cleanly; running distributed jobs finish unless the runner
  checks the cancel flag (it doesn't — same as other registry runners).
- Sweep values are float-typed by the existing framework; string dimensions
  (e.g. `protocol`) cannot be swept without a framework change.
- `distributed_circuit` runs use statevector mode, ideal local operations;
  grant fidelity is reported, not yet injected (next milestone).
- Experiments UI template is a fixed GHZ study; circuit editing inside the
  template is a listed next step.
- Auto-assigned partitions may leave a requested node empty; `node_count`
  reflects nodes actually hosting qubits.

## 7. Unfinished Work / Next Priorities

1. **NOISY EBITS / WERNER MODEL** — the intended next scientific milestone:
   map each network grant's fidelity into the protocol circuit (Werner-form
   ebit preparation) instead of reporting it separately. The engine's ebit
   admission path (`NetworkBridge` → `expand_remote_cnot`) is the integration
   point; `EbitGrant.fidelity` is already available.
2. MWPM decoder + planar rotated surface-code layout.
3. Process-isolated workers with checkpoint/resume (also enables interruptible
   RUNNING cancellation).
4. Playwright smoke tests (close the visual-inspection gap).
5. Template circuit editor in the distributed experiment UI.

## 8. Critical Context

- The experiment runner gets `(config, seed)` — no progress callback (matches
  every other runner). Progress is the generic 0.05→1.0 in `execute_run`.
- `run_distributed_circuit` requires either `qubit_to_node` or `num_nodes`
  (>=2) and raises on both missing and on distributed failure (so runs record
  FAILED, never fabricated COMPLETED).
- The `results` table stores the full document payload; list endpoints
  (`list_experiments`) use run_count only and never decompress result blobs.
- Do not reintroduce the partition-plan ebit estimate or the double-application
  fallback bug (both regression-covered in `test_distributed_experiment_runner.py`
  and `test_distributed_full.py`).
- `quantumlab.db` is gitignored; never commit it.

## 9. Agent Instructions

- Keep the standing loop: inspect → implement → test → validate science →
  integrate → document → benchmark → continue.
- Before implementing, re-run the full suite to confirm 437 green.
- Use `--collect-only` for the test count (the summary line is unreliable in
  this shell); trust exit code + FAILED/ERROR counts.