# D7 signature scaling and paired-decoder study

## Scope and scientific status

This is a bounded research measurement of the existing circuit-signature and decoder implementation after temporal-signature commit `d76a26c63f47969cf14314f1977bdb5a7a6246db`. No decoder, extraction, registry or existing test was changed. The instrument is [`backend/scripts/d7_study.py`](../backend/scripts/d7_study.py). Results below describe the **implemented Pauli-error-frame model**, not a validated physical extraction circuit, trained decoder, threshold or hardware benchmark.

The important limitation is not merely sampling uncertainty: the source's `fitted_pair` is an independent-pair extraction decomposition, **not a trained numerical fit**, and its physical readout circuit is not generally the same quantum measurement instrument as a single full stabilizer readout. An exact small-circuit counterexample below preserves the full parity distribution but destroys coherence. Production simulations do not represent that back-action.

The historical d7 baseline result (1,344 nontrivial round-1 fault injections, control 28 failures, correlation 0) is reproduced for three total rounds. It must **not** be described as correction of every temporal placement: exhaustive final-round gate injections leave 116/1,008 correlation failures for baseline and 107/1,008 for fitted extraction under the existing outcome contract.

## Reproducibility and measurement design

All commands ran from the repository root, using Python 3.13.14, NumPy 2.5.2 and SciPy 1.17.1 on Windows 11 x64. Each JSON records exact command, UTC start/end, interpreter path/version, package versions, git HEAD, seven relevant source SHA-256 hashes and the script SHA-256. Source hashes are checked again at experiment completion. These are local wall-clock measurements on a shared development machine, not isolated benchmark distributions; no confidence interval is claimed for timings.

```text
python backend/scripts/d7_study.py --phase oracle --output docs/data/d7_oracle.json
python backend/scripts/d7_study.py --phase mc --trials 20 --output docs/data/d7_mc_pilot.json
python backend/scripts/d7_study.py --phase scaling --output docs/data/d7_scaling.json
python backend/scripts/d7_study.py --phase single --output docs/data/d7_single_faults.json
python backend/scripts/d7_study.py --phase mc --trials 1000 --output docs/data/d7_mc.json
```

No project test, build, lint or formatter command was run for this study. The preserved script is research instrumentation, not another runner, registry or decoder. Its MC observer wraps the **existing** `simulate_decoder_comparison_mc` calls to record timing and paired outcomes, restoring originals afterward; it does not copy the sampling/decoding loop.

The 20-trial-per-cell runtime pilot is retained separately and is **not additional statistical evidence**: its seeds overlap the first 20 trials of the 1,000-trial run. The pilot took 10.619 s including database preparation; its 18 measured MC loops totaled 4.172 s, with the slowest cell 0.786 s. Linear projection of loop time to 1,000 trials/cell was 208.577 s. This made the maximum requested bounded sample, 1,000 trials per cell, practical. There are 18 cells (two extractions × three distances × three noise regimes), with three decoder outcomes on every identical sampled circuit.

## Cold-cache signature scaling (three rounds)

Source: [`data/d7_scaling.json`](data/d7_scaling.json). Clear the signature database cache and collect garbage before **each** measurement. Build code geometry before timing. First build without allocation tracing, then clear the cache again and repeat with `tracemalloc`. One measurement of each kind per cell; `collect_subparities=False`. Warm Python imports, code geometry and other module initialization are not “cold process” costs.

| Extraction | d | Mid/final signatures | Mid/final enumerated faults | Cold untraced s | Cold traced s | Traced current MiB | Traced peak MiB |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 3 | 120 / 120 | 200 / 144 | 0.0678 | 0.3315 | 0.218 | 0.227 |
| baseline | 5 | 400 / 400 | 648 / 480 | 0.3256 | 2.6125 | 1.056 | 1.097 |
| baseline | 7 | 840 / 840 | 1,344 / 1,008 | 1.6161 | 10.9847 | 2.453 | 2.565 |
| fitted_pair | 3 | 116 / 116 | 228 / 144 | 0.1217 | 0.9760 | 0.230 | 0.239 |
| fitted_pair | 5 | 384 / 384 | 760 / 480 | 0.9298 | 8.1237 | 1.118 | 1.157 |
| fitted_pair | 7 | 804 / 804 | 1,596 / 1,008 | 3.6972 | 35.9421 | 2.400 | 2.505 |

