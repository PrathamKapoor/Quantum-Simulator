# QuantumLab — Development Status

> **Purpose:** Persistent checkpoint for autonomous development. Any session resuming
> work MUST read this file first, then ROADMAP.md, ARCHITECTURE.md,
> SCIENTIFIC_MODELS.md, LIMITATIONS.md (directive §320).
>
> Last updated: 2026-08-30 (session 7 final checkpoint)

## Current state

**Integrated research platform with a first-class distributed experiment type.**
Session 1: validated foundations. Session 2: quantum information suite, channel
algebra, hardware/transpiler, error mitigation, purification + network
integration, repeater studies, loss-aware BB84, distributed double-teleportation
remote CNOT, reproducibility/statistics/export, frontend labs.
Session 3: distributed subsystem — single-ebit remote CNOT (1 ebit + 2 cbits)
executed as genuine protocol circuits, multi-node circuit partitioner,
real network-engine ebit accounting, distributed result schema, API endpoints,
Circuit Studio distributed workflow.
Session 4: **distributed experiment-runner integration** — `distributed_circuit`
is a first-class experiment module using the existing runner/lifecycle
(CREATED→QUEUED→RUNNING→COMPLETED, FAILED/CANCELLED), standard run-result
document wrapping the distributed-result v1 payload, seed handling /
reproduction / comparison / sweeps through the existing framework, and an
Experiments-UI workflow (template, distributed result view, reproduction).
Session 5: **noisy ebits / Werner-model entanglement injection (AD-012)** —
the NetworkBridge grant fidelity now governs the actual quantum state of each
consumed ebit: canonical Werner state (`DensityMatrix.werner`, reusing the
network subsystem's q = (4F-1)/3 family), sampled Pauli trajectory per ebit at
protocol expansion, per-operation provenance (`ebit_fidelity_applied`,
`ebit_noise`), modes ideal / network_fidelity / fixed (default ideal =
byte-identical legacy behavior), end-to-end through the experiment runner, API,
and Experiments UI (noisy template + fidelity/noise columns).
Session 6: **MWPM decoder + planar rotated surface code (AD-013)** — rotated
planar geometry (doubled-coordinate construction, algebra-validated), exact
MWPM decoder with boundary-copy reduction validated against brute force,
GF(2) coset-functional residual classification, exhaustive distance
verification (d = 3, 5, 7), Monte Carlo with the existing Wilson intervals,
`surface_code_mwpm` experiment module, two `/api/qec/rotated-surface-code/*`
endpoints, and a QecLab lattice/decode/Monte-Carlo workflow.
Session 7: **process-isolated experiment workers (AD-014)** — every
experiment run executes in a fresh Windows-spawn child process supervised by
the existing JobQueue; the parent owns all persistence and lifecycle state;
workers use the canonical registry and never touch the database; worker
exceptions, hard exits, serialization and persistence failures all become
FAILED (never COMPLETED); running-job cancellation is now process
termination; startup recovery converts orphaned RUNNING runs to FAILED; a
`process_probe` diagnostic experiment backs the adversarial test battery.

Run it: `dev.bat backend` + `dev.bat frontend` → http://localhost:5173

## Tests & validation

- Fast suite: **630 passed** (session 7 final; was 597 at session 6).
  Session 5 added: `test_werner_state.py` (40: trace/Hermiticity/PSD,
  target-fidelity = F at seven F values, F = 1/0/0.25/0.5 limit cases,
  q-parameterization consistency, ordering convention, negativity/concurrence
  entanglement regime) and `test_distributed_noisy_ebit.py` (30: sampling
  statistics, expansion noise ops, F=1 regression, legacy default, basis
  mixture, derived analytic channel references for BOTH protocols, GHZ-chain
  degradation, reproducibility, config errors, network-fidelity mode,
  multi-hop swap degradation, grant-model boundary, purification consistency);
  `test_api_distributed.py` extended (network-fidelity mode, fixed F=1 vs
  legacy, statistical degradation, schema rejections, noisy experiment
  run + reproduce).
- Distributed equivalence: Uhlmann fidelity = 1.0 vs centralized (reported in
  every experiment summary). Sweep machinery fixed: `expand_sweep` now seeds
  each combo from the base configuration (previously it silently dropped it).
- Resource accounting corrected: reported ebits/cbits now reflect the ACTUAL
  protocol (double teleportation reports 2 ebits + 4 cbits, not the partition
  estimate of 1); explicit centralized fallback emits a single local CNOT and
  records a warning instead of double-applying the protocol.
- Frontend build clean (`tsc -b` + `npm run build`, 31 modules).
- Browser inspection NOT performed (no browser tooling available).

## Session 4 — distributed experiment-runner integration

Lifecycle (existing infra, AD-011): create → runs (one per sweep combo, seed
`spec.seed + 7919*run_index`) → queue on the existing threaded JobQueue →
execute via `RUNNER_REGISTRY["distributed_circuit"]` → the standard
`quantumlab.run-result` v1 document stores resource metrics, an equivalence
summary, and the full `quantumlab.distributed-result` v1 payload under
`artifacts.distributed_result`. Distributed failures raise → run recorded
FAILED with error_code/error_message (never fabricated COMPLETED). Reproduction
creates a NEW run and compares documents (EXACT_MATCH); originals are
immutable. Comparison via existing `compare_runs` surfaces differing params and
per-run resource metrics. Sweeps use the existing float-based engine; the
engine-supported `num_nodes` (auto-assign) dimension is exposed, and the
base-config seeding bug was fixed. Cancellation follows the existing cooperative
model (queued jobs cancellable; in-process engine execution is atomic).

## Measured performance (session 3, this machine — simulation wall-clock)

Wall-clock runtime of the SIMULATION only. It is not modelled network latency
(reported separately per grant) and not hardware performance.

| Workload | Partition | Distributed exec | Centralized ref |
|----------|-----------|------------------|-----------------|
| 4q chain, 3 remote CNOTs (16-qubit expanded) | 0.05 ms | ~18 ms | ~1.1 ms |
| 6q chain, 5 remote CNOTs (16-qubit expanded) | 0.05 ms | ~380 ms | ~1.4 ms |
| 8q chain, 7 remote CNOTs (22-qubit expanded) | 0.06 ms | ~34 s | ~1.8 ms |

Overhead grows steeply with the expanded register because every protocol step
is executed with mid-circuit-measurement trajectory semantics (no fast path);
each single-ebit gate adds 2 carriers. This is simulator cost of genuine
protocol execution — the honest price of not faking distribution.

## Recently completed (session 2)

| Phase | Deliverable | Status |
|-------|-------------|--------|
| A | app.quantum.info_theory (18 measures) + /api/quantum-info/state-report | IMPLEMENTED+VALIDATED |
| B | Choi/composition/tensor/fidelity + GAD + readout channel | IMPLEMENTED+VALIDATED |
| C | HardwareProfile presets, SWAP-insertion transpiler (permutation-verified), circuit analysis | IMPLEMENTED+VALIDATED |
| D | Readout mitigation, folding ZNE (density-mode expectations), parity postselection + endpoints | IMPLEMENTED+VALIDATED |
| E | BBPSSW/DEJMPS purification (exact recurrences, exact resource accounting) + engine integration | IMPLEMENTED+VALIDATED |
| F | Repeater L0/L1/L2 studies; loss-aware network BB84 (+dark counts, secret fraction estimate) + runners | IMPLEMENTED+VALIDATED |
| G | Distributed remote CNOT (double teleportation), centralized-equivalence validated | IMPLEMENTED+VALIDATED |
| H | reproduce_run with comparison classification, provenance CSV export, statistics subsystem | IMPLEMENTED+VALIDATED |
| I/J | Mitigation/info/hardware/reproduce/export API endpoints; full documentation set | IMPLEMENTED |

Frontend labs for the new endpoints are PLANNED (backend contracts stable).
See docs/AUTONOMOUS_FINAL_REPORT.md and docs/AUTONOMOUS_SESSION_LOG.md.

## Correctness bugs fixed this session (all regression-covered)

1. partial_trace multi-qubit output ordering (latent; exposed by off-diagonal
   validation during remote-CNOT work)
2. teleportation correction order X-before-Z (phase-invisible in isolation;
   observable inside entangling circuits)
3. ZNE driver used trajectories instead of density-mode expectations
4. Choi TP-check block summation; GAD weighting convention
5. transpiler verifier permutation direction; benchmark circuit clbits
6. three undefined-name lint issues

## Key architectural decisions

AD-001…AD-008 in docs/ARCHITECTURE_DECISIONS.md (ordering conventions,
honest-refusal policies for purification/asymmetric inputs, guard-error
surfacing, no-dependency policy).

## Measured performance (unchanged from session 1 reference)

| Workload | Result |
|----------|--------|
| Shot sampling fast path | ~6.8M shots/s |
| QFT-18q evolution | ~3.1 s |
| Density GHZ-8 | ~22 ms |
| Network events | ~80k/s |

## Next priorities

1. **Noisy ebit / Werner-entanglement injection**: map each network grant's
   fidelity into the protocol circuit (Werner-form ebit preparation) instead of
   reporting fidelity separately — the next intended scientific milestone.
2. MWPM decoder + planar surface-code layout.
3. Process-isolated workers with checkpoint/resume (would also make RUNNING
   cancellation interruptible rather than cooperative-at-queue).
4. Playwright UI smoke tests (would also close the visual-inspection gap).
5. Distribution-aware experiments in the Experiments UI: circuit editor inside
   the distributed template (currently a fixed GHZ template + generic config).

## Session 5 — noisy ebits / Werner-model entanglement injection

Classification: VERIFIED = exercised by the passing automated suite; STATICALLY
REVIEWED = code-reviewed, build-verified, not behavior-tested in a browser.

- VERIFIED — Werner state model and invariants (`DensityMatrix.werner`).
- VERIFIED — grant fidelity reaches the quantum state: single trajectory
  sampling with recorded Pauli components; statistical aggregate matches the
  derived analytic Pauli-channel reference for both protocols (F=1 reduces to
  the ideal path bit-for-bit; noise applied exactly once).
- VERIFIED — configuration surfaces: executor (`DistributedConfig`), API
  schemas (`/api/distributed/simulate`, `/api/distributed/remote-cnot`),
  experiment runner config (`ebit_noise`, `ebit_noise_fidelity`), sweepable
  fixed-fidelity dimension.
- VERIFIED — provenance/reproducibility: same config+seed reproduces the same
  sampled components and results; noisy experiment run + reproduce via the
  live API; original records immutable.
- VERIFIED — network coupling: direct-link base fidelity, multi-hop swap
  degradation, and bad-vs-missing resource semantics flow into the distributed
  result; equivalence fidelity < 1 documented as noise degradation (reference
  remains the ideal centralized run).
- STATICALLY REVIEWED — frontend: ebit-noise mode selector + fixed-fidelity
  input in Circuit Studio's DistributedPanel, noisy distributed template,
  per-operation "Ebit F" / "Werner sample" columns and mean-ebit-fidelity card
  in the Experiments result view. All values rendered come from the backend
  document. Visual browser validation NOT performed (no browser tooling).
- VERIFIED — no performance regression (benchmark: ideal vs noisy within
  run-to-run variance for 2-4 qubit GHZ chains) and no memory regression
  (no global density matrices; equivalence path unchanged).

## Session 6 — MWPM decoder + planar rotated surface code

Classification: VERIFIED = exercised by the passing automated suite;
STATICALLY REVIEWED = code-reviewed, build-verified, not browser-tested.

- VERIFIED — geometry: counts ((d^2-1)/2 checks per type), commutation
  (every X/Z pair), no duplicate supports, full data-qubit coverage, boundary
  structure (weight-2 X checks top/bottom, weight-2 Z checks left/right),
  for d = 3, 5, 7.
- VERIFIED — logical operators: commute with all checks, anticommute with
  each other, weight exactly d, and are genuinely nontrivial (functional
  fires).
- VERIFIED — code distance independently computed (exhaustive per-component
  enumeration) equals d for d = 3, 5, 7.
- VERIFIED — syndromes: per-qubit fast path equals the algebraic
  `syndrome_of` for every single-qubit Pauli on every data qubit at d = 3, 5.
- VERIFIED — MWPM matcher: exact; matches an independent brute-force
  enumeration on 900 random instances (2, 4, 6 defects, boundary exits,
  ties); deterministic tie-breaking.
- VERIFIED — decoder: all weight-1 errors corrected (d = 3, 5, 7), ALL
  weight-2 errors corrected at d = 5, full weight-2 classification at d = 3,
  degeneracy/syndrome collisions, zero-syndrome classification (identity /
  stabilizer / logical), logical strings flagged despite trivial syndrome,
  corner/boundary errors, residual invariant property test (2000 random
  errors per distance).
- VERIFIED — Monte Carlo: p = 0 gives zero failures; p_L rises with p;
  d = 5 beats d = 3 outside the d = 3 Wilson interval at p = 0.05; exact
  seed reproducibility; Wilson reuse verified by recomputation; x_only /
  z_only models.
- VERIFIED — API + experiments: decode/simulate endpoints with validation
  and honest notes; `surface_code_mwpm` experiment end-to-end (create ->
  execute -> COMPLETED -> result with Wilson CIs -> reproduce EXACT_MATCH ->
  original immutable) and d = 3 vs d = 5 comparison through the existing
  compare endpoint.
- STATICALLY REVIEWED — frontend: QecLab rotated-surface-code panel
  (lattice SVG with checks/defects/errors/matching/correction from backend
  data, per-match table, Monte Carlo summary). Browser visual validation NOT
  performed (no browser tooling).
- VERIFIED — performance: build 0.9/2.5/11.9 ms and decode 0.03/0.09/0.26 ms
  per trial at d = 3/5/7; MC throughput > 2500 trials/s at d = 7.

## Session 7 — process-isolated experiment workers

Classification: VERIFIED = exercised by the passing automated suite;
STATICALLY REVIEWED = code-reviewed, build-verified.

- VERIFIED — process boundary: experiment results are produced by child
  processes with distinct PIDs (spawn, Windows), via the canonical registry.
- VERIFIED — failure semantics: child exception -> FAILED with type/message/
  traceback; hard exit (exitcode 70) -> FAILED WorkerAborted; unserializable
  result -> explicit SerializationError; timeout -> FAILED WorkerTimeout;
  persistence failure -> FAILED PersistenceError. Never COMPLETED, never
  fabricated.
- VERIFIED — crash containment (the central acceptance demonstration):
  worker A hard-crashes; run A = FAILED; API and database remain healthy;
  worker B completes and persists afterwards — at both service and live-API
  levels.
- VERIFIED — cancellation: queued cancel never starts a worker; running
  cancel terminates the process; the cancel/completion race yields exactly
  one consistent terminal state shared by job and run row.
- VERIFIED — concurrency and isolation: different modules/seeds/configs run
  concurrently with results attributed to the correct runs; progress events
  carry run_id and never cross-contaminate; bounded capacity (jobs > workers
  remain queued).
- VERIFIED — reproducibility: same seed in different worker processes gives
  identical results; reproduction through the process boundary reports
  EXACT_MATCH with the original immutable; surface-code p_L is bit-identical
  in-process vs via a worker.
- VERIFIED — shutdown/restart: shutdown terminates active workers (no
  orphans; runs FAILED); startup recovery marks orphaned RUNNING runs FAILED
  (INTERRUPTED_BY_RESTART) and returns volatile QUEUED to CREATED.
- VERIFIED — real experiments through the boundary: surface_code_mwpm,
  distributed_circuit, bb84_study, vqe — all complete with correct results
  (the vqe run uncovered a PRE-EXISTING broken import
  `app.experiments.variational`; fixed at the root and noted below).
- VERIFIED — performance: ~0.4 s warm spawn overhead per job; heavy
  experiments amortize it; no dense-state or memory-regression changes.
- STATICALLY REVIEWED — frontend requires no changes (API contracts
  unchanged); TypeScript + production build clean.
- Bug found and fixed: `run_vqe_experiment` imported run_vqe from a
  nonexistent module (app.experiments.variational); the vqe experiment could
  never execute. Root-cause fixed (app.optimization.variational) with a
  regression test running vqe through the process boundary.
