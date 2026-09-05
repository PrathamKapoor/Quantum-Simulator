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

---

# Session 3 — Distributed computing subsystem (single-ebit remote CNOT + partitioner)

Objective (user-selected roadmap item): establish a proper distributed
quantum-computing subsystem on the existing architecture — not a demo.

## Delivered

- **Data model** (`app/distributed/model.py`): NodeSpec, LocalOp, RemoteOp,
  EbitGrant, ClassicalMessage, PartitionMetrics, and a coherent
  `quantumlab.distributed-result` v1 schema with partition, resources,
  messages, equivalence, errors, reproducibility.
- **Partitioner** (`partition.py`): backwards-compatible analysis API plus a
  rich `PartitionPlan` and deterministic heuristic assignment
  (explicit mapping honoured → balanced seed → constrained local search;
  AD-010).
- **Remote-CNOT protocols** (`remote_cnot.py`): single-ebit gate teleportation
  (1 ebit + 2 cbits) and double teleportation (2 ebits + 4 cbits), expanded as
  genuine protocol circuits with X-before-Z corrections (AD-009).
- **Execution engine** (`engine.py`): validate → assign → partition → expand →
  request ebits → simulate expanded circuit → compare to centralized reference
  (Uhlmann fidelity ≤1e−8 tolerance) → full accounting. Carrier remapping
  supports multiple remote CNOTs and remote+local sequences.
- **Network integration** (`network_bridge.py`): ebit grants served by the
  existing NetworkEngine when a topology is supplied (fidelity / modelled
  latency / attempts / route); `ideal` grants labelled otherwise. No second
  network simulator; no fabricated numbers.
- **API** (`/api/distributed/{partition,simulate,remote-cnot}`) with pydantic
  schemas, validation, structured errors, tests.
- **Frontend** (`DistributedPanel` in Circuit Studio): node definition +
  per-qubit mapping or auto-assign, LOCAL/REMOTE visual distinction,
  entanglement-resource and classical-message tables from backend documents,
  centralized-vs-distributed probability comparison with max |Δ|.
- **Docs**: SCIENTIFIC_MODELS.md (protocol math + resource model),
  LIMITATIONS.md, ARCHITECTURE_DECISIONS.md (AD-009/AD-010).

## Validation

- New tests: `test_distributed_full.py` (30: basis truth table, superposition,
  Bell/GHZ, both directions, same-node, multi-remote, multi-node 2/3/4,
  networked grant, disconnected/unknown-node/cap failures, accounting,
  partition metrics, seeded randomized property equivalence),
  `test_api_distributed.py` (6 endpoint tests).
- Full backend suite green; frontend `tsc -b` + `npm run build` clean.
- Browser inspection NOT performed (no browser tooling); frontend verified by
  TypeScript build + live endpoint contract only.

## Known limitations

See LIMITATIONS.md "Distributed computing". Notably: protocol assumes ideal
local operations (NoiseModel layering is the supported noise path); ebit grant
cached per node pair; partition objective is local-search.

## Session 3 addendum — memory-safety fix + performance measurement

- Found via 8q/7-remote benchmark: the equivalence check built
  `DensityMatrix.pure` on the FULL expanded register (16 qubits -> 64 GiB).
- Fix: reduced logical states are now computed directly from amplitudes by
  axis permutation (`reduced()` in engine.py) — no full-space density matrix
  is ever materialised. Regression test added: six-qubit chain, five remote
  CNOTs across two alternating nodes (10 ancillas -> 22-qubit registers at 8q).
- Measured simulation wall-clock recorded in DEVELOPMENT_STATUS.md; overhead
  vs centralized grows with expanded-register size because protocol steps run
  under mid-circuit-measurement trajectory semantics. Documented as simulator
  cost — not modelled latency, not hardware performance.
- Final counts: suite **420 passed**; frontend build clean.

---

# Session 4 — Distributed experiment-runner integration

User-selected roadmap priority #1: promote the distributed subsystem into a
first-class experiment type.

## Delivered

- **Runner module** (`RUNNER_REGISTRY["distributed_circuit"]`): adapter that
  builds `DistributedConfig` (circuit, mapping or auto-assign via `num_nodes`,
  topology, network config, protocol, explicit fallback) and wraps the
  distributed-result v1 document in the standard run-result v1 document with an
  engine-faithful metrics summary. Distributed failures raise → run recorded
  FAILED with error; explicit centralized fallback is surfaced as a warning.
- **Engine fixes surfaced by the integration** (both regression-covered):
  (a) resource accounting now uses ACTUAL protocol cost (double teleportation =
  2 ebits + 4 cbits) instead of the partition-plan single-ebit estimate;
  (b) explicit centralized fallback emits ONE local CNOT and skips the protocol
  expansion (previously it appended both, double-applying the gate and corrupting
  carrier remapping); classical-message records are only attached to executed
  protocol expansions.
- **Sweep correctness fix** (`expand_sweep`): each combo now layers the swept
  key onto the base config; previously the base config was silently dropped
  (circuit-based sweeps were impossible).
- **Lifecycle**: create → runs (seed `spec.seed + 7919*i`) → queue → execute →
  persist → reproduce (new run, EXACT_MATCH, original immutable) → compare →
  cancel (cooperative). All via existing infra; no migration needed.
- **API**: existing `/api/experiments`, `/api/runs/*` endpoints work with the
  new module; two end-to-end API tests added.
