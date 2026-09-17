# QuantumLab — McMahon book coverage matrix

This is a documentation-only source reconciliation, not an experiment registry. The companion [book_coverage.json](book_coverage.json) uses schema `quantumlab.book-coverage.v2`. All **413 original top-level records** are retained, with stable IDs, current status, legacy metadata, source existence/observation, classification and explicit limitations.

**No whole-book validation or completeness percentage is claimed.** The 413 records are 134 section locators, 119 numbered examples, 126 top-level exercises and 34 occurrence-ordered You Try It entries—not a complete substantive-concept or subpart denominator. The additional **563 task-output groups** and **92 body/figure groups** are identifiable records in the JSON, not invented numbered tasks. Some groups contain multiple related outputs; neither population is an exhaustive atomic inventory.

## Source and provenance

- David McMahon, *Quantum Computing Explained*, Wiley-Interscience, 2008; ISBN 978-0-470-09699-4.
- Original local PDF: `C:/Users/LENOVO/Downloads/David McMahon - Quantum Computing Explained-Wiley-Interscience _, IEEE Computer Society (2008).pdf`.
- SHA256: `89b670064e19d5e460ceab7bdfe0ddc3348b8e7a597d1533d7cb3266e7e5b636` (supplied by the coordinating audit; not recomputed by this documentation integrator).
- Complete extracted chapter bodies were read by `SourceCh1to5`, `SourceCh6to10` and `SourceCh11to15`; `BookSourceScout` established original-source access. Their session report URIs and chapter page ranges are recorded in JSON. The integration is a non-atomic code/test/source snapshot, not a fresh execution.
- Page references are printed pages. At verified locations, one-based PDF page = printed page +19; a zero-based library index uses +18.
- **No source pages were rasterized by these auditors.** Text observation does not resolve diagram geometry, all radicals, signs, inequalities or matrix layout. Extractor version/options and a portable reproduction script were not recorded; session agent URIs are not permanent portable archives.
- The invalid legacy `.pytest_cache/book_inventory.json` and sparse cached index are **not authoritative provenance or required inputs**. This document is grounded in the original-PDF reports.

## Status policy and accounting

Each source row has an explicit status; none inherits a status from a topic runner, UI badge or suite total. `PRIMITIVE_ONLY` includes partial generic experiments when the complete source task is not implemented/matched. Proofs remain in scope rather than being discarded as not applicable. `UNVERIFIED` can coexist with strong reusable capability when exact source interpretation is unresolved.

| Status | Meaning | Top-level | Task-output groups | Body/figure groups |
|---|---|---:|---:|---:|
| NOT_STARTED | No dedicated source implementation or proof artifact mapped; related capabilities may still be listed. | 33 | 44 | 5 |
| PRIMITIVE_ONLY | Reusable primitives or partial generic experiments exist, but the complete source record is not implemented and matched. | 318 | 393 | 83 |
| IMPLEMENTED | The explicitly scoped record has executable implementation; independent source-specific runtime validation not established. | 0 | 0 | 0 |
| EXPERIMENTAL | An executable bounded or exploratory model exists with unresolved physical/convergence or contract limitations. | 0 | 0 | 0 |
| VALIDATED | Exact scoped source inputs, outputs/conventions and independent oracle have fresh recorded runtime proof; never inherited from a suite total. | 0 | 0 | 0 |
| DEFERRED | Explicitly postponed scoped work; no completion implied. | 0 | 0 | 0 |
| NOT_APPLICABLE | Explicitly outside the book inventory; not a way to discard difficult proofs or tasks. | 0 | 0 | 0 |
| UNVERIFIED | A material source interpretation, glyph, diagram or mathematical conflict prevents exact matching. | 62 | 126 | 4 |
| **Total (separate populations)** | Do not sum into a coverage denominator | **413** | **563** | **92** |

The prior “44/45 = 97.78%”, “64 worked examples”, blanket chapter `VALIDATED`, and whole-book validated claims are retracted. Zero source records are newly `VALIDATED` here; this is not a claim that all underlying software is untested.

## Chapter summary and remaining source-specific fixtures

| Ch | Printed body | Top-level / output groups / body groups | Principal remaining boundary |
|---|---|---:|---|
| 1 | 1–9 | 11 / 12 / 5 | Classical code lengths, surprisal, exact frequency mode/mean/variance; arbitrary joint-distribution worksheet. |
| 2 | 11–37 | 26 / 32 / 2 | General complex/unnormalized vectors and exact Gram-Schmidt/trine/inequality inputs; native qutrit state support absent. |
| 3 | 39–72 | 66 / 54 / 13 | Arbitrary operators, characteristic polynomials, degeneracy, complex expectation, polar/SVD and nonzero uncertainty; proof artifacts absent. |
| 4 | 73–84 | 35 / 33 / 4 | Explicit source tensor arrays, unnormalized projections, factorization and subsystem-order fixtures. |
| 5 | 85–119 | 44 / 75 / 9 | Nonorthogonal ensembles, all basis probabilities/poststates, PSD validity and exact Phi-minus global density. |
| 6 | 121–146 | 31 / 58 / 3 | Five-/three-level measurement, joint versus marginal collapse, unambiguous discrimination and weak nondemolition instrument. |
| 7 | 147–171 | 33 / 40 / 7 | Three-axis Bell counting (not CHSH), full Pauli/Bell-weight worksheets and corrected separability oracles. |
| 8 | 173–196 | 34 / 40 / 9 | Exact gate tasks and all input branches; two circuit drawings and general controlled-U phase details unresolved. |
| 9 | 197–223 | 21 / 28 / 10 | Exact two-input DJ stages/general Uf, QFT wire order, QPE remaining outputs, modulus44 order example, beam splitter/adder/qudit DJ. |
| 10 | 225–238 | 19 / 26 / 5 | Source no-message marginal, locked two-recipient resource, unlike-pair swapping, GHZ coding; weighted W claim unresolved. |
| 11 | 239–249 | 11 / 12 / 5 | Toy arithmetic and fixed QKD transcripts; conceptual probe correlations are not intercept-resend or operational tooling. |
| 12 | 251–278 | 25 / 30 / 8 | Joint environment-to-Kraus derivations, oscillator family, collective-dephasing DFS and exact five-CNOT source syndrome. |
| 13 | 279–304 | 34 / 76 / 6 | Exact matrix-pair/root-fidelity/Bures cases, worst-case channel fidelity, entropy intermediates and parameter conversions. |
| 14 | 305–313 | 9 / 23 / 1 | Source well wavefunctions/energies/gap/time, excited contraction and nonlinear eigenpath; ground-state transfer is not full gate. |
| 15 | 315–327 | 14 / 24 / 5 | Exact graph sign/GHZ/witness fixtures, full stabilizer groups, five-node XYYY/phase pattern and pictured graph. |

## Capability evidence: implemented does not mean source-complete

Book Lab currently exposes **31 experiments**, not 28. This supplied current UI count is not a book-coverage denominator; no chapter/expansion split is guessed. Correct experiment ID: `book_adiabatic_hadamard` (the former `book_adabatic_hadamard` was a typo).

