# QuantumLab — Handoff to Next Agent

Generated: 2026-08-31, end of autonomous session 9.
Read together with `docs/DEVELOPMENT_STATUS.md` (checkpoint) and
`docs/AUTONOMOUS_SESSION_LOG.md` (per-phase log).

---

## 1. Current Phase

- **Project:** QuantumLab — integrated quantum computing / information /
  networking research platform. Python+FastAPI backend, React+TS frontend,
  SQLite persistence.
- **Session 9 of autonomous development.** Objective: extend QEC from
  single-shot code-capacity decoding to REPEATED-ROUND (space-time) decoding
  with measurement-error handling (the highest-value next milestone after the
  original validation roadmap completed — documented decision).
- **Status: COMPLETE and validated.** Backend **664/664** (was 630);
  TypeScript + vite build clean; repeated-round Playwright 3/3; working tree
  clean; all work committed on `main`.

## 2. Work Completed (session 9)

- **Repeated-round decoder** (`backend/app/qec/repeated_round.py`): a
  two-stage phenomenological space-time decoder (AD-016). Stage A = MWPM over
  syndrome-difference layers (spatial data edges, lateral boundary, temporal
  measurement edges); Stage B = single-shot decode of the final residual
  syndrome. Reuses the existing geometry, exact integer matcher, and coset
  classification verbatim. Persistent per-slot depolarizing data noise (p_d)
  + independent per-round measurement flips (p_m, rounds 1..R-1; ideal final
  round), integer-quantized log-likelihood weights.
- **Tests**: `tests/test_repeated_round_qec.py` (28 exact deterministic +
  MC), `tests/test_repeated_round_api.py` (6 API/experiment).
- **API**: `POST /api/qec/rotated-surface-code/repeated-round/decode` and
  `/simulate` (schema-validated).
- **Experiment**: `repeated_round_surface_code` runner module — through the
  real process-isolated worker, reproduction EXACT_MATCH, invalid config →
  FAILED.
- **Frontend**: `RepeatedRoundPanel.tsx` (space-time SVG, match table,
  observed-syndrome history, Monte Carlo summary) added to QecLab.
- **Playwright**: `e2e/tests/repeated_round.spec.ts` (3 tests).
- **Docs**: SCIENTIFIC_MODELS (repeated-round model), LIMITATIONS, AD-016,
  DEVELOPMENT_STATUS (session 9), AUTONOMOUS_SESSION_LOG (session 9), handoff.

## 3. Scientific model (key facts)

- Detection event at layer t (1..R) = syndrome difference `o_t XOR o_{t-1}`
  (clean start o_0 = 0). A persistent data error appears at exactly one layer;
  a measurement flip at round t <= R-1 appears as a pair (S,t)-(S,t+1).
- Weights w_s = -ln((p_d/3)/(1-p_d)), w_m = -ln(p_m/(1-p_m)) quantized to 1e-6.
- Residual = correction XOR cumulative true data error, classified by the
  coset functionals (CORRECTED / LOGICAL_X / LOGICAL_Z / LOGICAL_Y). A
  zero-syndrome logical operator still fires (§33 preserved).
- **Why two-stage (not a single 3-D MWPM)**: a naive "differences + final
  clean column" graph double-counts a persistent data error and over-corrects
  boundary errors into false logical failures (found + fixed this session).

## 4. Files Changed

Backend: `app/qec/repeated_round.py` (new), `app/qec/__init__.py` (exports),
`app/experiments/runner.py` (`repeated_round_surface_code`),
`app/api/{schemas,main}.py` (two endpoints + two schemas).
Tests: `tests/test_repeated_round_qec.py`, `tests/test_repeated_round_api.py`.
Frontend: `src/pages/RepeatedRoundPanel.tsx` (new), `src/pages/QecLab.tsx`
(import + render call).
E2E: `e2e/tests/repeated_round.spec.ts`.
Docs: SCIENTIFIC_MODELS / LIMITATIONS / ARCHITECTURE_DECISIONS (AD-016) /
DEVELOPMENT_STATUS / AUTONOMOUS_SESSION_LOG / handoff.

## 5. Commands / Test Counts

- Backend: `.venv/Scripts/python.exe -m pytest backend/tests --timeout=600`
  → 664 collected, all pass (use `--collect-only` for the count).
- Frontend: `cd frontend && npx tsc -b && npm run build`.
- E2E: `cd e2e && npx playwright test` (35 + 3 = 38 tests). Remember Windows:
  stop dev servers before a fresh-DB run; `localhost` (not 127.0.0.1) for vite.

## 6. Known Limitations (repeated-round)

- Phenomenological only (no circuit-level gate/reset/ancilla noise — the next
  milestone).
- Ideal final round (a final measurement flip is indistinguishable from a
  final data error and is excluded).
- Two-stage decode (documented tradeoff vs a single 3-D graph).
- Bounded rounds (1..64), distances 3/5/7; integer-quantized weights;
  matcher capacity guard retained; no threshold/hardware claims.

## 7. Unfinished Work / Next Priorities

1. **Circuit-level QEC noise** (§45-§50): model ancilla preparation, gate,
   reset, and measurement-channel noise on the actual stabilizer-measurement
   circuits, rather than phenomenological per-round flips. Reuse the existing
   circuit simulator + noise channels; keep the repeated-round decoder as the
   sink.
2. Optional: fold the final-round measurement-error handling back in via an
   explicit final-boundary model once circuit-level syndromes exist.

## 8. Critical Context

- Preserve: AD-003 (partial-trace ordering), AD-004 (X-before-Z), Werner
  semantics, existing MWPM, process-worker semantics (§106) — none were
  changed this session.
- `repeated_round.py` reuses `RotatedSurfaceCode.build`, the graph dicts
  (`dist`/`path`/`dist_exit`/`path_exit`), `RotatedSurfaceCodeDecoder` (incl.
  `._match_component`), `min_weight_perfect_matching`, and `wilson_interval`
  — do not fork these.
- The `measurement_flips` / `observed_syndromes` shapes are the round-trace
  contract for visualization (§23).
- `quantumlab.db` is gitignored; never commit it or E2E evidence.

## 9. Agent Instructions

- Keep the standing loop: inspect → implement → test → validate science →
  integrate → document → benchmark → commit.
- Backend baseline 664; Playwright baseline 38. Both must remain green.
- Before circuit-level QEC, reread AD-016 and the repeated-round SCIENTIFIC
  MODELS section; extend, do not replace.