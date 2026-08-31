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

# Session-3 additions

## Distributed quantum computing (single-ebit remote CNOT + partitioner)

### Remote-CNOT protocol (gate teleportation, 1 ebit)

Alice hosts control `c`, Bob hosts target `t`; they share one ebit
`|Φ⁺⟩_{a,b} = (|00⟩+|11⟩)/√2`. The distributed circuit executes, in order:

1. **Entanglement distribution** — `H(a); CX(a,b)` creates the shared ebit.
2. **Bell measurement** on `(c, a)`: `CX(c,a); H(c)`, then
   `measure c → m_z`, `measure a → m_x`.
3. **Classical communication** — Alice sends the 2 bits `(m_x, m_z)` to Bob.
4. **Pauli corrections** on Bob's half: `X^{m_x}` FIRST, then `Z^{m_z}`
   (AD-004: pre-correction state is `Z^{m_z} X^{m_x} |ψ⟩`; order is observable
   once the teleported wire enters entangling operations).
5. **Local gate** — Bob applies `CNOT(b → t)`.

Circuit identity (validated): the protocol implements exactly

    CNOT(c → t) ⊗ (consumed ebit)

for arbitrary inputs, including non-trivial target states. After the gate the
logical control co-locates with the target at Bob; this carrier migration is
tracked by the engine (`physical_of` remapping) so subsequent operations act on
the correct physical wire.

The double-teleportation variant (`protocol="double_teleport"`) consumes
2 ebits + 4 classical bits and returns the control to Alice on a fresh
carrier.

### Resource accounting (exact counts)

| Protocol | Ebits | Classical bits | Transient carriers |
|----------|-------|----------------|--------------------|
| single_ebit | 1 | 2 | 2 ancillas |
| double_teleport | 2 | 4 | 4 ancillas |

Ebit requests are served by the existing discrete-event network engine when a
topology is supplied: the reported fidelity, modelled latency, attempt count,
and route come from a real entanglement-generation run over that topology.
Without a topology grants are labelled `ideal` (fidelity 1, zero modelled
latency). Modelled network latency and wall-clock simulation runtime are
reported separately and never conflated.

### Partitioner

Deterministic heuristic (§PARTITIONING STRATEGY):

1. explicit user mapping wins verbatim (no search touches it),
2. otherwise balanced round-robin seed across the requested nodes,
3. then coordinate-descent local search minimising cross-node gate count.

Constraint: every requested node keeps at least one hosted qubit — otherwise
the search would collapse the whole circuit onto one node and report zero
remote operations, defeating the purpose of distribution. The objective is
*minimise cross-node gates subject to using all requested nodes*; it is NOT
claimed globally optimal (local search, reported as such).

Gates spanning >2 nodes or acting on ≠2 qubits are classified
`requires_decomposition` and are excluded from remote execution honestly
(they fail rather than silently degrade).

### Equivalence validation

Distributed output equals the centralized reference up to global phase:
Uhlmann fidelity of both states reduced to the logical qubits must reach
1 − 1e−8. Both reductions use the same partial-trace convention so ordering
cancels. Validated on basis states, superpositions, Bell/GHZ inputs, both
gate directions (A→B, B→A), 2/3/4-node partitions, mixed local+remote
sequences, and seeded randomized circuits (probability-vector agreement
≤1e−8 per basis outcome).

### Failure semantics

No silent fallback. If an ebit cannot be established (disconnected nodes,
unknown node, network failure) the result is `status=failed` with the reason,
unless the caller explicitly set `fallback="centralized"` — in which case the
degradation is recorded in warnings. Resource caps (max remote operations /
ancilla budget) fail loudly.

## Session-4 additions

### Distributed resources in experiment records

A `distributed_circuit` experiment run produces a `quantumlab.run-result` v1
document whose `metrics` report the engine-computed counts directly (no
re-calculation in the adapter):

- `remote_cnot_count`, `local_gate_count`, `remote_gate_count`
- `ebit_consumption` — ACTUAL protocol consumption (1/gate single-ebit, 2/gate
  double-teleport), not the partition-plan estimate
- `classical_message_count`, `communication_cost`
- `node_count`, `qubit_count`, `modeled_network_latency_ms` (max modelled grant
  latency, network model only)
- `equivalence_fidelity` / `equivalence_passed`

The full distributed-result v1 document is preserved verbatim under
`artifacts.distributed_result`; remote operations, entanglement grants,
classical messages, and output probabilities are also surfaced as artifacts for
the detail view.

### Reproducibility contract

