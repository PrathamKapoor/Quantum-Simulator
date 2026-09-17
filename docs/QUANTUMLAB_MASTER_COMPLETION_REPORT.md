# QuantumLab Master Completion Report

Date: 2026-09-17 · Session start: `0c19faf` (dirty tree) · Head: `d76a26c` · New commit: `567764b`

## 1. Executive summary

Session validated the platform end to end, corrected a real scientific defect in the
Book Lab Grover scan, completed an actual-PDF source audit, integrated it into the
coverage documentation, and re-ran the full distance-7 correlation-decoder research
study. All suites pass on the current tree. The book-coverage documentation now
carries honest per-item statuses; it does **not** claim whole-book validation.
Overall assessment: **PARTIAL** — book expansion and QEC research advanced with
verified evidence; several book gaps (operator worksheets, MBQC example 15.2,
classical ch.1 tasks, ch.11 RSA/eavesdropper) remain open and are documented.

## 2. Repository starting state

- Branch `main`, start/end-of-audit commit `0c19faf1aa3b8db0e06569b44ae9cee11c6afc44`.
- Tree was already dirty with pre-session expansion work (22 modified files,
  untracked tests/docs). Those changes were preserved, inspected, and later
  verified by the full suite; they were not authored wholesale by this session.

## 3. Repository final state

- Working tree: 1 new commit `567764b` (isolated Grover fix); remaining verified
  session work committed as below; evidence logs (`.pytest_full*.log`,
  `playwright_*.log`) and throwaway pytest basetemps remain untracked.
- Full backend suite: **1083 passed** (0 failures) in 754.74 s (run 1, observed)
  and 590.6 s (run 2, captured log corroborates: 1083 dots, no F/E markers).

## 4. Existing dirty work discovered

Pre-session uncommitted work included: six book-expansion runners (Gram-Schmidt,
purification, entanglement swapping, QEC codes, tomography, Rabi), Helstrom and
channel-algebra runners, semantics/correctness/MBQC/algorithm-contract tests,
Book Lab UI metadata, e2e isolation config, and the d7 study script. All were
preserved, inspected, and included in verification.

## 5. Book source used

David McMahon, *Quantum Computing Explained*, Wiley-IEEE (2008),
ISBN 978-0-470-09699-4. SHA-256 of the local PDF:
`89b670064e19d5e460ceab7bdfe0ddc3348b8e7a597d1533d7cb3266e7e5b636`.
PDF page = printed page + 19. Read-only inventory extraction was performed;
no book text is reproduced in the product.

## 6. Source extraction methodology

Extracted PDF body once to a read-only cached inventory (`backend/.pytest_cache/book_inventory.json`,
not authoritative for coverage). Three audit agents (SourceCh1to5, SourceCh6to10,
SourceCh11to15) read **all 15 extracted chapter bodies** including every numbered
example, exercise, and You-Try-It prompt, reconciled against existing inventory
rows, primitives, runners, registration, tests, and Book Lab UI. Visual/formula
transcription was not achievable from text extraction alone; unresolved glyph
items are itemized in `book_coverage.json` → `source_visual_limitations`.

## 7. Exhaustive source inventory methodology

`docs/book_coverage.json` (schema `quantumlab.book-coverage.v2`) preserves all
**413** top-level inventory identities (134 sections, 119 examples, 126
exercises, 34 You-Try-It) and adds: per-row source observation
(`OBSERVED_TEXT`), classification, current status, limitations, a 38-entry
evidence catalog with 0 dangling references, **563** identifiable task/output
groups and **92** body/figure groups (explicitly *not* an exhaustive
denominator), source-digest provenance, and per-entry runtime-evidence
freshness labels. No second experiment registry was created.

## 8. Book coverage statistics (honest denominators)

Top-level rows: NOT_STARTED 33 · PRIMITIVE_ONLY 318 · UNVERIFIED 62 · others 0.
No whole-book completeness percentage is claimed (`whole_book_validated: false`,
`subparts_exhaustively_reconciled: false`). The earlier "97.78% (44/45)"
scorecard and "64 worked examples" claims are **retracted** in the matrix.

