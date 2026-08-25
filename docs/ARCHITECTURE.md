# QuantumLab — Architecture

Services, modules, dependencies, data flow, simulation flow, and experiment flow.
Updated when architecture changes (directive §216).

## Layer map

```
FRONTEND (React 19 + TypeScript, Vite dev server :5173)
   │  fetch/WebSocket
API LAYER (FastAPI :8000)
   ├── /api/circuits/*      validation + execution
   ├── /api/algorithms/*    algorithm runners
   ├── /api/protocols/*     BB84/E91/CHSH/QRNG
   ├── /api/qec/*           codes, sweeps, surface code
   ├── /api/network/*       simulate + route explanation
   ├── /api/optimize/*      VQE/QAOA/H2/QML
   ├── /api/experiments/*   CRUD, runs, results, comparison
   ├── /api/jobs + /ws/jobs queue status + live progress
   └── /repo-docs           documentation files (read-only)
        │
EXPERIMENT SERVICE ──── JOB QUEUE (daemon threads, cooperative cancel)
        │                       │ progress events via WebSocket broadcast
PERSISTENCE (SQLite, WAL) — schema_migrations + versioned JSON documents
        │
SIMULATION ORCHESTRATOR (app.experiments.runner RUNNER_REGISTRY)
   ├── quantum core      app.quantum.*      states, operators, channels, density
   ├── circuit engine    app.circuits.*     model, validate, serialize, simulate
   ├── noise models      app.noise.*        explicit channel configs + presets
   ├── algorithms        app.algorithms.*   DJ/BV/Simon/Grover/QFT/QPE/Shor/walk
   ├── QEC               app.qec.*          stabilizer algebra, codes, benchmark
   ├── network engine    app.network.*      event engine, topology, routing…
   ├── protocols         app.protocols.*    BB84/E91/CHSH/QRNG/info-theory
   └── optimization      app.optimization.* Hamiltonians/VQE/QAOA/H2/QML
```

## Domain boundaries (directive §13)

- Quantum core owns qubits/states/operators/gates/channels; nothing else defines
  matrix semantics.
- Noise engine owns stochastic error application; fidelity is never hand-edited
  after simulation.
- Network engine owns nodes/links/events/routing; protocols consume services,
  never graph internals directly.
- Experiment engine owns definitions/execution/seeds/results.
- Frontend owns presentation only; authoritative state lives in the backend.

## Data flow: a circuit execution

1. UI posts a `quantumlab.circuit` v1 document to `/api/circuits/execute`.
2. Pydantic schema checks shape/schema; `circuit_from_dict` parses with strict
   version rejection.
3. `validate_circuit` produces structured issues; execution aborts with codes.
4. `simulate()` dispatches by mode:
   - statevector: axis-based gate contraction (`apply_matrix_to_axes`);
     terminal-only measurements use the exact multinomial fast path; circuits
     that consume measurement results run one collapsed trajectory per shot;
     noisy gates sample Kraus operators (quantum trajectories).
   - density_matrix: exact `M ρ M†` and CPTP channel application (≤ 12 qubits).
5. Result document returns counts/probabilities/state summary.

## Simulation flow: the network engine

Event loop pops `(time_ns, seq)` from a heap priority queue. Handlers mutate
topology/memory/pair state and push follow-up events. Requests track segment
coverage: link pairs cover one route segment; idealized swaps merge adjacent
coverage spans (Werner parameters multiply). Completion fires when a pair covers
the whole span; teleportation adds classical delivery latency unless idealized
mode is selected. Chaos scheduling injects node/link failures from Poisson rates
(capped by `max_chaos_events`).

## Experiment flow

```
ExperimentSpec (JSON, validated)
   → create_runs_for_experiment → sweep expansion → runs (status CREATED)
   → job submission → worker thread → execute_run_now
        → runner(config, seed) → result document {schema, metrics, artifacts, notes}
   → results table + metrics on run row; failures recorded with error_code
```

Reproducibility contract: every stored run carries resolved config, seed,
backend, noise model label, code version; identical inputs reproduce identical
outputs bit-for-bit for all stochastic modules.

## Persistence schema (migration 1 & 2)

projects, experiments (versioned base_config), runs (resolved_config, seed,
status, progress, metrics), results (schema_name/version + payload JSON),
notes (user-authored), audit_log (create/run/fail events), saved_circuits /
saved_networks (versioned documents).
