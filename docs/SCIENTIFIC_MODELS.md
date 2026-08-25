# QuantumLab — Scientific Models, Assumptions & Limitations

Every nontrivial model records: formula, parameters, assumptions, validation,
and limitations (directive §295). Validation against limiting cases and
independent references happens in the test suite (directive §296, §151).

## Quantum representation

- **Qubit ordering**: little-endian. Qubit 0 is the least-significant bit of a
  basis index: `index = Σ q_k · 2^k`. Basis strings in the UI print
  high-order-first (`|q2 q1 q0⟩`).
- **Gate-local basis**: a k-qubit gate matrix's local index uses the FIRST
  operand as most-significant bit (e.g. CX operands `(control, target)`).
- Angles are radians. Complex arithmetic is numpy complex128.
- Tolerance policy: construction validates norm/Hermiticity within documented
  tolerances; NaN/Inf input is rejected outright (never sanitized).

## Gate application

Fast path contracts gate matrices onto tensor axes (no full-space embedding).
Correctness cross-checked in tests against `embed_operator`, an independent
O(dim²) Kronecker construction, for 1-, 2-, and 3-qubit gates on many operand
orders.

## Channels and noise

| Channel | Kraus form | Notes |
|---------|-----------|-------|
| bit_flip(p) | √(1−p) I, √p X | symmetric |
| phase_flip(p) | √(1−p) I, √p Z | |
| bit_phase_flip(p) | √(1−p) I, √p Y | |
| depolarizing(p) | K₀=√(1−3q)I + √q(X,Y,Z), q=p/4 | E(ρ)=(1−p)ρ+p·I/2 |
| amplitude_damping(γ) | standard K₀,K₁ | energy relaxation toward \|0⟩ (T1-type) |
| phase_damping(γ) | K₀=√(1−γ)I, K₁=√γ\|0⟩⟨0\|, K₂=√γ\|1⟩⟨1\| | pure dephasing |
| thermal_relaxation(T1,T2,t) | composition of the above with γ₁=1−e^(−t/T1), γ_φ from 1/Tφ = 1/T2 − 1/(2T1) | zero-temperature bath; rejects T2 > 2·T1 |

Trace preservation is validated numerically at construction; application output
is renormalized with drift checks.

**Statevector noise execution** samples one Kraus operator per noisy gate per
shot with P(K_i)=‖K_i ψ‖² (quantum trajectories). Averaged over shots this
reproduces exact channel action — an ensemble-sampling method, not an
approximation of the channel itself.

**Readout error** is a classical confusion channel applied to measured bits:
P(read 1|actual 0)=p₁, P(read 0|actual 1)=p₂ (asymmetric).

## Measurement semantics

Outcome probabilities are exact marginals of |ψ|²; sampling uses one seeded RNG
stream. Terminal-only measurement circuits use a mathematically equivalent fast
path: evolve once, then draw all shots from the exact classical-outcome
distribution via multinomial sampling.

## Fidelity conventions

- Pure states: F = |⟨ψ|φ⟩|².
- Mixed/mixed or mixed/pure: Uhlmann fidelity F=(Tr√(√ρ σ √ρ))² via Hermitian
  eigendecomposition; eigenvalues in [−1e−12, 0] clipped (documented tolerance),
  more negative values rejected as corruption.
- Link/pair quality numbers labeled "fidelity" refer to the Werner-state
  fidelity parameterization below; nothing else in the platform reuses the word
  without qualification.

## Entanglement swapping (network engine)

Links produce Werner-form pairs ρ(q)=q|Φ⁺⟩⟨Φ⁺|+(1−q)·I/4 with
F=(3q+1)/4, q=(4F−1)/3. Under idealized Bell-state-measurement swapping,
Werner parameters multiply:

    q_out = Π q_i        ⇒        F_e2e = (3 Π q_i + 1)/4

Limiting behavior verified: perfect inputs → perfect output; any maximally-mixed
input (q=0) → F=1/4 output. Swap success probability configurable (default
ideal); failure destroys both pairs. Classical announcement latency added unless
idealized mode chosen (mode always labeled in results).

## Memory decay

A stored pair ages as a Werner state with exponentially decaying parameter:
`q(age) = q₀·exp(−age/T_memory)` ⇒ F(age)=(3q₀ e^(−age/T)+1)/4. At age ≫ T the
pair converges to F=1/4 (maximally mixed two-qubit state — no correlation left).
Pairs expire at memory_coherence_ns after creation.

## Entanglement generation

Per attempt survival probability η = 10^(−α·d/10)·detector_efficiency with
α=0.2 dB/km default fiber attenuation. Attempt duration = round-trip
propagation (5 µs/km each way) + 10 µs processing. d=0 gives lossless (limiting
case tested). Success requires free memory slots at both endpoints.

## Routing cost models

All strategies expose their score in route explanations:

- shortest_path: total km
- min_loss: additive dB loss Σ −10·log₁₀(η)
- max_fidelity: negative expected end-to-end fidelity (swap model above)
- min_expected_time: expected geometric attempts × round-trip propagation
- resource_aware: explicit weighted mix (fidelity_weight, loss_weight,
  latency_weight, resource_weight)

Routes failing a request's fidelity requirement are excluded even when cheapest;
when nothing qualifies, the best-effort explanation says why.

## QEC

- Errors are Pauli strings; syndromes computed group-theoretically
  (anticommutes-with-generator bits). Exact for Pauli noise; this benchmark
  path does not simulate syndrome-measurement circuits (circuit-based syndrome
  extraction demonstrated separately for the 3-qubit code).
