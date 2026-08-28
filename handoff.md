# QuantumLab — Handoff to Next Agent

Generated: 2026-08-29, end of autonomous session 5.
Read together with `docs/DEVELOPMENT_STATUS.md` (checkpoint) and
`docs/AUTONOMOUS_SESSION_LOG.md` (per-phase log). This file documents what
actually happened.

---

## 1. Current Phase

- **Project:** QuantumLab — integrated quantum computing / information /
  networking research platform. Python+FastAPI backend, React+TS frontend,
  SQLite persistence.
- **Session 5 of autonomous development.** Objective (roadmap priority #1):
  noisy ebits / Werner-model entanglement injection — make the network
  simulator's granted ebit fidelity causally affect the quantum state used by
  the distributed remote-CNOT protocols.
- **Status: COMPLETE and validated.** Backend suite green at **514 tests**
  (was 438); frontend build clean. All work committed on `main`.

## 2. Work Completed (session 5)

- **Canonical Werner state** (`backend/app/quantum/density.py`):
  `DensityMatrix.werner(F)` — rho_W(F) = F|Phi+><Phi+| + (1-F)/3 (|Phi-| +
  |Psi+| + |Psi-|), project Bell convention |Phi+> = (|00>+|11>)/sqrt(2),
  qubit 0 = most-significant bit. SAME family as the network subsystem's
  q = (4F-1)/3 parameterization (swapping/decay/purification reuse it); valid
  on all F in [0,1]; entangled iff F > 1/2; maximally mixed at F = 1/4.
- **Noise injection** (`backend/app/distributed/remote_cnot.py`):
  `sample_ebit_pauli_error(F, rng)` samples one Bell component per consumed
  ebit (I with prob F; X/Z/Y each (1-F)/3 — exact trajectory representation of
  the Bell-diagonal Werner state); the sampled Pauli is inserted as an
  unconditioned gate after ebit prep, before the Bell measurement (AD-004
  correction ordering untouched). Both single-ebit and double-teleport
  variants; F >= 1 or None emits the byte-identical historical op list.
- **Engine wiring** (`backend/app/distributed/engine.py`):
  `DistributedConfig.ebit_noise` = "ideal" (default/legacy) |
  "network_fidelity" (consume grant fidelity) | "fixed"
  (`ebit_noise_fidelity` in [0,1]); fail-fast config validation; noise RNG
  namespaced from the experiment seed (`default_rng([seed, 0xEB1A7])`);
  per-op provenance `ebit_fidelity_applied` + `ebit_noise` (additive fields,
  distributed-result v1 preserved); `equivalence.note` explains that fidelity
  < 1 vs the IDEAL centralized reference is noise degradation, not a failure;
  opt-in `include_reduced_state` (<= 6 logical qubits) for exact logical DMs.
- **Runner/API**: `ebit_noise`/`ebit_noise_fidelity` flow through
  `run_distributed_circuit` (metrics add `ebit_noise`, `mean_ebit_fidelity`)
  and the distributed API schemas (Literal-validated).
- **Frontend**: DistributedPanel ebit-noise selector + fixed-fidelity input;
  remote-op table "Ebit F" / "Werner sample" columns; "Noisy distributed GHZ
  study" Experiments template; result-view noise metrics and equivalence note.

## 3. Files Changed

Backend: `app/quantum/density.py`, `app/distributed/{remote_cnot,engine,model,__init__}.py`,
`app/experiments/runner.py`, `app/api/{schemas,main}.py`.
Tests: `tests/test_werner_state.py` (new, 40), `tests/test_distributed_noisy_ebit.py`
(new, 30), `tests/test_api_distributed.py` (extended).
Frontend: `src/components/DistributedPanel.tsx`, `src/pages/Experiments.tsx`.
Docs: SCIENTIFIC_MODELS / LIMITATIONS / ARCHITECTURE_DECISIONS (AD-012) /
DEVELOPMENT_STATUS / AUTONOMOUS_SESSION_LOG / handoff.

## 4. Testing and Verification

- Full backend suite: **514 passed** (exit 0; use `--collect-only` for counts —
  this shell drops pytest's summary line).
- New scientific validation: Werner invariants at seven F values; trajectory
  sampling statistics (30k draws within 6 sigma); F=1 vs ideal exact-match;
  derived analytic Pauli-channel references for BOTH protocols matched by the
  production trajectory average (300 seeds, Uhlmann fidelity > 0.98);
  basis/superposition/entangled-input coverage; reproducibility of sampled
  components; network-fidelity mode end-to-end (direct link, multi-hop swap
  degradation, bad-vs-missing resources) through the live experiment API.
- Frontend: `npx tsc -b && npm run build` clean.
- Benchmark: ideal vs noisy (fixed F=0.9) runtime within run-to-run variance
  for 2-4 qubit GHZ chains; no memory regression (no global density matrices;
  amplitude-space equivalence unchanged).
- Browser inspection NOT performed (no browser tooling); UI verified via
  TypeScript build + endpoint contracts only. Do not claim visual validation.

## 5. Decisions Made (new)

`docs/ARCHITECTURE_DECISIONS.md` → **AD-012**: Werner constructor lives in the
quantum layer; NetworkEngine owns the fidelity value, NetworkBridge carries
it, the distributed engine applies state-level noise exactly once at protocol
expansion; trajectory representation for production with the exact DM as
validation reference; default-ideal backward compatibility with a byte-
identical F>=1 fast path; additive-only result fields (v1 preserved). Standing
AD-001..AD-011 remain binding (AD-003 partial-trace ordering, AD-004 X-before-Z
corrections, AD-009 no silent fallback).

## 6. Known Limitations

- Werner model is phenomenological (no correlated/coherent/non-Markovian
  effects).
- Trajectory semantics: one run realizes ONE mixture component; the Werner
  distribution emerges over seeds (recorded per op in `ebit_noise`).
- Purification (BBPSSW/DEJMPS) cannot trigger through the NetworkBridge grant
  path (one in-flight chain per segment); consumed grants are unpurified;
  purification remains available standalone.
- Grant fidelity is the engine's analytic link-base swap model; memory decay
  affects internal swap bookkeeping but NOT the reported grant fidelity
  (pinned by a test; changing it is a network-engine decision).
- Cached grants are per ordered node pair: same-pair remote CNOTs share link
  quality, each consumed ebit gets an independent Werner realization.
- Experiments UI remains template-based (circuit editor still a next step).

## 7. Unfinished Work / Next Priorities

1. **MWPM decoder + planar rotated surface-code layout** (roadmap).
2. Process-isolated workers with checkpoint/resume (enables interruptible
   RUNNING cancellation).
3. Playwright smoke tests (close the visual-inspection gap).
4. Template circuit editor in the distributed experiment UI.
5. If the network engine later reports decayed/purified grant fidelities, the
   distributed protocol consumes them automatically (pinned contracts will
   surface the change).

## 8. Critical Context

- The experiment runner gets `(config, seed)`; per-run seed `spec.seed + 7919*i`.
  The Werner noise RNG derives from the same seed — no hidden randomness.
- `run_distributed_circuit` with no `ebit_noise` key behaves exactly as
  session 4 (ideal ebits) — legacy experiments and persisted results unchanged.
- A low-fidelity grant (bad resource) executes and degrades the result; a
  failed grant (missing resource) fails the run. Never conflate the two.
- Do not reintroduce double noise application: NetworkEngine must never inject
  circuit-level noise, and the distributed engine must never rewrite grant
  fidelity (regression-covered in `test_distributed_noisy_ebit.py`).
- `quantumlab.db` is gitignored; never commit it.

## 9. Agent Instructions

- Keep the standing loop: inspect → implement → test → validate science →
  integrate → document → benchmark → continue.
- Before implementing, re-run the full suite to confirm 514 green; use
  `--collect-only` for the test count (the summary line is unreliable in this
  shell); trust exit code + FAILED/ERROR counts.
- Statistical noise assertions must aggregate over seeds — a single
  trajectory at F = 0.9 realizes the ideal component ~10% of the time.
