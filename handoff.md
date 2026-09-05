# QuantumLab — Handoff to Next Agent

Generated: 2026-09-04, end of autonomous session 11.
Read together with `docs/DEVELOPMENT_STATUS.md` (checkpoint) and
`docs/AUTONOMOUS_SESSION_LOG.md` (per-phase log).

---

## 1. Current Phase

- **Project:** QuantumLab — integrated quantum computing / information /
  networking research platform. Python+FastAPI backend, React+TS frontend,
  SQLite persistence.
- **Session 11 of autonomous development.** Objective (milestone 12):
  fault-aware stabilizer CNOT scheduling + circuit-derived decoder
  graph. The fault catalogue enumerates every elementary fault mechanism
  in the explicit stabilizer-measurement circuit, the schedule optimizer
  selects the deterministic optimum, and the circuit-derived graph
  reports structural coverage honestly. Decoder semantics are preserved
  (the phenomenological MWPM remains the logical-decoding engine; the
  graph is structural metadata).
- **Status: COMPLETE and validated.** Backend **742/742** (was 704);
  TypeScript + vite build clean; fault-aware Playwright 3/3; the
  existing circuit-level/repeated-round/phenomenological suites remain
  green; working tree clean (in-progress commits pending); all
  scientific findings documented.

## 2. Work Completed (session 11)

- **`backend/app/qec/fault_catalogue.py`** (new): per-stabilizer
  enumeration of every elementary fault mechanism (ancilla reset,
  ancilla prep, every CNOT pre-gate, readout) with full propagation:
  data support, detection-event set (local + cross-checks), residual
  classification (STABILIZER / DATA_HOOK / LOGICAL_X / LOGICAL_Z /
  MEASUREMENT_FLIP), and minimum additional-fault count to complete
  a logical operator. Deterministic risk score; schedule optimizer
  picks the lowest composite.
- **`backend/app/qec/circuit_graph_decoder.py`** (new): circuit-
  derived detector graph builder. Per-mechanism classification into
  ZERO_EVENT / BOUNDARY / EDGE / MULTI_EVENT_APPROXIMATED; small-
  probability-union combination; `GraphCoverage` (exact pairwise vs
  multi-event-excluded) reported honestly. Graph adapts into the
  EXISTING exact MWPM via the standard defect-set + boundary-exit
  interface (no matcher changes, no duplicate algorithm).
- **API**: four new endpoints
  (`/api/qec/rotated-surface-code/schedule/analyze`,
  `/fault/analyze`, `/circuit-derived/graph`,
  `/circuit-derived/simulate`).
- **Experiment**: `surface_code_fault_aware` runner module — through
  the process-isolated worker; reproduction EXACT_MATCH.
- **Frontend**: `FaultAwarePanel.tsx` added to QecLab (schedule
  comparison, single-fault inspection, graph coverage, MC with graph).
- **Tests**: `tests/test_fault_catalogue.py` (18),
  `tests/test_circuit_graph_decoder.py` (11),
  `tests/test_fault_aware_api.py` (9),
  `e2e/tests/fault_aware.spec.ts` (3).
- **Docs**: SCIENTIFIC_MODELS (session-11 addition), LIMITATIONS
  (fault-aware + circuit-graph section), AD-018, DEVELOPMENT_STATUS
  (session 11), AUTONOMOUS_SESSION_LOG (session 11), handoff.

## 3. Scientific facts / honest findings

- CNOT propagation oracle matches the production `cnot_propagate`
  (independent code path) for every Pauli pair; every candidate
  schedule preserves the noiseless stabilizer measurement semantics.
- **KEY FINDING (documented, not hidden):** under the H-CNOTs-H
  stabilizer-measurement circuit, the schedule is provably
  degenerate — every permutation of a stabilizer's CNOT support
  produces the same `n_logical_risk_hooks`, `max_hook_weight`,
  `n_hooks`, and `sum_hook_weight` (the order of faults shifts
  the `gate_index` labels but the data-side support is invariant).
  The optimizer therefore selects the naive schedule as optimal;
  `stabilizers_with_changed_schedule = 0` for every distance.
  This is a real property of the implemented model. A different
  circuit template would expose a non-trivial selection; the
  optimizer is generic over the catalogue.
- Multi-event mechanisms (≥3 detection events from a single fault)
  account for ~13% (d=3) to ~23% (d=5) of the single-fault
  probability mass at the default noise; these are excluded from
  the exact pair-edge model and reported as
  `coverage.excluded_ratio`. Approach A (directive §21).
