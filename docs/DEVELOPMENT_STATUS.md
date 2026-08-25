# QuantumLab — Development Status

> **Purpose:** Persistent checkpoint for autonomous development. Any session resuming
> work MUST read this file first, then ROADMAP.md, ARCHITECTURE.md,
> SCIENTIFIC_MODELS.md, LIMITATIONS.md (directive §320).
>
> Last updated: 2026-08-25 (session 2 final checkpoint)

## Current state

**Integrated research platform, fully operational.**
Session 1 delivered the validated foundations. Session 2 added the quantum
information suite, channel algebra (Choi/composition/fidelity), hardware
profiles + transpiler + circuit analysis, error mitigation (readout/ZNE/
symmetry), entanglement purification (BBPSSW/DEJMPS) with network integration,
repeater strategy studies, loss-aware network BB84, distributed remote CNOT,
and the reproducibility/statistics/export layer of the experiment framework.

Run it: `dev.bat backend` + `dev.bat frontend` → http://localhost:5173

## Tests & validation

- Fast suite: **369 passed** (~3.7 min)
- Final API scientific sweep: **14/14 passed** against the running service
- Extended validation: 4/4 (`-m extended`)
- Frontend build clean; undefined-name lint count 0

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

1. Frontend labs for info-theory / hardware / mitigation endpoints.
2. Single-ebit remote CNOT; circuit partitioner.
3. MWPM decoder + planar surface-code layout.
4. Process-isolated workers with checkpoint/resume.
5. Playwright UI smoke tests.
