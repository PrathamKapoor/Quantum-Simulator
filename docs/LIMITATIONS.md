# QuantumLab — Known Limitations

Never hidden; updated whenever a limitation changes (directive §220).

## Simulation scale limits

| Component | Limit | Reason |
|-----------|-------|--------|
| Statevector engine | ~24 qubits practical (hard ceiling 30) | 2^n complex amplitudes |
| Density-matrix engine | 12 qubits (enforced) | ρ has 4^n entries |
| Grover MCZ oracle | 10 qubits (enforced) | dense diagonal matrix |
| Bounded Shor order finding | N ≤ 32, total ≤ 16 qubits (enforced) | dense permutation oracle + controlled powers |
| QPE runner input states | computational-basis only | superposition prep needs explicit circuits |
| QML classifier | ≤ 6 feature qubits | statevector per-sample evaluation |

## Model simplifications (all documented in SCIENTIFIC_MODELS.md)

- BB84/E91/CHSH: ideal channels and detectors; no loss, no detector noise,
  no finite-key security analysis. Simulations, not certified protocols.
- QRNG: seeded PRNG stands in for device output — NO physical entropy.
- Network links: single-photon survival model (fiber attenuation × detector
  efficiency); no multiplexing, no wavelength modeling.
- Entanglement swapping: Werner-parameter multiplication assumes Werner-form
  pairs and idealized Bell-state measurements up to configurable success
  probability.
- Surface code: toric (periodic) layout — NOT the planar rotated code used in
  hardware proposals. Weight-1 lookup decoder underestimates true capability;
  results metadata states this.
- QEC benchmark: Pauli errors only, syndrome extraction algebraic (no
  measurement-circuit noise), no syndrome-measurement errors yet.
- H2 chemistry: fixed two-qubit effective Hamiltonian with interpolated
  coefficients; not electronic structure.
- Thermal relaxation: zero-temperature bath model.

## Engineering limitations

- Job queue is in-process threads: a hard crash of the server process loses
  running jobs (completed runs persist). Process isolation is future work.
- Cooperative cancellation only: cancellation takes effect at progress
  boundaries; short jobs may finish before observing the request.
- Routing `resource_aware` cost is not guaranteed monotone under path
  extension, so Dijkstra optimality can be approximate for that strategy alone.
- No authentication/multi-user support: local research application by design.
- Frontend E2E browser automation not yet wired into CI (manual verification
  performed during development).
- Custom gates are structured matrices only — user code execution is never
  permitted (deliberate security boundary, directive §209).

## Deferred features

See ROADMAP.md P9 section: stabilizer/tensor-network backends, tomography,
randomized benchmarking, MWPM decoding, entanglement purification protocol
(interface exists, raises NotImplementedError honestly), planar surface-code
layout, process-isolated workers.

# Session-2 additions

## Quantum information
- Concurrence strictly two-qubit (enforced); negativity PPT scope labeled per
  bipartition dimension.
- Quantum-info state reports bounded at 10 qubits via API.

## Channels / mitigation
- Diamond norms NOT implemented; only Choi-based CP/TP validation and process
  fidelity to a reference unitary are provided.
- Readout mitigation assumes tensor-product confusion; ≤ 8 qubits.
- ZNE limited to odd-integral global folding and polynomial fits; circuits
  containing measurements/resets cannot fold (clear error).
- Mitigated values can be less reliable than raw ones under ill-conditioned
  inversion — condition number and clipped mass always reported.

## Hardware / transpiler
- SWAP routing is greedy shortest-path, not depth-optimal.
- Dense mapping verification capped at 7 qubits.
- Model presets have no crosstalk/leakage/correlated noise.

## Purification / repeaters
- Protocols require identical input fidelities (asymmetric skipped honestly).
- One purification round per generated pair event in the network engine.
- DEJMPS modeled on symmetric Werner inputs; full Bell-diagonal input support
  is roadmap work.

## Distributed computing
- Remote-CNOT protocols implemented: single-ebit gate teleportation (1 ebit +
  2 cbits) and double teleportation (2 ebits + 4 cbits). Only CNOT-class
  2-qubit gates between exactly two nodes are executable remotely; gates
  spanning >2 nodes or acting on ≠2 qubits are flagged
  `requires_decomposition` and fail rather than degrade.
- Ideal local operations assumed inside the protocol. The network grant's
  fidelity is REPORTED but not injected into the statevector execution;
  layering a NoiseModel on the expanded circuit is the supported way to add
  noise (documented in SCIENTIFIC_MODELS.md).