| Capability | Current evidence and exact boundary |
|---|---|
| `book_qubit_state` | Standard +Y projector sign corrected; test_book_semantics covers the measurement sign. Bloch-only checks are not whole chapter coverage. |
| `book_operator_report` | Pauli anticommutator semantics corrected and checked by test_book_semantics; arbitrary operators, meaningful nonzero uncertainty and proof worksheets still missing. |
| `book_grover_scan` | Committed fix 567764b: exact simulated marked probability compared against rotation oracle, independent of finite-shot noise; truncated-scan checks also exercised. Regression and canonical runner integration passed per Main. This does not prove every source derivation. |
| `book_qft` | Positive-sign DFT and phase-sensitive cutoff reference implemented; full DFT and retained-phase tests exist. Source wire order/intermediate fractions and diagram not fully reconciled. |
| `book_qpe` | Arbitrary-eigenstate primitive and Bloch-eigenstate runner implemented; finite geometric-sum/off-grid distribution oracle. Nearest-bin guarantee and retained eigenstate not all separately asserted. |
| `book_entanglement_swapping` | Outcome-conditioned and corrected Bell targets implemented; test_book_correctness inspects all four branches. Source label permutation and unlike-pair Exercise10.5 remain separate. |
| `book_qec_codes` | Ideal coherent logical states and exact syndrome branches implemented; test_book_correctness contains logical-density/branch-weight assertions. No fresh QEC rerun claimed. Source five-CNOT binary-position circuit is not covered by generic stabilizer recovery; pipeline helper is not a correct full recovery circuit. |
| `book_qi_metrics` | Common-channel trace-distance and squared-fidelity checks implemented against affine Bloch formulas. Root fidelity = sqrt(repository squared fidelity); Bures distance versus squared distance explicit. Exact source matrix pairs and worst-case minimization remain unmapped. |
| `book_mbqc` | Three-node two-measurement adaptive path implemented; four branches compared against H Rz(-beta) H Rz(-alpha). Not the five-node XYYY source task. |
| `book_teleportation` | Input tensor placement and both X/Z corrections fixed. Independent Bell-stage mechanism test passed; broader 88-test scoped run included teleportation. Final fidelity alone is not mechanism proof, nor all numbered steps/no-message source-task coverage. |
| `book_multigrover` | Implemented exact multi-target rotation trajectory; M=1 relates to source single-target material. Extra marked targets do not create source records. |
| `book_adiabatic_well` | Bounded eight-state truncated, renormalized model; sudden comparison uses quadrature of analytic eigenfunctions, not an independently executed closed-form source fixture. Moving-wall convergence/lost norm and source energies/wavefunctions/time estimates remain open. |
| `book_adiabatic_hadamard` | Source final ground-state recipe, not arbitrary-input Hadamard process. Example14.2 spans pp.308–309; Example14.3 spans pp.310–313. |
| `book_gate_decomposition` | Source-related CNOT = (I tensor H) CZ (I tensor H) identity and generic controlled-U/Z-Y algebra. It does not implement every gate exercise or unresolved drawing. |

### Runtime evidence boundaries

- Full backend suite: currently running in Main's fresh session, **pending** — no pass/fail claimed yet. Fresh targeted suites already passed: process workers **34**, preservation **163**, correlation decoder **31**, Grover regression and Grover contracts; canonical Grover smoke errors below `3e-15`; committed Grover fix **567764b**. Provenance per entry: **fresh session verification** (above) versus historical context.
- HISTORICAL: earlier reported **1077 backend passed**, full e2e **61 including 9 visual**, BookLab **10 with 9 reload checks**, and the earlier **88-test** scoped run (semantics, algorithm contracts, primitives, teleportation). Retained for context; not rerun in the current session and not source-item validation. The teleportation fix's independent Bell-stage mechanism oracle remains the specific mechanism evidence; it does not close all source intermediate states, every subpart or the no-classical-message task.
- **No fresh QEC rerun is claimed.** Current coherent logical-density and syndrome-branch assertions were inspected by source auditors. Ideal projective recovery is not the source five-CNOT binary-position ancilla circuit, noisy extraction or fault tolerance; the exported demonstration helper must not be credited as correct full recovery.
- No runtime commands, tests, formatters, lint or builds were run by this documentation integrator. No new source-specific experiment was added by this integration.

## Source discrepancies, conventions and visual gaps

All proposed mathematical source corrections remain **suspected source/extraction issues** until independently adjudicated. The audit reports contain analytical reasoning, not newly executed source-specific numerical oracles. Do not train tests on questionable source arithmetic or silently replace a literal source task with a corrected variant.

- Standard Pauli Y is retained. Contradictory extracted signs, trine/eigenvector global phase, linear-action amplitudes and normalized physical states require distinct checks.
- Tensor left factor is high-order; simulator global qubit indices are little-endian. Partial trace specifies kept factors, while the textbook names discarded factors; partial-transpose helpers have differing axis conventions. Asymmetric fixtures must map labels explicitly.
- The source uses **root fidelity**, while the repository uses its square. Source-facing conversion is `F_root = sqrt(F_repo)`. Bures distance and squared Bures distance are distinct. Werner mixing weight is not Bell-target fidelity: `F_Bell=(1+3q)/4`.
- Suspected arithmetic/interpretation conflicts include the chapter1 rounded mean, chapter2 dependence/triangle calculations, chapter5 coherent-mixture probability and exercise matrix values, Bell-diagonal separability/YY signs, weighted-W coding partition, channel completeness/Pauli identities, channel-fidelity parameter flips and GHZ witness inference. Detailed locations are retained in JSON.
- Source5.7(d) is a real requested computational-probability subpart despite no printed worked solution. Example7.9 is singlet Schmidt rank, not purification; Example10.3 is locked simultaneous teleportation; Example10.4 is weighted three-qubit W coding, not a generic two-bit message.
- Highest-priority visual gaps: Exercises3.4/3.12, several chapter4/5 radicals and matrices, Exercises8.11/8.12 circuit wiring, QFT wire/reversal details, Exercise10.3 coefficients, chapter12 oscillator/Kraus typography, chapter13 amplitudes, Example15.2 entangler indices and **Exercise15.2’s pictured graph**. Worked Example15.2 and Exercise15.2 are different objects.
- Five-node XYYY text is readable but topology/entangler details and all16 branch frames remain unresolved. Three-node/four-branch MBQC does not close it. Arbitrary-input process validation is a stronger extension than the source fixed preparation.

## Expansion and research separation

CHSH is not the source chapter7 three-axis Bell-counting demonstration. Chapter6 unambiguous three-outcome discrimination is not binary minimum-error Helstrom. Chapter12 qubit channels are not the infinite oscillator-loss family. These distinctions apply even when the UI uses a chapter label.

Educational expansions include Simon/Bernstein–Vazirani, approximate QFT, multi-target Grover, tomography, advanced Helstrom, channel Choi/process algebra, Rabi, sudden well overlap and fully developed five-qubit/Steane studies. They are not added McMahon numbered records. The source does contain basic distance/discrimination relations and mentions CSS; that does not make every related lab a source task.

Surface/toric/rotated-code extraction, decoder and D7 studies retain their separate historical research artifacts. Previous research `VALIDATED`/`COMPLETE` labels are not freshly certified by this integration. Landau–Zener, amplitude estimation/counting, Lindblad/Ramsey, finite-key rigor and noisy protocols remain research candidates, not substitutes for the book gaps.

## Per-item matrix

The following retains all original top-level identities. Every row’s source existence is `OBSERVED_TEXT`, never image-level confirmation. Full observations, legacy labels, evidence aliases, classifications, limits and child records are in the JSON. Section/YTI ordinals are inventory locators; examples/exercises correspond to source numbering.

### Chapter 1: A Brief Introduction to Information Theory

| ID | Printed page | Reconciled concept | Status |
|---|---|---|---|
| `ch01.section.1` | 1 | Classical Information | PRIMITIVE_ONLY |
| `ch01.section.2` | 2 | Information Content in a Signal | PRIMITIVE_ONLY |
| `ch01.section.3` | 3 | Entropy and Shannon's Information Theory | PRIMITIVE_ONLY |
| `ch01.section.4` | 7 | Probability Basics | PRIMITIVE_ONLY |
| `ch01.example.1` | 8 | Frequency-table mode and expectation | UNVERIFIED |
| `ch01.exercise.1` | 8-9 | Alphabet code lengths | NOT_STARTED |
| `ch01.exercise.2` | 8-9 | OR from AND and NOT | PRIMITIVE_ONLY |
| `ch01.exercise.3` | 8-9 | Storage message count | NOT_STARTED |
| `ch01.exercise.4` | 8-9 | Fair-coin entropy | PRIMITIVE_ONLY |
| `ch01.exercise.5` | 8-9 | Four-symbol entropy | PRIMITIVE_ONLY |
| `ch01.exercise.6` | 8-9 | Income mode mean variance | NOT_STARTED |