A run is reproducible if `(base_config, resolved_config, run seed)` are
persisted — they are. `reproduce_run` copies the stored resolved_config + seed
into a NEW run row and executes it; deterministic distributed runs reproduce
EXACT_MATCH (statevector, fixed seed). Completed runs are immutable; the
effective assignment (even for auto-assigned `num_nodes`) is recorded in
`reproducibility.assignment`, so there are no hidden defaults.

### Sweep semantics

Sweeps use the existing float-typed engine. Each combo now inherits the
experiment's base configuration (e.g. the circuit) with the swept key layered
on top — a correctness fix to `expand_sweep`, which previously produced combos
containing ONLY the swept keys. The engine-supported numeric dimension exposed
here is `num_nodes` (auto-assigned partition); iterating it changes the
cross-node resource profile of the same circuit while preserving per-run
evidence in resolved_config and metrics.

## Session-5 additions

### Noisy ebits: Werner-model entanglement injection (AD-012)

**Model.** A granted ebit with fidelity F is prepared as the canonical Werner
state toward the project's Bell target |Phi+> = (|00> + |11>)/sqrt(2) (qubit 0
= most-significant local bit, the same ordering as every gate operand):

    rho_W(F) = F |Phi+><Phi+|
             + (1-F)/3 * ( |Phi-><Phi-| + |Psi+><Psi+| + |Psi-><Psi-| )

This is the SAME state family the network subsystem already uses everywhere:
rho = q|Phi+><Phi+| + (1-q) I/4 with q = (4F-1)/3 (`werner_parameter`), which
is the parameterization of swapping (`swap_fidelity`), memory decay
(`aged_fidelity`), and purification. No second Werner model was introduced.
The direct Bell-weight form is mathematically valid on all F in [0, 1]
(the network q-form is quoted for F >= 0.25 only); the state is entangled iff
F > 1/2 (PPT), is maximally mixed at F = 1/4, and is a valid separable
Bell-diagonal state below. Values F <= 1/2 must not be labelled "entangled".
The exact constructor is `DensityMatrix.werner(F)` (4x4, with invariants
trace/Hermiticity/PSD/target-fidelity covered by dedicated tests).

**Representation.** The distributed engine executes under statevector
trajectory semantics, and a Bell-diagonal state IS a Pauli channel: applying
the single-qubit Pauli P on one ebit half of |Phi+> yields
I -> |Phi+> (probability F), X -> |Psi+>, Z -> |Phi->, Y -> |Psi-> each with
probability (1-F)/3. Production execution therefore samples ONE Pauli per
consumed ebit (`sample_ebit_pauli_error`) and inserts it as an unconditioned
gate immediately after ebit preparation and before the Bell measurement; the
aggregate over trajectories reproduces rho_W(F) exactly. The X^{mx}-before-
Z^{mz} correction ordering (AD-004) is untouched, and no global density
matrix is ever formed (the 64 GiB equivalence regression cannot recur; the
equivalence reduction remains the amplitude-space axis-permutation method).

**Channel equivalence (independent validation reference).** Teleportation
through a Pauli-errored ebit is ideal teleportation composed with the
corresponding Pauli on the carried qubit. Hence for the single-ebit protocol
the effective logical channel is

    rho_out = sum_P p_P * CNOT (P_c (x) I) rho_in (P_c (x) I)^dag CNOT^dag,

and for double teleportation the two ebit errors compose on both sides of the
local CNOT:

    rho_out = sum_{P1,P2} p1 p2 (P2 (x) I) CNOT (P1 (x) I) rho_in (...)^dag.

These derived references are checked against the trajectory-average of the
production engine (300 seeds: Uhlmann fidelity > 0.98, trace distance < 0.06
at F in {0.6, 0.85}), so the noisy implementation is not validated only
against itself.

**Ownership / noise composition.** The NetworkEngine computes the fidelity
that a grant reports (link base fidelity, Werner-parameter swap
multiplication, purification configuration); the NetworkBridge carries it
verbatim in `EbitGrant.fidelity`; the distributed engine applies the
state-level noise EXACTLY ONCE, at protocol expansion. The network engine
never injects circuit-level noise and the distributed engine never alters a
grant's fidelity, so no effect is applied twice. Local gate noise (a circuit
noise model) is a separate simulator feature and composes multiplicatively
with the ebit channel by construction (different application points).