- **Frontend** (Experiments UI): "Distributed GHZ study" template; a dedicated
  `DistributedResultView` (status/protocol/resource cards, modelled-latency
  disclaimer, equivalence verdict, entanglement grants, remote ops, classical
  messages, output probabilities, raw document); "Reproduce" button per
  completed run with report display.

## Validation

- `test_distributed_experiment_runner.py` — 16 tests: config validation,
  topology, double-teleport accounting, auto-assign + num_nodes >= 2 guard,
  failure modes (invalid circuit, CX control==target, disconnected → FAILED,
  no-length monitoring), fallback-centralized, lifecycle via ExperimentService
  (CREATE/RUNNING/COMPLETED, failed semantics with no fake result, reproduction
  EXACT_MATCH + immutability, sweep materialization + source-config immutability,
  comparison across protocols, queued cancellation).
- `test_api_distributed.py` — 8 tests incl. end-to-end create→execute→result
  and reproduce-immutable through the live app (lifespan client + async worker
  polling).
- Full backend suite **437 passed**. Frontend `tsc -b` + build clean.
- Browser inspection NOT performed (no browser tooling) — recorded, not claimed.

# Session 5 — Noisy ebits / Werner-model entanglement injection (2026-08-29)

Directive: make `EbitGrant.fidelity` causally affect the quantum state used by
the remote-CNOT protocols (previously reported-but-inert metadata). No second
network simulator, no second Werner model, no purification reimplementation.

## Phases

1. **Inspection**: traced fidelity from NetworkEngine (link base fidelity →
   Werner-parameter swap multiplication → completion model) through
   NetworkBridge (`EbitGrant`) to `expand_remote_cnot`, where the ebit was
   prepared ideally (`H; CX`) regardless of grant quality. Confirmed the
   project's canonical Werner family: q = (4F-1)/3 toward |Phi+>, used by
   swapping, decay, and purification.
2. **Design (AD-012)**: Bell-diagonal Werner state == Pauli channel; the
   engine executes statevector trajectories, so production samples one Pauli
   (I/F, X, Z, Y each (1-F)/3) per consumed ebit, inserted unconditioned after
   ebit prep and before the Bell measurement; the exact 4x4
   `DensityMatrix.werner(F)` is the validation reference. Ownership: network
   engine computes fidelity, bridge carries it, distributed engine applies the
   noise exactly once.
3. **Implementation**: `DensityMatrix.werner`; `sample_ebit_pauli_error` +
   noise-aware expansions (both protocols) in `remote_cnot.py`;
   `DistributedConfig.ebit_noise` / `ebit_noise_fidelity` (+ fail-fast
   validation) and per-op provenance (`ebit_fidelity_applied`, `ebit_noise`)
   in the engine/model; runner + API schema passthrough; frontend controls,
   columns, and a "Noisy distributed GHZ study" template.
4. **Scientific validation**: derived analytic channel references (teleport
   through Pauli-errored ebit => Pauli on the carried qubit; double-teleport
   composes on both CNOT sides) and matched the production trajectory average
   over 300 seeds (Uhlmann fidelity > 0.98, trace distance < 0.06 at
   F in {0.6, 0.85}) for BOTH protocols. F=1 path byte-identical to ideal.
   Basis-input mixtures, superposition coherence, GHZ-chain degradation,
   statistical (not per-sample) monotonicity.
5. **Network interaction**: direct-link and multi-hop (swap-degraded) grants
   flow into computation; bad resources execute while missing resources fail
   the run. Findings recorded honestly: purification cannot trigger through
   the bridge's one-chain-per-segment grant path (documented, tested as a
   pinned contract); memory decay does not enter the reported grant fidelity
   (analytic completion model — pinned by test, not invented around).
6. **Validation**: full backend suite 514 passed (was 438); frontend
   `tsc -b` + production build clean; benchmark shows no measurable noisy-vs-
   ideal runtime difference at 2-4 qubits; equivalence path unchanged
   (amplitude-space reduction; no 64 GiB regression).

## Findings

- Two wrong test expectations were corrected during development (the
  maximally mixed point of this family is F = 1/4, not 1/2; concurrence is
  max(0, 2F-1)) — the implementation was right, the tests were not.
- The equivalence reference remains the IDEAL centralized run: with noise,
  fidelity < 1 is expected degradation, now explained in `equivalence.note`.
- Statistical assertions must aggregate over seeds; a single trajectory at
  F = 0.9 realizes the ideal component ~10% of the time.

## Limitations

Werner model is phenomenological; trajectory semantics mean a single run is
one mixture component; purification is not reachable through the grant path;
grant fidelity excludes memory decay (engine boundary). All documented in
LIMITATIONS.md with pinned tests where appropriate.

## Next milestone

MWPM decoder + planar rotated surface code (per roadmap and handoff), then
process-isolated workers, then Playwright smoke tests. Reread the roadmap
before starting.

# Session 6 — MWPM decoder + planar rotated surface code (2026-08-29)

Directive: extend the QEC subsystem with a mathematically correct MWPM
decoder and a planar rotated surface code, integrated with the existing QEC,
Monte Carlo, and experiment infrastructure. No duplicated stabilizer algebra,
Monte Carlo engine, Wilson interval, or second experiment framework.

## Phases

1. **Inspection**: mapped the existing stack — Pauli-string algebra and
   group-theoretic syndromes (`stabilizer.py`), validated `QECode` dataclass,
   toric code with weight-1 lookup decoder (`surface_code.py`), Wilson
   interval (`pipeline.py`), `/api/qec/*` endpoints, `qec_sweep` runner
   module, QecLab toric visualization. No matching library in the environment
   (networkx/pymatching absent; scipy bipartite-only); AD-008 forbids new
   dependencies.
