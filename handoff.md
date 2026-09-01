# QuantumLab — Handoff to Next Agent

Generated: 2026-08-31, end of autonomous session 10.
Read together with `docs/DEVELOPMENT_STATUS.md` (checkpoint) and
`docs/AUTONOMOUS_SESSION_LOG.md` (per-phase log).

---

## 1. Current Phase

- **Project:** QuantumLab — integrated quantum computing / information /
  networking research platform. Python+FastAPI backend, React+TS frontend,
  SQLite persistence.
- **Session 10 of autonomous development.** Objective (milestone 11):
  circuit-level surface-code noise — replace the phenomenological repeated-
  round syndrome generator with a real stabilizer-measurement circuit
  simulator (ancillas, schedules, gate/reset/prep/readout noise, hook errors)
  feeding the existing repeated-round MWPM.
- **Status: COMPLETE and validated.** Backend **704/704** (was 664);
  TypeScript + vite build clean; circuit-level Playwright 2/2; the existing
  repeated-round/phenomenological suites remain green; working tree clean;
  all work committed on `main`.

## 2. Work Completed (session 10)

- **`backend/app/qec/circuit_level.py`** (new): a Pauli (Gottesman-Knill) frame
  simulator over data qubits + disposable ancillas. Deterministic X-/Z-check
  schedules; CNOT propagation (control X -> target X, target Z -> control Z)
  validated against an independent 4x4 matrix CNOT and syndrome_of. Independent
  gate / readout / reset / preparation noise channels. Hook errors emerge from
  the schedule and are recorded. `simulate_circuit_level`,
  `decode_circuit_level` (feeds `decode_repeated`), `simulate_circuit_level_mc`.
- **`backend/app/qec/repeated_round.py`**: additive `hook_events` field only
  (decoder unchanged from the proven session-9 state).
- **API**: `POST /api/qec/rotated-surface-code/circuit-level/{decode,simulate}`
  (schema-validated).
- **Experiment**: `surface_code_circuit_level` runner module — through the
  process-isolated worker; reproduction EXACT_MATCH.
- **Frontend**: `CircuitLevelPanel.tsx` added to QecLab (verdict, hook/data
  metrics, match table, Monte Carlo).
- **Tests**: `tests/test_circuit_level_qec.py` (24), `tests/test_circuit_level_api.py`
  (8), `e2e/tests/circuit_level.spec.ts` (2).
- **Docs**: SCIENTIFIC_MODELS (circuit-level model), LIMITATIONS, AD-017,
  DEVELOPMENT_STATUS (session 10), AUTONOMOUS_SESSION_LOG (session 10), handoff.

## 3. Scientific facts / honest findings

- CNOT propagation and noiseless syndrome extraction are independently
  validated; weight-1 data errors and measurement-flip histories decode
  correctly.
- **The naive schedule does NOT show distance suppression**: a single ancilla
  fault hooks to 2..4 data qubits (a correlated error beyond distance 3's
  correction radius), so p_L(d=5) ≥ p_L(d=3) in this model. This is a real,
  DOCUMENTED property, not a decoder defect. The follow-on is a hook-optimised
  schedule and/or the full circuit-level matching graph.
- Final round readout + single-qubit H gates are IDEAL (documented
  conventions) so the final syndrome equals the net data syndrome, honoring
  decode_repeated's ideal-final-round contract.

## 4. Files Changed

Backend: `app/qec/circuit_level.py` (new), `app/qec/repeated_round.py`
(`hook_events` field + `field` import only), `app/qec/__init__.py` (exports),
`app/experiments/runner.py` (`surface_code_circuit_level`),
`app/api/{schemas,main}.py`.
Tests: `tests/test_circuit_level_qec.py`, `tests/test_circuit_level_api.py`.
Frontend: `src/pages/CircuitLevelPanel.tsx` (new), `src/pages/QecLab.tsx`.
E2E: `e2e/tests/circuit_level.spec.ts`.
Docs: SCIENTIFIC_MODELS / LIMITATIONS / ARCHITECTURE_DECISIONS (AD-017) /
DEVELOPMENT_STATUS / AUTONOMOUS_SESSION_LOG / handoff.

## 5. Commands / Test Counts

- Backend: `.venv/Scripts/python.exe -m pytest backend/tests --timeout=600`
  → 704 collected, all pass (`--collect-only` for the count).
- Frontend: `cd frontend && npx tsc -b && npm run build`.
- E2E: `cd e2e && npx playwright test` (35 + 3 repeated-round + 2 circuit-level
  = 40). Windows: stop dev servers before a fresh-DB run; `localhost` for vite.

## 6. Known Limitations (circuit-level)

- Phenomenological noise only (depolarizing channels; no coherent/correlated
  spatial noise); ideal final-round readout + ideal single-qubit H.
- Decoder is the phenomenological MWPM (not the full circuit-level matching
  graph), per the milestone's "do not duplicate decoding logic".
- Naive schedule: no distance suppression at d=3 (hook errors).
- Bounded rounds (1..64), distances 3/5/7; matcher capacity guard retained;
  no threshold/hardware claims.

## 7. Unfinished Work / Next Priorities

1. **Hook-optimised schedule and/or the circuit-level matching graph** — make
   correlated hook errors decodable and recover distance suppression (the
   logical next step).
2. Optional: coherent errors, biased noise, or reset+preparation refinement.

## 8. Critical Context

- Preserve: AD-003/AD-004, Werner semantics, existing MWPM, process-worker
  semantics (§106) — none changed this session.
- `circuit_level.py` reuses `RotatedSurfaceCode`, `decode_repeated`, the exact
  matcher, and `wilson_interval`; do not fork these.
- The `decode_repeated` "ideal final round" contract is what makes the
  circuit-level final-round readout IDEAL necessary — if you change one, change
  the other and re-run BOTH test files.
- `quantumlab.db` is gitignored; never commit it or E2E evidence.

## 9. Agent Instructions

- Keep the standing loop: inspect → implement → test → validate science →
  integrate → document → benchmark → commit.
- Backend baseline 704; Playwright baseline 40. Both must remain green.
- Before the hook-optimised milestone, reread AD-017 and the SCIENTIFIC_MODELS
  "Session-10 additions" section; extend, do not replace.