### Chapter 2: Qubits and Quantum States

| ID | Printed page | Reconciled concept | Status |
|---|---|---|---|
| `ch02.section.1` | 11 | The Qubit | PRIMITIVE_ONLY |
| `ch02.section.2` | 14 | Vector Spaces | PRIMITIVE_ONLY |
| `ch02.section.3` | 17 | Linear Combinations of Vectors | PRIMITIVE_ONLY |
| `ch02.section.4` | 19 | Uniqueness of a Spanning Set | PRIMITIVE_ONLY |
| `ch02.section.5` | 20 | Basis and Dimension | PRIMITIVE_ONLY |
| `ch02.section.6` | 21 | Inner Products | PRIMITIVE_ONLY |
| `ch02.section.7` | 24 | Orthonormality | PRIMITIVE_ONLY |
| `ch02.section.8` | 26 | Gram-Schmidt Orthogonalization | PRIMITIVE_ONLY |
| `ch02.section.9` | 28 | Bra-Ket Formalism | NOT_STARTED |
| `ch02.section.10` | 31 | The Cauchy-Schwartz and Triangle Inequalities | NOT_STARTED |
| `ch02.section.11` | 35 | Summary | NOT_STARTED |
| `ch02.example.1` | 13 | Qubit probabilities and normalization | PRIMITIVE_ONLY |
| `ch02.example.2` | 16 | Arbitrary complex vector linear combination | PRIMITIVE_ONLY |
| `ch02.example.3` | 18 | Linear dependence certificate | UNVERIFIED |
| `ch02.example.4` | 22 | Bras, conjugate inner products and vector combination | PRIMITIVE_ONLY |
| `ch02.example.5` | 24 | Two norms and normalized vectors | PRIMITIVE_ONLY |
| `ch02.example.6` | 26 | Three-step Gram-Schmidt residuals and basis | PRIMITIVE_ONLY |
| `ch02.example.7` | 29 | Qutrit normalization and three probabilities | UNVERIFIED |
| `ch02.example.8` | 32 | Cauchy-Schwarz and triangle inequalities; two normalizations | UNVERIFIED |
| `ch02.example.9` | 33 | Three normalized trine orthogonal partners | NOT_STARTED |
| `ch02.exercise.1` | 36-37 | Complex-amplitude probabilities | PRIMITIVE_ONLY |
| `ch02.exercise.2` | 36-37 | Vector sum linear combination normalization | PRIMITIVE_ONLY |
| `ch02.exercise.3` | 36-37 | Invert Hadamard basis relation | PRIMITIVE_ONLY |
| `ch02.exercise.4` | 36-37 | Normalization and basis change | PRIMITIVE_ONLY |
| `ch02.exercise.5` | 36-37 | R4 Gram-Schmidt | PRIMITIVE_ONLY |
| `ch02.exercise.6` | 36-37 | Polarization overlaps | PRIMITIVE_ONLY |

### Chapter 3: Matrices and Operators

| ID | Printed page | Reconciled concept | Status |
|---|---|---|---|
| `ch03.section.1` | 40 | Observables | PRIMITIVE_ONLY |
| `ch03.section.2` | 40 | The Pauli Operators | PRIMITIVE_ONLY |
| `ch03.section.3` | 41 | Outer Products | PRIMITIVE_ONLY |
| `ch03.section.4` | 42 | The Closure Relation | PRIMITIVE_ONLY |
| `ch03.section.5` | 42 | Representations of Operators Using Matrices | PRIMITIVE_ONLY |
| `ch03.section.6` | 43 | Outer Products and Matrix Representations | PRIMITIVE_ONLY |
| `ch03.section.7` | 44 | Matrix Representation of Operators in Two-Dimensional Spaces | PRIMITIVE_ONLY |
| `ch03.section.8` | 45 | Definition: The Pauli Matrices | PRIMITIVE_ONLY |
| `ch03.section.9` | 46 | Hermitian, Unitary, and Normal Operators | PRIMITIVE_ONLY |
| `ch03.section.10` | 47 | Definition: Hermitian Operator | PRIMITIVE_ONLY |
| `ch03.section.11` | 48 | Definition: Unitary Operator | PRIMITIVE_ONLY |
| `ch03.section.12` | 48 | Definition: Normal Operator | NOT_STARTED |
| `ch03.section.13` | 48 | Eigenvalues and Eigenvectors | PRIMITIVE_ONLY |
| `ch03.section.14` | 49 | The Characteristic Equation | NOT_STARTED |
| `ch03.section.15` | 53 | Spectral Decomposition | PRIMITIVE_ONLY |
| `ch03.section.16` | 54 | The Trace of an Operator | PRIMITIVE_ONLY |
| `ch03.section.17` | 56 | Important Properties of the Trace | PRIMITIVE_ONLY |
| `ch03.section.18` | 57 | The Expectation Value of an Operator | PRIMITIVE_ONLY |
| `ch03.section.19` | 59 | Functions of Operators | PRIMITIVE_ONLY |
| `ch03.section.20` | 60 | Unitary Transformations | PRIMITIVE_ONLY |
| `ch03.section.21` | 62 | Projection Operators | PRIMITIVE_ONLY |
| `ch03.section.22` | 66 | Positive Operators | PRIMITIVE_ONLY |
| `ch03.section.23` | 66 | Commutator Algebra | PRIMITIVE_ONLY |
| `ch03.section.24` | 68 | The Heisenberg Uncertainty Principle | UNVERIFIED |
| `ch03.section.25` | 69 | Polar Decomposition and Singular Values | NOT_STARTED |
| `ch03.section.26` | 70 | The Postulates of Quantum Mechanics | NOT_STARTED |
| `ch03.section.27` | 70 | Postulate 1 | NOT_STARTED |
| `ch03.section.28` | 70 | Postulate 2 | NOT_STARTED |
| `ch03.section.29` | 70 | Postulate 3 | NOT_STARTED |
| `ch03.section.30` | 71 | Postulate 4 | NOT_STARTED |
| `ch03.example.1` | 41 | Outer-product Z action | PRIMITIVE_ONLY |
| `ch03.example.2` | 44 | Four Z matrix elements | PRIMITIVE_ONLY |
| `ch03.example.3` | 45 | Six computational-basis Pauli actions | PRIMITIVE_ONLY |
| `ch03.example.4` | 47 | Adjoint of an outer-product operator | PRIMITIVE_ONLY |
| `ch03.example.5` | 49 | General non-Hermitian characteristic equation | PRIMITIVE_ONLY |
| `ch03.example.6` | 50 | T eigenpairs and checks | PRIMITIVE_ONLY |
| `ch03.example.7` | 53 | Degenerate qutrit spectral reconstruction | PRIMITIVE_ONLY |
| `ch03.example.8` | 54 | Complex outer-product trace | PRIMITIVE_ONLY |
| `ch03.example.9` | 55 | Trace of Z | PRIMITIVE_ONLY |
| `ch03.example.10` | 56 | Three trace/spectrum comparisons | PRIMITIVE_ONLY |
| `ch03.example.11` | 57 | Outer-product trace identity proof | PRIMITIVE_ONLY |
| `ch03.example.12` | 57 | X expectation versus outcomes | PRIMITIVE_ONLY |
| `ch03.example.13` | 58 | Complex expectation of a non-Hermitian qutrit operator | UNVERIFIED |
| `ch03.example.14` | 61 | Basis matrix, transformed state and transformed T | PRIMITIVE_ONLY |
| `ch03.example.15` | 63 | Two computational projectors and completeness | PRIMITIVE_ONLY |
| `ch03.example.16` | 65 | Probabilities and unnormalized projections | PRIMITIVE_ONLY |
| `ch03.example.17` | 67 | Pauli commutator | PRIMITIVE_ONLY |
| `ch03.example.18` | 69 | Rotation-scaling polar decomposition | NOT_STARTED |
| `ch03.exercise.1` | 71-72 | X/Y outer-product action | PRIMITIVE_ONLY |
| `ch03.exercise.2` | 71-72 | X computational-basis matrix | PRIMITIVE_ONLY |
| `ch03.exercise.3` | 71-72 | X Hadamard-basis matrix | PRIMITIVE_ONLY |
| `ch03.exercise.4` | 71-72 | C3 operator adjoint | UNVERIFIED |
| `ch03.exercise.5` | 71-72 | X eigenpairs | PRIMITIVE_ONLY |
| `ch03.exercise.6` | 71-72 | Y tracelessness | PRIMITIVE_ONLY |
| `ch03.exercise.7` | 71-72 | Three-dimensional matrix eigenvalues | NOT_STARTED |
| `ch03.exercise.8` | 71-72 | Trace linearity and cyclicity proofs | NOT_STARTED |
| `ch03.exercise.9` | 71-72 | X spectral projectors | PRIMITIVE_ONLY |
| `ch03.exercise.10` | 71-72 | Three-state projectors and probabilities | NOT_STARTED |
| `ch03.exercise.11` | 71-72 | Remaining Pauli commutators | PRIMITIVE_ONLY |
| `ch03.exercise.12` | 71-72 | Pauli anticommutators | UNVERIFIED |
| `ch03.yti.1` | 42 | Identity outer-product action | PRIMITIVE_ONLY |
| `ch03.yti.2` | 44 | General qutrit ket-bra matrix: nine entries | PRIMITIVE_ONLY |
| `ch03.yti.3` | 45 | Identity computational matrix elements | PRIMITIVE_ONLY |
| `ch03.yti.4` | 47 | Adjoint of complex outer-product operator | PRIMITIVE_ONLY |
| `ch03.yti.5` | 50 | Z eigenvalues +1 and -1 | PRIMITIVE_ONLY |
| `ch03.yti.6` | 63 | Both Hadamard projectors and completeness | PRIMITIVE_ONLY |

