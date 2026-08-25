# Autonomous Session Log — Session 2

Concise per-phase record (directive §175). All commits keep the full suite
green before proceeding.

## Phase A — Quantum information expansion
- Added `app/quantum/info_theory.py`: 18 measures with formulas, domains,
  stability policies; `state_report` bundle.
- 28 property tests against analytic values (Bell/GHZ/W/product/mixed).
- API: `POST /api/quantum-info/state-report` with model labels + notes.
- **Test bug found:** my own wrong expectations (W-marginal ordering,
  conditional entropy of Bell = −1 not 0, Werner concurrence formula) —
  implementation verified correct against textbook math; tests corrected.
- Tests: 242 → 245 green.

## Phase B — Channel algebra
- Added `channel_algebra.py`: Choi matrix + validation (CP/TP/Hermitian),
  composition & tensor identities (verified numerically), process/average
  gate fidelity, generalized amplitude damping, readout confusion channel.
- **Bug found:** my first Choi partial-trace-over-output summed only diagonal
  blocks; fixed. GAD weighting convention fixed (N=0 must equal cold bath).
- Tests: +16.

## Phase C — Hardware profiles + transpiler
- HardwareProfile + line/ring/grid/star/all-to-all topologies; four labeled
  model presets.
- SWAP-insertion transpiler tracking logical→physical permutation; dense
  unitary verification under final permutation.
- Circuit analysis subsystem (depth/counts/T-accounting/pairs).
- **Bugs found:** verifier compared permutation in the wrong direction
  (row-gather vs column-scatter); benchmark circuit missing clbits.
- API: `/api/hardware/profiles`, `/api/hardware/transpile`,
  `/api/circuits/analyze`.
- Tests: 311 green at commit.

## Phase D — Error mitigation
- Readout confusion mitigation (lstsq inversion, conditioning report, flagged
  clipping), gate folding + linear/quadratic ZNE with raw-sample echo and
  instability warnings, parity postselection.
- **Bug found:** ZNE driver evaluated single trajectories (±1 noise);
  switched to exact density-mode expectations. End-to-end: noisy ⟨ZZ⟩
  0.9216 → mitigated 0.9696 (ideal 1.0).
- API: `/api/mitigation/readout`, `/api/mitigation/zne`.

## Phase E — Entanglement purification
- BBPSSW/DEJMPS exact recurrences; Monte Carlo schedules with exact pair
  accounting (failures consume both pairs and end chains); protocol comparison.
- Network engine integration: optional same-segment duplicate-pair
  purification with honest skip/failure semantics.
- Validated: DEJMPS at F=½ → 0.625 (textbook value).

## Phase F — Repeater framework + network BB84
- L0/L1/L2 repeater strategy studies across distances with Wilson CIs;
  trend test vs direct transmission.
- Loss-aware BB84 (fiber η model, dark counts, detection statistics,
  secret-fraction estimate labeled as asymptotic estimate).
- New experiment runners registered: purification_study, repeater_study,
  network_bb84.

## Phase G — Distributed quantum computing
- Remote CNOT via double teleportation (2 ebits, 4 cbits), validated against
  centralized execution on basis states AND superpositions.
- **Two significant bugs found & fixed** (see ARCHITECTURE_DECISIONS.md
  AD-003/AD-004): partial-trace output ordering; teleportation correction
  order X-before-Z. Both latent for a long time — caught precisely because
  validation used off-diagonal states and entanglement-sensitive circuits.

## Phase H — Experiments/reproducibility/statistics
- `reproduce_run`: re-executes stored config+seed as a NEW run, compares
  documents (EXACT/TOLERANCE/MISMATCH), original untouched.
- Provenance-rich CSV export (`experiment_id, run_id, seed, ...`).
- Statistics subsystem: summarize_samples (N explicit), normal-approx CI
  (documented assumption), seeded bootstrap, Wilson proportions.
- API: reproduce endpoint, export.csv endpoint.

## Phase I (this session) — Mitigation/info endpoints
- Mitigation readout+ZNE endpoints; quantum-info state-report endpoint.

## Final validation status

- Full suite: **367 passed**
- Undefined-name lint: 0
- Frontend build: clean (tsc -b + vite build)
- Services verified: API health ok, frontend serving
