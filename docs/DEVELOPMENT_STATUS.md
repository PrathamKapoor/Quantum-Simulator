# QuantumLab — Development Status

> **Purpose:** Persistent checkpoint file for autonomous development. Any session (human or agent)
> resuming work MUST read this file first, then ROADMAP.md, ARCHITECTURE.md, SCIENTIFIC_MODELS.md,
> LIMITATIONS.md (directive §320).
>
> Last updated: 2026-08-25 (session 1, checkpoint 2)

## Current phase

Phase 3 — Quantum core + circuit engine COMPLETE and validated (115 tests green).
Next: QEC subsystem → Network engine (flagship) → protocols → experiments → API → frontend.

## Completed tasks

| Task ID | Module | Description | State |
|---------|--------|-------------|-------|
| ENV-001 | infra | Python 3.13 venv; numpy/scipy/fastapi/pydantic/pytest installed | VALIDATED |
| DOC-001 | docs | Documentation system initialized | COMPLETE |
| CORE-001 | quantum | StateVector: norm/normalize policy explicit, tensor, marginals (vectorized), basis states | VALIDATED |
| CORE-002 | quantum | Gate library: 25+ gates, unitarity validation, custom-gate path | VALIDATED |
| CORE-003 | quantum | DensityMatrix: partial trace, Uhlmann fidelity, purity, entropy, Bloch, trace distance | VALIDATED |
| CORE-004 | quantum | Kraus channels: TP validation, bit/phase flip, depolarizing, amplitude/phase damping, T1/T2 thermal, composite | VALIDATED |
| CORE-005 | quantum | Measurement: exact marginals, collapse, seeded sampling, asymmetric readout error | VALIDATED |
| CIRC-001..005 | circuits | Circuit model, structured validation, versioned serialization (v1), statevector + density engines, mid-circuit measurement, classical conditions, reset semantics, shot fast-path with exact multinomial sampling | VALIDATED |
| ALGO-QFT | algorithms | QFT/iQFT verified against explicit DFT matrix; approximate QFT flags itself | VALIDATED |
| ALGO-DJ/BV/Simon/Grover/Superdense | algorithms | All verified against expected outputs | VALIDATED |
| ALGO-QPE/Shor-bounded | algorithms | Phase estimation (local controlled-U matrices); bounded order finding for N≤32 via dense permutation oracles + continued fractions | TESTING (order finding test pending re-run) |
| ALGO-WALK | algorithms | Coined walk cross-checked against independent reference implementation | VALIDATED |

## Active task

QEC-001: error correction subsystem.

## Key architectural decisions recorded

1. **Little-endian qubit ordering** (qubit 0 = LSB) everywhere; documented in app.quantum docstring.
2. **Gate-local basis convention**: first operand = most-significant local bit.
   `app/algorithms/conventions.local_reorder` converts full-register-indexed
   matrices to gate-local matrices — REQUIRED when building oracle gates from
   truth tables (this caused + was fixed by regression-prone bugs; see below).
3. **shots=None statevector mode** returns the full pre-measurement state unless
   measurement results are used downstream (then one collapsed trajectory runs).
4. Fast shot path: single evolution + exact multinomial sampling over the
   classical-register distribution (scientifically equivalent; documented).
5. Noise in statevector mode = per-shot Kraus trajectory sampling; density mode =
   exact CPTP application. Both documented in simulate.py module docstring.

## Bugs found and fixed during this session (regression-covered)

| Bug | Root cause | Test coverage |
|-----|-----------|---------------|
| DJ oracle flipped wrong register bit | matrix built in full-register indexing without local-basis conversion | conventions + DJ verdict tests |
| Simon measured first register before final H | missing mid-circuit second-register measurement | run_simon correctness test |
| QPE used len(system) as precision bits | t miscomputed after refactor | QPE estimate tests |
| operand_bit_mapping shifted by qubit offset | used `(f >> q)` instead of `(f >> pos)` for subsystem indexing | order-finding + QPE tests |
| Fast path sampled over all qubits not measured subset | design flaw | bell counts + DJ counts tests |
| shots=None never executed operations | loop bound bug | teleportation conditional test |
| Reset discarded population instead of forcing \|0⟩ | projection misuse | reset semantics test |

## Test status

- Fast suite: **115 passed, 0 failed** (`python -m pytest backend/tests`).

## Build/runtime status

- Backend: pure Python, no build step. API server not yet implemented.

## Scientific validation status

- Gate application cross-checked against explicit Kronecker embedding (§151).
- QFT cross-checked against DFT matrix; Grover peak vs analytic optimum;
  teleportation fidelity check; BB84/QEC pending.

## Known limitations (see LIMITATIONS.md for detail)

- Grover MCZ oracle: dense diagonal, capped at 10 qubits.
- Bounded Shor: N ≤ 32 (dense permutation oracle), total ≤ 16 qubits.
- Density-matrix engine: ≤ 12 qubits.

## Next recommended tasks

1. QEC-001..005 (codes, pipeline, decoder interface, Monte Carlo benchmark).
2. NET-001..012 network discrete-event engine (flagship).
3. PROTO-* (BB84, E91, CHSH, QRNG) on top of quantum core.
4. EXP-* experiment engine + SQLite persistence + worker queue.
5. API layer, then frontend shell.