MiB means bytes / 1,048,576. All reported null-location counts are zero. Allocation values are **Python-traced allocations, not process RSS**, native memory, total decoder memory or an upper bound on those quantities. Lazy translated-signature/event caches are not materialized by these database-only measurements. Tracing substantially increases runtime and must not be presented as production generation time. The complete scaling phase took 65.893 s; source hashes were unchanged. Three distances and one observation per cell do not establish an asymptotic complexity law.

## Exhaustive single-fault placements

Source: [`data/d7_single_faults.json`](data/d7_single_faults.json), including every failing tuple and both outcome labels. There were **12,816 deterministic injections** total. At each d=3/5/7 and both modes, every enumerated reset/preparation/readout/CNOT fault was evaluated at injection rounds 1 and 2; every CNOT fault was evaluated at final round 3. This exhausts the eligible single-fault placements for this three-round experiment, **not** arbitrary round counts, schedules, code states, modes or multi-fault histories.

The production hook only injects in round 1. For injection round t, the script runs the existing production circuit for `3-t+1` rounds with one forced fault, then prepends `t-1` clean syndrome rounds and translates hook timestamps. This is an exact clean-prefix construction **within this zero-background Pauli-frame model**: its data/ancilla frames start clean and it has no persistent ideal-state dynamics. It is not a simulation of physical pair-measurement back-action. Final-round injections are gate-only because reset/prep/readout are ideal in the sampled production final round.

Both decoders use the historical deterministic diagnostic pricing, all four noise parameters zero, seed 0. “Failure” means the existing decoder's `success=False` logical-outcome classification, not an independently reconstructed logical process fidelity. The enumeration includes diagnostic reset Y/Z injections even though the sampled reset channel only produces X; this is an unweighted mechanism count, not a noise-distributed failure probability. All enumerated rows were nontrivial by the existing data-error/detection-event criterion.

| Extraction | d | Round 1 cases: control / correlation failures | Round 2 cases: control / correlation failures | Final gate cases: control / correlation failures |
|---|---:|---:|---:|---:|
| baseline | 3 | 200: 16 / 2 | 200: 16 / 2 | 144: 41 / 37 |
| baseline | 5 | 648: 20 / 0 | 648: 20 / 0 | 480: 128 / 80 |
| baseline | 7 | 1,344: 28 / 0 | 1,344: 28 / 0 | 1,008: 268 / 116 |
| fitted_pair | 3 | 228: 36 / 12 | 228: 36 / 12 | 144: 41 / 35 |
| fitted_pair | 5 | 760: 20 / 0 | 760: 20 / 0 | 480: 128 / 74 |
| fitted_pair | 7 | 1,596: 28 / 0 | 1,596: 28 / 0 | 1,008: 268 / 107 |

Example unresolved d7 final injections: baseline `('X',3,'cnot',0,'c','Y')`, fitted `('X',3,'cnot',0,'t','Z')`; both decoders label each `LOGICAL_Z`. These are **different tuple semantics** across modes as detailed below. Counts alone do not establish whether the residuals are information-theoretically irreducible. No decoder fix or suppression was attempted. The experiment took 66.580 s, with exact per-placement timings in JSON; source hashes were unchanged.

## Paired Monte Carlo results (three rounds, 1,000 trials per cell)

Source: [`data/d7_mc.json`](data/d7_mc.json). All 18,000 trials ran through `simulate_decoder_comparison_mc`; each trial produced control, correlation-single and correlation-two-fault outcomes from the same sampled history. The original function supplied Wilson 95% intervals (z=1.96), retained at full precision in JSON. Observer outcome counts were checked against the function's returned counts for every cell.