### Chapter 4: Tensor Products

| ID | Printed page | Reconciled concept | Status |
|---|---|---|---|
| `ch04.section.1` | 74 | Representing Composite States in Quantum Mechanics | PRIMITIVE_ONLY |
| `ch04.section.2` | 76 | Computing Inner Products | PRIMITIVE_ONLY |
| `ch04.section.3` | 78 | Tensor Products of Column Vectors | PRIMITIVE_ONLY |
| `ch04.section.4` | 79 | Operators and Tensor Products | PRIMITIVE_ONLY |
| `ch04.section.5` | 83 | Tensor Products of Matrices | PRIMITIVE_ONLY |
| `ch04.example.1` | 74 | Four computational product vectors | PRIMITIVE_ONLY |
| `ch04.example.2` | 75 | Four expansion coefficients | PRIMITIVE_ONLY |
| `ch04.example.3` | 76 | Four Hadamard-product vectors and orthonormality | PRIMITIVE_ONLY |
| `ch04.example.4` | 77 | Factorized unnormalized inner product | PRIMITIVE_ONLY |
| `ch04.example.5` | 77 | Product-state factorization into plus tensor minus | PRIMITIVE_ONLY |
| `ch04.example.6` | 78 | Explicit tensor column vector | PRIMITIVE_ONLY |
| `ch04.example.7` | 79 | Product eigenvalue rule | PRIMITIVE_ONLY |
| `ch04.example.8` | 80 | X tensor Z on Phi-minus | PRIMITIVE_ONLY |
| `ch04.example.9` | 80 | Unnormalized product-projector action | PRIMITIVE_ONLY |
| `ch04.example.10` | 81 | Hermitian tensor-product proof | PRIMITIVE_ONLY |
| `ch04.example.11` | 82 | X tensor I on Phi-minus | PRIMITIVE_ONLY |
| `ch04.example.12` | 83 | Full X tensor Z matrix | PRIMITIVE_ONLY |
| `ch04.exercise.1` | 84 | Composite basis orthonormality | PRIMITIVE_ONLY |
| `ch04.exercise.2` | 84 | Composite basis orthogonality | UNVERIFIED |
| `ch04.exercise.3` | 84 | Factorized inner product | PRIMITIVE_ONLY |
| `ch04.exercise.4` | 84 | Explicit vector tensor product | UNVERIFIED |
| `ch04.exercise.5` | 84 | Product-state factorization | PRIMITIVE_ONLY |
| `ch04.exercise.6` | 84 | Bell-state nonfactorization | PRIMITIVE_ONLY |
| `ch04.exercise.7` | 84 | X tensor Y on singlet | PRIMITIVE_ONLY |
| `ch04.exercise.8` | 84 | Tensor adjoint identity proof | PRIMITIVE_ONLY |
| `ch04.exercise.9` | 84 | I tensor Y on Bell | PRIMITIVE_ONLY |
| `ch04.exercise.10` | 84 | X tensor Y matrix | PRIMITIVE_ONLY |
| `ch04.yti.1` | 76 | Remaining Hadamard-product norm and cross-inner-product checks; bra-ket glyph unresolved | UNVERIFIED |
| `ch04.yti.2` | 77 | Factorized inner product | PRIMITIVE_ONLY |
| `ch04.yti.3` | 77 | Uniform four-term state factorization; normalization denominator unresolved | UNVERIFIED |
| `ch04.yti.4` | 78 | Explicit vector tensor product; bottom components unresolved | UNVERIFIED |
| `ch04.yti.5` | 79 | X tensor Z action on \|01> | PRIMITIVE_ONLY |
| `ch04.yti.6` | 82 | Proof of unitary tensor closure | PRIMITIVE_ONLY |
| `ch04.yti.7` | 82 | Z tensor I acting on Phi+ | PRIMITIVE_ONLY |
| `ch04.yti.8` | 84 | Z tensor X full matrix and comparison with X tensor Z | PRIMITIVE_ONLY |

### Chapter 5: The Density Operator