- Lookup decoders enumerate errors up to weight ⌊(d−1)/2⌋ restricted to each
  code's declared correctable Pauli types; every table entry is verified to
  leave no logical residual. Degenerate same-syndrome classes pick any class
  member (valid because they differ by stabilizers).
- Repetition codes protect ONE error type (documented per code): a single Y on
  bit-flip-3 legitimately fails because Y carries a Z component.
- Logical failure test: residual anticommutes with either logical operator.
- Confidence intervals: Wilson score intervals (behaves well at small rates);
  trends validated statistically, never asserted exactly.

## Toric surface code (educational)

Planar-toric layout on a d×d torus: data qubits on edges, 4-edge X-star
stabilizers at vertices, 4-edge Z-plaquette operators on faces. Verified:
star/plaquette commutation, minimum nontrivial logical weight = lattice
distance. Decoder corrects single-qubit errors exactly; multi-qubit patterns
without a unique weight-1-consistent syndrome count as failures — this
UNDERSTATES true capability and the result metadata says so.

## BB84

Ideal channels/detectors. Eve performs intercept-resend independently per
signal with probability p_Eve. Expected QBER: ≈0 without Eve; ≈25% under full
intercept-resend (finite-size statistics). QBER estimated from a random sample
of the sifted key; sampled bits discarded as in the real protocol.

## E91 / CHSH

Singlet correlations: E(a,b) = −cos(θa−θb), P(same)=sin²(Δθ/2). Visibility model
for E91: outcomes re-randomized with probability (1−V)/2 each (depolarizing
visibility). CHSH lab uses an isotropic source model: fraction F of perfect
singlet pairs, remainder maximally mixed ⇒ S scales as 2√2·F with violation
threshold exactly F > 1/√2 (verified around threshold in tests). Finite-shot
fluctuations ~1/√N apply; tests assert bands rather than point values.

## QRNG

Protocol statistics demonstrated with a seeded PRNG standing in for device
output; the module states plainly that no physical entropy is produced.
Self-tests: mean-bias check and Wald–Wolfowitz runs test (normal approximation).

## Variational algorithms

VQE/QAOA use noiseless statevector expectations (no shot noise). Optimizers:
SPSA (standard gain schedules) plus optional coordinate-descent polish; QML
training uses documented multi-start initialization. H2 uses tabulated,
interpolated two-qubit effective-Hamiltonian coefficients — an approximate
molecular model, not electronic structure. MaxCut baselines are exact brute
force; "approximation ratio" compares QAOA's most likely cut to the optimum and
is explicitly NOT an advantage claim.

---

# Session-2 additions

## Quantum information measures
See QUANTUM_INFORMATION.md for the full table (18 quantities). Highlights:
Rényi family S_α = log₂Tr(ρ^α)/(1−α) with α→1 branch; min-entropy −log₂λ_max;
relative entropy with explicit support-violation errors; two-qubit concurrence
via Wootters spin-flip; negativity/logarithmic negativity via partial transpose
trace norm; Schmidt decomposition by SVD; PPT separability reports that label
their own scope (sufficient only for 2×2/2×3).

## Channel algebra
Choi matrix J(E)=Σ_ij |i⟩⟨j|⊗E(|i⟩⟨j|) (un-normalized); validated Hermitian,
PS (complete positivity), Tr_out J = I_in (TP). Composition {l_j k_i} and
tensor products verified against sequential application on test operators.
Process fidelity F_pro = ⟨Φ̃|J(E)|Φ̃⟩/d with Φ̃=(U*⊗I)|Φ⟩/√d;
F_avg=(d·F_pro+1)/(d+1). Reference points: unitary channel→1; fully
depolarizing single-qubit→F_avg=1/2.
Generalized amplitude damping: cold/hot bath mixture weighted by (1−N)/N
(N = bath excited population); N=0 reduces exactly to amplitude damping.
Readout confusion channel: classical off-diagonal Kraus pair acting on the
diagonal only (documented simplification).

## Hardware mapping
Mapped circuit satisfies M_mapped = P_end·M_logical where P_end scatters
logical bit l to physical bit final_mapping[l]; verified by dense column-
scatter comparison (≤7 qubits). Routing inserts shortest-path SWAPs (3 CX
each) updating the permutation consistently.

## Error mitigation
Readout mitigation inverts the tensor-product confusion matrix by least
squares; condition number reported; negative quasi-probabilities clipped with
the clipped mass reported. ZNE folds circuits U→U(U†U)^{(s−1)/2} (unitary
action preserved — dense-verified), estimates observables in exact
density-matrix mode, fits linear/quadratic polynomials over odd scale factors,
and WARNS when extrapolation leaves the measured range. Parity postselection
reports kept/discarded counts and discard rate.

## Purification
BBPSSW: p=F²+2F(1−F)/3+5((1−F)/3)², F'=(F²+((1−F)/3)²)/p.
DEJMPS: p=(F+(1−F)/3)², F'=(F²+((1−F)/3)²)/(F+(1−F)/3)².
Both assume identical Werner inputs, ideal local ops; each attempt consumes
both pairs; failure ends the chain. Validated fixed points (F=1; BBPSSW F=½)
and DEJMPS value 0.625 at F=½.

## Repeaters
L0/L1/L2 strategy studies run identical request workloads across distances on
chain topologies (~25 km spacing heuristic); success probabilities carry
Wilson CIs; pairs-generated-per-success reported as resource consumption.

## Lossy-channel QKD
Per-signal survival η=10^(−αd/10)·det_eff; lost signals excluded from sifting;
optional uniform-random dark counts; secret fraction r≥1−2h₂(QBER) labeled an
ASYMPTOTIC ESTIMATE under the documented model, not a finite-key proof.
