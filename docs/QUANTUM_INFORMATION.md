# Quantum Information Models

Every quantity: definition, formula, domain, numerical method, edge cases.
Implementation: `backend/app/quantum/info_theory.py`; validation:
`backend/tests/test_info_theory.py` (analytic values, not cross-implementation
checks). Entropies in BITS unless suffixed `_nats`.

## Conventions & numerical policy

- Little-endian qubit ordering platform-wide.
- Eigenvalue-based quantities clip eigenvalues into [0,1] at tolerance 1e-12;
  eigenvalues < −1e−8 raise `QuantumCoreError` (corrupt input) rather than
  producing silent nonsense.

## Entropies

| Quantity | Formula | Domain | Notes |
|----------|---------|--------|-------|
| von Neumann entropy | S = −Tr ρ log₂ρ | any ρ | pure→0; max log₂ d |
| Rényi entropy | S_α = ln Tr(ρ^α)/(1−α), base 2 | α>0, α≠1 | α=1 branch returns von Neumann; monotone ↓ in α |
| min-entropy | H_min = −log₂ λ_max | any ρ | largest Rényi; pure→0 |
| linear entropy | S_L = 1 − Tr ρ² | any ρ | range [0, 1−1/d] |

Validated: |0⟩/|+⟩ → all zero; maximally mixed d=2^n → n bits for all α;
Rényi(0.999) ≈ von Neumann.

## Distinguishability

| Quantity | Formula | Properties tested |
|----------|---------|-------------------|
| trace distance | ½Tr\|ρ−σ\| | orthogonal→1; identical→0 |
| relative entropy | D(ρ\|\|σ) = −S(ρ) − Tr(ρ log₂σ) | D(ρ\|\|ρ)=0; D(ρ\|\|I/d)=log₂d−S; support violation RAISES (never returns inf); non-negativity checked numerically |

## Bipartite / correlations

| Quantity | Formula | Scope & notes |
|----------|---------|---------------|
| mutual information | I(A:B)=S_A+S_B−S_AB | Bell → exactly 2 bits; product → 0 |
| conditional entropy | S(A\|B)=S_AB−S_B | NEGATIVE for entangled states (pure Bell → −1 bit): meaningful, not an error |
| correlation matrix | T[i,j]=⟨σ_i⊗σ_j⟩ | two qubits only; \|Φ+⟩ → diag(1,−1,1); product states rank-1 |

## Entanglement measures

| Quantity | Formula | Scope |
|----------|---------|-------|
| entanglement entropy | S(reduced) | canonical ONLY for pure globals |
| concurrence | C = max(0, √λ₁−√λ₂−√λ₃−√λ₄), λ from R=ρ(sy⊗sy)ρ*(sy⊗sy) | two-qubit only (enforced); Bell→1; isotropic state F: C=max(0,(3F−1)/2) |
| negativity | N=(‖ρ^{T_A}‖₁−1)/2 | partial transpose over chosen subsystem; symmetric under subsystem swap |
| log. negativity | E_N=log₂‖ρ^{T_A}‖₁ | identity E_N=log₂(2N+1) holds |
| Schmidt decomposition/rank | SVD of dim_A×dim_B coefficient matrix | reconstruction validated; rank 1 iff product |

## Separability diagnostics

PPT test with HONEST scope labeling: necessary AND sufficient for 2×2 and 2×3
bipartitions (Peres–Horodecki); in higher dimensions a passing PPT test is
reported as `ppt_inconclusive` — bound-entangled states would pass PPT while
entangled. The report includes the basis string so UIs can display it.

## Edge cases handled

- Zero-eigenvalue handling in logs (clip at 1e−12).
- Support violation for relative entropy raises instead of returning inf.
- Multi-qubit `partial_trace` output ordering regression (see
  ARCHITECTURE_DECISIONS.md AD-003).
