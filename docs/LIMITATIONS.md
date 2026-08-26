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
