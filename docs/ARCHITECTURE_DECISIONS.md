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

## AD-017 — Circuit-level QEC is a Pauli-frame simulator feeding the repeated-round MWPM

**Decision.** Circuit-level surface-code noise is modeled by a Pauli
(Gottesman-Knill) frame simulator over data qubits + disposable ancillas,
driving the EXISTING repeated-round decoder — not by a second decoder or a
second graph.

1. **Frame simulation, not density matrices** (§44): only Clifford gates
   (H, CNOT, reset, Z-measure) and Pauli noise appear, so the whole noisy
   circuit is tracked exactly as a Pauli frame. CNOT propagation (control X ->
   target X; target Z -> control Z) is validated against an independent 4x4
   matrix CNOT.
2. **Hook errors emerge, never inject:** ancilla faults propagate through the
   schedule's remaining CNOTs onto data qubits; recorded explicitly. No
   separate "hook-error" random variable exists.
3. **Decoder reuse:** the syndrome history + net data frame feed the existing
   two-stage repeated-round decoder; circuit-level hook correlation is NOT
   folded into a bespoke matching graph (documented limitation — the
   follow-on milestone).
4. **Ideal final round + ideal single-qubit gates:** modeling choices so the
   final syndrome is the clean net data syndrome (consistent with
   decode_repeated's contract) and to bound scope.
5. **Channel separation:** gate / readout / reset / preparation noise are four
   independent configurable probabilities, never conflated.

**Rejected alternatives.** (a) A dedicated circuit-level matching graph — out
of scope for this milestone and would duplicate decoding logic (§M). (b)
Modeling a final-round measurement flip as a data error heuristically —
rejected; the ideal-final-round convention is cleaner and documented.
(c) Folding reset into preparation or gate noise — rejected; the milestone
requires them distinct.

## AD-018 — Fault-aware scheduling and circuit-derived decoder graph (milestone 12)

**Decision.** The circuit-level QEC subsystem gains a fault-catalogue
infrastructure, a deterministic schedule optimizer, and a
circuit-derived detector graph that is reported as STRUCTURAL metadata
alongside the EXISTING phenomenological MWPM decoder. Decoder
semantics are unchanged (the graph is not a replacement decoder);
the schedule optimizer is reproducible and, under the implemented
H-CNOTs-H circuit model, selects the naive schedule as optimal
(documented degenerate finding).

1. **Single-fault propagation catalogue** (`qec/fault_catalogue.py`)
   enumerates every elementary fault mechanism in the actual
   stabilizer-measurement circuit for every round: ancilla reset,
   ancilla prep, every CNOT (pre-gate, both qubits, all three Paulis),
   and readout. For each mechanism the catalogue computes the
   propagated data support, the syndrome delta on the affected
   stabilizer, the FULL detection-event set (local + cross-checks),
   the residual classification (STABILIZER / DATA_HOOK / LOGICAL_X /
   LOGICAL_Z / MEASUREMENT_FLIP), and the minimum additional-fault
   count to complete a logical. The CNOT propagation is the project's
   existing `cnot_propagate` (already oracle-tested against the
   independent 4x4 matrix CNOT); the catalogue's per-mechanism
   event-set computation is a separate function
   (`_all_detection_events_from_data`) so the test suite can
   cross-check.

2. **Schedule optimization is deterministic and documented.** Every
   candidate ordering of a stabilizer's CNOT support is enumerated
   (24 permutations for weight 4, 120 for weight 5, 5040 for
   weight 7). For each candidate, the catalogue is built and a
   composite risk score is computed: (n_logical_risk_hooks,
   max_hook_weight, n_hooks, sum_hook_weight, canonical-order).
   The lowest lexicographic key wins.

3. **KEY FINDING (documented, not hidden):** under the H-CNOTs-H
   stabilizer-measurement circuit (the model implemented in the
   production simulator), the schedule is provably degenerate — every
   permutation of a stabilizer's CNOT support produces the same
   `n_logical_risk_hooks`, `max_hook_weight`, `n_hooks`, and
   `sum_hook_weight` (the order of faults shifts the `gate_index`
   labels but the data-side support is invariant). The optimizer
   therefore selects the naive schedule as optimal and the
   `compare_naive_vs_optimized` report shows
   `stabilizers_with_changed_schedule = 0` for every distance.
   This is a real and important property of the implemented model.
   A non-degenerate circuit (e.g. a different stabilizer-measurement
   template, or a noisy basis preparation) would expose a different
   selection; the optimizer is generic over the catalogue.

4. **Circuit-derived detector graph** (`qec/circuit_graph_decoder.py`):
   the catalogue is converted to a matching graph by classifying each
   mechanism into ZERO_EVENT / BOUNDARY (1 event) / EDGE (2 events) /
   MULTI_EVENT_APPROXIMATED (≥3 events). Pair edges are weighted by
   the combined probability of every independent mechanism mapping
   to the same detector pair, using a small-probability union
   (Σp_i, the documented combination rule). The graph adapts into
   the EXISTING exact MWPM via the same defect-set + boundary-exit
   interface (no matcher changes, no duplicate algorithm). Multi-event
   mechanisms are excluded from the exact pair-edge model (Approach A
   in the directive) and reported as `coverage.excluded_ratio` with
   honest probability-mass accounting.

5. **Decoder semantics are preserved.** The graph is reported as
   STRUCTURAL metadata alongside the phenomenological MWPM, which
   remains the logical-decoding engine. The Monte Carlo endpoint
   (`circuit_derived_simulate`) and the experiment runner
   (`surface_code_fault_aware`) report the graph coverage per
   distance, the per-distance schedule report, and the
   phenomenological-decoder logical-error rate (with Wilson
   intervals). No experiment uses the graph as a logical decoder.

6. **API + experiment integration.** Four new endpoints
   (`/schedule/analyze`, `/fault/analyze`, `/circuit-derived/graph`,
   `/circuit-derived/simulate`) follow the existing pydantic
   validation pattern (directive §34, §35). The new
   `surface_code_fault_aware` experiment uses the existing
   `ExperimentService` lifecycle and reproduces EXACT_MATCH through
   the process-isolated worker (directive §37, §38, AD-014).

7. **Frontend.** A new `FaultAwarePanel` is integrated into QecLab
   with explicit schedule-comparison, single-fault inspection, and
   circuit-derived-graph coverage rendering. Every value comes from
   the backend (directive §42: no scientific calculation in
   TypeScript). The schedule-comparison section prominently
   explains that "naive = optimized" is the implemented finding,
   not a UI simplification.

**Rejected alternatives.** (a) A different stabilizer-measurement
template (e.g. Shor-style cat states, or a doubled CNOT schedule) —
out of scope: the milestone is about adding FAULT-AWARENESS to the
existing circuit, not redesigning the circuit. (b) Treating the
graph itself as the decoder (replacing the phenomenological MWPM) —
rejected: directive §41, §42 explicitly preserve decoder semantics
and the graph is a structural diagnostic, not a replacement. (c)
Sub-1e-3 floating-point probability combinations in the graph
weights — rejected: the integer-quantized 1e-6 LLR convention
(AD-016) is reused for determinism and to integrate with the
existing matcher.

## AD-019 — Circuit-aware hybrid decoder with multi-event attribution (milestone 13)

**Decision.** The circuit-derived graph (AD-018) is promoted from
structural metadata to an actively consulted decoder component via
a hybrid architecture (directive §5, §7, §9, §23, §37).

1. **Hybrid candidate generation.** For each (d, R, noise)
   configuration the decoder produces TWO candidate corrections:
   - CANDIDATE 1 (phenomenological, AD-016): the existing
     `decode_repeated` with the standard phenomenological noise
     parameters. The full temporal chain reconstruction is
     preserved.
   - CANDIDATE 2 (circuit-derived): the SAME `decode_repeated`
     chain reconstruction, but with `p_data` and `p_measurement`
     derived from the circuit-level fault-catalogue graph
     (the per-event rate that corresponds to the actual fault
     propagation in the stabilizer-measurement circuits).
   This reuses the existing matcher (the temporal + final-residual
   2-stage decoder) and only varies the noise model input. The
   architecture is minimally invasive.

2. **Multi-event post-processing.** The decoder enumerates
   ≥3-event single-fault mechanisms from the catalogue. For
   each whose event set is a SUBSET of the observed events, the
   proposed data-side hook is offered as a candidate correction.
   Acceptance is CONSERVATIVE: only weight-1 hooks (canonical
   hook pattern) are accepted, and only if the proposed
   correction REMOVES a logical failure. This avoids
   over-aggressive attributions that would degrade p_L.

3. **Candidate selection.** The decoder picks the candidate
   with the lowest (matching_weight, number-of-logical-
   failures) score. The `best_source` field records which
   candidate won (transparent attribution; the user can
   inspect whether the circuit-derived candidate was preferred
   or not).

4. **The circuit-derived graph is REAL, not metadata.** The
   `p_data` / `p_measurement` for CANDIDATE 2 are sourced from
   the graph's actual mechanism probabilities (not
   re-invented). When the v1 hybrid's cir candidate is
   selected, the decoder is genuinely using the circuit-derived
   information; the previous milestone's `circuit_graph_decoder`
   was strictly metadata.

