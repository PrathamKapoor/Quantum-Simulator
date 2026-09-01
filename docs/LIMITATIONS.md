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
