# QuantumLab — Autonomous Session 2 Final Report

Date: 2026-08-25 · Baseline: commit `397c91d` (239 tests) · Final: **369 tests**

## Executive summary

Session 2 transformed QuantumLab from a validated collection of subsystems into
an integrated research platform. Five new scientific capabilities were added
with independent validation at every step; two latent correctness bugs in the
existing foundation were discovered by the new capabilities' stricter
validation requirements — exactly the integration effect the directive
targets (§249). The full suite grew 239 → 369 tests; all prior functionality
remains intact.

## Starting state

239 passing tests; quantum core, circuit engine, algorithms, QEC, network
engine, protocols, VQE/QAOA/QML, experiment framework (SQLite + threaded jobs +
WebSocket), FastAPI layer, React workspace. Services verified healthy before
any change (RULE 1).

## Features added

| Capability | Module | Status |
|------------|--------|--------|
| Quantum information suite (18 measures incl. Rényi/min-entropy, relative entropy, concurrence, negativity, Schmidt) | app.quantum.info_theory | IMPLEMENTED + VALIDATED |
| Channel algebra: Choi matrix, CP/TP validation, composition/tensor identities, process fidelity | app.quantum.channel_algebra | IMPLEMENTED + VALIDATED |
| Generalized amplitude damping, readout confusion channel | app.quantum.channels/algebra | IMPLEMENTED + VALIDATED |
| Hardware profiles (4 labeled model presets), topology generators, SWAP-insertion transpiler with permutation verification | app.hardware | IMPLEMENTED + VALIDATED |
| Circuit analysis (depth/counts/T-accounting with honest None) | app.circuits.analysis | IMPLEMENTED + VALIDATED |
| Error mitigation: readout confusion mitigation, gate-folding ZNE, parity postselection | app.mitigation | IMPLEMENTED + VALIDATED |
| Entanglement purification: BBPSSW/DEJMPS exact recurrences, Monte Carlo schedules, engine integration | app.network.purification | IMPLEMENTED + VALIDATED |
| Repeater strategy framework (L0/L1/L2 studies) | app.network.repeaters | IMPLEMENTED + VALIDATED |
| Loss-aware network BB84 (+dark counts, secret-fraction estimate) | app.protocols.network_bb84 | IMPLEMENTED + VALIDATED |
| Distributed remote CNOT via double teleportation | app.distributed | IMPLEMENTED + VALIDATED |
| Reproducibility service (reproduce + comparison classification) | app.experiments.reproducibility | IMPLEMENTED + VALIDATED |
| Provenance-rich CSV export | ExperimentService.export_run_csv | IMPLEMENTED |
| Statistics subsystem (SEM CI, seeded bootstrap, Wilson) | app.analytics.statistics | IMPLEMENTED + VALIDATED |
| New API endpoints (quantum-info, hardware×2, analyze, mitigation×2, reproduce, export.csv) | app.api | IMPLEMENTED |

## Correctness bugs found & fixed (all regression-covered)

1. **Partial-trace output ordering** (`DensityMatrix.partial_trace`): for
   len(keep) ≥ 2, interleaved row/col output letters axis-mixed reduced states.
   Diagonal marginals (GHZ tests) masked it; off-diagonal validation from
   distributed-CNOT work exposed it. Fixed: row letters then column letters.
2. **Teleportation correction order**: corrections must apply X before Z;
   wrong order is invisible (global phase) until the teleported wire enters
   entangling operations. Caught by distributed CNOT truth-table test.
3. Benchmark circuit missing classical registers (test infrastructure).
4. ZNE driver evaluated single trajectories instead of expectations.
5. GAD weighting convention inverted (N=0 must equal cold bath).
6. Choi partial-trace-over-output summed only diagonal blocks.
7. Three undefined-name lint issues (StateVector/np/build_gate).

## Scientific validation performed

- Analytic-value tests: Rényi/von Neumann/min-entropy on canonical states,
  Werner concurrence formula, DEJMPS ⅝ at F=½, BBPSSW fixed points.
- Identity verifications: folding preserves unitary action; channel composition
  E₂(E₁(X))=(E₂∘E₁)(X); tensor identity on product operators; mapped-circuit
  equals logical circuit under permutation (dense scatter check).
- End-to-end: ZNE improves noisy ⟨ZZ⟩ 0.9216 → 0.9696 toward ideal 1.0;
  remote CNOT matches centralized execution bit-for-bit on basis states and to
  <1e−8 fidelity on superpositions.
- Final API sweep: **14/14** scientific checks passed against the running
  service (including reproduce-run and provenance CSV over HTTP).

## Performance

Measured (this machine): shot fast path ~6.8M shots/s; QFT-18q ~3.1 s;
density GHZ-8 ~22 ms; network ~80k events/s (session-1 reference retained).
No regressions observed; new subsystems are eigendecomposition/SVD-bound and
bounded by documented qubit caps.

## Known limitations

See LIMITATIONS.md (extended this session). Notable new entries: diamond norm
not implemented; readout mitigation ≤8 qubits tensor-product confusion; greedy
(not optimal) SWAP routing; purification requires identical input fidelities;
distributed computing implements only the double-teleportation remote CNOT.

## Architecture decisions

Documented in ARCHITECTURE_DECISIONS.md (AD-001…AD-008), including two
bug-driven decisions elevated to permanent policy: partial-trace output
ordering (AD-003) and teleportation correction order (AD-004).

## Recommended next steps

1. Frontend labs consuming new endpoints (Information Theory Lab, Hardware Lab,
   mitigation panels in Circuit Studio, purification controls in Network
   Studio) — backend contracts are stable and documented.
2. Single-ebit remote-CNOT optimization; multi-node circuit partitioner.
3. MWPM decoder interface for the surface code; planar rotated layout.
4. Process-isolated job workers with checkpoint/resume for long Monte Carlo.
5. Playwright UI smoke suite wired into dev scripts.
6. Student-t quantiles if scipy dependency ever becomes acceptable.