5. **Performance.** The graph is precomputed once per (d, R,
   noise) configuration (deterministic, cached). Each trial
   uses the precomputed pair-edge + exit-edge weights to run
   the matcher; the per-trial cost is dominated by the matcher
   itself (unchanged from `decode_repeated`).

6. **Honest limitations.** The v1 hybrid shares the temporal
   chain reconstruction with the phenomenological MWPM. Distance
   suppression is NOT observed at d=3, 5, 7 with the current
   circuit (documented in SCIENTIFIC_MODELS). The Wilson CIs
   of the two decoders overlap substantially at every tested
   (regime, distance) cell; the decoder is competitive but not
   strictly superior to the phenomenological MWPM at every point.

**Rejected alternatives.** (a) A standalone circuit-level decoder
with its own temporal chain logic — would duplicate the matcher
(directive §7). (b) Multi-event mechanism EXCLUSION without
attribution (Approach A in the previous milestone) — gives up
the information that the decoder could use. (c) A heavier
hypergraph decoder — out of scope for the current architecture
and unnecessary given that the v1 hybrid is competitive.


## AD-020 — Lattice-wide temporal interleaving for circuit-level QEC (milestone 15)

**Decision.** Add a round-level temporal interleaving mode to the
circuit-level stabilizer-measurement simulator. In alternating mode,
X-checks are measured in odd rounds and Z-checks in even rounds (or
vice versa). The unmeasured family's syndrome is carried forward
(its value is the same as the previous round) and contributes 0
detection events.