**Provenance & seeding.** Each executed remote operation records
`ebit_fidelity` (granted), `ebit_fidelity_applied` (used for the state;
differs only in fixed-fidelity mode), and `ebit_noise` (the sampled Pauli per
consumed ebit). The noise RNG is a numpy Generator namespaced from the
experiment seed (`default_rng([seed, 0xEB1A7])`), independent of the
simulator's stream; identical config + seed reproduce identical sampled
components and results bit-for-bit. Reproducibility records the noise mode.

**Equivalence semantics.** The equivalence reference remains the IDEAL
centralized execution. With ebit noise enabled, `equivalence.fidelity < 1`
is the expected, scientifically meaningful outcome (noise-induced
degradation), and the result document says so explicitly (`equivalence.note`);
this is not a validation failure.

### Experiment integration

`ebit_noise` ("ideal" | "network_fidelity" | "fixed") and
`ebit_noise_fidelity` are regular `distributed_circuit` experiment-config
fields (absent = "ideal" = historical behavior, byte-identical). Metrics add
`ebit_noise` and `mean_ebit_fidelity` (mean applied fidelity over executed
remote operations). Because the existing sweep engine types values as floats,
`ebit_noise_fidelity` (fixed mode) is sweepable with the base-config fix from
session 4; `ebit_noise` itself is a string and deliberately not sweepable.

## Session-6 additions

### Rotated planar surface code (geometry, stabilizers, logicals)