Noise tuples are `(p_gate,p_readout,p_reset,p_prep)`: `gate_low=(.001,0,0,0)`, `combined_low=(.001,.001,.001,.001)`, `combined_mid=(.005,.005,.003,.003)`. For distance d and regime index i=0/1/2 in that order, cell seed is `20260917 + 100000*d + 10000*i`; trial j=0..999 uses `cell_seed + 7919*j`. Thus d3 seeds are 20560917/20570917/20580917; d5 20760917/20770917/20780917; d7 20960917/20970917/20980917, reused for the other extraction without claiming cross-extraction matched circuits.

Entries are failures out of 1,000, then `(percentage [Wilson95 lower, upper])`. Discordance is **control-only fails / correlation-single-only fails**, not independent samples. Full 2×2 tables are saved for single and two-fault versus control.

| Extraction | d | Regime | Control | Correlation single | Correlation two-fault | Discordance single |
|---|---:|---|---|---|---|---:|
| baseline | 3 | gate_low | 21 (2.1 [1.38, 3.19]) | 11 (1.1 [0.62, 1.96]) | 12 (1.2 [0.69, 2.09]) | 10 / 0 |
| baseline | 3 | combined_low | 21 (2.1 [1.38, 3.19]) | 16 (1.6 [0.99, 2.58]) | 16 (1.6 [0.99, 2.58]) | 5 / 0 |
| baseline | 3 | combined_mid | 117 (11.7 [9.85, 13.84]) | 89 (8.9 [7.29, 10.83]) | 90 (9.0 [7.38, 10.93]) | 31 / 3 |
| baseline | 5 | gate_low | 51 (5.1 [3.90, 6.64]) | 36 (3.6 [2.61, 4.94]) | 38 (3.8 [2.78, 5.17]) | 17 / 2 |
| baseline | 5 | combined_low | 59 (5.9 [4.60, 7.54]) | 34 (3.4 [2.44, 4.71]) | 31 (3.1 [2.19, 4.37]) | 25 / 0 |
| baseline | 5 | combined_mid | 224 (22.4 [19.92, 25.09]) | 190 (19.0 [16.69, 21.55]) | 189 (18.9 [16.59, 21.44]) | 37 / 3 |
| baseline | 7 | gate_low | 97 (9.7 [8.02, 11.69]) | 60 (6.0 [4.69, 7.65]) | 57 (5.7 [4.43, 7.31]) | 40 / 3 |
| baseline | 7 | combined_low | 101 (10.1 [8.38, 12.12]) | 64 (6.4 [5.04, 8.09]) | 65 (6.5 [5.13, 8.20]) | 38 / 1 |
| baseline | 7 | combined_mid | 349 (34.9 [32.01, 37.91]) | 340 (34.0 [31.13, 36.99]) | 340 (34.0 [31.13, 36.99]) | 13 / 4 |
| fitted_pair | 3 | gate_low | 24 (2.4 [1.62, 3.55]) | 10 (1.0 [0.54, 1.83]) | 11 (1.1 [0.62, 1.96]) | 14 / 0 |
| fitted_pair | 3 | combined_low | 37 (3.7 [2.70, 5.06]) | 25 (2.5 [1.70, 3.66]) | 25 (2.5 [1.70, 3.66]) | 26 / 14 |
| fitted_pair | 3 | combined_mid | 161 (16.1 [13.95, 18.51]) | 154 (15.4 [13.30, 17.77]) | 150 (15.0 [12.92, 17.35]) | 84 / 77 |
| fitted_pair | 5 | gate_low | 49 (4.9 [3.73, 6.42]) | 34 (3.4 [2.44, 4.71]) | 34 (3.4 [2.44, 4.71]) | 17 / 2 |
| fitted_pair | 5 | combined_low | 58 (5.8 [4.51, 7.42]) | 35 (3.5 [2.53, 4.83]) | 34 (3.4 [2.44, 4.71]) | 25 / 2 |
| fitted_pair | 5 | combined_mid | 259 (25.9 [23.28, 28.70]) | 242 (24.2 [21.65, 26.95]) | 239 (23.9 [21.36, 26.64]) | 38 / 21 |
| fitted_pair | 7 | gate_low | 103 (10.3 [8.57, 12.34]) | 65 (6.5 [5.13, 8.20]) | 58 (5.8 [4.51, 7.42]) | 43 / 5 |
| fitted_pair | 7 | combined_low | 112 (11.2 [9.39, 13.31]) | 80 (8.0 [6.47, 9.85]) | 82 (8.2 [6.66, 10.06]) | 32 / 0 |
| fitted_pair | 7 | combined_mid | 386 (38.6 [35.63, 41.66]) | 383 (38.3 [35.34, 41.35]) | 383 (38.3 [35.34, 41.35]) | 23 / 20 |