- Partitioner objective is local-search (not globally optimal); explicit user
  mappings are honoured verbatim and never searched.
- Ebit grants are cached per node pair per request: repeated remote CNOTs on
  the same pair reuse one modelled generation run rather than re-simulating
  per gate.
- No hardware claims: this models distributed *protocols* over the existing
  simulator; modelled latency/loss come from the network engine's documented
  phenomenological models, not measurements.

## QKD over loss
- Dark counts modeled as uniform random registrations (no time windows).
- Secret-fraction figure is an asymptotic estimate, not finite-key security.

## Distributed experiment-runner integration
- Distributed runs execute in-process on the existing threaded worker; the
  engine executes atomically, so cancellation is guaranteed for QUEUED jobs,
  and RUNNING jobs finish unless they observe a progress-boundary cancel flag.
  Process isolation with checkpoint/resume is a separate roadmap item.
- Sweep values are floats by design of the existing framework; string-valued
  dimensions (e.g. protocol) cannot be swept without a framework change and are
  intentionally not engineered here.
- `distributed_circuit` runs use statevector mode with ideal local operations
  (the engine's documented model). Noisy ebits (AD-012) are supported via
  Werner-model injection with these boundaries:
  - The Werner model is phenomenological: it does not represent correlated
    noise, coherent errors, non-Markovian effects, or hardware-specific
    microscopic channels.
  - Production execution is trajectory-based: a single run realizes ONE pure
    Bell component (recorded in `remote_operations[].ebit_noise`); the Werner
    mixture emerges over seeds/repetitions. Single-run output probabilities
    are pure-component, not mixture averages.
  - Purification (BBPSSW/DEJMPS) cannot trigger through the NetworkBridge
    grant path: the network engine runs one in-flight generation chain per
    route segment, and purification requires two live pairs on one segment.
    Grants consumed by distributed runs are therefore unpurified; the
    purification subsystem remains available standalone.
  - The fidelity reported at request completion is the network engine's
    analytic link-base swap model (`expected_end_to_end_fidelity`); memory
    aging affects internal swap bookkeeping but not the reported grant
    fidelity. This engine boundary is pinned by a test so any future engine
    change flows through to the distributed protocol automatically.
  - Repeated remote CNOTs between the SAME node pair reuse one cached grant
    (existing bridge design): link quality is per node pair, while each
    consumed ebit receives an independent Werner realization.
  - `include_reduced_state` (exact logical density matrix in the result) is
    guarded to <= 6 logical qubits and off by default.
- The Experiments UI exposes a fixed "Distributed GHZ study" template plus full
  result inspection; a circuit editor inside the template is a listed next
  step.
- Empty nodes: an auto-assigned partition may leave a requested node unused
  (reported node_count reflects nodes actually hosting qubits).

## Rotated planar surface code + MWPM decoder

- **Code-capacity, perfect syndrome (§19, §40):** syndromes are computed from
  stabilizer algebra in a single perfect round. No circuit-level noise, no
  measurement errors, no fault-tolerant syndrome extraction; temporal
  (repeated-round) decoding is not implemented, though detection events carry
  a round field for future extension.
- **Independent Pauli data-qubit noise only:** depolarizing (I w.p. 1-p, else
  X/Y/Z equally), X-only, or Z-only. No correlated, coherent, or measurement
  noise.
- **Supported distances:** d = 3, 5, 7 (odd distances; even and other values
  are rejected, never rounded). Distances are independently verified by
  exhaustive per-component enumeration (the d = 7 verification enumerates
  ~100M supports and is the slowest validation test).
- **Matcher limits:** the exact MWPM DP carries a memo-state budget; if a
  pathological syndrome exceeded it, decoding fails loudly (DECODER_ERROR /
  runtime error in simulation) and is never reported as success. For the
  supported distances and error rates the guard is far out of reach.
- **MWPM is not the optimal decoder:** maximum-likelihood decoding would be
  more accurate; MWPM is the standard near-optimal benchmark. Degenerate
  equal-weight matchings are resolved deterministically (sorted indices,
  smallest exit first), which can in principle pick a logical-failing
  representative among physically equivalent corrections - inherent to MWPM,
  and detected by the residual classification rather than hidden.
- **Finite-size threshold studies (§39, §80):** bounded sweeps over
  (d, p, trials) produce logical-error curves with Wilson intervals. They are
  evidence of behaviour; no threshold value is claimed or derivable from the
  shipped defaults. The all-failures Wilson upper bound inherits the shared
  pipeline implementation's float quirk (1 - 1e-16 instead of exactly 1).
- **Error-correction context:** the rotated planar code is a simulator
  construct; no hardware, real-time decoding, or physical-threshold claims
  are made anywhere in the subsystem.

## Process-isolated experiment workers (AD-014)

- **Not a sandbox:** worker processes run with the same operating-system
  user rights as the API process. Fault containment is provided; security
  isolation is not. No hard CPU or memory quotas are enforced.
- **Startup overhead:** each experiment pays a Windows-spawn interpreter
  start (~0.4 s warm). Trivial experiments are slower than the former
  in-thread model; isolation was deliberately preferred over micro-latency.
- **No silent fallback:** if worker creation fails, the run is FAILED - the
  experiment is never silently executed inside the API process.
- **Shutdown:** shutting down the API terminates active worker processes;
  their runs are recorded FAILED (never COMPLETED). Results of completed
  runs are persisted before shutdown is requested by normal means.
- **Stale-run recovery:** RUNNING/CANCELLING rows orphaned by a previous
  crash become FAILED (INTERRUPTED_BY_RESTART) at next startup; QUEUED rows
  return to CREATED (the in-memory queue is volatile). This is implemented
  and tested - but it is recovery of bookkeeping, not checkpoint/resume.
- **Cancellation of RUNNING jobs is process termination:** partial results
  are discarded (never persisted); a run cancelled near completion may
  still complete if the result was accepted before the cancellation - the
  deterministic ordering is documented in AD-014.
- **Windows specifics:** spawn semantics are required (no fork); the worker
  entrypoint is module-level and import-safe; child results are flushed
  explicitly before exit to avoid IPC-feeder message loss.

## Browser validation (E2E milestone)

- **Chromium only, two viewports** (1440x900 desktop, 820px reduced width):
  no cross-browser, mobile-device, or WCAG certification is claimed.
- **Functional accessibility only:** semantic roles/labels and keyboard
  reachability of primary navigation and forms were exercised; a full
  accessibility audit was not performed.
- **No pixel-regression harness:** screenshots are manually inspected
  evidence, not automated visual diffs.
- **Windows webServer teardown:** Playwright does not reliably kill the
  npm.cmd -> node process tree; orphan dev servers are removed explicitly
  after runs (see AD-015). Test runs use `reuseExistingServer` so an already
  running dev stack is reused rather than duplicated.
- **Test database:** browser suites run against `e2e/e2e-test.db` (isolated
  via QUANTUMLAB_DB) and reset it at session start; the developer database
  is untouched.

## Repeated-round surface-code decoding

- **Phenomenological model only:** independent per-slot depolarizing data
  noise + independent per-round measurement flips. No circuit-level noise
  (ancilla preparation, gate, reset, correlated errors) is modeled; these
  are the next milestone (§45-§50).
- **Ideal final round:** the final syndrome is decoded assuming a perfect
  final measurement; a final-round measurement flip is indistinguishable
  from a final data error and is excluded by the model.
- **Two-stage decoder, not a single 3-D MWPM:** documented in SCIENTIFIC
  MODELS — it avoids the persistent-error double-counting artifact of the
  naive "differences + final clean column" construction, at the cost of
  splitting the decode into a temporal pass and a final single-shot pass.
- **Bounded scope:** rounds 1..64, distances 3/5/7; the matcher retains its
  capacity guard and fails loudly rather than running away.
- **Integer-quantized weights:** likelihood weights are rounded to 1e-6
  precision for the exact integer matcher (deterministic; not claimed
  optimal beyond the stated model).
- **No threshold / hardware claims:** distance and round trends are bounded
  evidence, not threshold estimates; the model is a simulator.

## Circuit-level surface-code simulation

- **Naive schedule, no distance suppression at d=3:** correlated hook errors
  (one ancilla fault -> 2..4 data qubits) exceed the distance-3 correction
  radius, so p_L(d=5) is not lower than p_L(d=3) in this model. This is a real
  physical property, reported, not a decoder defect.
- **Decoder is the phenomenological MWPM:** the circuit-generated detection
  events are decoded by the existing repeated-round MWPM (per the milestone's
  "do not duplicate decoding logic"). It is not the full circuit-level
  matching graph, so optimal decoding of general correlated hooks is not
  provided.
- **Ideal final-round readout** (and ideal single-qubit H gates): documented
  modeling choices so the final syndrome equals the net data syndrome.
- **Phenomenological noise channels only:** no coherent errors, no
  frequency/timing dependence, no hardware-realistic gate-level Pauli-twirled
  noise beyond the stated depolarizing channels.
- **Bounded scope:** rounds 1..64, distances 3/5/7; matcher capacity guard
  retained; no threshold/hardware claims.

## Fault-aware scheduling & circuit-derived decoder graph

- **Schedule is provably degenerate under the implemented circuit.** The
  H-CNOTs-H stabilizer-measurement template (the one implemented in the
  production simulator) produces the same single-fault risk profile for
  every permutation of a stabilizer's CNOT support. The optimizer
  therefore selects the naive schedule as optimal and
  `stabilizers_with_changed_schedule = 0` for every distance. This is
  a real, documented property of the model — not a UI simplification.
  A different circuit template (e.g. Shor-style cat states, a doubled
  schedule, or a different basis preparation) would expose a non-trivial
  selection; the optimizer is generic over the catalogue.
- **Production-simulator reset model is X-only.** The production
  simulator models reset noise as ancilla X (the ancilla starts as
  `|1>`). The catalogue enumerates Y/Z reset mechanisms as
  `p_reset_y_extension` / `p_reset_z_extension` with probability 0
  (documented model extensions, not in the production model).
- **Graph is structural, not a decoder.** The circuit-derived graph is
  reported as metadata alongside the phenomenological MWPM (which
  remains the logical-decoding engine). Multi-event mechanisms
  (≥3 detection events from a single fault) are excluded from the
  exact pair-edge model and reported as `coverage.excluded_ratio`
  (Approach A in the directive, §21).
- **Combination rule is small-probability union (Σ p_i).** For the
  low-noise regime this is accurate; under high noise the exact
  combination `1 − ∏(1 − p_i)` is more accurate but the deviation
  is below the integer-quantization precision (1e-6) at the documented
  noise levels.
- **No distance-suppression investigation is implied.** The
  schedule-optimization infrastructure is the foundation; whether
  distance suppression RECOVERS under a non-degenerate circuit
  template is the natural next milestone and is NOT claimed by
  this work.
- **Bounded scope:** rounds 1..64, distances 3/5/7; matcher capacity
  guard retained; no threshold/hardware claims.

## Shor cat-state extraction (AD-021)

- **Not an improvement under the implemented model (measured):**
  p_L is significantly worse than the baseline H-CNOT-H extraction
  in every non-zero noise regime tested (e.g. combined-mid d=3:
  28.5% vs 14.1%), because gate exposure roughly doubles (2k−1
  CNOTs vs k), reset/prep/readout exposure scales k-fold, and the
  phenomenological MWPM decoder cannot exploit hook confinement.
  The mode ships as a comparison alternative, NOT a default; the
  default is unchanged.
- **Unverified cat state: weight-1 confinement is NOT achieved.**
  The honest worst case is a weight-2 correlated data error
  (Y fault on cat ancilla a_1: Z back-propagates through the
  fan-out, both legs hook after the H layers). Canonical Shor
  extraction includes cat-state verification, which is not
  implemented; adding it is the identified follow-on with a
  falsifiable prediction (restores weight-1 at k+1 ancillas plus
  verification noise and flagged-shot semantics).
- **Even-weight supports only:** the stabilizer outcome is the
  parity of the k cat measurements, which cancels the random GHZ
  offset only for even k. Odd-weight supports are rejected loudly.
  All rotated-code supports (d=3,5,7) are weight 2 or 4, so no
  real configuration is affected.
- **H gates remain ideal** (including the cat-preparation H and
  the X-check H layers): the simulator has no H noise channel
  (pre-existing contract, unchanged). Real Shor FT analysis
  includes H faults; this model does not.
- **Preparation-noise convention differs from baseline:** Shor
  prep noise is per-ancilla, applied right after reset (before
  any H); baseline prep noise applies once, after its initial H.
  Both are documented; neither is silently conflated.
- Bounded scope: rounds 1..64, distances 3/5/7; no threshold or
  hardware claims; the ideal-final-round contract is unchanged.

## Verified Shor cat-state extraction (AD-022)

- **Does NOT achieve weight-1 confinement (measured).** Exhaustive
  production-path single-fault enumeration finds W_max_accepted
  (DANGEROUS = LOGICAL outcome) = 2, unchanged from unverified Shor;
  W_max_accepted (frame weight) = 4, but those weight-4 accepted
  errors are the check's own stabilizer (v-reset-X -> v-Z ->
  Z^tensor-k -> H-all -> X^tensor-support) and decode CORRECTED.
