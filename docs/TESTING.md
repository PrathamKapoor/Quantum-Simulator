# QuantumLab — Testing

## Categories (directive §137)

1. **Mathematical** — does each calculation make sense? Gate truth tables,
   unitarity, rotation-generator identities, entropy/fidelity reference values.
2. **Simulation** — does the engine behave correctly? Mid-circuit measurement,
   conditioning, reset semantics, noise trajectories, readout error, shot fast
   path equivalence, density/statevector agreement.
3. **Integration** — do modules work together? Teleportation through the circuit
   engine, repeater-chain swapping through the network engine, experiment
   lifecycle over SQLite, API end-to-end flows including background job execution.
4. **UI** — can a user operate the system? Manual inspection during development;
   automated browser tests are future work (documented limitation).

## Cross-checking strategy (§151)

Fast implementations are validated against independent references:
gate application vs explicit Kronecker embedding; QFT circuit vs DFT matrix;
quantum walk vs an independent loop implementation; VQE vs exact spectra;
QAOA vs brute-force MaxCut; swap fidelity vs analytic limiting cases;
BB84 QBER vs theoretical intercept-resend statistics.

## Running

```bash
# fast suite (~80 s)
cd backend && ..\.venv\Scripts\python -m pytest tests --timeout=300

# single module
python -m pytest tests/test_network.py -v

# extended validation (long Monte Carlo, run when idle)
python -m pytest tests -m extended
```

## Reference-value regression suite (§152)

H|0⟩→|+⟩; H² = I; S·S† = T·T† = I; Bell counts {00,11}; GHZ marginals diagonal;
QFT(3q) equals F matrix elementwise; Grover peak within ±1 iteration of
analytic optimum; phase estimation error < 2^-t+²; order of 7 mod 15 = 4;
TFIM limiting-case spectra; CHSH threshold at visibility 1/√2.

## Regression policy (§146)

Every bug found during development receives a test before the fix is considered
complete. Session-1 examples: little-endian/local-basis conversion for oracle
matrices, Simon mid-circuit collapse ordering, QPE precision-register size,
shots=None trajectory execution, reset-to-zero semantics, fast-path marginal
sampling scope, toric star incidence geometry.
