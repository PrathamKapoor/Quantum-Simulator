# QuantumLab — Development Status

> **Purpose:** Persistent checkpoint for autonomous development. Any session resuming
> work MUST read this file first, then ROADMAP.md, ARCHITECTURE.md,
> SCIENTIFIC_MODELS.md, LIMITATIONS.md (directive §320).
>
> Last updated: 2026-08-26 (session 4 final checkpoint)

## Current state

**Integrated research platform with a first-class distributed experiment type.**
Session 1: validated foundations. Session 2: quantum information suite, channel
algebra, hardware/transpiler, error mitigation, purification + network
integration, repeater studies, loss-aware BB84, distributed double-teleportation
remote CNOT, reproducibility/statistics/export, frontend labs.
Session 3: distributed subsystem — single-ebit remote CNOT (1 ebit + 2 cbits)
executed as genuine protocol circuits, multi-node circuit partitioner,
real network-engine ebit accounting, distributed result schema, API endpoints,
Circuit Studio distributed workflow.
Session 4: **distributed experiment-runner integration** — `distributed_circuit`
is a first-class experiment module using the existing runner/lifecycle
(CREATED→QUEUED→RUNNING→COMPLETED, FAILED/CANCELLED), standard run-result
document wrapping the distributed-result v1 payload, seed handling /
reproduction / comparison / sweeps through the existing framework, and an
Experiments-UI workflow (template, distributed result view, reproduction).

Run it: `dev.bat backend` + `dev.bat frontend` → http://localhost:5173

## Tests & validation

- Fast suite: **437 passed** (~4 min).
  This session added: `test_distributed_experiment_runner.py` (16: unit config /
  topology / protocols / failure / fallback / lifecycle / failed semantics /
  reproduction immutability / sweep / comparison / cancellation) and extended
  `test_api_distributed.py` (create→execute→result and reproduce-immutable
  end-to-end via the experiment API).
- Distributed equivalence: Uhlmann fidelity = 1.0 vs centralized (reported in
  every experiment summary). Sweep machinery fixed: `expand_sweep` now seeds
  each combo from the base configuration (previously it silently dropped it).
- Resource accounting corrected: reported ebits/cbits now reflect the ACTUAL
  protocol (double teleportation reports 2 ebits + 4 cbits, not the partition
  estimate of 1); explicit centralized fallback emits a single local CNOT and
  records a warning instead of double-applying the protocol.
- Frontend build clean (`tsc -b` + `npm run build`, 31 modules).
- Browser inspection NOT performed (no browser tooling available).

## Session 4 — distributed experiment-runner integration

Lifecycle (existing infra, AD-011): create → runs (one per sweep combo, seed
`spec.seed + 7919*run_index`) → queue on the existing threaded JobQueue →
execute via `RUNNER_REGISTRY["distributed_circuit"]` → the standard
`quantumlab.run-result` v1 document stores resource metrics, an equivalence
summary, and the full `quantumlab.distributed-result` v1 payload under
`artifacts.distributed_result`. Distributed failures raise → run recorded
FAILED with error_code/error_message (never fabricated COMPLETED). Reproduction
creates a NEW run and compares documents (EXACT_MATCH); originals are
immutable. Comparison via existing `compare_runs` surfaces differing params and
per-run resource metrics. Sweeps use the existing float-based engine; the
engine-supported `num_nodes` (auto-assign) dimension is exposed, and the
base-config seeding bug was fixed. Cancellation follows the existing cooperative
model (queued jobs cancellable; in-process engine execution is atomic).

## Measured performance (session 3, this machine — simulation wall-clock)

Wall-clock runtime of the SIMULATION only. It is not modelled network latency
(reported separately per grant) and not hardware performance.

| Workload | Partition | Distributed exec | Centralized ref |
|----------|-----------|------------------|-----------------|
| 4q chain, 3 remote CNOTs (16-qubit expanded) | 0.05 ms | ~18 ms | ~1.1 ms |
| 6q chain, 5 remote CNOTs (16-qubit expanded) | 0.05 ms | ~380 ms | ~1.4 ms |
| 8q chain, 7 remote CNOTs (22-qubit expanded) | 0.06 ms | ~34 s | ~1.8 ms |

Overhead grows steeply with the expanded register because every protocol step
is executed with mid-circuit-measurement trajectory semantics (no fast path);
each single-ebit gate adds 2 carriers. This is simulator cost of genuine
protocol execution — the honest price of not faking distribution.

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

1. **Noisy ebit / Werner-entanglement injection**: map each network grant's
   fidelity into the protocol circuit (Werner-form ebit preparation) instead of
   reporting fidelity separately — the next intended scientific milestone.
2. MWPM decoder + planar surface-code layout.
3. Process-isolated workers with checkpoint/resume (would also make RUNNING
   cancellation interruptible rather than cooperative-at-queue).
4. Playwright UI smoke tests (would also close the visual-inspection gap).
5. Distribution-aware experiments in the Experiments UI: circuit editor inside
   the distributed template (currently a fixed GHZ template + generic config).