The baseline low-noise point differences grow from 1.0 percentage point at d3 gate-only to 3.7 points at d7, but **logical-error point estimates also increase with distance** (baseline correlation gate-only 1.1%, 3.6%, 6.0%). These fixed-three-round, three-distance observations are not distance suppression or a threshold. At d7 combined-mid the net gain is only 9/1,000 baseline and 3/1,000 fitted; fitted discordance is 23 improvements against 20 harms. The d3 fitted combined-mid row similarly has 84 improvements and 77 harms. Neither a small positive point difference nor overlapping marginal intervals justifies an operational-significance claim. No new hypothesis test, multiple-comparison claim or trained-fit claim is made. The paired measurements do not cure the extraction/back-action or likelihood limitations above.

### Per-decoder overhead

Every timing below is for 1,000 trials, in seconds. Dividing decoder totals by 1,000 gives seconds/trial; equivalently each printed decoder total is numerically its average milliseconds/trial. Database generation is outside each MC cell's timer (prebuilt); first-use lazy signature caches can enter the first trial. Cell wall time includes circuit sampling and all three decodes. `C/S/T` denotes control/single/two-fault. Ratios compare the entire candidate call to control, including its internal control decode. They are not incremental pure-attribution cost. Instrumentation bookkeeping and shared-machine contention make these descriptive timings, not stable performance bounds.

| Extraction | d | Regime | Cell wall s | Decoder seconds C / S / T | S/C / T/C |
|---|---:|---|---:|---:|---:|
| baseline | 3 | gate_low | 0.833 | 0.064 / 0.151 / 0.208 | 2.37 / 3.27 |
| baseline | 3 | combined_low | 0.887 | 0.064 / 0.152 / 0.225 | 2.38 / 3.52 |
| baseline | 3 | combined_mid | 2.645 | 0.112 / 0.737 / 1.172 | 6.56 / 10.43 |
| baseline | 5 | gate_low | 4.785 | 0.226 / 1.185 / 1.829 | 5.25 / 8.10 |
| baseline | 5 | combined_low | 5.991 | 0.247 / 1.534 / 2.413 | 6.20 / 9.75 |
| baseline | 5 | combined_mid | 13.301 | 0.367 / 4.595 / 6.556 | 12.52 / 17.87 |
| baseline | 7 | gate_low | 12.782 | 0.537 / 3.825 / 5.683 | 7.12 / 10.58 |
| baseline | 7 | combined_low | 16.387 | 0.608 / 5.009 / 7.464 | 8.24 / 12.28 |
| baseline | 7 | combined_mid | 34.320 | 1.048 / 13.102 / 16.950 | 12.51 / 16.18 |
| fitted_pair | 3 | gate_low | 1.386 | 0.087 / 0.216 / 0.302 | 2.47 / 3.46 |
| fitted_pair | 3 | combined_low | 1.660 | 0.091 / 0.268 / 0.394 | 2.95 / 4.33 |
| fitted_pair | 3 | combined_mid | 3.253 | 0.125 / 0.878 / 1.336 | 7.05 / 10.73 |
| fitted_pair | 5 | gate_low | 5.383 | 0.223 / 1.191 / 1.812 | 5.35 / 8.14 |
| fitted_pair | 5 | combined_low | 7.082 | 0.247 / 1.674 / 2.587 | 6.79 / 10.49 |
| fitted_pair | 5 | combined_mid | 14.983 | 0.397 / 4.921 / 7.102 | 12.41 / 17.91 |
| fitted_pair | 7 | gate_low | 14.785 | 0.574 / 4.062 / 5.953 | 7.08 / 10.37 |
| fitted_pair | 7 | combined_low | 19.574 | 0.650 / 5.598 / 8.419 | 8.61 / 12.96 |
| fitted_pair | 7 | combined_mid | 38.485 | 1.227 / 14.368 / 17.898 | 11.71 / 14.59 |

