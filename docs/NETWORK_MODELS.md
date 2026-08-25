# Network & Channel Models

Implementation: `backend/app/network/*`, `backend/app/quantum/channels.py`,
`backend/app/quantum/channel_algebra.py`. Validation: `test_network.py`,
`test_channel_algebra.py`, `test_purification.py`, extended tests.

## Link physics

Fiber survival: η = 10^(−α·d/10) · detector_efficiency, α in dB/km, d in km.
Limiting cases tested: d=0 → η=det_eff; 100 km at 0.2 dB/km → 0.01.
Attempt duration: round-trip propagation (5 µs/km each way) + 10 µs processing.

## Entanglement representation

Pairs are Werner states ρ(q) = q|Φ⁺⟩⟨Φ⁺| + (1−q)·I/4 with F=(3q+1)/4,
q=(4F−1)/3. Memory aging: q(age)=q₀·exp(−age/T_mem); fully aged pairs reach
F=1/4 (maximally mixed — no correlation). Pairs expire at memory_coherence_ns.

## Swapping

Idealized Bell measurement: Werner parameters multiply,
q_out = q_a·q_b ⇒ F_out=(3 q_a q_b + 1)/4. Limits validated: (1,1)→1;
(x,½)→½·... exact identity F_out(F₁,F₂)=(3·q₁q₂+1)/4. Configurable success
probability; failure destroys both pairs.

## Purification

Inputs: two IDENTICAL Werner-form pairs, F∈[½,1]. Asymmetric inputs are
rejected (never silently approximated).

| Protocol | Success probability | Output fidelity |
|----------|--------------------|-----------------|
| BBPSSW | p = F² + 2F(1−F)/3 + 5((1−F)/3)² | F' = (F² + ((1−F)/3)²)/p |
| DEJMPS | p = (F + (1−F)/3)² | F' = (F² + ((1−F)/3)²)/(F+(1−F)/3)² |

Validated fixed points: F=1→(1,1); F=½ BBPSSW→(½); DEJMPS at F=½ gives ⅝.
Resource accounting: every attempt consumes exactly both input pairs;
failure ends the chain (no surviving entanglement). Network-engine
integration purifies only when two live same-segment pairs have equal
fidelity (within 1e−6); otherwise skipped honestly.

## Repeaters

Levels L0 (direct), L1 (swapping), L2 (swapping+DEJMPS purification).
Comparison studies report success probability with Wilson CIs, mean fidelity,
latency, and pairs-generated-per-success. Trend test: chained repeaters do
not underperform direct transmission at long distance beyond stochastic
margin.

## QKD over lossy channels

BB84 with per-signal survival η; lost signals never enter sifting (passive
loss). Optional dark counts register uniform-random bits (crude approximation;
no time-window modeling). Secret-fraction ESTIMATE r ≥ 1 − 2·h₂(QBER)
(asymptotic one-way bound) is labeled an estimate — NOT a finite-key proof.

## Chaos injection

Poisson-rate node/link failures with configurable recovery time; capped by
`max_chaos_events`. Zero-fault chaos configs reproduce baseline behavior
(regression-tested).

## Limitations

- No multiplexing, wavelength modeling, or time-window detector physics.
- Swap/purification assume Werner-form states and ideal local operations.
- Fairness (Jain index) computed over per-source throughput only.
