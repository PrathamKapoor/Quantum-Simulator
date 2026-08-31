# Architecture Decisions

Significant decisions with reasons, alternatives, and consequences (§176).

## AD-001 — Little-endian qubit ordering platform-wide
- **Decision:** qubit 0 = least-significant basis bit everywhere.
- **Reason:** matches Qiskit-style mental model and numpy reshape conventions
  used by the axis-based gate application.
- **Alternative rejected:** big-endian (textbook ket reading) — would require
  conversions at every UI boundary.
- **Consequence:** register strings print high-bit-first; documented in the
  quantum package docstring and tested.

## AD-002 — Gate-local operand convention + explicit conversion helper
- **Decision:** k-qubit gate matrices use FIRST operand as most-significant
  local bit; truth-table-indexed matrices must pass through
  `app/algorithms/conventions.local_reorder`.
- **Reason:** single well-defined convention; conversion is testable.
- **Consequence:** three session-1 bugs traced to skipping this conversion;
  now enforced by convention tests and documented in SCIENTIFIC_MODELS.md.

## AD-003 — Partial-trace einsum output ordering (bug fix elevated to decision)
- **Decision:** kept ROW letters first, then kept COLUMN letters, in the
  einsum output spec of `DensityMatrix.partial_trace`.
- **Incident:** interleaved per-qubit [row,col] output silently produced
  transposed-axis mixing for multi-qubit keeps; diagonal marginals (GHZ)
  masked it until distributed remote-CNOT validation hit an off-diagonal case.
- **Alternatives:** keep interleaving and transpose after — equivalent but
  obscures the invariant.
- **Consequence:** regression tests require off-diagonal multi-qubit keeps,
  full-system identity, and random-state trace preservation.

## AD-004 — Teleportation correction order: X before Z
- **Decision:** conditioned corrections apply X^{mx} then Z^{mz}.
- **Reason:** Bob's pre-correction state is Z^{mz}X^{mx}|ψ⟩.
- **Incident:** wrong order is invisible for isolated teleportation (differs
  only by global phase) but corrupts circuits where the teleported wire later
  participates in entangling operations (distributed CNOT).
- **Consequence:** distributed remote-CNOT validates bit-exact; standalone
  teleportation tests unchanged (fidelity-based).

## AD-005 — Network engine exception guard surfaces errors
- **Decision:** engine-level guards append to `result.engine_errors` instead
  of silently continuing.
- **Incident:** a missing import was swallowed for a full test cycle.
- **Consequence:** API consumers can inspect `engine_errors`; silent failure
  class eliminated.

## AD-006 — Purification refuses asymmetric inputs
- **Decision:** BBPSSW/DEJMPS require identical input fidelities; mismatches
  skip purification rather than approximate.
- **Reason:** recurrence math assumes symmetric inputs; approximating would
  violate RULE 2.
- **Consequence:** network integration may skip purification opportunities;
  documented in NETWORK_MODELS.md.

## AD-007 — ZNE uses density-matrix expectations
- **Decision:** ZNE driver executes folded circuits in exact density-matrix
  mode.
- **Incident:** statevector trajectories produced ±1 "estimates" that fit
  garbage extrapolations.
- **Consequence:** bounded at 12 qubits; smooth scale-dependent estimates.

## AD-008 — No dependency additions (RULE 7)
- **Decision:** all Phase A–H capabilities implemented on numpy/scipy/stdlib.
- **Consequence:** Student-t quantiles replaced by normal approximation with
  documented CLT assumption; bootstrap provided as robust alternative.

## AD-009 — Distributed subsystem expands remote gates into genuine protocol circuits
- **Decision:** cross-node CNOTs are compiled in-place into their full
  protocol expansion (entanglement distribution, Bell measurement, classical
  bits, X-before-Z corrections, local CNOT) on the ordinary simulator, with an
  explicit logical→physical carrier map (`physical_of`) rewritten after each
  remote gate so later operations act on the migrated wire.
- **Alternatives rejected:** (a) executing a centralized CNOT and labelling it
  "remote" — prohibited fake distribution; (b) simulating each node
  independently and stitching — incorrect once carriers migrate and states
  entangle across nodes.
- **Consequence:** distributed execution is physically the protocol; every
  ebit/classical-bit cost is a real circuit operation count, not a label.
- **Related policy:** failures stay failures. An unavailable ebit fails the
  result (`status=failed`) unless the caller explicitly requested
  `fallback="centralized"`; degradation is then recorded in warnings.

## AD-010 — Explicit partition mappings are honoured verbatim
- **Decision:** when a user supplies `qubit_to_node`, no local search may move
  those qubits; search only refines auto-seeded assignments, and can never
  empty a node (otherwise minimising cross-node gates collapses everything to
  one node).