- **Decoder semantics are preserved** (AD-016, AD-017): the
  phenomenological MWPM remains the logical-decoding engine; the
  graph is structural metadata. The `surface_code_fault_aware`
  experiment reports the phenomenological p_L with Wilson interval
  and the graph coverage as a side metric.
- Production simulator's reset model is ancilla X only; the
  catalogue's Y/Z reset entries are model extensions with
  probability 0 (documented as `p_reset_y_extension` /
  `p_reset_z_extension`).

## 4. Files Changed

Backend: `app/qec/fault_catalogue.py` (new),
`app/qec/circuit_graph_decoder.py` (new),
`app/qec/__init__.py` (exports),
`app/api/{schemas,main}.py` (4 endpoints),
`app/experiments/runner.py` (surface_code_fault_aware).
Tests: `tests/test_fault_catalogue.py`,
`tests/test_circuit_graph_decoder.py`,
`tests/test_fault_aware_api.py`.
Frontend: `src/pages/FaultAwarePanel.tsx` (new),
`src/pages/QecLab.tsx` (import + render).
E2E: `e2e/tests/fault_aware.spec.ts`.
Docs: SCIENTIFIC_MODELS / LIMITATIONS / ARCHITECTURE_DECISIONS
(AD-018) / DEVELOPMENT_STATUS / AUTONOMOUS_SESSION_LOG / handoff.

## 5. Commands / Test Counts

- Backend: `./.venv/Scripts/python.exe -m pytest backend/tests
  --timeout=600` → **742 passed** (was 704; +38 new). Collected
  count: 742.
- Frontend: `cd frontend && npx tsc -b && npm run build`. Both
  clean.
- E2E: `cd e2e && npx playwright test` (40 + 3 fault-aware = 43).
  Windows: stop dev servers before a fresh-DB run; `localhost` for
  vite.

## 6. Known Limitations (fault-aware)

- Schedule is degenerate under the H-CNOTs-H circuit; the
  optimizer reports this honestly.
- Production simulator's reset model is ancilla X only; Y/Z
  reset mechanisms are model extensions (probability 0 in the
  graph).
- Graph is structural, not a decoder; the phenomenological
  MWPM remains the logical-decoding engine.
- Multi-event mechanisms are excluded from the exact pair-edge
  model (Approach A) and reported as `coverage.excluded_ratio`.
- Combination rule is small-probability union (Σ p_i); accurate
  in the low-noise regime, documented.
- Bounded scope: rounds 1..64, distances 3/5/7; matcher capacity
  guard retained; no threshold/hardware claims.

## 7. Unfinished Work / Next Priorities

1. **Non-degenerate stabilizer-measurement circuit** — the natural
   follow-on. A different circuit template (e.g. doubled CNOT
   schedule, Shor-style cat states, or a different basis preparation)
   would expose a non-trivial schedule selection and let the
   optimizer demonstrate distance suppression recovery.
2. **Circuit-level matching graph as a real decoder** — replace
   the phenomenological MWPM with a matching graph that handles
   multi-event mechanisms (e.g. via hypergraph or a documented
   approximation).
3. Optional: coherent errors, biased noise, or reset+preparation
   refinement.

## 8. Critical Context

- Preserve: AD-003, AD-004, AD-008, AD-013, AD-014, AD-015, AD-016,
  AD-017, AD-018. Process-worker semantics (§106) — none changed
  this session.
- `fault_catalogue.py` and `circuit_graph_decoder.py` reuse
  `cnot_propagate`, `min_weight_perfect_matching`,
  `wilson_interval`, and `RotatedSurfaceCode`; do not fork these.
- The decoder semantics preservation is what makes the graph
  STRUCTURAL rather than a replacement decoder. If you change one,
  update AD-018 and re-run BOTH test files.
- `quantumlab.db` is gitignored; never commit it or E2E evidence.

## 9. Agent Instructions

- Keep the standing loop: inspect → implement → test → validate
  science → integrate → document → benchmark → commit.
- Backend baseline 742; Playwright baseline 43. Both must remain
  green.
- Before the next milestone, reread AD-018 and the SCIENTIFIC_MODELS
  "Session-11 additions" section; extend, do not replace.
- If you change the circuit-level noise model, the fault catalogue
  and the graph builder will both need to be updated to match the
  new simulator's actual fault locations (directive §7).
