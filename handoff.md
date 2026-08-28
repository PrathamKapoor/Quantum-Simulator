# QuantumLab — Handoff to Next Agent

Generated: 2026-08-29, end of autonomous session 6.
Read together with `docs/DEVELOPMENT_STATUS.md` (checkpoint) and
`docs/AUTONOMOUS_SESSION_LOG.md` (per-phase log). This file documents what
actually happened.

---

## 1. Current Phase

- **Project:** QuantumLab — integrated quantum computing / information /
  networking research platform. Python+FastAPI backend, React+TS frontend,
  SQLite persistence.
- **Session 6 of autonomous development.** Objective (roadmap priority):
  MWPM decoder + planar rotated surface code — a complete surface-code/QEC
  research workflow (geometry → stabilizers → syndrome → matching graph →
  exact MWPM → correction → logical outcome → Monte Carlo → Wilson CIs →
  experiment framework → QecLab UI).
- **Status: COMPLETE and validated.** Backend suite green at **597 tests**
  (was 514); frontend build clean. All work committed on `main`.

## 2. Work Completed (session 6)

- **Geometry** (`backend/app/qec/rotated_surface_code.py`): rotated planar
  surface code on doubled integer coordinates; X checks terminate top/bottom,
  Z checks left/right; exactly (d^2-1)/2 checks per type; build-time algebra
  validation (commutation, coverage, duplicates, logical structure); logical
  X = column x = d, logical Z = row y = d (verified by string construction).
  Distances d = 3, 5, 7 (odd; others rejected, never rounded).
- **Distance verification**: exhaustive per-component enumeration
  (exact for CSS: d = min(d_X, d_Z)), numpy-vectorized GF(2) masks; verified
  d = 3, 5, 7 exactly (d = 7 enumerates ~100M supports, ~46 s — the slowest
  test).
- **MWPM** (`backend/app/qec/matching.py`): exact minimum-weight perfect
  matching over the defect + per-defect boundary-copy graph (always
  matchable, fully expressive); DP over subsets with memoization + loud
  state-budget guard; deterministic tie-breaking. Validated against an
  independent brute-force enumeration on 900 random instances.
- **Decoder**: CSS split (Z errors -> X-check syndrome -> Z chains on the
  X-check graph, and mirror); precomputed BFS chain weights and actual chain
  paths; syndrome fast paths validated against `syndrome_of`; residual
  classification via GF(2) coset functionals (O(1), no group enumeration);
  outcomes CORRECTED / LOGICAL_X / LOGICAL_Z / LOGICAL_Y / DECODER_ERROR.
- **Monte Carlo**: `simulate_rotated_surface_code` + bounded
  `sweep_rotated_surface_code`; depolarizing/x_only/z_only models; reuses
  `random_pauli_errors` and `wilson_interval` (no second implementation).
- **Experiments**: `surface_code_mwpm` runner module — bounded (d, p) sweeps
  with Wilson CIs in the standard run-result document; reproduction
  (EXACT_MATCH) and comparison through the existing framework.
- **API**: `POST /api/qec/rotated-surface-code/decode` (explicit Pauli error
  or sampled from (model, p, seed); returns syndrome, events, matching with
  chains, correction, residual, outcome, layout) and `POST
  /api/qec/rotated-surface-code/simulate` (Monte Carlo point).
- **Frontend** (`QecLab.tsx`): rotated-surface-code panel — lattice SVG
  (data qubits, X/Z checks, syndrome defects, errors, dashed MWPM chains,
  correction rings), per-match table, outcome badge, Monte Carlo summary;
  every value rendered from backend documents.

## 3. Files Changed

Backend: `app/qec/rotated_surface_code.py` (new), `app/qec/matching.py`
(new), `app/qec/__init__.py` (exports), `app/experiments/runner.py`
(`surface_code_mwpm`), `app/api/{schemas,main}.py` (two endpoints).
Tests: `tests/test_mwpm_matching.py`, `tests/test_rotated_surface_code_geometry.py`,
`tests/test_rotated_surface_code_decoder.py`,
`tests/test_rotated_surface_code_mc.py`,
`tests/test_api_rotated_surface_code.py` (all new).
Frontend: `src/pages/QecLab.tsx`.
Docs: SCIENTIFIC_MODELS / LIMITATIONS / ARCHITECTURE_DECISIONS (AD-013) /
DEVELOPMENT_STATUS / AUTONOMOUS_SESSION_LOG / handoff.