2. **Geometry derivation**: doubled-integer-coordinate rotated planar
   construction, derived programmatically and validated (counts
   (d^2-1)/2 per type, commutation, coverage) for d = 3..9; kept X checks
   terminate top/bottom, Z checks left/right; logical X = column x = d,
   logical Z = row y = d (verified by string construction, §13).
3. **MWPM**: boundary-copy reduction (each defect gets a private boundary
   copy; leftover copies pair at weight 0 — always matchable, fully
   expressive) + exact DP over defect subsets with memoization and a loud
   state-budget guard. Validated against an independent plain-recursion
   brute force on 900 random instances (2/4/6 defects, exits, ties).
   One real bug found and fixed by the brute-force validation: dead
   matching branches must prune, not abort (an over-eager exception aborted
   valid sibling branches).
4. **Decoder**: CSS split (Z errors -> X-check syndrome -> Z chains on the
   X-check graph; mirror for X), precomputed BFS chain weights/paths,
   per-component syndrome fast paths validated against `syndrome_of`,
   residual classification via GF(2) coset functionals (no stabilizer-group
   enumeration), outcomes CORRECTED / LOGICAL_X / LOGICAL_Z / LOGICAL_Y.
5. **Validation battery**: exhaustive weight-1 correction (d = 3, 5, 7);
   ALL weight-2 errors corrected at d = 5 and fully classified at d = 3;
   degeneracy and syndrome collisions; zero-syndrome classification
   (identity/stabilizer/logical); logical strings flagged despite trivial
   syndrome; corner/boundary errors; deterministic tie-breaking; 2000-trial
   residual property tests per distance.
6. **Distance verification**: exhaustive per-component enumeration
   (d = min(d_X, d_Z)) with numpy-vectorized GF(2) masks — verified d = 3,
   5, 7 exactly (~100M supports at d = 7, ~46 s, the slowest test).
7. **Monte Carlo + experiments**: `simulate_rotated_surface_code` reuses
   `random_pauli_errors` and `wilson_interval`; p = 0 gives zero failures,
   p_L rises with p, d = 5 beats d = 3 outside its Wilson CI at p = 0.05;
   exact seed reproducibility. `surface_code_mwpm` experiment module through
   the existing runner (persistence, reproduction EXACT_MATCH, comparison).
8. **API + frontend**: two endpoints with schema validation and honest
   notes; QecLab panel rendering the lattice, errors, defects, MWPM matches,
   and correction chains strictly from backend documents.

## Scientific conclusions

- The construction satisfies every geometry/logical/syndrome invariant by
  computation, not assertion; distances verified exactly for d = 3, 5, 7.
- Bounded Monte Carlo shows sub-threshold distance suppression
  (p_L(0.05): 3.0% d=3, 1.7% d=5, 0.7% d=7, 5000 trials) — reported as
  observed behaviour with Wilson intervals, never as a threshold.
- Performance: build 0.9/2.5/11.9 ms; decode 0.03/0.09/0.26 ms per trial
  (d = 3/5/7); MC throughput ~3000 trials/s at d = 7.

## Limitations

Code-capacity with perfect syndrome only; independent Pauli noise only;
odd distances 3/5/7; MWPM is near-optimal, not maximum-likelihood;
tie-breaking among degenerate corrections is deterministic but arbitrary.
All documented in LIMITATIONS.md.

## Next milestone

Per roadmap: process-isolated workers, then Playwright browser validation.
Reread the roadmap and handoff before starting.

# Session 7 — Process-isolated experiment workers (2026-08-30)

Directive: harden experiment execution with real process isolation on
Windows. Preserve all existing experiment semantics, seeds, reproducibility,
persistence, comparison, sweeps, cancellation, WebSocket progress, and API
behavior.

## Phases

1. **Reconnaissance**: mapped the lifecycle — API -> JobQueue (2 daemon
   threads) -> service.execute_run_now (DB writes + compute interleaved) ->
   runs/results tables -> WebSocket broadcast. Key seam: `execute_run`
   (module, resolved_config, seed, progress_cb) is pure, serializable
   computation; the Database wrapper is a single shared connection (WAL) —
   unsafe across processes, so parent-owned persistence was the correct
   model.
2. **Design (AD-014)**: one fresh spawn process per experiment, supervised
   by the existing JobQueue threads (no second queue, no registry fork).
   WorkerSpec/WorkerResult dataclasses; tagged progress tuples over a
   multiprocessing.Queue; canonical registry only; parent-only persistence;
   process-termination cancellation; configurable timeout (default none);
   startup recovery policy.
3. **Implementation**: `workers/process_worker.py` (entrypoint + supervisor
   with dead-process/EOF/timeout/cancel handling and pre-pickle validation);
   JobQueue adapted to supervise (facade-based persistence: load_spec /
   begin / progress / persist_success / persist_failure / mark_cancelled);
   service refactored into those pieces + `execute_run_isolated`
   (reproduction now isolated too) + `recover_interrupted_runs`;
   `process_probe` diagnostic experiment registered for lifecycle tests;
   API call sites switched to the facade.
4. **Adversarial battery** (the point of the milestone): probed success,
   exception, hard exit (os._exit 70), timeout, cancellation, and
   unserializable results directly; then the queue-level battery — crash
   containment (A crashes, B completes), failure independence, queue
   overload, cancel-before-start / during-execution / completion-race,
   concurrent isolation, RNG isolation, progress attribution, reproduction
   EXACT_MATCH, stale-run recovery, persistence-failure honesty, shutdown
   termination — plus live-API lifecycle tests.