1. **Round semantics.** A "round" is a single layer of stabilizer
   measurements. Under the standard mode ("none"), every round
   measures all X and Z checks. Under the alternating mode, every
   round measures only ONE stabilizer family; the OTHER family's
   syndrome is carried forward.

2. **Carry-forward semantics.** The unmeasured family's syndrome
   value at round t equals its value at round t-1. The measured
   family's syndrome is computed normally. This is EXPLICIT
   observation semantics, not "unmeasured = zero" (which would
   introduce a silent error mode). The carry-forward is implemented
   in `simulate_circuit_level` (the simulator), not in the
   decoder; the decoder's `decode_repeated` correctly handles the
   carried-forward syndrome (its syndrome-difference construction
   gives 0 detection events for the carry-forward family).

3. **Empirical findings (milestone 15).** Under the same (d, R,
   noise) configuration with the same seed stream:
   - Gate-only d=3: standard 15.0% → alternating 9.8% (-5.2pp)
   - Gate-only d=5: standard 33.0% → alternating 22.5% (-10.5pp)
   - Gate-only d=7: standard 44.2% → alternating 41.6% (-2.6pp)
   The improvement is real at every (d, regime) cell tested. The
   forensic shows alternating reduces data-hook reports by ~49%
   (the unmeasured family's events are carried forward as 0).

4. **Distance suppression is NOT recovered.** At every tested
   noise regime, p_L(d=5) > p_L(d=3) under both standard AND
   alternating. The alternating schedule improves absolute p_L
   but does not change the underlying scaling. The hook error
   structural problem is unchanged.

5. **Decoder compatibility.** `decode_repeated` is reused
   unchanged. The 2-stage temporal + final-residual decoder
   correctly handles the carry-forward: syndrome differences
   for the unmeasured family are 0, so no spurious detection
   events are generated for it.

6. **Honest limitations.** Alternating reduces measurement
   density by 50% (one family is not measured per round). This
   may be acceptable for the phenomenological MWPM (which uses
   the carried-forward syndromes correctly) but could affect
   more sophisticated decoders that rely on dense temporal
   information.

7. **Trade-off territory.** The alternating schedule trades
   measurement density for better decoding on the measured
   family. The improvement comes from cleaner syndrome history,
   NOT from a fundamentally safer circuit. The H-CNOT-H circuit
   is unchanged.

**Rejected alternatives.** (a) Shor cat-state extraction (4
ancillas per stabilizer) — requires multi-ancilla architecture,
deferred. (b) Per-stabilizer schedule permutation — provably
degenerate under H-CNOT-H (AD-018, AD-019). (c) 3-cycle temporal
interleaving (X, Y, Z per round) — Y is not measured in CSS
surface codes; not applicable.


## AD-021 — Shor cat-state extraction: implemented, honestly measured, NOT recommended (milestone 17)

**Decision.** The extraction registry gains a second, genuinely
multi-ancilla template: `shor_cat_state`. For a weight-k check it
prepares k ancillas in a GHZ cat state (H on a_0, CNOT fan-out),
couples each ancilla to exactly ONE data qubit, measures all k
ancillas, and defines the stabilizer outcome as the parity of the
k measurement bits. Odd-weight supports are rejected loudly (the
random GHZ measurement offset cancels only in the even-k parity;
all rotated-code supports are weight 2 or 4). X-checks add an H
layer before and after the data coupling (Z-GHZ -> X-GHZ -> Z
basis). The construction was selected for measurement because the
cleanup report identified hook-error confinement as the open
scientific question; it is NOT adopted as a default and no
existing behavior changes (the default remains
`baseline_h_cnot_h`).

**Circuit conventions** (all validated against the algebraic
syndrome oracle — `RotatedSurfaceCodeDecoder.syndrome` — for every
single-qubit data error at d=3 and d=5, 102 cases, 0 mismatches):
CNOT frame rules identical to the baseline routine; H layers are
frame swaps; the Z-basis outcome of an ancilla flips iff its frame
carries an X component; reset/prep noise fires per ancilla; every
CNOT (fan-out AND data coupling) takes gate noise on both
participants; readout noise is an independent per-ancilla bit flip
before the parity; H gates remain IDEAL (the existing documented
contract).

**Validation evidence (all deterministic, in
`tests/test_shor_extraction.py`):**

1. *Ideal correctness* — noiseless Shor syndrome equals the
   algebraic syndrome for every single-qubit error, d = 3, 5.
2. *Exhaustive single-fault enumeration* (408 faults at d=3, 1376
   at d=5, driven through the PRODUCTION routine via a
   deterministic `forced_faults` harness — the oracle is not a
   second implementation of the circuit):
   - the baseline's dominant failure mode (one ancilla fault
     hooking to the FULL support, weight 4) is IMPOSSIBLE under
     Shor extraction;
   - the honest worst case is weight **2**, not the textbook
     weight-1: a Y fault on ancilla a_1 back-propagates its Z
     component through the fan-out to a_0 (target-Z -> control
     rule); after the H layers both a_0's and a_1's X components
     hook to two different data qubits. UNVERIFIED Shor extraction
     does not achieve weight-1 confinement — cat-state
     verification (an extra ancilla measuring the cat's parity
     before coupling) is the identified missing ingredient and the
     concrete next step;
   - readout faults NEVER produce data errors (pure syndrome
     errors — the data/measurement fault separation the repeated-
     round decoder relies on);
   - a fault injected for one check never leaks into another
     check's circuit;
   - unreachable forced faults fail loudly.
