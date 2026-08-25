# Hardware Models

Implementation: `backend/app/hardware/*`. Validation: `test_hardware.py`.

## HardwareProfile

Data-driven simulation configuration. Fields: qubit count, coupling graph
(undirected), native gate set (name/arity/duration/error-rate), T1/T2,
asymmetric readout rates, measurement/reset durations.

**These are MODEL PROFILES, explicitly labeled** (`model_label` on every
profile and API response). They do not represent specific commercial devices.

| Preset | Coupling | Character |
|--------|----------|-----------|
| Ideal-8Q | all-to-all | zero error, zero duration |
| NoisyGeneric-8Q | line | generic error rates, µs-scale T1/T2 |
| SuperconductingInspired-16Q | 4×4 grid | ns gates, ~100 µs coherence |
| TrappedIonInspired-10Q | all-to-all | slower gates, long coherence |

## Transpiler

- Trivial initial mapping; on-demand SWAP insertion along BFS shortest coupling
  paths for non-adjacent two-qubit gates.
- Logical→physical permutation tracked through every swap; final mapping
  returned so measurement keys can be interpreted.
- Non-native gates are REJECTED with an actionable message (no silent
  decomposition fallbacks — §142).
- Correctness contract: under ideal execution M_mapped = P_end · M_logical;
  verified by dense unitary column-scatter comparison for ≤7-qubit circuits.
  Statevector-level equivalence additionally tested with remapped counts.

## Noise-aware execution

`to_noise_model(profile)` converts the profile into an executor NoiseModel:
per-gate depolarizing ⊗ thermal relaxation (T1/T2 at gate duration),
asymmetric readout at measurement. Composition uses the validated
CompositeChannel.

## Circuit analysis

Measured structural metrics only: depth, per-arity gate counts, measurements,
resets, barriers, parameter count, connectivity pairs used, gate histogram.
T-count/T-depth follow standard Clifford+T accounting and are reported as
None when ANY gate lacks a defined cost — never invented (§9).

## Limitations

- SWAP routing is shortest-path greedy, not optimal-depth search.
- Mapping verification is dense (≤7 qubits).
- Presets are phenomenological: no crosstalk, no correlated noise, no leakage.
