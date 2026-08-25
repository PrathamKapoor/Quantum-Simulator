# QuantumLab — Development Status

> **Purpose:** Persistent checkpoint for autonomous development. Any session resuming
> work MUST read this file first, then ROADMAP.md, ARCHITECTURE.md,
> SCIENTIFIC_MODELS.md, LIMITATIONS.md (directive §320).
>
> Last updated: 2026-08-25 (session 1, checkpoint 3)

## Current phase

Phase 7 — Full stack operational: quantum core, circuit engine, algorithms, noise,
QEC, network engine, protocols, optimization/QML, experiments+persistence+workers,
FastAPI layer, React frontend. Extended idle-time validation running.

**The application is runnable end-to-end**: start the API (`dev.bat backend`) and
frontend (`dev.bat frontend`), open http://localhost:5173.

## Completed modules (all tested)

| Module | Contents | Tests |
|--------|----------|-------|
| app.quantum | states, gates, density matrices, channels, observables, measurement | test_quantum_core |
| app.circuits | model, validation, serialization v1, statevector + density executors | test_circuits |
| app.noise | NoiseModel configs/presets, readout error | (via circuits) |
| app.algorithms | DJ/BV/Simon/Grover/QFT±/QPE/order-finding/superdense/walk | test_algorithms |
| app.qec | stabilizer algebra, 5 codes + toric code, lookup decoders, MC benchmarks | test_qec |
| app.network | event engine, topology/routing/explanations, memory, scheduler, chaos | test_network |
| app.protocols | BB84/E91/QRNG/CHSH/info-theory | test_protocols |
| app.optimization | Hamiltonians, VQE(+polish), QAOA, H2 curve, QML classifier/kernel | test_optimization |
| app.experiments | specs, runners registry, sweeps, service lifecycle | test_experiments |
| app.persistence | SQLite migrations v1-v2, audit trail | test_experiments |
| app.workers | threaded job queue, cooperative cancellation | test_experiments |
| app.api | validated endpoints, health/diagnostics, WebSocket progress | test_api |
| frontend | Dashboard/Circuit/Algorithms/Network/QEC/Crypto/Optimize/Experiments/Docs | manual + build |

## Test status

- Fast suite: **230 passed** (~75 s): `dev.bat test` or
  `cd backend && ..\.venv\Scripts\python -m pytest tests --timeout=300`
- Endpoint smoke: **26/26 passed** across every UI-critical route.
- Extended validation (`-m extended`): running during idle time — Shor-9 trend
  over 20k trials/point, BB84 Eve-linearity, CHSH-vs-fidelity line, repeater
  success vs time budget.

## Runtime status

- API: uvicorn :8000 — healthy; docs proxy `/repo-docs` verified via Vite.
- Frontend: Vite dev server :5173 — serves; production build clean (`tsc -b` +
  `vite build`).

## Key architectural decisions (binding)

1. Little-endian qubit ordering platform-wide.
2. Gate-local basis = first operand MSB; `app/algorithms/conventions.py`
   converts truth-table-indexed matrices (REQUIRED when building oracles).
3. shots=None statevector mode: pre-measurement state unless results are used.
4. Shot fast path: single evolution + exact multinomial sampling.
5. Statevector noise = per-shot Kraus trajectories; density mode = exact CPTP.
6. Network requests track segment coverage; swaps merge coverage spans;
   at most one in-flight attempt chain per segment.
7. Engine-level exception guard records errors into `result.engine_errors`
   (never silent).

## Bugs found & fixed this session (regression-covered)

(see previous checkpoint list, plus:)
| Bug | Fix |
|-----|-----|
| `swap_classical_latency_ns` missing import silently swallowed by run-loop guard | import added; guard now surfaces errors in `engine_errors` |
| duplicate parallel attempt chains per segment | `pending_segments` bookkeeping |
| toric star operators used wrong incident edges | corrected incidence (verified commutation + distance) |
| phase-flip-3 logicals misassigned | derived from encoding; structural checks enforce |
| CSV header-skip inverted | fixed + actionable-error ordering |

## Next recommended tasks

1. Check extended-validation output when it finishes; investigate any trend failures.
2. UI E2E automation (Playwright) — currently manual inspection only.
3. Process-isolated workers; run checkpoint/resume for long jobs (§100).
4. Planar rotated surface-code layout + MWPM decoder interface.
5. Entanglement purification protocol implementation (interface refuses to fake).
6. Experiment templates gallery wired into frontend creation dialog.
7. Performance: statevector gate batching; network engine priority-queue profiling.

## Known limitations

See LIMITATIONS.md. Highlights: statevector ≤ ~24q practical / density ≤ 12 /
Grover ≤ 10q dense oracle / bounded Shor N ≤ 32 / surface code weight-1 decoder /
idealized-channel QKD sims / no physical entropy from QRNG.
