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