Total measured cell wall time was 198.522 s; the full MC phase including database preparation and serialization took 205.754 s. Source hashes were unchanged. Single-decoder overhead ranged from 2.37× to 12.52×; two-fault overhead from 3.27× to 17.91×. The optional two-fault outcomes are retained as existing research instrumentation; this bounded run does not reopen the closed decoder-complexity direction.

## Exact fitted-pair circuit semantics

Source: [`data/d7_oracle.json`](data/d7_oracle.json). The independent oracle constructs a complex state vector, applies ideal H/CNOT permutations and sums the outer products of actual ancilla-measurement branches. It does not call production error propagation or decoding.

It exercises one isolated weight-4 Z check with input

\[
|\psi\rangle=(|0000\rangle+|0101\rangle)/\sqrt2.
\]

Baseline uses one reset ancilla coupled to all four data qubits and then read out; fitted uses two independent reset ancillas coupled to pairs (0,1) and (2,3), both read out, with only their XOR retained. This is the structure written in `circuit_extraction.py:463-470, 540-605`. Both components have even total Z parity, but their pair parities differ. For an X check, conjugate the data input by H on all four qubits and use the source's H–ancilla-controlled-CNOT–H extraction.

| Isolated check | Extraction | Observed ancilla outcomes | Full XOR parity | Squared fidelity to input after forgetting readout | Purity |
|---|---|---|---|---:|---:|
| Z | baseline | 0 with probability 1 | 0 with probability 1 | 1 | 1 |
| Z | fitted_pair | 00 and 11, each probability 1/2 | 0 with probability 1 | 1/2 | 1/2 |
| X | baseline | 0 with probability 1 | 0 with probability 1 | 1 | 1 |
| X | fitted_pair | 00 and 11, each probability 1/2 | 0 with probability 1 | 1/2 | 1/2 |

Numerical deviations from these values were below 3×10^-15. Even when the pair records are discarded, measurement (or tracing out those distinguishing ancillas) dephases the superposition. In projector terms the two maps for full even parity differ:

\[
\mathcal E_{\rm full}(\rho)=P_+\rho P_+,\quad
\mathcal E_{\rm pair,+}(\rho)=P_{++}\rho P_{++}+P_{--}\rho P_{--}.
\]

The cross-coherence terms between pair sectors survive only in the first map. Equality of XOR parity probabilities is therefore insufficient for nondemolition extraction equivalence. This counterexample is for an **isolated check**; it does not quantify full-code logical fidelity or establish a threshold.

Production `_measure_check_fitted` initializes ancilla **error-frame** bits to zero (`circuit_extraction.py:526-527`), propagates those bits and appends modeled pair flips (`:593-605`). They are not Born measurements sampled from a data density matrix. Its no-error syndrome results and fitted-mode MC curves cannot validate the missing quantum back-action. The oracle ran in 0.0054 s; source hashes were unchanged.

## Source audit and interpretation limits

Links refer to the source state fingerprinted in the JSON, not a newly introduced model.

