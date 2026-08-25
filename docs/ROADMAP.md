# QuantumLab — Roadmap & Prioritized Backlog

Task states: NOT_STARTED / BLOCKED / IN_PROGRESS / IMPLEMENTED / TESTING / VALIDATED / COMPLETE / DEFERRED

Priority classes follow the master directive §9 (P0 broken foundations … P9 advanced optional).

## P1 — Core architecture / quantum foundation

| ID | Module | Description | Acceptance criteria | State |
|----|--------|-------------|---------------------|-------|
| CORE-001 | quantum | StateVector class: norm, normalize, inner product, fidelity (pure), tensor, probabilities | Unit tests incl. normalization policy explicitness | IN_PROGRESS |
| CORE-002 | quantum | Operator/gate library: I,X,Y,Z,H,S,S†,T,T†,Rx,Ry,Rz,U3,CX,CZ,SWAP,CRx,CRy,CRz,Toffoli,Fredkin + custom gates | Unitarity validation within tolerance; truth-table tests | NOT_STARTED |
| CORE-003 | quantum | DensityMatrix: trace/Hermiticity validation, partial trace, fidelity (mixed), purity, von Neumann entropy, Bloch vector | Bell/product partial-trace tests; entropy reference values | NOT_STARTED |
| CORE-004 | quantum | Kraus channel framework w/ trace preservation validation | TP validation test; depolarizing/damping channels round-trip | NOT_STARTED |
| CORE-005 | quantum | Measurement: probabilities, collapse, multi-qubit subsets | Statistical tests vs analytic probabilities (seeded) | NOT_STARTED |

## P1 — Circuit engine

| ID | Module | Description | Acceptance criteria | State |
|----|--------|-------------|---------------------|-------|
| CIRC-001 | circuits | Circuit/Operation model + structured validation errors | Validation rejects bad refs/dims/params with clear messages | NOT_STARTED |
| CIRC-002 | circuits | Versioned JSON serialization (schema v1) + round-trip tests | save→load→execute equivalence | NOT_STARTED |
| CIRC-003 | circuits | Statevector executor incl. mid-circuit measurement + classical conditioning | Teleportation-style conditional flow works | NOT_STARTED |
| CIRC-004 | circuits | Shot-based execution w/ seed, counts; fast path (no mid-measure ⇒ sample final distribution) | Seeded determinism test; statistical agreement with exact probs | NOT_STARTED |
| CIRC-005 | circuits | Density-matrix execution mode | Matches statevector on unitary-only circuits (fidelity ≈ 1) | NOT_STARTED |

## P2 — Scientific correctness (continuous)

Regression/reference suite REF-001: known values (H|0⟩, Bell correlations, GHZ, QFT of |1⟩, etc.).

## P3 — Flagship functionality

| ID | Module | Description | State |
|----|--------|-------------|-------|
| ALGO-001..010 | algorithms | Deutsch, DJ, BV, Simon, Grover, QFT/iQFT, phase estimation, teleportation, superdense, bounded Shor, quantum walk | NOT_STARTED |
| HW-001..003 | hardware | Data-driven backends, transpiler (routing/SWAP), optimizer passes | NOT_STARTED |
| QEC-001..005 | qec | Codes, encode/noise/syndrome/decode/recover pipeline, lookup decoder, Monte Carlo benchmark, surface-code educational model | NOT_STARTED |
| NET-001..012 | network | Event engine, clock, queue, topology/graph, nodes/links, memory service, entanglement generation/swapping/purification hook, routing strategies + explanation, scheduler, failures/chaos, resource accounting | NOT_STARTED |
| PROTO-001..006 | protocols | Network teleportation, entanglement distribution, BB84, E91, QRNG, CHSH/Bell lab | NOT_STARTED |
| INFO-001 | analytics | Information theory metrics (entropy, mutual information, trace distance) | NOT_STARTED |

## P4 — Integration

| ID | Module | Description | State |
|----|--------|-------------|-------|
| OPT-001..004 | optimization | Pauli Hamiltonians, VQE (+optimizers), QAOA MaxCut vs brute force, H2 pipeline | NOT_STARTED |
| QML-001..003 | optimization/qml | Angle encoding, variational classifier, quantum kernel/QSVM-style experiment | NOT_STARTED |
| EXP-001..006 | experiments | Experiment/run/result model, SQLite persistence + migrations, sweeps, Monte Carlo batching, Wilson CIs, background worker queue w/ progress + cancellation + checkpoints | NOT_STARTED |
| API-001..006 | api | FastAPI app, validated schemas, structured errors, WebSocket progress, health/diagnostics endpoints | NOT_STARTED |

## P7/P8 — UX, demos, polish

| ID | Module | Description | State |
|----|--------|-------------|-------|
| FE-001..010 | frontend | App shell, Circuit Studio, State panel, Algorithms pages, Network Studio, Experiments UI, results/plots, docs viewer, themes, command palette | NOT_STARTED |
| DEMO-001..010 | examples | Flagship demos (teleportation, repeater chain, BB84±Eve, QEC curve, QAOA, noisy-vs-ideal, network failure, QML, hardware awareness) | NOT_STARTED |

## Deferred / advanced (P9)

Stabilizer backend, tensor-network backend, tomography, randomized benchmarking,
Trotterized Hamiltonian simulation, quantum sensing/metrology, MWPM decoder,
purification studies, topology optimization, multi-objective routing weights UI.
