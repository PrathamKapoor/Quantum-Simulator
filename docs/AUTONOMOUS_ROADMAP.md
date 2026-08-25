# QuantumLab — Autonomous Roadmap (Session 2+)

Written at session-2 start after reconnaissance. Baseline verified before any change:

- git clean @ `397c91d`
- fast suite **239 passed**
- API :8000 health `ok`; frontend :5173 serving

## Current state (summary)

QuantumLab v0.1.0 has validated foundations: quantum core (statevectors/density
matrices/channels/observables), circuit engine (mid-circuit measurement,
conditioning, trajectories, density mode), algorithm suite, QEC (5 stabilizer
codes + toric model, MC benchmarks), discrete-event network engine (routing,
scheduling, chaos, fairness), protocol sims (BB84/E91/CHSH/QRNG), VQE/QAOA/H2/QML,
experiment framework (SQLite migrations, job queue, WebSocket progress), FastAPI
layer, React workspace. Scientific models documented in SCIENTIFIC_MODELS.md;
limits in LIMITATIONS.md.

## Missing capabilities (directive §4 layer audit)

| Layer | Gap |
|-------|-----|
| L5 information theory | Rényi/min-entropy, conditional entropy, relative entropy, linear entropy, concurrence, negativity/log-negative, Schmidt decomposition/rank, correlation matrices |
| L3 channels | Choi representation, channel composition/tensor verification, generalized amplitude damping, process-fidelity metric |
| L9 networking | entanglement as first-class resource lifecycle; purification (BBPSSW/DEJMPS); repeater strategy framework |
| L8 mitigation | measurement-error mitigation, zero-noise extrapolation, symmetry verification |
| L11 hardware | HardwareProfile abstraction, topology presets, SWAP-insertion mapping, mapping validation, noise-aware presets |
| L6 circuits | circuit analysis (depth/gate counts/T-count where defined, connectivity requirements), inverse/compose circuits |
| L10 distributed | remote CNOT via entanglement + classical communication, validated vs local CNOT |
| L12 experiments | reproducibility check, reusable statistics subsystem, provenance-rich CSV export |
| L13 UI | Information Theory Lab, Hardware Lab, mitigation views, purification controls |

## Planned phases (deep > broad, §139)

| Phase | Scope | Validation gate |
|-------|-------|-----------------|
| A | Quantum information expansion (`app/quantum/info_theory.py`): 18 quantities with formulas, domains, stability notes | property tests on known states (Bell/GHZ/product/maximally mixed), bounds tests |
| B | Channel framework: Choi matrix, composition/tensor identities, generalized amplitude damping, entanglement/process fidelity | Choi of known channels matches analytic forms; E2∘E1 == composed; TP preserved |
| C | Circuit analysis + HardwareProfile + transpiler (SWAP insertion for line/ring/grid), mapping correctness under ideal execution | mapped ideal action equals logical action up to permutation; regression on depth/SWAP counts |
| D | Error mitigation: measurement confusion-matrix mitigation, ZNE (linear/quadratic), symmetry verification postselection | mitigated ≈ ideal within tolerance on standard examples; raw noisy results always reported alongside |
| E | Entanglement purification: BBPSSW & DEJMPS on Werner states with exact recurrence relations; full resource accounting | fidelity improves per protocol math; consumed-pair accounting exact; success probabilities match analytic forms |
| F | Repeater framework (levels 0–2) + network-integrated BB84 loss model | repeater-vs-direct comparison study; loss reduces key rate per fiber model |
| G | Distributed remote CNOT (entanglement-assisted) | distributed action == local CNOT on basis states and superpositions |
| H | Experiment framework: reproduce-run endpoint, statistics subsystem, provenance CSV export | reproduce(ideal deterministic exp) == original bit-for-bit |
| I | Frontend labs for new capabilities | build green; endpoints consumed by real pages (no dead UI §140) |
| J | Documentation set (NETWORK_MODELS/QEC_MODELS/QUANTUM_INFORMATION/HARDWARE_MODELS/EXPERIMENTS/REPRODUCIBILITY/ARCHITECTURE_DECISIONS/SESSION_LOG/FINAL_REPORT) | docs match implementation (§173) |

## Dependencies

- Phases are ordered by dependency: B extends channels used by D (mitigation uses
  noise scaling); E uses Werner machinery already in resources.py; F uses E.
- No new dependencies planned (RULE 7). numpy/scipy suffice.

## Risks

- Purification recurrence formulas must be transcribed exactly; validated against
  analytic special cases (equal inputs → known fixed points).
- ZNE extrapolation can be unstable near degenerate fits — must surface warnings,
  never silently clip (§12).
- Transpiler SWAP mapping must preserve unitary semantics; validated by comparing
  full-space unitaries including final permutation (small n only).
- Keeping 239-test baseline green at every commit is mandatory (§78).

## Session log

See docs/AUTONOMOUS_SESSION_LOG.md (created with Phase A).