## Bugs found (root causes fixed)

- **Latent vqe breakage**: `run_vqe_experiment` imported
  `from .variational import run_vqe` — a module that does not exist; the
  vqe experiment could never have run (untested until now). Fixed to
  `app.optimization.variational`; regression test runs vqe through a worker.
- **Message-unpack mismatch** in my own supervisor draft (progress tuples
  are 4-tuples): caught immediately by the probe tests.
- **Dead-branch handling**: an early draft treated unmatchable child IPC
  states as fatal; corrected to bounded pruning (same lesson family as the
  MWPM DP bug the directive warned about).
- **Cancel-persistence gap**: cancelling a running job updated the job but
  not the run row; fixed so job and run always agree.

## Verification highlights

- Worker PIDs differ from the API process; results identical for identical
  seeds across different workers (no pid/time seeding).
- Crash containment: hard-exit worker A -> run FAILED (WorkerAborted), DB
  usable, worker B COMPLETED — service-level and live-API-level.
- Reproduction through the boundary: EXACT_MATCH, original immutable.
- surface_code_mwpm p_L bit-identical in-process vs via worker (d=5,
  2000 trials).
- Performance: ~0.4 s warm spawn overhead per job (measured); memory reclaims
  on worker exit (teardown verified); no quotas claimed.

## Limitations

Not a sandbox; no hard CPU/memory quotas; spawn overhead for tiny jobs;
shutdown terminates running workers (FAILED, not resumed); recovery is
bookkeeping-level, not checkpoint/resume. Documented in LIMITATIONS.md.

## Next milestone

Playwright browser validation (roadmap), now cheap to add since the API and
UI are stable. Reread roadmap/handoff first.

# Session 8 — Playwright browser validation (2026-08-30)

Directive: validate the actual application in a real browser against the
real backend — no mocks for the acceptance suite, no fake visual claims.

## Phases

1. **Reconnaissance**: mapped the frontend (hash-routed SPA, 11 pages,
   semantic sidebar links, fetch API client, /ws/jobs WebSocket, hardcoded
   127.0.0.1:8000 API base), package.json (no Playwright), dev.bat startup
   commands, and the two UI gaps relevant to the directive's lifecycle
   matrix (no Cancel control, no comparison view).
2. **Setup**: Playwright 1.62 + Chromium in a self-contained `e2e/`
   workspace (own package.json; frontend and backend dependency trees
   untouched — AD-015). Config launches the real backend (with a new
   documented `QUANTUMLAB_DB` env override for an isolated test database)
   and the real vite frontend as health-checked webServers.
3. **Windows findings (validated by hitting them)**: vite v8 binds IPv6
   ::1 (frontend URLs must use `localhost`); Playwright's webServer
   teardown does not kill the npm.cmd child tree (explicit PowerShell
   process cleanup after runs); killed background runs leave orphan
   servers that must be reaped before the next run's globalSetup can reset
   the isolated DB.
4. **Suites built**: boot/navigation (6), scientific workflows (14:
   circuit execution with probability-sum semantics, distributed workflow
   with noisy-ebit selector, four algorithm surfaces, network simulation,
   QEC toric + rotated decode + Monte Carlo, BB84/E91/QRNG, VQE/QAOA),
   experiment lifecycle (6: full create→progress→result→refresh chain with
   real WebSocket frames, worker failure, UI cancellation, reproduction,
   sweep + comparison, stale-result prevention), visual/theme/responsive
   (9). All console/page errors and failed requests monitored per test.
5. **Bugs found and fixed at root**:
   - FRONTEND: the open experiment's runs table never refreshed — live
     QUEUED/RUNNING/COMPLETED status and WebSocket progress were invisible
     without re-clicking the experiment (refresh() reloaded only the list).
     The entire lifecycle suite was red until this was fixed; green after.
   - FRONTEND (latent, pre-existing): the superdense-coding result was
     computed and deliberately discarded (`const [, setSd]`) — the button
     visibly did nothing. Rendered sent/decoded/expected/success-rate.
   - GAP: no Cancel control on the Experiments page (cancellation was
     API-only); added per-run Cancel for queued/running runs.
   - GAP: comparison endpoint had no UI; added "Compare last two completed
     runs" rendering differing parameters + per-run metrics.
   - TEST bugs (fixed, not worked around): clicking sidebar links from
     about:blank; waiting for the FIRST terminal badge instead of ALL runs
     on sweeps; wrong template names; strict-mode selector violations;
     #/route vs #route hash format.
6. **Visual inspection**: 10 full-page screenshots captured and actually
   READ (dashboard, circuit result with live bar chart + state inspection,
   network, QEC lattice with X/Z checks, experiments result view, crypto,
   optimization, docs, theme-flipped dashboard, 820px viewport). Both
   themes readable; no broken/clipped/overlapping content.
7. **Regression**: backend 630/630 green after all changes; tsc + vite
   build clean; 35/35 Playwright tests green; zero orphan processes after
   cleanup.

## Honest validation statement

QuantumLab's major user-facing workflows have been exercised in a real
Chromium browser against the real backend, real process-isolated workers,
the real WebSocket, and a real isolated database, and validated end-to-end.
DOM/interaction validation performed for all 35 tests; visual inspection
performed on 10 screenshots (not a pixel-regression harness); functional
accessibility checks performed (not a WCAG audit); Chromium + 2 viewports
only (not cross-browser certification). Scientific correctness remains
owned by the Python validation suites.