- **Reason:** explicit mapping is user intent; silently re-assigning would make
  the reported partition unrelated to the request.

## AD-011 — Distributed experiments are an adapter over the existing engine
- **Decision:** `distributed_circuit` is a run-registry module whose runner is
  a thin adapter: parse config → construct `DistributedConfig` → call the
  existing `DistributedExecutor` → wrap the `quantumlab.distributed-result` v1
  document inside the standard `quantumlab.run-result` v1 document
  (`artifacts.distributed_result`). No distributed logic lives in the generic
  experiment runner.
- **Result ownership:** the scientific output is, and remains, the
  distributed-result v1 document; the run-result document is the wrapper record
  (metrics summary + equivalence summary + full payload reference).
- **Persistence strategy:** existing `results` table (schema_name/version/
  payload JSON), existing `runs` row (resolved_config / seed / status /
  metrics). No new tables, no migration required.
- **Seed strategy:** existing convention — per-run seed `spec.seed + 7919*i`;
  the effective seed is echoed into metrics/reproducibility. No second RNG
  system.
- **Cancellation strategy:** existing cooperative job cancellation. Within the
  in-process worker the engine executes atomically; queued jobs cancel cleanly,
  running jobs finish unless the runner checks the cancel flag at progress
  boundaries (documented limitation, not hidden).
- **Large-result strategy:** the run row stores only the metrics summary; the
  full distributed document (including output probabilities, remote ops,
  entanglement grants) is stored once in the `results` payload and only loaded
  by detail endpoints. List endpoints never decompress result blobs.
- **Sweeps:** reuse the existing float-based sweep engine; base configuration is
  now correctly seeded into every combo (bug fix). Only engine-supported
  numeric dimensions are exposed (`num_nodes` with auto-assignment); sweeps over
  strings (e.g. protocol) were deliberately NOT engineered because the existing
  framework types sweep values as floats.

## AD-012 — Werner ebit noise: ownership, representation, and compatibility

**Decision.** The network's granted fidelity (`EbitGrant.fidelity`) is made to
govern the actual quantum state consumed by remote-CNOT protocols, with these
boundaries:

1. **Where the constructor lives.** The canonical Werner state is
   `DensityMatrix.werner(F)` in `app/quantum/density.py` — quantum-state
   mathematics stays in the quantum layer; the network and distributed layers
   reference it, they do not reimplement it. It reuses the network subsystem's
   existing Werner parameterization (q = (4F-1)/3) rather than introducing a
   second model.

2. **Who applies the noise.** The NetworkEngine OWNS the fidelity value
   (link model, swaps, purification config). The NetworkBridge OWNS carrying
   it. The distributed engine OWNS the single application of state-level
   noise, at protocol expansion (`remote_cnot._ebit_prep`), inserted as an
   unconditioned Pauli before the Bell measurement. Exactly one layer applies
   the effect; AD-004 correction ordering and AD-003 partial-trace semantics
   are untouched.

3. **Density matrix vs trajectory.** Production execution samples one
   Bell-state component per consumed ebit (exact trajectory representation of
   the Bell-diagonal Werner state — the architecture already executes under
   statevector trajectory semantics). The exact 4x4 density-matrix constructor
   is the validation reference and an opt-in result artifact
   (`include_reduced_state`, <= 6 qubits). Global density matrices are never
   materialised; the amplitude-space equivalence reduction (64 GiB fix)
   remains.