## 9. Every new experiment

This session's only new product change is the corrected `book_grover_scan`
validation. Expansion experiments (Helstrom, channel algebra, tomography, Rabi,
QEC codes, MBQC, Simon, QFT, QPE, multigrover) predate this session and were
validated, not newly invented. No new runner/registry/UI framework was added.

## 10. Existing experiments promoted

`book_helstrom`, `book_channel_algebra`, `book_state_tomography`,
`book_rabi_oscillations` were verified against independent oracles this session:
Helstrom unequal-prior closed form; channel order trace distance 0.12 (analytic
p·γ) and identity-reference process fidelity; tomography ideal-inversion exact +
physical projection; Rabi sampled-grid analytic law (detuning=1, steps=101).

## 11. Scientific validation

- Born-rule oracle tests (textbook Paulis, +Y projector sign), Pauli anticommutation
  truth table, Robertson bound computed (nonzero for (Y,Z) on |+⟩) —
  `tests/test_book_semantics.py` (3 tests).
- Teleportation mechanism: independent Bell-stage oracle —
  `tests/test_teleportation_mechanism.py`.
- Grover exact rotation oracle incl. truncated scan — `tests/test_book_grover_scan.py`.
- Channel algebra/Choi/composition, Helstrom, tomography, Rabi suites: 163 passed.
- Correlation decoder (incl. two-fault attribution): 31 passed.
- Process isolation lifecycle/failure semantics: 34 passed.
- Full backend: 1083 passed (§3).

## 12. Bugs found

1. `book_grover_scan` validated a *sampled* peak near the optimum (hard-coded
   pass, duplicate `passed` keys, variable shadowing) — fixed to compare exact
   simulated marked-state probability with `sin²((2k+1)θ)`, θ = asin(1/√N);
   regression covers a scan ending before the optimum.
2. `book_qubit_state` +Y projector sign (minus branch) — fixed; Born-rule oracle test.
3. `book_operator_report` anticommutation predicate inverted; `passed` constant — fixed.
4. Teleportation corrections applied in wrong tensor placement — fixed and tested
   at Bell-stage level (pre-existing fix, regression-verified this session).

## 13. Root causes

(1) Validation keyed on noisy sampled peaks; (2) amplitude-literal vs projector
form conflation; (3) commutator/anticommutator predicate inversion; (4) tensor
operand placement. Each fixed at source; no symptom suppression.

## 14. Fixes

See §12. All covered by the focused suites in §11; Grover fix committed as
`567764b` with regression `tests/test_book_grover_scan.py`.

## 15. Backend test results

- Full suite (current tree): **1083 passed** (two independent runs; §3).
- Targeted: semantics 3 · algorithm contracts (Grover subset) 7 ·
  preservation (expansion/primitives/channel/info-theory) 163 ·
  process+API workers 34 · correlation decoder 31 ·
  teleportation mechanism 1 — all passed.

## 16. Frontend test results

- TypeScript + production build: passed (`npm run build`: tsc -b && vite build; 38 modules).
- Lint (oxlint): 0 errors, **10 warnings** (pre-existing React hook/purity advisories).
- No separate npm test script exists (documented limitation, unchanged).

## 17. Playwright results

Full suite: **61 passed (2.1 m)** with isolated E2E database + strict ports;
includes 9 visual and 10 Book Lab tests. Durable log: `playwright_final.log`
(untracked evidence).

## 18. Visual results

Visual suite executed within the 61-test Playwright run (reduced-width viewport
checks); no clipped content, stuck loaders, or missing labels observed in
failure-free run. Representative inspection of Book Lab pages occurred during
reload-regression work earlier in the session.

## 19. Build results

- Vite production build: passed (dist assets listed in §16 command output).
- Backend compile check: clean (module imports exercised by full suite).

## 20. Secret scan

Regex sweep over tracked + untracked files for keys/tokens/passwords/private
keys: only BV `secret` bitstring parameters, BB84 "secret-fraction" metric
prose, and doc text matched. `.env` is git-ignored; `.env.example` contains
placeholders only. No credentials in tracked files; no databases tracked.

## 21. D7 signature results (research, not book coverage)