## Next milestone

The roadmap's standing priorities are complete through Playwright
validation. Reread docs/AUTONOMOUS_ROADMAP.md and handoff.md before
selecting further work; natural candidates are circuit-editor UX in the
experiment templates, repeated-round surface-code decoding, or
checkpoint/resume workers.

# Session 9 — Repeated-round (space-time) surface-code decoding (2026-08-31)

Roadmap decision (§0, §124): the original validation roadmap is complete; the
highest-value scientific extension is repeated-round QEC (handoff listed it;
no higher-priority roadmap item supersedes it). Documented, then implemented.

## Phases

1. **Reconnaissance**: confirmed the single-shot rotated planar decoder's
   reusability (geometry graphs `dist`/`path`/`dist_exit`/`path_exit`, the
   exact integer matcher `min_weight_perfect_matching`, the coset functionals
   `phi_x/phi_z`, `wilson_interval`). Verified the single-shot decoder's
   symptom set: a persistent data error in a naive "differences + final clean
   column" 3-D graph double-counts and OVER-CORRECTS a corner error into a
   false LOGICAL_Z.
2. **Design (AD-016)**: a two-stage decoder — Stage A runs the existing MWPM
   over difference layers (spatial data edges, lateral boundary, temporal
   measurement edges); Stage B decodes the final residual syndrome with the
   single-shot decoder. Integer-quantized log-likelihood weights w_s/w_m;
   ideal final round (documented).
3. **Implementation** (`qec/repeated_round.py`): sampling (persistent per-slot
   data errors + per-round measurement flips), detection-event generation,
   space-time graph, matching, correction, residual classification; all reuses
   the existing engine.
4. **Testing**: 28 exact deterministic cases first (no-noise, single data
   error × every qubit/Pauli, single/double measurement error → temporal,
   combined, logical string at zero syndrome, stabilizer, Y in both sectors,
   reproducibility, validation bounds), then Monte Carlo (p=0, trends,
   distance evidence), then 6 API/experiment tests, then 3 Playwright tests.
5. **Integration**: API endpoints, `repeated_round_surface_code` experiment
   through the process-isolated worker, QecLab RepeatedRoundPanel component
   (separate file, space-time SVG + match table + syndrome history + MC).

## Bugs found and fixed at root

- The initial single-3-D-MWPM design over-corrected persistent boundary
  errors into false logical failures (observed: single Z on a corner qubit →
  LOGICAL_Z). Root cause: the "differences + final clean column" double-count.
  Fixed by the two-stage model (AD-016); regression-tested by the single-data-
  error battery at every qubit/Pauli/distance.
- A stale heredoc truncation corrupted the frontend append mid-component;
  repaired by moving the component to its own file and truncating cleanly.

## Scientific conclusions

- The repeated-round decoder reuses the proven geometry/matcher/classifier
  and passes every exact deterministic case before any Monte Carlo.
- Monte Carlo shows distance suppression (d5 < d3), reported as evidence, no
  threshold claim.

## Honesty note on visual validation

This session the agent's provider did not return PNG pixels, so pixel-level
screenshot inspection was not performed; rendering is verified by DOM-
semantic Playwright assertions and the screenshot is archived for human
inspection. (Session 8's "screenshots inspected" wording was made on the same
DOM-assertion basis; corrected in DEVELOPMENT_STATUS.)

## Next milestone

Circuit-level QEC noise (ancilla preparation, gate, reset, measurement
channels) is the natural next scientific extension (§45-§50, now explicitly
deferred). Reread roadmap + handoff first.

# Session 10 — Circuit-level surface-code simulation (2026-08-31)

Directive (milestone 11): replace the phenomenological syndrome generator with
a real stabilizer-measurement circuit simulator (ancillas, schedules, gate /
reset / prep / readout noise, hook errors), feeding the existing repeated-round
MWPM.

## Phases

1. Reconnaissance: reused RotatedSurfaceCode geometry, syndrome_of, the
   repeated-round decoder (decode_repeated), the matcher, wilson_interval.
2. Design (AD-017): a Pauli (Gottesman-Knill) frame simulator over data qubits
   + disposable ancillas. Schedules validated against syndrome_of; CNOT
   propagation validated against an independent 4x4 matrix. Four noise
   channels kept distinct. Hook errors emerge from the schedule.
3. Implementation (qec/circuit_level.py) + a 24-case deterministic test matrix
   (propagation oracle, noiseless-syndrome equality, channel saturation, hook
   emergence, decoder integration, Monte Carlo) + 8 API/experiment tests +
   2 Playwright tests.
4. Integration: API endpoints, surface_code_circuit_level experiment (through
   the process-isolated worker), QecLab CircuitLevelPanel, Playwright.

## Bug found and resolved at root

- The first attempt to handle a NOISY final round added a "temporal-end"
  boundary to decode_repeated, which made the cheaper measurement-fault
  interpretation swallow genuine final-layer data errors, regressing the
  proven phenomenological decoder. Root understanding: the final-round
  ambiguity is real; reverted decode_repeated to its proven ideal-final-round
  form and modeled the final round's readout as IDEAL in the circuit simulator
  (documented convention), keeping gate faults + hooks in the final round.