| ID | Printed page | Reconciled concept | Status |
|---|---|---|---|
| `ch05.section.1` | 86 | The Density Operator for a Pure State | PRIMITIVE_ONLY |
| `ch05.section.2` | 87 | Definition: Density Operator for a Pure State | PRIMITIVE_ONLY |
| `ch05.section.3` | 88 | Definition: Using the Density Operator to Find the Expectation Value | PRIMITIVE_ONLY |
| `ch05.section.4` | 90 | Time Evolution of the Density Operator | PRIMITIVE_ONLY |
| `ch05.section.5` | 91 | Definition: Time Evolution of the Density Operator | PRIMITIVE_ONLY |
| `ch05.section.6` | 91 | The Density Operator for a Mixed State | PRIMITIVE_ONLY |
| `ch05.section.7` | 92 | Key Properties of a Density Operator | PRIMITIVE_ONLY |
| `ch05.section.8` | 95 | Expectation Values | PRIMITIVE_ONLY |
| `ch05.section.9` | 95 | Probability of Obtaining a Given Measurement Result | PRIMITIVE_ONLY |
| `ch05.section.10` | 99 | Characterizing Mixed States | PRIMITIVE_ONLY |
| `ch05.section.11` | 108 | Probability of Finding an Element of the Ensemble in a Given State | PRIMITIVE_ONLY |
| `ch05.section.12` | 111 | Completely Mixed States | PRIMITIVE_ONLY |
| `ch05.section.13` | 111 | The Partial Trace and the Reduced Density Operator | PRIMITIVE_ONLY |
| `ch05.section.14` | 115 | The Density Operator and the Bloch Vector | PRIMITIVE_ONLY |
| `ch05.example.1` | 88 | Complex pure density and trace | PRIMITIVE_ONLY |
| `ch05.example.2` | 93 | Three density validity requirements | PRIMITIVE_ONLY |
| `ch05.example.3` | 96 | Reject non-Hermitian unit-trace matrix | PRIMITIVE_ONLY |
| `ch05.example.4` | 96 | Density, purity, two Z probabilities and X expectation | PRIMITIVE_ONLY |
| `ch05.example.5` | 100 | Mixture versus coherent superposition in two bases | UNVERIFIED |
| `ch05.example.6` | 102 | Conditional postmeasurement density | PRIMITIVE_ONLY |
| `ch05.example.7` | 103 | Nonorthogonal ensemble and probabilities in two bases | PRIMITIVE_ONLY |
| `ch05.example.8` | 105 | Mixed-state purity bound proof | PRIMITIVE_ONLY |
| `ch05.example.9` | 106 | Hermiticity, spectrum, purity and X expectation | PRIMITIVE_ONLY |
| `ch05.example.10` | 109 | Constituent and ensemble densities and probabilities | PRIMITIVE_ONLY |
| `ch05.example.11` | 114 | Complex product vector, density and purity | UNVERIFIED |
| `ch05.example.12` | 116 | Bloch validity and mixed-state classification | PRIMITIVE_ONLY |
| `ch05.exercise.1` | 117-119 | Normalization probabilities density trace | UNVERIFIED |
| `ch05.exercise.2` | 117-119 | Complex trigonometric pure density | PRIMITIVE_ONLY |
| `ch05.exercise.3` | 117-119 | Density purity and basis change | UNVERIFIED |
| `ch05.exercise.4` | 117-119 | Purity and X expectation | PRIMITIVE_ONLY |
| `ch05.exercise.5` | 117-119 | Density validity then purity | UNVERIFIED |
| `ch05.exercise.6` | 117-119 | Purity and Pauli expectations | PRIMITIVE_ONLY |
| `ch05.exercise.7` | 117-119 | Two-state ensemble and measurements | UNVERIFIED |
| `ch05.exercise.8` | 117-119 | Ensemble computational probability | UNVERIFIED |
| `ch05.exercise.9` | 117-119 | Bell density and Alice marginal | PRIMITIVE_ONLY |
| `ch05.exercise.10` | 117-119 | Hermiticity spectrum validity probability Bloch vector | UNVERIFIED |
| `ch05.yti.1` | 89 | Qutrit density and trace | PRIMITIVE_ONLY |
| `ch05.yti.2` | 96 | Reject I2 as density: trace 2 | PRIMITIVE_ONLY |
| `ch05.yti.3` | 98 | State normalization and density | PRIMITIVE_ONLY |
| `ch05.yti.4` | 99 | Z expectation; suspected wrong Example5.2 reference | UNVERIFIED |
| `ch05.yti.5` | 99 | Hadamard-minus projector and probability; suspected wrong Example5.2 reference | UNVERIFIED |
| `ch05.yti.6` | 103 | Weighted mixture matrix, p1 and conditional poststate | PRIMITIVE_ONLY |
| `ch05.yti.7` | 108 | Validity, eigenvalues, mixedness and Z expectation | PRIMITIVE_ONLY |
| `ch05.yti.8` | 113 | Alice marginal of Phi-minus, local and global purity | PRIMITIVE_ONLY |

### Chapter 6: Quantum Measurement Theory

| ID | Printed page | Reconciled concept | Status |
|---|---|---|---|
| `ch06.section.1` | 121 | Distinguishing Quantum States and Measurement | PRIMITIVE_ONLY |
| `ch06.section.2` | 123 | Projective Measurements | PRIMITIVE_ONLY |
| `ch06.section.3` | 132 | Measurements on Composite Systems | PRIMITIVE_ONLY |
| `ch06.section.4` | 139 | Generalized Measurements | PRIMITIVE_ONLY |
| `ch06.section.5` | 141 | Positive Operator-Valued Measures | PRIMITIVE_ONLY |
| `ch06.example.1` | 125 | Five-level energy projectors, collapse and expectation | PRIMITIVE_ONLY |
| `ch06.example.2` | 128 | Y eigenprojectors and both qubit probabilities | UNVERIFIED |
| `ch06.example.3` | 130 | X projectors, probabilities and expectation | PRIMITIVE_ONLY |
| `ch06.example.4` | 132 | Two singlet projections and matrix action | PRIMITIVE_ONLY |
| `ch06.example.5` | 133 | Joint and first-qubit marginal measurement | PRIMITIVE_ONLY |
| `ch06.example.6` | 135 | Three-qubit normalization, joint and first-qubit collapse | PRIMITIVE_ONLY |
| `ch06.example.7` | 136 | XYZ action on GHZ and Hadamard-basis probabilities | UNVERIFIED |
| `ch06.example.8` | 138 | First-factor Y action and two output probabilities | PRIMITIVE_ONLY |
| `ch06.example.9` | 140 | Density trace probability 5/6 | PRIMITIVE_ONLY |
| `ch06.example.10` | 140 | Coherent density in arbitrary orthonormal basis | PRIMITIVE_ONLY |
| `ch06.example.11` | 141 | Computational PVM as POVM | PRIMITIVE_ONLY |
| `ch06.example.12` | 142 | Three-outcome unambiguous discrimination | PRIMITIVE_ONLY |
| `ch06.example.13` | 143 | Weak nondemolition instrument and disturbance | UNVERIFIED |
| `ch06.exercise.1` | 145-146 | Commuting projector product proof | PRIMITIVE_ONLY |
| `ch06.exercise.2` | 145-146 | Three-level energy projectors probabilities expectation | NOT_STARTED |
| `ch06.exercise.3` | 145-146 | X projectors measuring one | PRIMITIVE_ONLY |
| `ch06.exercise.4` | 145-146 | Two-qubit joint marginal and collapse | PRIMITIVE_ONLY |
| `ch06.exercise.5` | 145-146 | Y expectation | PRIMITIVE_ONLY |
| `ch06.exercise.6` | 145-146 | Three-qubit joint marginal collapse normalization | PRIMITIVE_ONLY |
| `ch06.exercise.7` | 145-146 | X gate then joint measurement | PRIMITIVE_ONLY |
| `ch06.exercise.8` | 145-146 | Imperfect distinguishability POVM construction | PRIMITIVE_ONLY |
| `ch06.exercise.9` | 145-146 | POVM completeness | PRIMITIVE_ONLY |
| `ch06.exercise.10` | 145-146 | Why source measurement operators are not effects | PRIMITIVE_ONLY |
| `ch06.yti.1` | 130 | Verify both Y eigenvectors; sign convention needs reconciliation | PRIMITIVE_ONLY |
| `ch06.yti.2` | 136 | Normalize Example6.6 poststate | PRIMITIVE_ONLY |
| `ch06.yti.3` | 138 | GHZ expansion in Hadamard basis; normalization glyph unresolved | UNVERIFIED |

### Chapter 7: Entanglement