**Lattice (doubled integer coordinates).** Data qubits at odd (x, y),
1 <= x, y <= 2d-1; index q = ((y-1)//2)*d + ((x-1)//2). Stabilizer centers at
even (x, y) in [0, 2d]^2 with type X iff (x+y) % 4 == 0, else Z; support =
diagonally adjacent data qubits. Kept checks: all interior (weight 4), plus
weight-2 X checks on the top/bottom edges and weight-2 Z checks on the
left/right edges; the four weight-1 corners are dropped. This yields exactly
(d^2-1)/2 checks of each type, all pairs commuting, every data qubit covered
by at least one check of each type (validated at construction and re-verified
in tests for d = 3, 5, 7).

**Logical operators.** Logical X = vertical column x = d (d data qubits,
top-bottom); logical Z = horizontal row y = d (left-right). They commute with
every check, anticommute with each other (overlap at (d, d)), and have weight
exactly d. Boundary semantics (§13 of the milestone) are verified through
string construction, not naming: X-check syndrome chains terminate on the
left/right exits, Z-check syndrome chains on the top/bottom exits, and the
logical X column crosses Z checks while the logical Z row crosses X checks.

**Distance verification.** The distance is COMPUTED, not assumed: for each
CSS component the minimum weight of a nontrivial logical is found by
exhaustive binary enumeration over supports of weight <= d (exact for CSS
codes because d = min(d_X, d_Z)), vectorized with per-qubit GF(2) generator
masks and numpy. Verified equal to d for d = 3, 5, 7.

### MWPM decoder (code capacity)

**CSS split.** Z errors flip X checks and are corrected by Z chains on the
X-check graph; X errors flip Z checks and are corrected by X chains on the
Z-check graph. A Y error enters both components. The two matching problems
never mix syndrome types.

**Chain graph.** Vertices = one CSS component's checks; a data qubit in two
check supports is an internal chain edge (weight 1); a data qubit with a
single support is a boundary EXIT (the point where a correction chain leaves
the lattice). All-pairs minimum chain weights and the actual chains (data
qubit lists) are precomputed once per code by BFS over the alternating
check-data incidence graph with sorted expansion (deterministic, §53).

**Matching reduction.** Decoding = minimum-weight perfect matching on the
defect set where each defect either pairs with another defect (cost = chain
weight) or takes a boundary exit (cost = min chain weight to an exit). The
implementation gives each defect a private "boundary copy" vertex (leftover
copies pair at weight 0), which makes the graph always perfectly matchable
for any defect parity while representing EVERY valid correction. The matcher
(`qec/matching.py`) is EXACT dynamic programming over defect subsets with
memoization and a loud state-budget guard - genuine minimum-weight perfect
matching, not greedy nearest-neighbour pairing (§74). It is validated against
an independent plain-recursion brute force on hundreds of random instances
with 2, 4, and 6 defects (§22, §54).

**Correction and residual.** Each matched pair contributes its actual chain;
overlapping chains combine by GF(2) XOR. The residual R = correction XOR
error has zero syndrome by construction (asserted). R is stabilizer-equivalent
to identity iff its component coset functionals are silent; a firing
functional is a genuine logical operator. Outcomes: CORRECTED, LOGICAL_X,
LOGICAL_Z (X-/Z-type residual), LOGICAL_Y (both). The functional is a GF(2)
bitmask solved from the generator algebra at build time (k = 1 makes the
coset space one-dimensional), so classification never enumerates the
stabilizer group (§29).

**Edge-weight model.** Edge weight = number of data qubits on the minimum
correction chain (a probability-derived weight under uniform noise reduces to
this Manhattan-like lattice metric; the BFS makes the metric exact for the
rotated lattice rather than assumed Euclidean).

**Zero-syndrome semantics (§49-§50).** Identity and stabilizer products
decode to CORRECTED; a bare logical operator has zero syndrome but is flagged
by the functional - never silently "successful".

### Monte Carlo and experiments

`simulate_rotated_surface_code(d, p, trials, seed, error_model)` samples
independent Pauli data-qubit noise (depolarizing = I w.p. 1-p, X/Y/Z equally -
the existing stabilizer.py model; x_only / z_only also supported), decodes
each trial, and reports p_L = failures/trials with the EXISTING Wilson 95%
interval from `qec.pipeline` (no second implementation). Experiments use the
`surface_code_mwpm` module in the existing runner (configuration, persistence,
reproduction, comparison, sweep through the standard framework); seeds follow
the existing conventions and per-point seeds derive deterministically from
the base seed. Threshold language: sweeps report observed behaviour with
confidence intervals; no threshold value is claimed.

## Session-9 additions

### Repeated-round (space-time) surface-code decoding

**Model (phenomenological, §45-§50 deferred).** The single-shot code-capacity
decoder is extended to R rounds of stabilizer measurement. The rotated planar
code (d = 3, 5, 7) is decoded per CSS sector (X errors from Z-check syndromes,
Z errors from X-check syndromes, independently).

- Data noise: at each of R "slots" (the interval before each measurement),
  every data qubit takes an independent depolarizing error with probability
  p_d (I w.p. 1-p_d, else X/Y/Z each p_d/3). Errors are PERSISTENT — each new
  error XORs onto the cumulative data error. Reuses `random_pauli_errors`.
- Measurement noise: each stabilizer measurement in rounds 1..R-1 has an
  independent bit flip with probability p_m. A flip is a TEMPORAL fault and is
  never converted into a data-qubit correction. The final round R is assumed
  IDEAL — a necessary, documented choice, because a final measurement flip is
  otherwise indistinguishable from a final data error in any single-slice
  final decode.

**Detection events (§12, derived).** Layer t (t = 1..R) is the syndrome
difference d_t = observed_t XOR observed_{t-1}, with observed_0 = 0 (a
known-clean start). A persistent data error introduced at slot t appears as
detection events at exactly one layer; a measurement flip at round t (R-1 or
below) appears as a pair at (stabilizer, t) and (stabilizer, t+1).

**Two-stage decode (chosen and validated convention).** A single 3-D
"differences + final clean column" MWPM double-counts a persistent data
error (its syndrome enters the difference stream when introduced and exits
again at a final clean round), which over-corrected boundary errors into
false logical failures. The chosen construction is therefore:

1. Stage A (temporal): MWPM over layers 1..R with SPATIAL edges (same-layer
   data-error chains, cost chain_len * w_s), LATERAL boundary exits (data
   error leaving the code, any layer), and TEMPORAL edges (measurement flip,
   (S,t)-(S,t+1), cost w_m).
2. Stage B (final residual): the last observed syndrome minus the syndrome
   already explained by Stage A's data correction is decoded with the
   EXISTING single-shot decoder, yielding the final data correction.

**Weights (§15).** w_s = -ln((p_d/3)/(1-p_d)), w_m = -ln(p_m/(1-p_m)),
integer-quantized to 1e-6 so the existing exact integer matcher
(`matching.min_weight_perfect_matching`) is reused unchanged; matching is
deterministic and, under the independent per-location model, maximum
likelihood (for that model only — not claimed optimal beyond it).

**Correction & classification.** correction = Stage A data correction XOR
Stage B final correction; residual = correction XOR cumulative true data
error; classified with the existing coset functionals into CORRECTED /
LOGICAL_X / LOGICAL_Z / LOGICAL_Y (identical semantics to single-shot; a
zero-syndrome logical string still fires the functional).

**Validation.** Exact deterministic cases (no noise; single data error per
qubit/Pauli at every distance; single and double measurement errors; data +
measurement; logical string at zero syndrome; stabilizer equivalence; Y
errors in both sectors; reproducibility) pass before any Monte Carlo. Monte
Carlo reuses `wilson_interval`; p=0 gives zero failures; p_L increases with
noise; larger distance suppresses p_L as evidence (not a threshold claim).