3. *Genuine-cat signature* — a Z fault on a_0 immediately after
   reset is completely benign (no data error, no hook, no syndrome
   flip): it is equivalent to the all-legs-X stabilizer of the GHZ.
   A degenerate product-state scheme would flip one measurement
   bit here, so this test proves the cat state is real (this
   mattered: an implementation bug that omitted the initial H(a_0)
   silently produced the product-state scheme, which passes the
   ideal-syndrome oracle — only this signature test and the
   exhaustive enumeration distinguish the two).

**Measured result: Shor extraction is NOT an improvement under
this noise model and decoder.** Monte Carlo (2000 trials/point,
rounds 4, Wilson 95% CIs, seeds 11/23):

| regime        | d=3 baseline | d=3 Shor  | d=5 baseline | d=5 Shor |
|---------------|--------------|-----------|--------------|----------|
| gate-only     | 14.30%       | 21.40%    | 32.05%       | 44.65%   |
| readout-only  | 0.00%        | 0.00%     | 0.00%        | 0.00%    |
| reset-only    | 0.00%        | 0.70%     | 0.00%        | 0.20%    |
| prep-only     | 0.00%        | 4.05%     | 0.00%        | 1.25%    |
| combined-mid  | 14.10%       | 28.50%    | 28.35%       | 42.45%   |
| combined-low  | 2.85%        | 5.65%     | 7.45%        | 9.95%    |