4. **Backward compatibility.** Default mode is "ideal": with no noise config
   (or F >= 1) the emitted operation list is byte-identical to the previous
   implementation, so legacy experiments, persisted results, and their
   semantics are unchanged. Modes: "ideal" | "network_fidelity" (consume the
   grant's fidelity) | "fixed" (`ebit_noise_fidelity` in [0,1]); invalid
   configurations fail fast at `DistributedConfig` construction and a failed
   remote grant still fails the run (bad resources execute, missing resources
   do not).

5. **Result schema.** `quantumlab.distributed-result` stays v1 with additive
   fields only (`ebit_fidelity_applied`, `ebit_noise` per remote operation;
   `ebit_noise` in reproducibility; `equivalence.note`). Equivalence continues
   to reference the IDEAL centralized execution; with noise enabled a fidelity
   below 1 is documented degradation, not a validation failure.

**Rejected alternatives.** (a) Applying noise inside NetworkBridge — wrong
layer: the bridge translates resources, it does not execute circuits.
(b) Random bit-flip heuristics — not a Werner state, destroys mixed-state
semantics. (c) Density-matrix execution of the expanded register — reintroduces
the 64 GiB scaling failure. (d) Injecting memory decay into grant fidelity —
the network engine's completion model is analytic by design; changing it is a
network-subsystem decision, not a distributed-layer workaround.

## AD-013 — Surface code integrates the existing QEC stack; exact MWPM without new dependencies

**Decision.** The rotated planar surface code is built ON the existing QEC
infrastructure rather than beside it:

1. **Reuse over duplication.** Pauli algebra, syndrome generation
   (`stabilizer.syndrome_of` semantics), the depolarizing sampling convention
   (`random_pauli_errors`), and the Wilson interval (`pipeline.wilson_interval`)
   are reused unchanged. The toric code remains untouched; the planar code is
   a sibling, not a fork. No second stabilizer algebra, Monte Carlo engine,
   confidence-interval formula, or experiment framework exists.
2. **Geometry is derived and algebra-gated.** The doubled-coordinate
   construction is validated at build time (check counts, commutation,
   coverage, logical structure); construction FAILS LOUDLY rather than
   shipping a broken lattice. Distance is computed by exhaustive per-component
   enumeration, never taken from the constructor argument.
3. **Exact MWPM without dependencies (AD-008).** No matching library exists in
   the environment and AD-008 forbids additions; scipy's matcher is
   bipartite-only and the decoder graph is general. The decoder therefore uses
   an exact dynamic-programming MWPM over the defect+boundary-copy graph with
   a loud capacity guard, validated against brute force on small instances.
   The boundary-copy reduction keeps the graph always perfectly matchable and
   expressive for every valid correction. Complexity: O(2^k) worst case in the
   defect count k with memoization - exact and fast for supported distances
   (k <= 24), documented honestly instead of claiming blossom-scalability.
4. **Residual classification via coset functionals.** Stabilizer-equivalence
   of zero-syndrome operators is decided by precomputed GF(2) coset
   functionals (valid: k = 1), so logical failure detection is O(1) per trial
   and independent of decoder internals.
5. **Experiments and API reuse the existing frameworks.** The
   `surface_code_mwpm` runner module and the two `/api/qec/rotated-surface-
   code/*` endpoints follow the existing conventions; no new database,
   migration, or result-versioning scheme was needed.

**Rejected alternatives.** (a) Greedy/nearest-neighbour "MWPM" - prohibited
(§74) and empirically worse. (b) A new dependency (networkx/pymatching) -
violates AD-008. (c) Dense-statevector simulation of the code - unnecessary
and unscalable; everything operates in stabilizer/Pauli space. (d) Reusing the
toric lookup decoder - it corrects only weight-1 patterns and would silently
understate the planar code's capability.

## AD-014 — Experiments execute in disposable worker processes (Windows spawn)

**Decision.** Experiment execution moved OUT of the API process: each
submitted run is computed by a fresh child process (Windows spawn, the
native semantics on this platform), supervised by the existing threaded
JobQueue pool. The worker entrypoint is a module-level function
(`workers/process_worker.worker_main`); nothing at import time spawns
processes, so no recursive-startup hazard exists.

**Process model.** One fresh process per experiment (option A of the
milestone's decision space), chosen over a persistent pool because it makes
state leakage structurally impossible, gives OS-level memory reclamation on
exit, and lets cancellation terminate the child outright. Measured cost:
~0.4 s warm spawn overhead per job - acceptable for experiments and
documented rather than hidden; isolation is not traded away for trivial-job
latency.

**Contracts.** `WorkerSpec` (run_id, module, resolved_config, seed) is the
only input; `WorkerResult` (ok, result, error_type/message, traceback text,
exitcode, cancelled, timed_out) is the only output; progress crosses as
run_id-tagged tuples. Everything is deliberately picklable; database
connections, WebSocket objects, request objects, locks, and closures never
cross. The worker resolves experiments through the CANONICAL
`RUNNER_REGISTRY` via `runner.execute_run` - no second registry, no
experiment-specific worker logic. The `process_probe` registered experiment
is the sanctioned diagnostic vehicle for lifecycle tests.

**Ownership.** The parent (JobQueue + ExperimentService) is the authoritative
lifecycle owner and the ONLY database writer: it records RUNNING, progress,
the result row, and COMPLETED/FAILED/CANCELLED. Workers never open the
database, so no SQLite concurrency is added by parallel workers (writes
remain serialized in the parent; WAL mode was already enabled). A parent
database connection is never passed to a worker.

**Failure semantics.** Child exception, non-zero/abnormal exit, missing
result, result-serialization failure, and timeout all become FAILED - never
COMPLETED, never fabricated results. The child pre-pickles its result so a
serialization failure is an explicit SerializationError rather than a
silently lost message. Malformed/mismatched worker messages are rejected
(run_id validated). Persistence failures in the parent are reported
honestly: the run is FAILED with a PersistenceError, not COMPLETED.

**Cancellation.** QUEUED jobs cancel without starting (worker never spawns;
run row marked CANCELLED). RUNNING jobs are cancelled by TERMINATING the
child process - strictly stronger than the previous cooperative thread
model - and the run becomes CANCELLED with no partial result. The
cancel/completion race is resolved deterministically: a cancellation
requested before result acceptance wins; otherwise the completion stands.
Exactly one terminal state is ever recorded.

**Shutdown/restart.** `JobQueue.shutdown()` terminates active children; no
new worker spawns after shutdown begins (no orphans). Startup recovery
(`ExperimentService.recover_interrupted_runs`, called in the API lifespan):
RUNNING/CANCELLING runs orphaned by a dead process become FAILED with
error_code INTERRUPTED_BY_RESTART; the volatile queue's QUEUED marks return
to CREATED so runs can be re-executed. Recovery is implemented and tested -
not merely documented.

**Timeouts.** A per-queue configurable `process_timeout_s` (default None:
no arbitrary cap that could kill legitimate long-running experiments). On
timeout the child is terminated and the run is FAILED with WorkerTimeout.

**Honest limits.** Process isolation contains faults and reclaims memory;
it is NOT a sandbox - workers run with the same OS-user rights as the
parent, and no hard CPU/memory quotas exist. No broker, no Docker, no
microservices: this remains a local application on the standard library.

## AD-015 — Playwright end-to-end validation as an isolated dev workspace

**Decision.** Real browser validation uses Playwright (Chromium) in a
self-contained `e2e/` workspace with its own package.json; `@playwright/test`
is a devDependency OF THAT WORKSPACE ONLY. The backend runtime dependencies
are unchanged (AD-008's no-new-runtime-dependency rule is untouched), the
frontend package.json is unchanged, and no browser framework enters either
production surface.

**Mechanics.** `e2e/playwright.config.ts` launches the REAL backend (uvicorn
with an isolated `QUANTUMLAB_DB` test database - a small, documented env-var
override added to the API lifespan) and the REAL frontend (vite) as
webServers, with health-check gating and `reuseExistingServer` for
interactive runs. The acceptance suite never mocks the backend, the workers,
the WebSocket, or the database (§9, §122-§127). Global setup wipes only the
isolated E2E database; the developer's `quantumlab.db` is never touched.
Evidence (screenshots, traces, reports) is gitignored.

**Windows notes (validated, not assumed).** Vite v8 binds IPv6 ::1 - use
`localhost`, not 127.0.0.1, for the frontend URL. Playwright's webServer
teardown does not reliably kill npm.cmd child process trees on Windows;
orphan servers are cleaned with an explicit PowerShell process query. These
are recorded so the next agent does not rediscover them.

**Scope honesty.** Chromium-only, two viewports, functional accessibility
checks - not cross-browser certification, not WCAG certification, not a
visual-regression pixel harness. Scientific correctness remains owned by the
Python suites; browser tests prove the UI->API->worker->result->UI chain.

## AD-016 — Repeated-round QEC is a two-stage decoder over the existing single-shot engine

**Decision.** Temporal (repeated-round) surface-code decoding is implemented
as a THIN extension (`qec/repeated_round.py`) built on the existing rotated
planar geometry, the existing exact integer matcher, and the existing
single-shot decoder — not as a second framework.

1. **Two-stage model over a single 3-D MWPM.** The naive "syndrome
   differences + final clean column" single graph double-counts a persistent
   data error (its syndrome enters the difference stream on introduction and
   exits at a final clean round), over-correcting boundary errors into false
   logical failures. Instead: Stage A runs MWPM over the difference LAYERS
   1..R (spatial data edges + temporal measurement edges + lateral boundary);
   Stage B decodes the final residual syndrome with the proven single-shot
   decoder. This is equivalent in information and validated by the exact-case
   battery, and it reuses the matcher/single-shot verbatim.
2. **Weights are integer-quantized log-likelihood ratios** (1e-6) so the
   exact integer matcher is reused unchanged; matching stays deterministic.
3. **Ideal final round:** the model assumes a perfect final measurement;
   without it a final measurement flip is indistinguishable from a final data
   error. Documented in LIMITATIONS.
4. **Reuse, not duplication:** geometry, `min_weight_perfect_matching`, the
   single-shot residual classifier (coset functionals), `wilson_interval`,
   the experiment runner / process-isolated worker / WebSocket progress, and
   the Playwright webServer harness are all reused. Circuit-level noise is
   deliberately deferred to a later milestone (§45-§50).

**Rejected alternatives.** (a) A single 3-D MWPM with a final clean column —
   reintroduces the double-count artifact. (b) Persistent vs per-slice error
   model ambiguity left implicit — the per-slot persistent-error sampling
   with difference detection is made explicit and testable. (c) A new matcher
   or graph framework — unnecessary; the existing DP matcher's complete-graph
   + boundary-copy interface suffices for the space-time graph.