- **Verifier's own faults are real and partly harmful.** v-reset-X
  back-propagates Z onto every cat leg (accepted, frame-weight-4
  stabilizer); v-Z during a verification CNOT contaminates legs
  i..k-1 with Z (partial, caught only if it flips v's measured
  X-parity). These are exercised in the exhaustive enumeration; none
  are silently free.
- **Rejection semantics are flagged-round only** (no retry, no
  postselection). Rejected rounds retain their data errors and are
  counted unconditionally; the conditional p_L|accept is a diagnostic,
  never the reported headline rate. At d=5 the measured rejection
  rate is 94% (gate-only), which makes the no-retry construction
  operationally self-defeating there.
- **Single verifier only.** The remaining even-pattern weight-2
  accepted mechanisms require a second verifier (X-parity) to close;
  not implemented. The two-verifier variant is the documented
  falsifiable next experiment.
- **H gates ideal** (including the verification H, the cat-prep H,
  and the X-check H layers): no H noise channel in the simulator
  (pre-existing contract; unchanged).
- **Worse than baseline and unverified Shor in every measured regime
  (AD-022 table).** Not recommended as a default; the default
  extraction remains `baseline_h_cnot_h`.
- Bounded scope: rounds 1..64, distances 3/5/7; no threshold or
  hardware claims; ideal-final-round contract unchanged.