| ID | Printed page | Reconciled concept | Status |
|---|---|---|---|
| `ch07.section.1` | 151 | Bell's Theorem | PRIMITIVE_ONLY |
| `ch07.section.2` | 155 | Bipartite Systems and the Bell Basis | PRIMITIVE_ONLY |
| `ch07.section.3` | 157 | When Is a State Entangled? | PRIMITIVE_ONLY |
| `ch07.section.4` | 162 | The Pauli Representation | PRIMITIVE_ONLY |
| `ch07.section.5` | 166 | Entanglement Fidelity | UNVERIFIED |
| `ch07.section.6` | 166 | Using Bell States for Density Operator Representation | PRIMITIVE_ONLY |
| `ch07.section.7` | 168 | Schmidt Decomposition | PRIMITIVE_ONLY |
| `ch07.section.8` | 169 | Purification | PRIMITIVE_ONLY |
| `ch07.example.1` | 157 | ZZ Bell parity proof | PRIMITIVE_ONLY |
| `ch07.example.2` | 158 | Four Bell-state nonfactorization checks | PRIMITIVE_ONLY |
| `ch07.example.3` | 158 | H tensor H product-state preparation | PRIMITIVE_ONLY |
| `ch07.example.4` | 159 | Dipole Hamiltonian spectrum and entanglement | PRIMITIVE_ONLY |
| `ch07.example.5` | 162 | Single-qubit Pauli density reconstruction | UNVERIFIED |
| `ch07.example.6` | 163 | Product and Bell correlation comparison | PRIMITIVE_ONLY |
| `ch07.example.7` | 167 | Bell-diagonal reconstruction and separability question | UNVERIFIED |
| `ch07.example.8` | 168 | Product-state Schmidt decomposition | PRIMITIVE_ONLY |
| `ch07.example.9` | 169 | Singlet Schmidt rank | PRIMITIVE_ONLY |
| `ch07.exercise.1` | 170-171 | Arbitrary-direction spin eigenvectors | UNVERIFIED |
| `ch07.exercise.2` | 170-171 | Singlet in Y basis | PRIMITIVE_ONLY |
| `ch07.exercise.3` | 170-171 | ZZ Bell eigenvalues | PRIMITIVE_ONLY |
| `ch07.exercise.4` | 170-171 | XX Bell eigenvalues | PRIMITIVE_ONLY |
| `ch07.exercise.5` | 170-171 | YY Bell eigenvalues | UNVERIFIED |
| `ch07.exercise.6` | 170-171 | XX and ZZ commutation | PRIMITIVE_ONLY |
| `ch07.exercise.7` | 170-171 | Hamiltonian spin-correlation simultaneous eigenstates | PRIMITIVE_ONLY |
| `ch07.exercise.8` | 170-171 | Local Pauli preserves Bell entanglement | PRIMITIVE_ONLY |
| `ch07.exercise.9` | 170-171 | Single-qubit Pauli representation | PRIMITIVE_ONLY |
| `ch07.exercise.10` | 170-171 | Source correlation criterion on Bell states | PRIMITIVE_ONLY |
| `ch07.exercise.11` | 170-171 | Bell projector Pauli expansion proof | PRIMITIVE_ONLY |
| `ch07.exercise.12` | 170-171 | Bell-diagonal state and separability | UNVERIFIED |
| `ch07.exercise.13` | 170-171 | Product criterion | PRIMITIVE_ONLY |
| `ch07.exercise.14` | 170-171 | Schmidt number of Bell superposition | UNVERIFIED |
| `ch07.yti.1` | 162 | YY and ZZ tensor matrices | PRIMITIVE_ONLY |
| `ch07.yti.2` | 162 | Two dipole-Hamiltonian eigenstate checks; second state label unresolved | UNVERIFIED |

### Chapter 8: Quantum Gates and Circuits

| ID | Printed page | Reconciled concept | Status |
|---|---|---|---|
| `ch08.section.1` | 173 | Classical Logic Gates | PRIMITIVE_ONLY |
| `ch08.section.2` | 176 | Single-Qubit Gates | PRIMITIVE_ONLY |
| `ch08.section.3` | 180 | More Single-Qubit Gates | PRIMITIVE_ONLY |
| `ch08.section.4` | 183 | Exponentiation | PRIMITIVE_ONLY |
| `ch08.section.5` | 185 | The Z-Y Decomposition | PRIMITIVE_ONLY |
| `ch08.section.6` | 185 | Basic Quantum Circuit Diagrams | PRIMITIVE_ONLY |
| `ch08.section.7` | 186 | Controlled Gates | PRIMITIVE_ONLY |
| `ch08.section.8` | 192 | Gate Decomposition | PRIMITIVE_ONLY |
| `ch08.example.1` | 178 | NOT outer product and Hadamard-basis matrix | PRIMITIVE_ONLY |
| `ch08.example.2` | 179 | Real rotation amplitudes and probabilities | PRIMITIVE_ONLY |
| `ch08.example.3` | 181 | Phase-gate azimuth shift | PRIMITIVE_ONLY |
| `ch08.example.4` | 182 | Hadamard outer product and both basis actions | PRIMITIVE_ONLY |
| `ch08.example.5` | 183 | Hermitian-unitary exponential proof | PRIMITIVE_ONLY |
| `ch08.example.6` | 187 | CNOT on three target inputs | PRIMITIVE_ONLY |
| `ch08.example.7` | 188 | Bell preparation from all computational inputs | PRIMITIVE_ONLY |
| `ch08.example.8` | 190 | Controlled H in matrix and Dirac forms | PRIMITIVE_ONLY |
| `ch08.example.9` | 191 | Attempted CNOT cloning with targets 1 and 0 | PRIMITIVE_ONLY |
| `ch08.exercise.1` | 195-196 | Y Bloch rotation | PRIMITIVE_ONLY |
| `ch08.exercise.2` | 195-196 | Hubbard matrices and Hadamard-basis action | NOT_STARTED |
| `ch08.exercise.3` | 195-196 | Pauli operators in Hubbard basis | NOT_STARTED |
| `ch08.exercise.4` | 195-196 | CNOT Hermiticity and unitarity | PRIMITIVE_ONLY |
| `ch08.exercise.5` | 195-196 | Bell preparation source Figure8.5 | UNVERIFIED |
| `ch08.exercise.6` | 195-196 | CZ matrix and Dirac representation | PRIMITIVE_ONLY |
| `ch08.exercise.7` | 195-196 | Squares of X Y Z S T | PRIMITIVE_ONLY |
| `ch08.exercise.8` | 195-196 | Hadamard Bloch rotation axis | UNVERIFIED |
| `ch08.exercise.9` | 195-196 | Pauli conjugation | PRIMITIVE_ONLY |
| `ch08.exercise.10` | 195-196 | Projector-sum controlled X | PRIMITIVE_ONLY |
| `ch08.exercise.11` | 195-196 | Circuit equivalence | UNVERIFIED |
| `ch08.exercise.12` | 195-196 | Toffoli controlled square-root-X decomposition | UNVERIFIED |
| `ch08.yti.1` | 175 | NAND-only OR synthesis | PRIMITIVE_ONLY |
| `ch08.yti.2` | 179 | Transformed NOT action on both Hadamard states | PRIMITIVE_ONLY |
| `ch08.yti.3` | 181 | Y action on arbitrary qubit in matrix and outer-product forms | PRIMITIVE_ONLY |
| `ch08.yti.4` | 183 | Hadamard-transformed complex qubit probability p1 | PRIMITIVE_ONLY |
| `ch08.yti.5` | 184 | RZ matrix from exponentiation | PRIMITIVE_ONLY |

### Chapter 9: Quantum Algorithms

