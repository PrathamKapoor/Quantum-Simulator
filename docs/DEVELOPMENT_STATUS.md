# QuantumLab — Development Status

> **Purpose:** Persistent checkpoint for autonomous development. Any session resuming
> work MUST read this file first, then ROADMAP.md, ARCHITECTURE.md,
> SCIENTIFIC_MODELS.md, LIMITATIONS.md (directive §320).
>
> Last updated: 2026-08-26 (session 3 final checkpoint)

## Current state

**Integrated research platform with a genuine distributed-computing subsystem.**
Session 1: validated foundations. Session 2: quantum information suite, channel
algebra, hardware/transpiler, error mitigation, purification + network
integration, repeater studies, loss-aware BB84, distributed double-teleportation
remote CNOT, reproducibility/statistics/export, frontend labs.
Session 3: distributed subsystem — single-ebit remote CNOT (1 ebit + 2 cbits)
executed as genuine protocol circuits, multi-node circuit partitioner with
deterministic heuristic assignment, real network-engine ebit accounting,
distributed result schema, API endpoints, Circuit Studio distributed workflow.

Run it: `dev.bat backend` + `dev.bat frontend` → http://localhost:5173

## Tests & validation

- Fast suite: **419 passed** (~4 min) — 369 prior + 30 distributed + 20 earlier
  distributed/partition tests retained.
- Distributed equivalence: Uhlmann fidelity = 1.0 vs centralized on basis,
  superposition, Bell/GHZ inputs; both gate directions; 2/3/4 nodes; seeded
  randomized circuits ≤1e−8 per-outcome probability agreement.
- Frontend build clean (`tsc -b` + `npm run build`, 31 modules).
- Browser inspection NOT performed (no browser tooling available).

## Recently completed (session 2)

| Phase | Deliverable | Status |
|-------|-------------|--------|
| A | app.quantum.info_theory (18 measures) + /api/quantum-info/state-report | IMPLEMENTED+VALIDATED |
| B | Choi/composition/tensor/fidelity + GAD + readout channel | IMPLEMENTED+VALIDATED |
| C | HardwareProfile presets, SWAP-insertion transpiler (permutation-verified), circuit analysis | IMPLEMENTED+VALIDATED |
| D | Readout mitigation, folding ZNE (density-mode expectations), parity postselection + endpoints | IMPLEMENTED+VALIDATED |
| E | BBPSSW/DEJMPS purification (exact recurrences, exact resource accounting) + engine integration | IMPLEMENTED+VALIDATED |
| F | Repeater L0/L1/L2 studies; loss-aware network BB84 (+dark counts, secret fraction estimate) + runners | IMPLEMENTED+VALIDATED |
| G | Distributed remote CNOT (double teleportation), centralized-equivalence validated | IMPLEMENTED+VALIDATED |
| H | reproduce_run with comparison classification, provenance CSV export, statistics subsystem | IMPLEMENTED+VALIDATED |
| I/J | Mitigation/info/hardware/reproduce/export API endpoints; full documentation set | IMPLEMENTED |

Frontend labs for the new endpoints are PLANNED (backend contracts stable).
See docs/AUTONOMOUS_FINAL_REPORT.md and docs/AUTONOMOUS_SESSION_LOG.md.

## Correctness bugs fixed this session (all regression-covered)

1. partial_trace multi-qubit output ordering (latent; exposed by off-diagonal
   validation during remote-CNOT work)
2. teleportation correction order X-before-Z (phase-invisible in isolation;
   observable inside entangling circuits)
3. ZNE driver used trajectories instead of density-mode expectations
4. Choi TP-check block summation; GAD weighting convention
5. transpiler verifier permutation direction; benchmark circuit clbits
6. three undefined-name lint issues

## Key architectural decisions

AD-001…AD-008 in docs/ARCHITECTURE_DECISIONS.md (ordering conventions,
honest-refusal policies for purification/asymmetric inputs, guard-error
surfacing, no-dependency policy).

## Measured performance (unchanged from session 1 reference)

| Workload | Result |
|----------|--------|
| Shot sampling fast path | ~6.8M shots/s |
| QFT-18q evolution | ~3.1 s |
| Density GHZ-8 | ~22 ms |
| Network events | ~80k/s |

## Next priorities

1. Experiment-engine integration for distributed runs (runner registration +
   persistence of distributed-result documents; reproducibility hooks exist in
   the result schema already).
2. Noisy-ebit injection: map network grant fidelity into the protocol circuit
   (Werner-form ebit preparation) instead of reporting it separately.
3. MWPM decoder + planar surface-code layout.
4. Process-isolated workers with checkpoint/resume.
5. Playwright UI smoke tests (would also close the visual-inspection gap).
