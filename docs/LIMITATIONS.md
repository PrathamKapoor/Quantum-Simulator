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
