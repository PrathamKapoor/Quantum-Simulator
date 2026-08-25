# Error Mitigation Models

Implementation: `backend/app/mitigation/`. Validation: `test_mitigation.py`.
Every mitigated result ships with the RAW unmitigated estimate alongside.

## Readout error mitigation

- Assignment matrix A[measured, true] = tensor product of single-qubit
  confusions (asymmetric rates supported). Practical bound: ≤ 8 qubits.
- Inversion via least squares (`lstsq`); condition number REPORTED with a
  well-conditioned/ill-conditioned verdict.
- Negative quasi-probabilities are clipped and renormalized; the clipped mass
  is reported so reliability can be judged. All-zero solutions raise.

## Zero-noise extrapolation

- Noise scaling: odd-integral global unitary folding U → U(U†U)^{(s−1)/2}.
  Folding preserves the logical unitary exactly (validated by dense unitary
  comparison) while multiplying effective noise depth.
- Estimation runs in EXACT density-matrix mode so observables see the channel
  action, not single-trajectory noise (a real bug found by testing: trajectory
  samples produced ±1 estimates).
- Extrapolation models: linear / quadratic polynomial fits over
  (scale, estimate) points; evaluated at zero.
- HONESTY RULES: raw samples always returned; residuals shown; physically
  implausible extrapolations (far outside measured range, sign flips, large
  residuals) produce WARNINGS — values are never silently clipped.

Validated end-to-end: noisy Bell ⟨ZZ⟩ raw 0.9216 → extrapolated 0.9696 toward
ideal 1.0 at depolarizing p=0.04.

## Symmetry verification

Parity postselection for circuits whose ideal outputs obey a parity sector:
violating shots discarded; kept/discarded counts and discard_rate reported
with an explicit biasing note. The caller asserts the symmetry; the module
cannot verify physical validity of that assertion.

## Limitations

- Readout model assumes tensor-product (uncorrelated) confusion.
- Folding requires every operation to have an implemented inverse rule;
  measurements/resets make circuits unfoldable (clear error).
- ZNE assumes monotone-ish decay within the sampled range — flagged when the
  data contradicts this.
