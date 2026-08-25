# QEC Models

Implementation: `backend/app/qec/*`. Validation: `test_qec.py`.

## Framework

- Errors/corrections are Pauli strings; syndromes computed group-theoretically
  (anticommutes-with-generator bits). Exact for Pauli noise; the benchmark
  path does NOT simulate syndrome-measurement circuits. Circuit-based syndrome
  extraction is demonstrated for the 3-qubit code through the real engine.
- Codes structurally validated at construction: generator commutation,
  logical/stabilizer commutation, logical X·Z anticommutation.
- Lookup decoders enumerate errors up to weight ⌊(d−1)/2⌋ restricted to each
  code's `corrects_paulis` declaration; every table entry verified to leave no
  logical residual.

## Codes

| Code | n | d | corrects | Notes |
|------|---|---|----------|-------|
| bit-flip-3 | 3 | 3 | X only | Y fails legitimately (carries Z) |
| phase-flip-3 | 3 | 3 | Z | H-conjugated repetition |
| Shor-9 | 9 | 3 | X,Y,Z | logicals derived from encoding |
| Steane-7 | 7 | 3 | X,Y,Z | CSS from self-orthogonal Hamming |
| five-qubit | 5 | 3 | X,Y,Z | perfect code |
| toric surface | 2d² | d (verified) | weight-1 decoder | periodic layout, educational |

## Monte Carlo methodology

- Independent depolarizing errors per physical qubit per trial.
- Wilson score 95% confidence intervals; N reported with every estimate.
- Trend validation over distributions, never exact monotonicity of single
  samples (directive §198).
- Threshold claims REFUSED: curves are labeled "logical error-rate crossover /
  trend studies" unless sample sizes justify more (§121).

## Toric surface code

Periodic d×d torus: data qubits on edges, 4-edge X-stars at vertices, 4-edge
Z-plaquettes on faces. Verified programmatically: star/plaquette commutation,
minimum nontrivial logical weight = lattice distance. Decoder corrects single
qubit errors exactly; multi-qubit patterns without a unique weight-1-consistent
syndrome count as FAILURES — this underestimates true capability and results
metadata says so.

## Limitations

- No syndrome-measurement noise, no fault-tolerant circuits, no MWPM decoding.
- Repetition-code benchmarks include Y/Z failures honestly (depolarizing MC),
  so their logical rates exceed the protected-type-only intuition.