1. **Extraction, not learning.** [`circuit_extraction.py`](../backend/app/qec/circuit_extraction.py), lines 426-489, defines a fan-in-at-most-two decomposition and engineering motivation. There is no training dataset, fitted parameter optimization or holdout accuracy in this experiment. Do not use the name to imply machine learning.
2. **Gate noise is pre-CNOT in the actual implementation.** Baseline [`circuit_level.py`](../backend/app/qec/circuit_level.py):135-171 and fitted `circuit_extraction.py:553-589` apply sampled and forced Pauli noise before propagating the gate. Descriptions elsewhere saying “after CNOT” are not the executed contract. In general these timing conventions are not interchangeable for independent single-participant channels.
3. **Forced participant naming differs.** Baseline `circuit_level.py:139-147` uses actual control/target names: for X checks `c=ancilla,t=data`; for Z checks `c=data,t=ancilla`. Fitted `circuit_extraction.py:559-562` uses `c=data,t=ancilla` for both check kinds. Both participants are enumerated, so coverage totals remain exhaustive, but cross-mode fault tuples must not be interpreted as identical physical faults. Baseline applies the last forced Pauli at a gate location (`:150-151`); fitted XOR-composes them (`:567-569`). This contradicts the historical all-sites-fixed statement in AD-025. This study forces only one fault per trial, so that overwrite issue does not affect its exhaustive counts; stochastic MC does not use forced faults.
4. **Reset likelihood mismatch.** [`circuit_signatures.py`](../backend/app/qec/circuit_signatures.py):236-240 enumerates reset X/Y/Z, and `FaultSignature.probability` at :134-140 gives every aggregated reset count weight `p_reset`. Actual reset sampling only applies X (`circuit_level.py:119-120`; `circuit_extraction.py:532-534`). Thus the database prices unsupported Y/Z reset contributions; it is not an exact likelihood catalogue of the sampled reset channel. Gate/preparation depolarizing alternatives receive p/3; even apart from reset, bucket probabilities are first-order sums, not an exact multi-fault posterior. Gate-only cells avoid nonzero reset likelihood weights; combined-noise cells do not.
5. **Final readout assumption.** `circuit_level.py:342-350` removes final reset/prep/readout noise but leaves gate faults during the sequential final check circuit. Its comment claiming the final outcome is exactly the net data syndrome is not generally guaranteed: later gate faults can change data after an earlier check was measured. [`repeated_round.py`](../backend/app/qec/repeated_round.py):338-341 uses the last observed syndrome for its final residual stage. This is relevant to the final-placement failures; the present study reports outcomes without asserting a complete causal explanation or altering the final-boundary model.
6. **Paired uncertainty is not two independent estimates.** The existing comparison function (`correlation_decoder.py:451-468`) generates one circuit history per trial and runs all three decoders on it. Marginal Wilson intervals are not confidence intervals for the paired difference, and overlap/non-overlap is not a paired significance test. Discordant pair counts are retained so directional changes are visible without that mistake. Different extraction modes use the same nominal seed but different gate/ancilla RNG consumption; only the decoders **within a cell** receive identical samples.
7. **Timing field caveat.** Existing `correlation_aware.decode_seconds` sums both the single- and two-fault decoder calls (`correlation_decoder.py:460-469`); it is not single-decoder overhead. The script's separate instrumented times are the appropriate overhead measurements. Correlation calls internally execute their own control decode; their total time, including that work, is retained rather than subtracted.

This report leaves closed AD-025 two-fault/exposure-reduction research closed. The existing two-fault column is measured because the canonical paired instrument already executes it, not as a proposal to add decoder complexity or a production mode. Older numerical tables and claims are not independently revalidated or promoted by this bounded study.

## Output integrity

After all experiments, an independent arithmetic check recomputed Wilson intervals directly from each saved failure count, verified both paired 2×2 tables against the returned marginals in every cell, checked the 18×1,000 MC and 12,816 injection totals, and verified all five result files against current source/script SHA-256 hashes. All checks passed; every saved experiment reports unchanged source hashes. This checks report/data consistency, not independent correctness of the production decoder. There is no claim that every enumerated fault was corrected, that fitted extraction preserves encoded states, or that the model establishes an error threshold.