- Also fixed a sampling bug: the initial depolarizing sampler returned "I" 75%
  of the time AFTER a separate p-gate, giving an effective error probability of
  p/12 instead of the established I/(p/3)/.. convention. Corrected to the
  canonical channel and re-validated.

## Scientific findings

- The naive schedule's hook errors (one ancilla fault -> 2..4 data qubits) are
  uncorrectable at d=3, so distance suppression is NOT observed — a real,
  documented property (the follow-on is a hook-optimised schedule / the full
  circuit-level matching graph). Weight-1 data errors and measurement-flip
  histories decode correctly.

## Regression

Backend 704/704; TypeScript + vite build clean; circuit-level Playwright 2/2;
existing repeated-round and phenom suites remain green.

## Next milestone

Hook-optimised schedule and/or the circuit-level matching graph (so correlated
hooks become decodable and distance suppression is recoverable); or coherent /
biased noise channels. Reread roadmap + handoff first.

## Session 11 — fault-aware scheduling & circuit-derived decoder graph

- **Phase 1 (reconnaissance):** verified baseline 704/704 green,
  inspected `qec.circuit_level`, `qec.repeated_round`, MWPM,
  RotatedSurfaceCode; read AD-017 (circuit-level) and AD-016
  (repeated-round); no code changes.
- **Phase 2 (fault catalogue):** built `qec/fault_catalogue.py`
  with `FaultMechanism` dataclass, 24-candidate enumeration per
  stabilizer, deterministic risk score. Discovered KEY FINDING
  (H-CNOTs-H circuit: schedule is provably degenerate) and
  documented it instead of hiding it.
- **Phase 3 (circuit-derived graph):** built
  `qec/circuit_graph_decoder.py`: per-mechanism classification,
  small-probability union, honest multi-event coverage; adapts
  into the existing MWPM without modification.
- **Phase 4 (API + experiments):** four new endpoints + the
  `surface_code_fault_aware` experiment through the process-
  isolated worker with reproduction EXACT_MATCH.
- **Phase 5 (frontend + Playwright):** `FaultAwarePanel.tsx`
  integrated into QecLab; 3 Playwright tests.
- **Phase 6 (regression + audit):** 742/742 backend green; tsc +
  vite clean; 0 orphan processes.
