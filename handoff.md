# QuantumLab — Handoff to Next Agent

Generated: 2026-08-30, end of autonomous session 7.
Read together with `docs/DEVELOPMENT_STATUS.md` (checkpoint) and
`docs/AUTONOMOUS_SESSION_LOG.md` (per-phase log). This file documents what
actually happened.

---

## 1. Current Phase

- **Project:** QuantumLab — integrated quantum computing / information /
  networking research platform. Python+FastAPI backend, React+TS frontend,
  SQLite persistence.
- **Session 7 of autonomous development.** Objective (roadmap): process-
  isolated experiment workers — experiments execute in disposable child
  processes that cannot crash or corrupt the API process.
- **Status: COMPLETE and validated.** Backend suite green at **630 tests**
  (was 597); frontend build clean; all work committed on `main`.

## 2. Work Completed (session 7)

- **Worker transport** (`backend/app/workers/process_worker.py`):
  `WorkerSpec` (run_id, module, resolved_config, seed) in; `WorkerResult`
  (ok/result/error_type/traceback/exitcode/cancelled/timed_out) out;
  progress as run_id-tagged tuples over a multiprocessing.Queue. The
  entrypoint is module-level (Windows-spawn safe), imports the CANONICAL
  registry, pre-pickles the result so serialization failures are explicit,
  and never touches the database. The supervisor (`run_spec_in_process`)
  handles dead processes/EOF, timeouts (configurable, default none), and
  cancellation via termination — always bounded, never orphans.
- **JobQueue adaptation** (`workers/jobs.py`): the existing bounded queue is
  preserved; its worker threads now SUPERVISE child processes. The submit
  signature takes a persistence facade (the ExperimentService) instead of an
  inline executor. Failures (exception, abnormal exit, missing result,
  serialization, persistence) become FAILED — never COMPLETED. Queued
  cancellation never starts a worker; running cancellation terminates the
  process; the cancel/completion race resolves deterministically (cancellation
  wins if requested before result acceptance). Shutdown terminates active
  children; no new workers spawn after shutdown begins.
- **Service refactor** (`experiments/service.py`): lifecycle persistence
  extracted (`load_run_spec`, `begin_run`, `update_run_progress`,
  `persist_run_success/failure`, `mark_run_cancelled`);
  `execute_run_isolated` runs a run in a worker process (used by
  reproduction); `execute_run_now` remains the documented in-process path
  for direct service use; `recover_interrupted_runs` converts orphaned
  RUNNING/CANCELLING rows to FAILED (INTERRUPTED_BY_RESTART) and returns
  volatile QUEUED to CREATED (called in API lifespan).
- **Diagnostic experiment**: `process_probe` registered in the canonical
  registry (actions: succeed / fail / hard_exit / slow / unserializable) —
  the sanctioned vehicle for worker-lifecycle tests; no experiment-specific
  worker logic exists.
- **Frontend**: unchanged (API contracts preserved) — builds clean.

## 3. Files Changed

Backend: `app/workers/process_worker.py` (new), `app/workers/jobs.py`
(process supervision), `app/workers/__init__.py` (unchanged exports),
`app/experiments/service.py` (persistence extraction + isolated execution +
recovery), `app/experiments/runner.py` (probe + vqe import fix),
`app/api/main.py` (facade call sites + lifespan recovery).
Tests: `tests/test_process_workers.py` (new, 28), 
`tests/test_api_process_workers.py` (new, 5), existing queue call sites
updated to the facade (same contract).
Docs: ARCHITECTURE_DECISIONS (AD-014) / LIMITATIONS / DEVELOPMENT_STATUS /
AUTONOMOUS_SESSION_LOG / handoff.

## 4. Testing and Verification

- Full backend suite: **630 passed** (exit 0; use `--collect-only` for
  counts — the shell drops pytest's summary line).
- Frontend: `npx tsc -b && npm run build` clean (no changes required).
- Crash containment (the central demonstration): worker A hard-exits ->
  run FAILED (WorkerAborted), no result row, DB usable, API healthy,
  worker B completes and persists — at service level AND through the live
  API endpoints.
- Isolation: worker PIDs differ from the API process; identical seeds in
  different workers give identical results; concurrent different-seed
  experiments keep results/progress/seeds correctly attributed.
- Reproducibility: reproduction executes in a worker process and reports
  EXACT_MATCH with the original immutable; surface_code_mwpm p_L is
  bit-identical in-process vs via worker.
- Performance: ~0.4 s warm spawn overhead per job (measured, documented);
  worker exit reclaims memory (teardown verified in tests); no quotas
  claimed.
- Browser validation NOT performed (no tooling); UI unaffected by this
  milestone (internal execution concern).

## 5. Decisions Made (new)

`docs/ARCHITECTURE_DECISIONS.md` → **AD-014**: process-per-experiment on
Windows spawn; parent owns lifecycle + persistence; workers compute only;
strong cancellation via termination; explicit failure taxonomy
(WorkerAborted / WorkerTimeout / SerializationError / PersistenceError /
INTERRUPTED_BY_RESTART); no broker, no Docker, no sandbox claims. Standing
AD-001..AD-013 remain binding.

## 6. Known Limitations

- Process isolation is fault containment, NOT a sandbox: workers run with
  the same OS-user rights; no hard CPU/memory quotas.
- Spawn overhead (~0.4 s warm) makes trivial experiments slower than the
  old threaded model — accepted deliberately.
- Shutdown terminates running workers (runs FAILED); there is no
  checkpoint/resume, only bookkeeping-level stale-run recovery.
- A run cancelled near completion may still complete if the result was
  accepted first (deterministic documented ordering).
- The all-failures Wilson upper-bound quirk (1 - 1e-16) noted in session 6
  remains (shared pipeline code, untouched).

## 7. Unfinished Work / Next Priorities

1. **Playwright browser smoke tests** (roadmap) — the remaining validation
   gap; the API and UI are stable.
2. Optional hardening: checkpoint/resume for very long experiments;
   per-job timeout policy surfaced in the API if ever needed.

## 8. Critical Context

- The persistence facade methods on ExperimentService
  (load_run_spec/begin_run/update_run_progress/persist_run_success/
  persist_run_failure/mark_run_cancelled) are the contract between queue
  and persistence — keep them authoritative; workers must NEVER write.
- `process_probe` is diagnostic-only; do not expose it in frontend
  templates or use it for scientific studies.
- vqe experiment: the import fix restored a module that had never worked;
  its config keys are `system` ("h2"|"tfim"), `n_qubits`, `max_iter`,
  `bond_length_angstrom`.
- Tests spawn real processes (~0.5 s each); `test_process_workers.py` is
  bounded but adds runtime to the suite — this is intentional.
- `quantumlab.db` is gitignored; never commit it.

## 9. Agent Instructions

- Keep the standing loop: inspect → implement → test → validate →
  integrate → document → benchmark → continue.
- Before implementing, re-run the full suite to confirm 630 green; use
  `--collect-only` for the test count; trust exit code + FAILED/ERROR
  counts.
- When touching the worker boundary, re-run `test_process_workers.py` and
  `test_api_process_workers.py` first — they are the adversarial safety
  net (crashes, races, shutdown).