| ID | Printed page | Reconciled concept | Status |
|---|---|---|---|
| `ch09.section.1` | 198 | Hadamard Gates | PRIMITIVE_ONLY |
| `ch09.section.2` | 201 | The Phase Gate | PRIMITIVE_ONLY |
| `ch09.section.3` | 201 | Matrix Representation of Serial and Parallel Operations | PRIMITIVE_ONLY |
| `ch09.section.4` | 202 | Quantum Interference | PRIMITIVE_ONLY |
| `ch09.section.5` | 203 | Quantum Parallelism and Function Evaluation | PRIMITIVE_ONLY |
| `ch09.section.6` | 207 | Deutsch-Jozsa Algorithm | PRIMITIVE_ONLY |
| `ch09.section.7` | 211 | Quantum Fourier Transform | PRIMITIVE_ONLY |
| `ch09.section.8` | 213 | Phase Estimation | PRIMITIVE_ONLY |
| `ch09.section.9` | 216 | Shor's Algorithm | PRIMITIVE_ONLY |
| `ch09.section.10` | 218 | Quantum Searching and Grover's Algorithm | PRIMITIVE_ONLY |
| `ch09.example.1` | 200 | Single-qubit phase-to-bit conversion | PRIMITIVE_ONLY |
| `ch09.example.2` | 208 | Constant-one two-input Deutsch-Jozsa stages | PRIMITIVE_ONLY |
| `ch09.example.3` | 209 | Specified balanced two-input Deutsch-Jozsa stages | UNVERIFIED |
| `ch09.exercise.1` | 221-223 | H tensor H matrix and action | PRIMITIVE_ONLY |
| `ch09.exercise.2` | 221-223 | Beam-splitter superposition and double application | NOT_STARTED |
| `ch09.exercise.3` | 221-223 | Serial phase-Hadamard matrix | PRIMITIVE_ONLY |
| `ch09.exercise.4` | 221-223 | Function-evaluation relations9.17-9.19 | UNVERIFIED |
| `ch09.exercise.5` | 221-223 | Quantum half-adder construction | UNVERIFIED |
| `ch09.exercise.6` | 221-223 | Qudit Hadamard and generalized Deutsch-Jozsa | UNVERIFIED |
| `ch09.exercise.7` | 221-223 | Grover relation9.67 derivation | PRIMITIVE_ONLY |
| `ch09.exercise.8` | 221-223 | Modular multiplication eigenvectors | UNVERIFIED |

### Chapter 10: Applications of Entanglement: Teleportation and Superdense Coding

| ID | Printed page | Reconciled concept | Status |
|---|---|---|---|
| `ch10.section.1` | 226 | Teleportation | PRIMITIVE_ONLY |
| `ch10.section.2` | 226 | Step 1 | PRIMITIVE_ONLY |
| `ch10.section.3` | 226 | Step 2 | PRIMITIVE_ONLY |
| `ch10.section.4` | 227 | Step 3 | PRIMITIVE_ONLY |
| `ch10.section.5` | 227 | Step 4 | PRIMITIVE_ONLY |
| `ch10.section.6` | 228 | Step 5 | PRIMITIVE_ONLY |
| `ch10.section.7` | 229 | The Peres Partial Transposition Condition | PRIMITIVE_ONLY |
| `ch10.section.8` | 234 | Entanglement Swapping | PRIMITIVE_ONLY |
| `ch10.section.9` | 236 | Superdense Coding | PRIMITIVE_ONLY |
| `ch10.example.1` | 229 | Bell beta01 density and partial transpose | PRIMITIVE_ONLY |
| `ch10.example.2` | 230 | Separable minus-tensor-minus partial transpose | PRIMITIVE_ONLY |
| `ch10.example.3` | 232 | Locked simultaneous teleportation resource and reductions | UNVERIFIED |
| `ch10.example.4` | 237 | Weighted three-qubit W1 encoding and distinguishability | UNVERIFIED |
| `ch10.exercise.1` | 238 | Teleportation without classical communication | PRIMITIVE_ONLY |
| `ch10.exercise.2` | 238 | PPT on signed uniform pure state | PRIMITIVE_ONLY |
| `ch10.exercise.3` | 238 | PPT on mixed state | UNVERIFIED |
| `ch10.exercise.4` | 238 | Derive post-lock reduced matrix Eq10.25 | PRIMITIVE_ONLY |
| `ch10.exercise.5` | 238 | Swapping unlike Bell pairs and different pairing | PRIMITIVE_ONLY |
| `ch10.exercise.6` | 238 | GHZ-assisted superdense coding | NOT_STARTED |

### Chapter 11: Quantum Cryptography

| ID | Printed page | Reconciled concept | Status |
|---|---|---|---|
| `ch11.section.1` | 241 | A Brief Overview of RSA Encryption | NOT_STARTED |
| `ch11.section.2` | 243 | Basic Quantum Cryptography | PRIMITIVE_ONLY |
| `ch11.section.3` | 246 | Conceptual basis-dependent probe correlations | NOT_STARTED |
| `ch11.section.4` | 247 | The B92 Protocol | PRIMITIVE_ONLY |
| `ch11.section.5` | 248 | The E91 Protocol (Ekert) | PRIMITIVE_ONLY |
| `ch11.example.1` | 242 | RSA encryption example | NOT_STARTED |
| `ch11.example.2` | 245 | BB84 transcript | PRIMITIVE_ONLY |
| `ch11.exercise.1` | 249 | RSA encrypt and decrypt | NOT_STARTED |
| `ch11.exercise.2` | 249 | Fixed BB84 source sequence and random Bob bases | PRIMITIVE_ONLY |
| `ch11.exercise.3` | 249 | Conceptual basis-dependent probe correlations | NOT_STARTED |
| `ch11.exercise.4` | 249 | Fixed B92 preparation/measurement transcript | UNVERIFIED |

### Chapter 12: Quantum Noise and Error Correction

| ID | Printed page | Reconciled concept | Status |
|---|---|---|---|
| `ch12.section.1` | 252 | Single-Qubit Errors | PRIMITIVE_ONLY |
| `ch12.section.2` | 254 | Quantum Operations and Krauss Operators | PRIMITIVE_ONLY |
| `ch12.section.3` | 260 | The Depolarization Channel | PRIMITIVE_ONLY |
| `ch12.section.4` | 261 | The Bit Flip and Phase Flip Channels | PRIMITIVE_ONLY |
| `ch12.section.5` | 262 | Amplitude Damping | PRIMITIVE_ONLY |
| `ch12.section.6` | 270 | Phase Damping | PRIMITIVE_ONLY |
| `ch12.section.7` | 272 | Quantum Error Correction | PRIMITIVE_ONLY |
| `ch12.section.8` | 275 | Step One | PRIMITIVE_ONLY |
| `ch12.section.9` | 275 | Step Two | PRIMITIVE_ONLY |
| `ch12.section.10` | 275 | Step Three | PRIMITIVE_ONLY |
| `ch12.section.11` | 275 | Step Four | PRIMITIVE_ONLY |
| `ch12.section.12` | 275 | Step Five | PRIMITIVE_ONLY |
| `ch12.example.1` | 255 | Unread measurement from joint interaction | PRIMITIVE_ONLY |
| `ch12.example.2` | 257 | ZZ environment coupling and derived Kraus map | PRIMITIVE_ONLY |
| `ch12.example.3` | 259 | Environment-controlled bit-flip derivation | PRIMITIVE_ONLY |
| `ch12.example.4` | 265 | Oscillator Hamiltonian and infinite loss-Kraus family | UNVERIFIED |
| `ch12.example.5` | 271 | Controlled environment rotation and phase suppression | UNVERIFIED |
| `ch12.exercise.1` | 277-278 | Controlled-X projector sum | PRIMITIVE_ONLY |
| `ch12.exercise.2` | 277-278 | Environment-dependent phase-flip probability | UNVERIFIED |
| `ch12.exercise.3` | 277-278 | Pauli conjugation Bloch identity | UNVERIFIED |
| `ch12.exercise.4` | 277-278 | Controlled environment Rz interaction | UNVERIFIED |
| `ch12.exercise.5` | 277-278 | System-environment phase-flip channel derivation | UNVERIFIED |
| `ch12.exercise.6` | 277-278 | Phase-damping relations12.51-12.53 | PRIMITIVE_ONLY |
| `ch12.exercise.7` | 277-278 | Third-qubit flip yields ancillary11 | PRIMITIVE_ONLY |
| `ch12.exercise.8` | 277-278 | Bit-flip algorithm ancillary outcome | UNVERIFIED |