Fresh full run (`--phase all --trials 300`, seed 20260917, 245.3 s,
`sources_unchanged=true`, output `docs/data/d7_study_verified.json`):

| Extraction | d | Signatures mid/final | Faults mid/final | Cold untraced s | Cold traced s | Peak traced MiB |
|---|---:|---|---|---:|---:|---:|
| baseline | 3 | 120/120 | 200/144 | 0.080 | 0.381 | 0.239 |
| baseline | 5 | 400/400 | 648/480 | 0.391 | 3.132 | 1.150 |
| baseline | 7 | 840/840 | 1344/1008 | 1.406 | 9.979 | 2.690 |
| fitted_pair | 3 | 116/116 | 228/144 | 0.109 | 0.877 | 0.251 |
| fitted_pair | 5 | 384/384 | 760/480 | 0.838 | 7.495 | 1.213 |
| fitted_pair | 7 | 804/804 | 1596/1008 | 2.725 | 46.487 | 2.627 |

## 22. D7 single-fault results

Exhaustive enumerated placements (12,816 injections historically; this session's
fresh run reproduces the pattern). Representative fresh counts: d7 baseline
round-1: 1344 cases, control 28 failures, correlation 0; d7 baseline final-round
gate faults: 1008 cases, control 268, correlation 116; fitted: 107. Full tables:
`docs/D7_SCALING_STUDY.md` + `d7_study_verified.json`. Diagnostic reset Y/Z
injections are included unweighted (documented).

## 23. Monte Carlo results (paired, identical circuits, 300 trials/cell × 18 cells)

Wilson 95% intervals; failures/300. Correlation-aware improves or equals control
in 17/18 cells; the d7 combined-mid cell is statistically indistinguishable:

- baseline d7 combined_mid: control 108 (CI 0.308–0.416) vs correlation 105 (0.298–0.406)
- fitted d7 combined_mid: control 105 (0.298–0.406) vs correlation 106 (0.301–0.409)
- fitted d3 gate_low: control 7 vs correlation 0 (CI 0–0.0126) — largest relative gain
- Correlation overhead 2.1–12.2× (single) / 2.7–17.6× (two-fault) decode time.

## 24. Statistical methodology

Paired trials on identical sampled circuits (same cell seed per extraction),
Wilson 95% binomial intervals, per-decoder timing split via observer wrapping of
the existing MC function (no copied sampling loop), fixed seed rule
`cell_seed + 7919·trial`. 300 trials/cell is a **distance-scaling sample**,
not a threshold study.

## 25. Performance measurements

Signature generation (§21) and decoder overhead (§23) are the session's
performance measurements. No new optimization was introduced; none was needed.

## 26. Remaining limitations

- Book: general operator worksheets (ch.3), MBQC Example 15.2 exact pattern,
  classical ch.1 tasks (code lengths/mode/mean/variance), RSA worked example +
  coherent CNOT attack (ch.11), ch.12 system-environment Kraus derivations,
  teleportation-without-communication / GHZ superdense (ch.10) — NOT_STARTED.
- Source visual/OCR limitations itemized in `book_coverage.json`
  (`source_visual_limitations`); suspected source errata labeled *suspected*.
- No finite-key QKD, no threshold/fault-tolerance claim, no production security claim.

## 27. Deferred work

Landau-Zener (needs finite-time reference), amplitude estimation/counting,
process/multi-qubit tomography, Lindblad/Ramsey, QKD finite-key rigor —
documented research candidates in `EXPANSION_RESEARCH.md`.

## 28. Exact commits created

- `567764b` — fix(book): validate Grover scan against exact rotation probabilities
  (2 files: runner + regression test).
- Session-closing docs commit (this report, handoff, coverage docs, D7 study) —
  see final git log.

## 29. Final release assessment

**PARTIAL.** Platform is release-ready for what is documented: all 1083 backend
tests, 61 Playwright tests, build, and lint pass; Grover scan corrected with
regression; coverage documentation is honest (no whole-book claim); D7 research
re-run with verified provenance. Book coverage remains partial by design of the
honest denominator; deferred/missing items are itemized rather than hidden.