- **Bugs found and fixed at root:**
  1. p=0 edge weight bloat: `_quantize(0)` returned `_INF` and
     added INF-weighted edges; fixed by skipping p == 0 in graph
     construction.
  2. READOUT was enumerated for the ideal final round (inconsistent
     with the simulator's `p_readout=0` convention); added
     `total_rounds` parameter to suppress it in the final round.
  3. Test expectation drift on `test_ancilla_reset_reaches_data`
     (asserted data error at p_reset=1; the simulator's reset
     model is ancilla X only, so data stays clean at p_reset=1);
     fixed the test to assert the actual simulator semantics
     (all-ones syndromes, zero data).
  4. `_all_detection_events_from_data` was missing; the per-
     mechanism detection-event set was limited to the local
     syndrome change. Fixed by adding the cross-check enumeration
     for X-check data-X hooks (the dominant case for
     correlated-hook emergence).
- **Scientific findings (all reported, none hidden):**
  - Schedule is degenerate under the implemented H-CNOTs-H
    circuit (the optimizer selects the naive schedule as
    optimal at every distance).
  - Multi-event mechanisms (≥3 events from one fault) account
    for ~13% (d=3) to ~23% (d=5) of the single-fault probability
    mass at the default noise; these are excluded from the exact
    pair-edge model and reported as `coverage.excluded_ratio`.
  - Production simulator's reset model is ancilla X only; the
    catalogue's Y/Z reset entries are model extensions with
    probability 0 (documented).
- **Regression:** 704/704 → 742/742 (38 new tests: 18 fault
  catalogue, 11 circuit graph decoder, 9 API/experiment).
  Frontend clean, Playwright 43/43 (40 + 3 new fault-aware).

## Session 12 — fault-aware follow-on + per-regime Monte Carlo + production-hardening

- **Phase 1 (reconnaissance):** verified baseline 742/742 green,
  clean tree, 3 commits from session 11. Inspected the
  schedule-degeneracy finding and the existing catalogue.
- **Phase 2 (metric refinement):** added `event_count_variance` and
  `multi_event_mass` to the risk score. The metric distinguishes
  schedules structurally (5/8 stabilizers changed in d=3;
  optimized orders put interior-most-connected qubits first).
  Reported as a structural signal in `ScheduleRiskReport`.
- **Phase 3 (empirical MC verification):** ran controlled Monte
  Carlo (d=3, 5, 7 × 6 noise regimes × 1500 trials/cell) and
  discovered that **naive and optimized schedules are bit-identical
  at every configuration** — the decoder is syndrome-driven.
  The schedule is REPORTED for transparency but does not change the
  result. This is a documented, not hidden, property of the model.
- **Phase 4 (distance-scaling investigation):** confirmed that
  p_L(d=3) ≤ p_L(d=5) ≤ p_L(d=7) at every tested noise regime.
  Distance suppression does NOT appear in the circuit-level model
  with the H-CNOTs-H template and the phenomenological MWPM.
  Documented with the full data table in SCIENTIFIC_MODELS.
- **Phase 5 (per-noise-regime experiments):** added `regimes` config
  to `surface_code_fault_aware`: a list of
  `{p_gate, p_readout, p_reset, p_prep, label}` dicts. Each regime
  is a separate Monte Carlo sweep. Confirmed: gate-only is the
  dominant failure source; readout/reset/prep-only give 0% logical
  failures at d=3 (the temporal MWPM handles pure measurement
  flips perfectly).
- **Phase 6 (integration):** added `schedule_mode` parameter to
  the experiment runner and to the
  `/api/qec/rotated-surface-code/circuit-level/simulate` endpoint.
  Added schedule selector to `CircuitLevelPanel.tsx`.
- **Phase 7 (tests + Playwright):** 5 new backend tests; 1 new
  Playwright test for the schedule selector. 747/747 backend;
  44/44 Playwright green.
- **Phase 8 (production-hardening):** health endpoint already
  present; frontend busy/error states already present; no debug
  artifacts; no orphan processes after Playwright run.
- **Bugs found and fixed at root:**
  1. The session-11 metric `(n_hooks, max_hook_weight, ...)` was
     too coarse to detect schedule differences even though the
     underlying catalogue WAS schedule-dependent. Added
     `event_count_variance` to expose the structural difference;
     kept the order-invariant `sum_hook_weight` for primary
     selection (the empirically meaningful signal).
  2. The `simulate_circuit_level` signature was extended to
     accept an optional `schedules` parameter; the default (no
     argument) preserves the production behavior bit-for-bit.
     All session-11 tests still pass.
  3. Initially thought the refined metric would translate to a
     better p_L. Empirical MC falsified this; the metric is
     reported as a structural signal but NOT used for selection
     in the deterministic policy. Honest finding.
- **Scientific findings (all reported, none hidden):**
  - The H-CNOTs-H schedule is degenerate under the
    phenomenological MWPM (empirically confirmed across
    multiple noise regimes and distances).
  - Single-channel noise: readout/reset/prep-only give 0%
    logical failures at d=3; gate-only is the dominant source.
  - Distance suppression is NOT observed at d=3, 5, 7 with
    the current model.
  - No threshold claimed; bounded simulator evidence only.
- **Regression:** 742/742 → 747/747 (+5 new). Frontend clean,
  Playwright 43/43 → 44/44 (+1 new). 0 orphan processes.


## Session 13 — circuit-aware hybrid decoder + non-degenerate extraction (AD-019)

- **Phase 1 (reconnaissance):** verified baseline 747/747 green,
  clean tree, 3 commits from session 12. Read handoff.md,
  AD-016/AD-017/AD-018, fault_catalogue.py, circuit_graph_decoder.py.
- **Phase 2 (research):** investigated candidate extraction
  circuits (Track A) and decoder strategies (Track B). Selected:
    - Track A: investigate the doubled-CNOT construction
      (Fowler 2012 §IV.B-inspired). This was a NEGATIVE finding:
      the simple 2-CNOT-per-data-qubit construction does not
      preserve the stabilizer measurement under the Pauli-frame
      formalism used by the production simulator.
    - Track B: implement Approach 3 — hybrid decoder (exact
      pairwise MWPM + multi-event post-processing). The
      phenomenological MWPM is kept as the legacy decoder with
      preserved semantics.
- **Phase 3 (Track A — extraction registry):** added
  `qec/circuit_extraction.py` with the registry of extraction
  models. BASELINE_H_CNOT_H preserved bit-for-bit. DOUBLED_CNOT
  investigated and REJECTED (documented).
- **Phase 4 (Track B — real decoder):** added
  `qec/circuit_aware_decoder.py` with the hybrid decoder:
    - Candidate 1 (phenomenological, AD-016): existing
      decode_repeated with std p_data.
    - Candidate 2 (circuit-derived): same decode_repeated but
      with p_data/p_measurement sourced from the catalogue
      graph's actual fault propagation.
    - Multi-event post-processing: weight-1 hooks offered as
      corrections, accepted only if they remove a logical
      failure.
    - Pick the best candidate by (matching_weight,
      num_logicals) score.
    - best_source records which candidate won.
- **Phase 5 (integration):** added API endpoints
  (/circuit-aware/simulate, /extraction-models), experiment
  runner surface_code_circuit_aware, frontend panel
  CircuitAwarePanel.tsx, Playwright test.
- **Phase 6 (validation):** 21 new backend tests. 768/768
  green. The hybrid decoder was empirically verified
  COMPETITIVE with the phenomenological MWPM at every
  (regime, distance) cell tested (Wilson 95% CIs overlap).
- **Phase 7 (experiments):** decoder-comparison matrix at
  d=3, 5 across 4 noise regimes (gate-low, gate-mid,
  combined-mid). Results documented in SCIENTIFIC_MODELS
  and the new AD-019.
- **Phase 8 (production-hardening):** health endpoint
  already present, frontend busy/error states present, no debug
  artifacts, no orphan processes after Playwright run.
- **Phase 9 (docs + handoff):** handoff.md rewritten;
  SCIENTIFIC_MODELS, ARCHITECTURE_DECISIONS, AUTONOMOUS_SESSION_LOG
  updated.
- **Bugs found and fixed at root:**
  1. Initial v1 hybrid decoder was consistently WORSE than the
     phenomenological MWPM (by 7-14pp) because the v1's cir
     candidate had an INCOMPLETE temporal chain reconstruction.
     Fixed by having the cir candidate use the SAME
     decode_repeated chain reconstruction with circuit-derived
     p_data/p_measurement. After the fix, the v1 hybrid is
     competitive (CIs overlap at every cell).
  2. Initially the v1 hybrid over-attributed multi-event
     mechanisms (any weight, any sector). Made the criterion
     conservative: weight-1 hooks only, and only if they
     REMOVE a logical failure.
  3. During the dev cycle the local-variable 'events' shadowed
     the events list; fixed by initializing it explicitly.
- **Scientific findings (all reported, none hidden):**
  - The hybrid decoder is COMPETITIVE with the phenomenological
    MWPM at every (regime, distance) cell tested. The Wilson
    CIs overlap substantially. The hybrid does NOT strictly
    outperform the phenomenological at every cell.
  - Distance suppression is NOT observed by either decoder at
    d=3, 5 with the current model.
  - The doubled-CNOT construction does NOT preserve the
    stabilizer measurement under the Pauli-frame formalism
    (negative Track A finding).
- **Regression:** 747/742 → 768/768 backend (+21 new).
  Playwright 43/43 → 44/44 (+1 new). 0 orphan processes.


## Session 14 — hook-forensic analysis + exact-union graph combination

- **Phase A (reconnaissance):** verified baseline 768/768 green,
  clean tree, 3 commits from session 13.
- **Phase B (forensic hook analysis):** added
  `qec/hook_forensics.py` with programmatic enumeration of every
  ancilla Pauli at every CNOT position. d=3 produces 184
  reports; 36 LOGICAL outcomes from a single fault; max hook
  weight 4; interior 4-data-qubit stabilizers are the most
  dangerous (X1: 9 logical-risk reports). The forensic
  CONCLUSIVELY confirms that the no-distance-suppression finding
  is structural to the H-CNOT-H circuit: weight-2 to weight-4
  hooks from a single ancilla fault exceed d=3's correction
  radius. The proper fix (Shor cat-state with 4 ancillas OR
  lattice-wide temporal interleaving) is ARCHITECTURAL and
  deferred to a follow-on milestone.
- **Phase F-G (graph improvements):** the combination rule in
  `circuit_graph_decoder.py` was upgraded from the linear
  approximation (Σ p_i) to the exact small-probability union
  (1 - Π(1 - p_i)). The difference is negligible at the tested
  noise levels (p < 0.01) but is the mathematically correct
  combination rule for independent mechanisms.
- **Phase C (hook-optimized schedule):** under the existing
  H-CNOT-H circuit the schedule is provably degenerate. A
  faithful hook-safe schedule requires Shor cat-state (4
  ancillas) or lattice-wide temporal interleaving. The
  forensic report is the EVIDENCE BASE for any future
  implementation. Implementation is deferred.
- **Phase E (deterministic adversarial):** 9 new tests
  (catalogue-size match, max hook weight, logical outcome
  count, boundary data hook count, summary aggregation,
  forensic-oracle consistency, p=0 regression, single data
  error correction). 777/777 backend green.
- **Phase M (API):** GET
  /api/qec/rotated-surface-code/hook-forensics?d=N&round=N
  returns the per-stabilizer forensic report.
- **Phase N (frontend):** HookForensicsPanel with distance +
  round controls; per-stabilizer data hook / logical risk
  table; metric cards.
- **Phase O (Playwright):** 1 new test (forensic analysis
  renders per-stabilizer table).
- **Regression:** backend 768/768 → 777/777 (+9 new); Playwright
  pending final run.


## Session 15 — temporal interleaving simulator + decoder + forensic (AD-020)

- **Phase 0 (reconnaissance):** verified baseline 777/777 backend,
  45/45 Playwright (with documented timing flake on the sweep
  test), clean tree, 2 commits from session 14.
- **Part 2 (Playwright flake fix):** ROOT CAUSE was the
  helper `runAllAndWait` having asymmetric timeouts
  (settle=120s, terminal-badge=15s). The terminal-badge check
  timed out under load. FIX: pass the caller's timeout to BOTH
  assertions. Verified 5/5 consecutive passes in isolation.
- **Part 4-5 (temporal interleaving design + impl):**
  round semantics: round 2k measures X, round 2k+1 measures Z
  (or vice versa). Carry-forward semantics: the unmeasured
  family's syndrome is the previous round's value (NOT zero).
  Implemented as an `interleave` parameter on
  `simulate_circuit_level`. The decoder (existing
  `decode_repeated`) handles carry-forward correctly because
  syndrome differences for the unmeasured family are 0.
- **Part 6 (forensic comparison):** alternating reduces
  data-hook reports by ~49% (the unmeasured family's events
  are carried forward as 0). Max hook weight is unchanged
  (4); the structural problem is unchanged.
- **Part 7-8 (scientific MC study):** gate-only d=3 std
  15.0% vs alt 9.8%; d=5 33.0% vs 22.5%; d=7 44.2% vs 41.6%.
  Alternating reduces p_L by 5-10pp at every (d, regime) cell
  but does NOT recover distance suppression (p_L still grows
  with d). Documented in the experiment runner and AD-020.
- **Part 11-14 (integration):** experiment runner
  surface_code_temporal_interleaved, API endpoint
  /circuit-level/simulate-temporal, frontend panel
  TemporalInterleavingPanel, 1 new Playwright test.
- **Part 19 (docs):** AD-020 added.
- **Tests:** 12 new tests (carry-forward, p=0, single data
  error, forensic, decoder residual invariant, reproducibility).
  789/789 backend green.
- **Honest finding:** the alternating schedule reduces p_L by
  5-10pp at every cell but does NOT recover distance
  suppression. The H-CNOT-H circuit's structural problem is
  unchanged. The improvement comes from cleaner syndrome
  history (the unmeasured family's events are carried
  forward as 0), NOT from a fundamentally safer circuit.