### Chapter 13: Tools of Quantum Information Theory

| ID | Printed page | Reconciled concept | Status |
|---|---|---|---|
| `ch13.section.1` | 279 | The No-Cloning Theorem | PRIMITIVE_ONLY |
| `ch13.section.2` | 281 | Trace Distance | PRIMITIVE_ONLY |
| `ch13.section.3` | 286 | Fidelity | PRIMITIVE_ONLY |
| `ch13.section.4` | 291 | Entanglement of Formation and Concurrence | PRIMITIVE_ONLY |
| `ch13.section.5` | 296 | Information Content and Entropy | PRIMITIVE_ONLY |
| `ch13.example.1` | 282 | Two commuting trace distances | PRIMITIVE_ONLY |
| `ch13.example.2` | 283 | Trace norm and Bloch-distance cross-check | PRIMITIVE_ONLY |
| `ch13.example.3` | 285 | Basis conversion and distance from mixed rho | PRIMITIVE_ONLY |
| `ch13.example.4` | 287 | Two commuting root fidelities | PRIMITIVE_ONLY |
| `ch13.example.5` | 289 | Square both preceding root fidelities | PRIMITIVE_ONLY |
| `ch13.example.6` | 289 | Two squared-Bures distances and comparison | PRIMITIVE_ONLY |
| `ch13.example.7` | 290 | Worst-case channel fidelity and minimizing state | UNVERIFIED |
| `ch13.example.8` | 291 | Product spin flip and concurrence via two routes | PRIMITIVE_ONLY |
| `ch13.example.9` | 293 | Singlet spin flip, spectrum and concurrence | PRIMITIVE_ONLY |
| `ch13.example.10` | 294 | Phi+ spin flip, spectrum and concurrence | PRIMITIVE_ONLY |
| `ch13.example.11` | 295 | Werner spectrum, concurrence and EoF | UNVERIFIED |
| `ch13.example.12` | 298 | Maximally mixed spectrum and entropy | PRIMITIVE_ONLY |
| `ch13.example.13` | 299 | Two diagonal entropies and ordering | PRIMITIVE_ONLY |
| `ch13.example.14` | 299 | Nondiagonal spectrum, purity and entropy | PRIMITIVE_ONLY |
| `ch13.example.15` | 300 | Plus-state spectrum and zero entropy | PRIMITIVE_ONLY |
| `ch13.example.16` | 301 | Basis-invariant spectrum and entropy | PRIMITIVE_ONLY |
| `ch13.example.17` | 302 | Phi-minus global and both marginal entropies | PRIMITIVE_ONLY |
| `ch13.exercise.1` | 303-304 | Trace distance in Hadamard basis | PRIMITIVE_ONLY |
| `ch13.exercise.2` | 303-304 | Commuting root-fidelity formula proof | PRIMITIVE_ONLY |
| `ch13.exercise.3` | 303-304 | Trace distances and root fidelities | PRIMITIVE_ONLY |
| `ch13.exercise.4` | 303-304 | Worst-case pure-state channel fidelity | UNVERIFIED |
| `ch13.exercise.5` | 303-304 | Werner concurrence | PRIMITIVE_ONLY |
| `ch13.exercise.6` | 303-304 | Werner entanglement of formation | PRIMITIVE_ONLY |
| `ch13.exercise.7` | 303-304 | Diagonal mixed-state entropy | PRIMITIVE_ONLY |
| `ch13.exercise.8` | 303-304 | Pure-state entropy | UNVERIFIED |
| `ch13.exercise.9` | 303-304 | Product global and marginal entropy | PRIMITIVE_ONLY |
| `ch13.exercise.10` | 303-304 | Compare two pure-state entropies | UNVERIFIED |
| `ch13.yti.1` | 283 | Three matrix representations and two distances for Example13.1 | PRIMITIVE_ONLY |
| `ch13.yti.2` | 296 | EoF of Example13.9 and Example13.10 separately | PRIMITIVE_ONLY |

### Chapter 14: Adiabatic Quantum Computation

| ID | Printed page | Reconciled concept | Status |
|---|---|---|---|
| `ch14.section.1` | 308 | Adiabatic Processes | PRIMITIVE_ONLY |
| `ch14.section.2` | 310 | Adiabatic Quantum Computing | PRIMITIVE_ONLY |
| `ch14.example.1` | 307 | Infinite square-well stationary states and energies | PRIMITIVE_ONLY |
| `ch14.example.2` | 308-309 | Adiabatic well widening a to3a | PRIMITIVE_ONLY |
| `ch14.example.3` | 310-313 | Adiabatic Hadamard ground-state recipe | PRIMITIVE_ONLY |
| `ch14.exercise.1` | 313 | Separable Schrodinger time dependence derivation | NOT_STARTED |
| `ch14.exercise.2` | 313 | Characteristic time dimensional analysis | NOT_STARTED |
| `ch14.exercise.3` | 313 | Adiabatic contraction of excited-state well | NOT_STARTED |
| `ch14.exercise.4` | 313 | Adiabatic CNOT with nonlinear coupling path | NOT_STARTED |

### Chapter 15: Cluster State Quantum Computing

| ID | Printed page | Reconciled concept | Status |
|---|---|---|---|
| `ch15.section.1` | 316 | Cluster States | PRIMITIVE_ONLY |
| `ch15.section.2` | 316 | Cluster State Preparation | PRIMITIVE_ONLY |
| `ch15.section.3` | 319 | Adjacency Matrices | PRIMITIVE_ONLY |
| `ch15.section.4` | 320 | Stabilizer States | PRIMITIVE_ONLY |
| `ch15.section.5` | 322 | Aside: Entanglement Witness | PRIMITIVE_ONLY |
| `ch15.section.6` | 324 | Cluster State Processing | PRIMITIVE_ONLY |
| `ch15.example.1` | 317 | Three-node lambda then triangle graph states | PRIMITIVE_ONLY |
| `ch15.example.2` | 326 | Five-qubit cluster Hadamard via X Y Y Y | UNVERIFIED |
| `ch15.exercise.1` | 326-327 | Local Hadamards turn source lambda into GHZ | PRIMITIVE_ONLY |
| `ch15.exercise.2` | 326-327 | Adjacency matrix of pictured graph | UNVERIFIED |
| `ch15.exercise.3` | 326-327 | CZ computational-basis phases | PRIMITIVE_ONLY |
| `ch15.exercise.4` | 326-327 | Cluster pi/2 phase gate | PRIMITIVE_ONLY |
| `ch15.exercise.5` | 326-327 | Signed XX ZZ stabilizers across Bell basis | PRIMITIVE_ONLY |
| `ch15.exercise.6` | 326-327 | GHZ stabilizers | PRIMITIVE_ONLY |

## Child-record navigation

In JSON, `identified_subparts` contains563 task-output groups with IDs such as `ch05.example.7.output.5` (requested computational probabilities); `identified_body_records` contains92 page-located body/table/figure groups with IDs `chNN.body.N`. Each records its parent where established, source observation, evidence, classification, status and limitation. Embedded prompts remain children/body records rather than fabricated numbered examples. Their status accounting above is separate from the413 retained records.

This reconciliation is complete as a documentation integration of the collected evidence, **not a completed source-specific fixture corpus, visual audit or exhaustive substantive/subpart enumeration**.
