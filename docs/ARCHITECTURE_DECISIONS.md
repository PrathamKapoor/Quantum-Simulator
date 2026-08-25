# Architecture Decisions

Significant decisions with reasons, alternatives, and consequences (§176).

## AD-001 — Little-endian qubit ordering platform-wide
- **Decision:** qubit 0 = least-significant basis bit everywhere.
- **Reason:** matches Qiskit-style mental model and numpy reshape conventions
  used by the axis-based gate application.
- **Alternative rejected:** big-endian (textbook ket reading) — would require
  conversions at every UI boundary.
- **Consequence:** register strings print high-bit-first; documented in the
  quantum package docstring and tested.

## AD-002 — Gate-local operand convention + explicit conversion helper
- **Decision:** k-qubit gate matrices use FIRST operand as most-significant
  local bit; truth-table-indexed matrices must pass through
  `app/algorithms/conventions.local_reorder`.
- **Reason:** single well-defined convention; conversion is testable.
- **Consequence:** three session-1 bugs traced to skipping this conversion;
  now enforced by convention tests and documented in SCIENTIFIC_MODELS.md.

## AD-003 — Partial-trace einsum output ordering (bug fix elevated to decision)
- **Decision:** kept ROW letters first, then kept COLUMN letters, in the
  einsum output spec of `DensityMatrix.partial_trace`.
- **Incident:** interleaved per-qubit [row,col] output silently produced
  transposed-axis mixing for multi-qubit keeps; diagonal marginals (GHZ)
  masked it until distributed remote-CNOT validation hit an off-diagonal case.
- **Alternatives:** keep interleaving and transpose after — equivalent but
  obscures the invariant.
- **Consequence:** regression tests require off-diagonal multi-qubit keeps,
  full-system identity, and random-state trace preservation.

## AD-004 — Teleportation correction order: X before Z
- **Decision:** conditioned corrections apply X^{mx} then Z^{mz}.
- **Reason:** Bob's pre-correction state is Z^{mz}X^{mx}|ψ⟩.
- **Incident:** wrong order is invisible for isolated teleportation (differs
  only by global phase) but corrupts circuits where the teleported wire later
  participates in entangling operations (distributed CNOT).
- **Consequence:** distributed remote-CNOT validates bit-exact; standalone
  teleportation tests unchanged (fidelity-based).

## AD-005 — Network engine exception guard surfaces errors
- **Decision:** engine-level guards append to `result.engine_errors` instead
  of silently continuing.
- **Incident:** a missing import was swallowed for a full test cycle.
- **Consequence:** API consumers can inspect `engine_errors`; silent failure
  class eliminated.

## AD-006 — Purification refuses asymmetric inputs
- **Decision:** BBPSSW/DEJMPS require identical input fidelities; mismatches
  skip purification rather than approximate.
- **Reason:** recurrence math assumes symmetric inputs; approximating would
  violate RULE 2.
- **Consequence:** network integration may skip purification opportunities;
  documented in NETWORK_MODELS.md.

## AD-007 — ZNE uses density-matrix expectations
- **Decision:** ZNE driver executes folded circuits in exact density-matrix
  mode.
- **Incident:** statevector trajectories produced ±1 "estimates" that fit
  garbage extrapolations.
- **Consequence:** bounded at 12 qubits; smooth scale-dependent estimates.

## AD-008 — No dependency additions (RULE 7)
- **Decision:** all Phase A–H capabilities implemented on numpy/scipy/stdlib.
- **Consequence:** Student-t quantiles replaced by normal approximation with
  documented CLT assumption; bootstrap provided as robust alternative.