### Fitted pair-decomposed extraction (`fitted_pair`, AD-023)

- **Worse than baseline at d=3 in every regime.** At d=3, weight-2
  errors are undetectable, so capping ancilla fan-in at 2 buys nothing
  while the extra reset/prep/readout on weight-4 checks is pure cost.
  The mode is distance-specific: it only matches or beats baseline at
  d=5.
- **Prep-noise weakness.** Under prep-dominated noise fitted is far
  worse than baseline (3.01% vs 0.01% at p_prep=0.01, d=5): baseline
  prep faults hook the check's FULL support (stabilizer-equivalent,
  benign); fitted prep faults hook a 2-qubit partial support.
- **Combined-mid is a wash.** The gate-noise benefit and the
  prep-noise cost cancel (29.31% vs 29.22% at 200k trials/mode,
  overlapping CIs). Fitted is NOT a uniform improvement; it is a
  gate-noise-regime improvement.
- **The decoder cannot exploit the fan-in-2 structure.** The
  phenomenological MWPM receives only per-round check outcomes; the
  20 accepted-LOGICAL single faults at d=5 are mismatches a
  correlation-aware decoder would fix. Realizing the full structural
  benefit requires a circuit-derived matching graph (future work).
- **~1.8x wall-clock vs baseline** in the Python frame simulator
  (9.3 s vs 5.2 s per 2000 d=5 trials) despite identical CNOT count —
  interpreter overhead from 2x ancillas on weight-4 checks.