## 4. Testing and Verification

- Full backend suite: **597 passed** (exit 0; use `--collect-only` for the
  count — this shell drops pytest's summary line).
- Frontend: `npx tsc -b && npm run build` clean.
- Independent validation mechanisms (§76): algebraic geometry gating;
  brute-force MWPM comparison; explicit logical-operator construction;
  analytic Monte Carlo expectations (p=0, low-p, distance protection).
- Performance (§72): build 0.9/2.5/11.9 ms and decode 0.03/0.09/0.26 ms per
  trial at d = 3/5/7; MC throughput ~3000 trials/s at d = 7. No dense-state
  construction anywhere; everything runs in stabilizer/Pauli space.
- Browser inspection NOT performed (no browser tooling); UI verified via
  TypeScript build + endpoint contracts. Do not claim visual validation.

## 5. Decisions Made (new)

`docs/ARCHITECTURE_DECISIONS.md` → **AD-013**: reuse the existing QEC stack
(algebra, sampling, Wilson, toric code untouched); geometry is derived and
algebra-gated; exact MWPM without new dependencies via the boundary-copy
reduction + subset DP (honest complexity documentation instead of claiming
blossom scalability); coset-functional residual classification; experiments
and API follow existing conventions. Standing AD-001..AD-012 remain binding.

## 6. Known Limitations

- Code-capacity, perfect single-round syndrome: no measurement errors, no
  circuit-level noise, no repeated-round decoding (events carry a round field
  for future extension).
- Independent Pauli data-qubit noise only (depolarizing / X-only / Z-only).
- MWPM is near-optimal, not maximum-likelihood; degenerate equal-weight
  corrections are tie-broken deterministically (sorted indices, smallest exit
  first), which may select a logical-failing representative among equivalent
  corrections — detected by residual classification, never hidden.
- Matcher state budget: pathological syndromes beyond ~4M memo states fail
  loudly (DECODER_ERROR / RuntimeError in simulation) instead of degrading
  silently; unreachable at supported distances/rates.
- Threshold sweeps are bounded behavioural studies with confidence intervals;
  no threshold value is claimed anywhere.
- Shared Wilson pipeline quirk: all-failures upper bound is 1 - 1e-16 rather
  than exactly 1.0 (pre-existing implementation, left untouched).

## 7. Unfinished Work / Next Priorities

1. **Process-isolated workers** with checkpoint/resume (roadmap; also enables
   interruptible RUNNING cancellation).
2. **Playwright** browser smoke tests (close the visual-inspection gap).
3. Optional surface-code extensions: repeated-round (temporal) decoding,
   circuit-level noise via the existing circuit simulator, measurement-error
   graphs.

## 8. Critical Context

- The decoder graph reduction and its exactness argument are documented in
  `matching.py` and SCIENTIFIC_MODELS.md — read before touching the matcher;
  the brute-force tests are its safety net.
- `RotatedSurfaceCode.build(d)` fails loudly on any algebraic invariant
  violation; do not weaken `_validate` to make tests pass.
- Pauli-string convention: leftmost char = highest qubit index (project-wide;
  `error_from_string` handles the mapping for explicit API errors).
- Experiment module name is `surface_code_mwpm` (RUNNER_REGISTRY); seeds for
  sweep points derive from the base seed (`seed + 1000 + di*7919 + i*104729`).
- `quantumlab.db` is gitignored; never commit it.

## 9. Agent Instructions

- Keep the standing loop: inspect → implement → test → validate science →
  integrate → document → benchmark → continue.
- Before implementing, re-run the full suite to confirm 597 green; use
  `--collect-only` for the test count; trust exit code + FAILED/ERROR counts.
- The d = 7 distance-verification test takes ~45 s; it is intentional
  exhaustive validation, not a hang.