Every non-zero regime shows Shor significantly WORSE (non-
overlapping CIs). The mechanism is measured, not speculative:
(1) gate exposure roughly doubles (2k-1 CNOTs vs k); reset/prep/
readout exposure scales k-fold; (2) the phenomenological MWPM
decoder cannot exploit hook confinement — it decodes the same
syndrome history with the same spatial/temporal edges, so the
weight-4-to-2 improvement buys nothing while the extra noise
costs p_L directly. Per-channel nuance: baseline prep faults on
X-checks propagate the check's own stabilizer (benign), whereas
Shor prep faults land on cat ancillas and produce genuine weight-
1/2 data errors — hence prep-only 0% vs 4.05%.

Distance behavior: p_L(d=5) > p_L(d=3) for BOTH extractions in
every regime with non-zero failures — no distance suppression for
either, unchanged from AD-018/AD-019/AD-020 conclusions.

**Performance** (measured, d=3, 4 rounds): baseline ~0.49 ms/trial,
Shor ~1.26 ms/trial (~2.6x) at 2000 trials; d=5 ~1.44 vs ~3.94 ms.

**Rejected alternatives.** (a) Adopting Shor as the default —
prohibited by the measured result; the default is unchanged.
(b) Adding cat-state verification in the same milestone — the
verified construction needs an extra measured ancilla and a
reject/retry (or flag) semantics that changes the Monte Carlo
outcome space; deferred as the concrete follow-on with a precise
prediction to test (restores weight-1 confinement at the cost of
k+1 ancillas plus verification-gate noise). (c) Implementing the
Shor circuit inside `fault_catalogue`'s enumeration — the
catalogue is baseline-specific; the `forced_faults` harness is
the honest equivalent for multi-ancilla circuits.

**Scope.** `circuit_extraction.py` (+ Shor model, measure routine,
forced-fault harness), `circuit_level.py` (single dispatch point
`_run_check_measurement`, `forced_faults` round-1 test parameter,
`extraction_model` on the MC entry point), API `extraction_model`
on the two circuit-level endpoints (default = legacy behavior;
invalid modes rejected by schema), experiment runner
`extraction_model` config (validated, echoed in provenance),
QecLab extraction selector with the measured caveat rendered
from the AD.
