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
