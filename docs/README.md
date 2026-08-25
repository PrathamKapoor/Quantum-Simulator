# QuantumLab

**QuantumLab** is an integrated quantum computing, quantum information, and quantum
networking research laboratory: a circuit simulator, an algorithm suite, a noise
laboratory, an error-correction bench, a discrete-event quantum network simulator,
a cryptography protocol sandbox, variational-algorithm tools, and a reproducible
experiment framework — one coherent platform on shared foundations.

## Scientific integrity statement

Every number, plot, and statistic in QuantumLab comes from real computation.
The platform never fabricates results; simulations are labeled as simulations;
approximations are documented where they are made; stochastic outputs always
carry their seeds; failures are reported as failures. Hardware profiles are
simulation configurations, not claims about real devices.

## Major features

- **Quantum core** — exact statevectors and density matrices, 25+ validated gates,
  partial trace, Uhlmann fidelity, purity, von Neumann entropy, Bloch vectors.
- **Circuit Studio** — visual circuit building with mid-circuit measurement,
  classical conditioning, reset, seeded shot statistics, density-matrix mode.
- **Noise lab** — depolarizing/bit-flip/phase-flip/amplitude-damping/
  phase-damping/T1-T2 thermal channels plus asymmetric readout error.
- **Algorithms** — Deutsch, Deutsch–Jozsa, Bernstein–Vazirani, Simon, Grover,
  QFT/inverse QFT (verified against the DFT matrix), phase estimation, bounded
  Shor order finding for N ≤ 32, teleportation, superdense coding, quantum walks.
- **Error correction** — bit-flip-3, phase-flip-3, Shor-9, Steane-7, five-qubit
  codes with verified lookup decoding, Monte Carlo logical-vs-physical sweeps
  with Wilson confidence intervals, and a toric surface-code educational model.
- **Network Studio (flagship)** — discrete-event quantum network simulation:
  entanglement generation over lossy links, Werner-model swapping, memory decay
  and expiration, five routing strategies with explanations, FIFO/priority/deadline
  schedulers, node/link chaos injection, fairness metrics, event timelines.
- **Protocols** — BB84 with intercept-resend Eve, E91 with CHSH estimation,
  simulated QRNG with statistical self-tests, CHSH/Bell laboratory,
  information-theory metrics.
- **Optimization & QML** — Pauli Hamiltonians, VQE (SPSA + coordinate-descent
  polish) against exact spectra, QAOA MaxCut versus brute force, an H2
  dissociation pipeline, a variational classifier, and a fidelity-kernel experiment.
- **Experiments** — experiment/run separation, parameter sweeps, SQLite persistence
  with versioned migrations, background job queue with live WebSocket progress,
  cancellation, structured failure recording, run comparison, audit trail.

## Architecture overview

```
Frontend (React + TS, Vite)
    |
    | HTTP/WebSocket
FastAPI application layer  ──► job queue (threads) ──► runs/results
    |
    ├── quantum core (states/operators/channels)
    ├── circuit engine (statevector + density)
    ├── noise models          ├── QEC subsystem
    ├── algorithm library     ├── network engine (discrete event)
    ├── protocol simulators   └── optimization/QML
    |
SQLite persistence (versioned migrations)
```

Details in [ARCHITECTURE.md](ARCHITECTURE.md); every physical/stochastic model is
documented in [SCIENTIFIC_MODELS.md](SCIENTIFIC_MODELS.md).

## How to run

Prerequisites: Python 3.11+, Node 18+.

```bash
# backend
python -m venv .venv
.venv\Scripts\pip install -e "backend[dev]"   # or install deps from pyproject
cd backend && ..\.venv\Scripts\python -m uvicorn app.api.main:app --port 8000

# frontend (second terminal)
cd frontend && npm install && npm run dev
```

Open http://localhost:5173. The status bar shows whether the backend is reachable.

## Example workflows

1. **Run a circuit**: Circuit Studio → place H on q0, CX(0→1) → Run → inspect
   counts (only `00`/`11`), amplitudes, entanglement entropy.
2. **Study repeaters**: Network Studio → default chain → *Explain route* →
   *Run simulation* → read outcomes, swaps, event log.
3. **Compare BB84 with/without Eve**: Cryptography page → run both settings →
   compare QBER.
4. **QEC curve**: Error Correction → pick Shor-9 → sweep p = 1‰…50‰ → plot
   logical vs physical rate with confidence intervals.
5. **Reproducible study**: Experiments → create from template → Execute all runs →
   open stored result documents (config + seed recorded).

## Testing

```bash
cd backend && ..\.venv\Scripts\python -m pytest tests --timeout=300
```

See [TESTING.md](TESTING.md) for categories and extended validation.

## Known limitations

See [LIMITATIONS.md](LIMITATIONS.md). Highlights: statevector mode ≤ ~24 qubits
practically, density mode ≤ 12, Grover oracle dense (≤ 10 qubits), bounded Shor
N ≤ 32, surface code uses weight-1 lookup decoding, BB84/E91 are idealized-channel
simulations.
