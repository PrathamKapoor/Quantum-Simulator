# QuantumLab expansion research

## Scope and provenance

The session began on `main` at `0c19faf1aa3b8db0e06569b44ae9cee11c6afc44` with six uncommitted expansion experiments already present: Gram-Schmidt, purification, entanglement swapping, QEC codes, state tomography and Rabi oscillations. Those are not new work from this session. Source inspection found 24 Book Lab entries, 41 registry entries and 45 chapter-map rows (44 labeled VALIDATED, one EXPERIMENTAL). The historical 46/51 score was not the chapter-table count.

This expansion adds `book_helstrom` and `book_channel_algebra`, repairs tomography/Rabi validation, and preserves NumPy booleans in result serialization. No registry, worker, validation framework or UI page was added. The existing Book Lab metadata list is static, not dynamically discovered from the server; two entries were added there and in `RUNNER_REGISTRY`.

## Sources actually consulted

| Source | Topic and relevance | Repository gap or decision |
|---|---|---|
| [IBM: discrimination and tomography](https://quantum.cloud.ibm.com/learning/en/courses/general-formulation-of-quantum-information/general-measurements/discrimination-and-tomography) | Helstrom spectral measurement, optimal success; Pauli inversion may be non-PSD | Add binary discrimination; distinguish raw inversion from physical estimation |
| [Qiskit Experiments: state tomography](https://qiskit-community.github.io/qiskit-experiments/manuals/verification/state_tomography.html) | Raw/fitted eigenvalues and physicality correction | Preserve raw reconstruction and identify the estimator; do not call it MLE |
| [IBM: Simon](https://quantum.cloud.ibm.com/learning/en/courses/fundamentals-of-quantum-algorithms/quantum-query-algorithms/simon-algorithm) | GF(2) equations, sampling and rank | Existing algorithm; direct educational UI/rank study remains an opportunity |
| [IBM: phase estimation](https://quantum.cloud.ibm.com/learning/en/courses/fundamentals-of-quantum-algorithms/phase-estimation-and-factoring/phase-estimation-procedure) | Exact dyadic and non-dyadic phases, QFT | Existing backend; direct QFT/QPE UI exposure is incomplete |
| [IBM: Grover iterations](https://quantum.cloud.ibm.com/learning/en/courses/fundamentals-of-quantum-algorithms/grover-algorithm/number-of-iterations) | Marked-set-dependent rotation and overshoot | Existing single-target implementation; multi-target study deferred |
| [IBM: QEC curriculum](https://quantum.cloud.ibm.com/learning/en/courses/foundations-of-quantum-error-correction) | Repetition, Shor, CSS, stabilizers and surface codes | These already substantially exist; prioritize logical-superposition validation over adding code names |
| [IBM: variational design](https://quantum.cloud.ibm.com/learning/en/courses/variational-algorithm-design) | Reference state, ansatz, objective and optimizer | Existing VQE/QAOA/QML; better controlled studies rather than duplicate algorithms |
| [IBM: channels](https://quantum.cloud.ibm.com/learning/en/courses/general-formulation-of-quantum-information/quantum-channels/introduction) | Physical maps and representations | Promote existing channel algebra into an executable study |
| [Qiskit Finance: amplitude estimation](https://qiskit-community.github.io/qiskit-finance/tutorials/00_amplitude_estimation.html) | Preparation/reflections and measurement-derived estimates | Genuine missing algorithm; larger than the selected exact studies |
| [Qiskit characterization index](https://qiskit-community.github.io/qiskit-experiments/stable/0.6/apidocs/mod_characterization.html) | Pulse-amplitude Rabi calibration and Ramsey | Different from this repository's ideal RWA time evolution; no pulse-calibration claim |
| [QuTiP tomography implementation](https://qutip.org/docs/4.7/modules/qutip/tomography.html) | Superoperator-to-process-matrix conversion | Representation conversion is not measurement-based process tomography |
| [Quirk manual](https://github.com/Strilanc/Quirk/wiki/How-to-use-Quirk) | Bloch/density/amplitude displays, ensemble versus sampled observations | Educational value in exposing raw versus inferred quantities; no UI redesign needed |

PennyLane MBQC and discrimination pages yielded metadata only, not technical bodies; they are not used as scientific authority. External technical cryptography/networking research was not completed; no new security theorem, finite-key guarantee or networking formula is claimed. No external code or substantial prose was copied.

## Candidate gap matrix

P = primitive availability; R = registered experiment; V = existing test evidence (not comprehensive proof). H/M/L are relative educational/UI value and implementation difficulty. A = selected or strong bounded opportunity, B = reusable primitive work, C = larger study, D = low incremental value. Availability is the session-start source inventory.

| Candidate | Already exists / P | R | V | UI value | Education | Difficulty | Priority / decision |
|---|---|---|---|---|---|---|---|
| Helstrom discrimination | No optimizer; density/POVM P | No | POVM only | H | H | L | A/B selected |
| Channel algebra | Yes P | Scan only | Channel tests | H | H | L | A selected promotion |
| Physical qubit tomography | Raw inversion only | Yes | Defaults only | H | H | M | A selected correction |
| Rabi sampled validation | RWA P | Yes | Defaults only | M | H | L | A selected correction |
| BV noisy/explanatory study | BV exists | No dedicated book R | Recovery tests | M | M | L | D, algorithm already present |
| Simon rank acquisition | Dense oracle/solver | No dedicated R | Algorithm tests | H | H | M | A deferred promotion |
| QFT approximation study | QFT/inverse/cutoff/DFT | No dedicated R | DFT tests | H | H | M | A deferred promotion |
| QPE resolution | Builder/basis-state runner | Indirect factoring | QPE tests | H | H | M | A, preparation contract needed |
| Multi-target Grover | Single target only | Grover studies | Single-target tests | M | H | M | A/B, new marked-set logic |
| Amplitude estimation/counting | QPE/Grover blocks only | No | No estimator tests | H | H | H | C, bounded future algorithm |
| VQE convergence | VQE/H2 exist | Yes | Optimization tests | M | H | M | D, avoid duplicate VQE |
| QAOA depth/expectation | MaxCut QAOA exists | Callable only | Optimization tests | M | H | M | A promotion deferred |
| Logical QEC superpositions | Five code families | Yes | Basis recovery | H | H | M | A, deeper validation needed |
| Surface/fault-tolerant QEC | Extensive specialized stack | Yes | Extensive tests | L | H | H | D, not a missing subsystem |
| QKD finite-key rigor | BB84/B92/E91 models | Yes | Protocol tests | M | H | H | C, security research prerequisite |
| Noisy teleportation | Ideal branches | Yes | Ideal tests | H | H | M | A, channel characterization deferred |
| Noisy swapping bridge | Ideal + Werner network models | Yes | Separate tests | H | H | H | C, model bridge needs derivation |
| Distillation cross-check | BBPSSW/DEJMPS recurrence | Yes | Test file exists | M | H | H | C, independent formula audit needed |
| Information contraction | Metrics/channels exist | Reports only | Metric tests | H | H | M | A promotion deferred |
| Multi-state discrimination | POVM but no optimizer | POVM demo | POVM tests | M | H | H | C, binary first |
| Process/multi-qubit tomography | No general estimator | No | No | H | H | H | C, CP/TP estimation work |
| Adaptive MBQC | Graph/X measurement only | Cluster demo | Graph tests | H | H | M/H | A/B, branch/feed-forward logic needed |
| Finite-window Landau-Zener | Adiabatic blocks | No | No LZ tests | M | H | H | C, numerical convergence work |
| Continuous-time walk | Coined walk only | Callable walk | Walk tests | M | M | M | D, existing walk limitations first |
| Lindblad/Ramsey | Kraus channels, no generator | No | No dedicated tests | H | H | H | C, larger dynamics scope |

Gram-Schmidt, mixed-state purification, Schmidt decomposition, density matrices, fidelity, trace distance, entropy, negativity, concurrence, BB84/B92/E91, teleportation and superdense coding already exist. They were not reimplemented.

## Executable contracts and independent oracles

### Helstrom

`book_helstrom(config, seed)` accepts finite `theta` (default pi/2), `phi` (0.4), `prior` (0.5 in [0,1]) and `mixing` (0 in [0,1]). The alternatives have Bloch vectors r0=(1-mixing)z and r1=(1-mixing)(sin(theta)cos(phi), sin(theta)sin(phi), cos(theta)). Angles are radians. No randomness or shot count is used.

`helstrom_measurement(rho, sigma, prior)` returns two effects from the nonnegative eigenspace of prior*rho-(1-prior)*sigma and its complement. Inputs require equal dimensions, PSD and unit trace within core tolerance. Born probabilities use existing `povm_probabilities`.

The runner's independent qubit oracle is
`Psuccess = (1 + max(abs(2*prior-1), norm(prior*r0-(1-prior)*r1)))/2`.
The achieved success is computed from conditional measurement probabilities, not copied from this formula. Tests also use the pure-state overlap formula and commuting mixed-state classical optimum. Outputs expose effects, conditional probabilities, achieved error and prior-only baseline. This is binary minimum-error discrimination, not unambiguous or multi-state discrimination.

### Channel algebra

`book_channel_algebra` accepts `flip_probability` (0.3) and `gamma` (0.4), each in [0,1]. It reuses the existing Kraus constructors, composition, Choi validation, operator-basis composition check, process fidelity and average gate fidelity. No sampling.

For bit flip followed by damping, the ground-state output differs from reverse order by trace distance p*gamma. Identity-reference process fidelity has the independent closed form `((1-p)*(1+sqrt(1-gamma))**2+p*gamma)/4`. Average fidelity is independently evaluated over the six axial pure qubit states, an exact state 2-design. The Choi convention is unnormalized: trace J=2, output partial trace I. This does not claim arbitrary-unitary reference validation, process tomography or diamond norm.

### Tomography correction

The existing three-axis binomial sampling remains. Raw linear inversion is retained in `raw_bloch_finite`; the physical estimate is `r/max(1, norm(r))`. This is Euclidean projection onto the Bloch ball, not maximum likelihood and not unbiased. PSD, ideal inversion and non-increase of Euclidean distance to the known target are checked. The shot scan reports each realization and analytic raw RMS `sqrt(sum(1-r_i**2)/shots)`. It no longer requires monotonically improving independent samples. Statistical-bound status is reported separately from deterministic invariant validation.

Regression: shots=10, seed=1 previously yielded r=(0.8,0,0.8), minimum eigenvalue -0.0656854. Projection produces a physical boundary state while preserving the raw result.

### Rabi correction

The existing exact-step RWA propagation remains. Every detuning is checked against the analytic law on the actual sampled grid; sampled peaks are not compared with unattainable continuous maxima at a fixed tolerance. First-maximum timing is checked within one timestep. Resonant fields use the actual zero-detuning row, or null when none is supplied. Tests cover detuning=1, steps=101. This is not a laboratory-frame or time-dependent integrator validation.

## Verification and remaining limitations

Focused primitive/runner tests and full browser checks exercise the selected additions through the existing architecture. The session report records exact command results, including baseline invocation problems and unrelated lint findings. No claim is made that every historical VALIDATED row has equally strong oracles. Remaining gaps include adaptive MBQC, direct Simon/QFT/QPE controls, arbitrary-logical-state QEC recovery, corrected-target swap fidelity, and general tomography. The original PDF was not re-extracted during this session; conflicting page references remain unverified rather than silently invented.
