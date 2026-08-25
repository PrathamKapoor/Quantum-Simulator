# Changelog

All meaningful milestones. Format: informal per-session entries with module scope.

## 0.1.0 — Session 1 (2026-08-25)

### Quantum core
- StateVector with explicit normalization policy, exact marginals (vectorized),
  tensor products, seeded sampling primitives.
- Gate library: I X Y Z H S S† T T† Rx Ry Rz U3 P, CX CZ SWAP CRx CRy CRz CU3 RZZ,
  Toffoli, Fredkin; unitarity-validated custom gates.
- Density matrices: partial trace (order-preserving), Uhlmann fidelity, purity,
  von Neumann entropy (bits/nats), Bloch vectors, trace distance.
- Kraus channel framework with TP validation: bit/phase/bit-phase flip,
  depolarizing, amplitude damping, phase damping, T1/T2 thermal relaxation,
  composite channels.

### Circuit engine
- Versioned serialization (`quantumlab.circuit` v1) with strict version rejection.
- Structured multi-issue validation (codes + suggestions).
- Statevector executor: mid-circuit measurement, classical conditioning,
  deterministic reset, exact multinomial shot fast path, Kraus trajectory noise.
- Density-matrix engine (≤ 12 qubits) with exact channel application.

### Algorithms
- Deutsch, Deutsch–Jozsa, Bernstein–Vazirani, Simon (with GF(2) post-processing),
  Grover (per-iteration probability curves), QFT/inverse QFT (DFT-verified),
  approximate QFT that flags itself, phase estimation, bounded Shor order
  finding (N ≤ 32) with continued fractions, teleportation, superdense coding,
  discrete quantum walk vs classical baseline.

### Noise / hardware foundations
- Explicit noise-model configs and presets; readout confusion channel.

### QEC subsystem
- Stabilizer algebra; bit-flip-3, phase-flip-3, Shor-9, Steane-7, five-qubit codes
  with construction-time structural verification; verified lookup decoders;
  Monte Carlo sweeps with Wilson CIs; toric surface-code educational simulator
  with visualization layout data.

### Network engine (flagship)
- Discrete-event simulation with logical clock, bounded traces (full/summary/sampled).
- Topology graph, five routing strategies with explanations, FIFO/priority/deadline
  schedulers, memory service with decay/expiry, Werner-model swapping, chaos
  injection, fairness metrics, deterministic seeded runs.

### Protocols
- BB84 (+ intercept-resend Eve), E91 with CHSH estimation, simulated QRNG with
  runs test, CHSH/Bell laboratory, information-theory metrics.

### Optimization & QML
- Pauli-sum Hamiltonians; H2 effective model; TFIM reference; VQE (SPSA +
  coordinate-descent polish); QAOA MaxCut vs brute force; H2 dissociation curve;
  variational classifier with noisy comparison; fidelity-kernel experiment;
  CSV dataset validation with actionable errors.

### Experiments & persistence
- SQLite storage with numbered migrations; experiment/run separation; sweep
  expansion; result documents (versioned schema); run comparison; audit trail;
  threaded job queue with cooperative cancellation and WebSocket progress.

### API layer
- FastAPI app: validated endpoints for every lab; structured errors; health/
  diagnostics checks (database, quantum engine, network engine, worker);
  WebSocket job progress; static documentation serving.

### Frontend
- React + TypeScript workspace: Dashboard, Circuit Studio, Algorithms, Network
  Studio (interactive canvas), QEC Lab, Cryptography, Optimization & QML,
  Experiments with live progress, Documentation viewer; dark/light themes;
  dependency-free SVG charts.

### Tests
- 230 fast tests green covering all modules including integration flows.