- **Ancilla readout noise doubles on weight-4 checks** (2 readout
  locations vs baseline's 1); the outcome bit is the XOR of two noisy
  sub-parity bits. Measured impact is small (readout-only p_L stays
  0.00-0.01%) but the exposure is real and counted in the cost model.

### Correlation-aware decoder (`correlation_aware`, AD-024)

- **Single-signature attribution.** Trials with TWO OR MORE
  simultaneous correlated faults are attributed at most once per
  decode; the residual re-decoding handles independent errors, but
  jointly-correlated multi-fault mechanisms are not enumerated
  (combinatorial; bounded by design).
- **Confusable-set degeneracy at d=3.** Syndromes that several
  equally-likely single faults explain identically cannot be
  disambiguated; the ML pick is wrong for the faults in the dearer
  buckets. Irreducible from the observed history (documented with an
  explicit 5-explanation example).
- **~2-6x decode time** vs the control (bounded by branch-and-bound
  at 8 residual decodes/trial). The signature DB is cached per
  (d, rounds, extraction) — a cold worker pays the build once
  (0.1-15 s).
- **Sub-parity conditioning** (opt-in) resolves within-check pair
  ambiguity only; it is OFF in production (measured negative).
- **First-order signature probabilities**: a signature produced by k
  alternative locations uses the sum of channel probabilities
  (exact up to O(p^2)).
- **d=7** is supported by the DB builder but was not exhaustively
  validated (DB build and enumeration cost); documented scope limit.
