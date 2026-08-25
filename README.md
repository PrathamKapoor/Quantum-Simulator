# QuantumLab

An integrated **quantum computing, quantum information, and quantum networking
research laboratory**. One coherent platform on shared foundations:

- exact statevector & density-matrix circuit simulation (mid-circuit measurement,
  classical conditioning, noise channels),
- the standard algorithm suite (Grover, QFT, phase estimation, bounded Shor,
  teleportation, …) verified against independent references,
- error-correction experiments (repetition, Shor, Steane, 5-qubit codes; toric
  surface-code educational model) with Monte Carlo logical-error sweeps,
- a discrete-event **quantum network simulator** (flagship): lossy links, Werner
  swapping, memory decay, routing strategies with explanations, schedulers,
  chaos injection,
- protocol simulators (BB84, E91, CHSH, simulated QRNG), information theory,
  VQE / QAOA / H2 / QML with classical baselines,
- a reproducible experiment framework: parameter sweeps, SQLite persistence with
  versioned migrations, background job queue with live WebSocket progress.

## Scientific integrity statement

Every number in QuantumLab comes from real computation. Simulations are labeled
as simulations, approximations are documented where they are made, stochastic
outputs always carry seeds, and failures are reported as failures. Nothing is
fabricated to look finished. See [docs/SCIENTIFIC_MODELS.md](docs/SCIENTIFIC_MODELS.md)
for every formula and assumption, and [docs/LIMITATIONS.md](docs/LIMITATIONS.md)
for honest scope statements.

## Quick start

```bash
# backend (Python 3.11+)
python -m venv .venv
.venv\Scripts\python -m pip install fastapi "uvicorn[standard]" numpy scipy pydantic aiosqlite pytest pytest-timeout httpx
cd backend && ..\.venv\Scripts\python -m uvicorn app.api.main:app --port 8000

# frontend (Node 18+), second terminal
cd frontend && npm install && npm run dev
```

Open **http://localhost:5173**. Interactive API docs: http://127.0.0.1:8000/docs

## Repository layout

```
backend/app/quantum        states, operators/gates, density matrices, channels
backend/app/circuits       circuit model, validation, serialization, executors
backend/app/noise          explicit noise-model configs & presets
backend/app/algorithms     Deutsch…Shor, QFT, Grover, walks
backend/app/qec            stabilizer algebra, codes, benchmarks, surface code
backend/app/network        discrete-event engine, routing, scheduler, memory
backend/app/protocols      BB84, E91, CHSH, QRNG, information theory
backend/app/optimization   Hamiltonians, VQE, QAOA, H2, QML
backend/app/experiments    experiment specs, runners, sweep expansion
backend/app/persistence    SQLite + versioned migrations
backend/app/workers        threaded job queue
backend/app/api            FastAPI application layer
frontend/                  React + TypeScript workspace UI
docs/                      development status, roadmap, architecture, science…
```

## Documentation index

| File | Purpose |
|------|---------|
| [docs/DEVELOPMENT_STATUS.md](docs/DEVELOPMENT_STATUS.md) | where development stands; read first when resuming |
| [docs/ROADMAP.md](docs/ROADMAP.md) | prioritized backlog |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | services, data flow, boundaries |
| [docs/SCIENTIFIC_MODELS.md](docs/SCIENTIFIC_MODELS.md) | every formula + assumption |
| [docs/LIMITATIONS.md](docs/LIMITATIONS.md) | what the platform does NOT do |
| [docs/TESTING.md](docs/TESTING.md) | test categories and how to run |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | milestones |

## Testing

```bash
cd backend && ..\.venv\Scripts\python -m pytest tests --timeout=300
```
