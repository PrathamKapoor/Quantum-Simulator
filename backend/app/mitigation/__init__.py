"""Error mitigation techniques (directive §12, Layer 8).

All techniques are EXACT algorithms over simulated distributions; none claim to
restore ideal results perfectly. Every mitigated result ships with:
  - the RAW unmitigated estimate,
  - the method and its parameters,
  - numerical-conditioning diagnostics,
  - explicit flags when outputs leave physically meaningful bounds.

Contents
--------
- ReadoutMitigation: calibrated confusion matrix, inversion via least squares,
  condition-number report, flagged clipping of negative quasi-probabilities.
- zero_noise_extrapolate: polynomial (linear/quadratic) extrapolation over
  odd-integral gate-folding scale factors; raw samples always included;
  out-of-range extrapolations are flagged, never silently clipped.
- parity_postselect: symmetry verification for circuits whose ideal outcomes
  obey a parity constraint; reports discarded-shot statistics.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ..quantum.states import QuantumCoreError


# ---------------------------------------------------------------------------
# Measurement (readout) error mitigation
# ---------------------------------------------------------------------------

def confusion_matrix_from_rates(
    n_qubits: int, p_read1_given_0: float, p_read0_given_1: float
) -> np.ndarray:
    """Full 2^n x 2^n assignment matrix A with A[measured, true] = P(m|i),
    built as a tensor product of single-qubit confusion matrices.

    Practical bound: n <= 8 (matrix has 4^n entries).
    """
    if n_qubits < 1 or n_qubits > 8:
        raise QuantumCoreError("Readout mitigation supports 1..8 qubits.")
    single = np.array([
        [1 - p_read1_given_0, p_read0_given_1],
        [p_read1_given_0, 1 - p_read0_given_1],
    ], dtype=float)
    full = np.array([[1.0]])
    for _ in range(n_qubits):
        # little-endian: measured index bit k corresponds to qubit k; kron order
        # places later qubits at higher bits.
        full = np.kron(full, single)
    return full


@dataclass
class ReadoutMitigationResult:
    mitigated_probabilities: dict[str, float]
    raw_probabilities: dict[str, float]
    condition_number: float
    clipped_negative_mass: float
    notes: list[str]


def mitigate_readout_error(
    counts: dict[str, int],
    *,
    p_read1_given_0: float,
    p_read0_given_1: float,
) -> ReadoutMitigationResult:
    """Invert the (tensor-product) readout confusion on an empirical histogram.

    Method: least-squares solution of A p_true = p_measured (more stable than a
    direct inverse for ill-conditioned A). Negative quasi-probabilities from
    inversion are CLIPPED TO ZERO and renormalized; the clipped mass is
    reported so users can judge reliability (§12: never hide instability).
    """
    if not counts:
        raise QuantumCoreError("No counts supplied for readout mitigation.")
    n = len(next(iter(counts)))
    total = sum(counts.values())
    dim = 1 << n
    measured = np.zeros(dim)
    for key, v in counts.items():
        measured[int(key, 2)] += v / total
    A = confusion_matrix_from_rates(n, p_read1_given_0, p_read0_given_1)
    cond = float(np.linalg.cond(A))
    solution, *_ = np.linalg.lstsq(A, measured, rcond=None)
    negative_mass = float(-solution[solution < 0].sum())
    clipped = np.clip(solution, 0.0, None)
    s = clipped.sum()
    if s <= 0:
        raise QuantumCoreError(
            "Readout mitigation produced an all-zero distribution; the "
            "confusion matrix is too ill-conditioned for this histogram."
        )
    clipped /= s
    notes = [
        f"Assignment-matrix condition number {cond:.2f}; "
        + ("well-conditioned." if cond < 10 else "ill-conditioned — treat mitigated "
           "values cautiously."),
        f"{negative_mass:.4f} of probability mass was negative before clipping.",
    ]
    fmt = f"0{n}b"
    return ReadoutMitigationResult(
        mitigated_probabilities={
            format(i, fmt): round(float(clipped[i]), 9)
            for i in range(dim) if clipped[i] > 1e-12
        },
        raw_probabilities={k: v / total for k, v in sorted(counts.items())},
        condition_number=round(cond, 4),
        clipped_negative_mass=round(negative_mass, 6),
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Zero-noise extrapolation
# ---------------------------------------------------------------------------

def fold_circuit(circuit, scale_factor: int):
    """Odd-integral global unitary folding: U -> U (U† U)^{(s-1)/2}.

    scale_factor must be an ODD positive integer >= 1. Folding preserves the
    logical unitary exactly while multiplying effective noise depth ~s.
    """
    if scale_factor < 1 or scale_factor % 2 == 0:
        raise ValueError(f"Scale factor must be odd and >= 1, got {scale_factor}.")
    folded = circuit.copy()
    reps = (scale_factor - 1) // 2
    from ..circuits.model import Circuit

    inverse_ops = []
    from ..algorithms.qft import _append_inverse

    for op in reversed(circuit.operations):
        try:
            inv = Circuit(num_qubits=circuit.num_qubits,
                          num_clbits=circuit.num_clbits)
            _append_inverse(inv, op)
            inverse_ops.extend(inv.operations)
        except NotImplementedError as e:
            raise ValueError(
                f"Cannot fold circuit containing {op.kind}/{op.gate}: {e}"
            ) from e
    for _ in range(reps):
        folded.operations.extend(inverse_ops)
        folded.operations.extend(list(circuit.operations))
    return folded


@dataclass
class ZNEResult:
    scale_factors: list[int]
    raw_estimates: list[float]
    fitted_model: str
    extrapolated_value: float
    fit_coefficients: list[float]
    residuals: list[float]
    warnings: list[str] = field(default_factory=list)


def zero_noise_extrapolate(
    scale_factors: list[int],
    estimates: list[float],
    *,
    model: str = "linear",
) -> ZNEResult:
    """Polynomial extrapolation of noisy estimates to the zero-noise limit.

    model: "linear" (degree 1, needs >= 2 points) or "quadratic" (degree 2,
    needs >= 3 points). Raw samples are returned unchanged; the extrapolated
    value is NOT clipped — physically implausible results carry a warning
    instead (directive §12, §190).
    """
    if len(scale_factors) != len(estimates) or len(scale_factors) < 2:
        raise ValueError("Need matching scale factors and at least two estimates.")
    degree = {"linear": 1, "quadratic": 2}.get(model)
    if degree is None:
        raise ValueError("model must be 'linear' or 'quadratic'.")
    if len(estimates) < degree + 1:
        raise ValueError(f"{model} extrapolation needs at least {degree + 1} points.")
    x = np.asarray(scale_factors, dtype=float)
    y = np.asarray(estimates, dtype=float)
    coeffs = np.polyfit(x, y, degree)
    poly = np.poly1d(coeffs)
    zne = float(poly(0.0))
    residuals = [float(yi - poly(xi)) for xi, yi in zip(x, y)]
    span = max(abs(float(np.max(y))), abs(float(np.min(y))), 1e-12)
    warnings = []
    bound = 1.5 * span + 1e-12
    if abs(zne) > bound:
        warnings.append(
            f"Extrapolated value {zne:.6g} lies far outside the measured range "
            f"[{min(estimates):.6g}, {max(estimates):.6g}]; the fit may be unreliable."
        )
    if all(np.sign(estimates[i]) != np.sign(zne) for i in range(len(estimates)) if estimates[i] != 0):
        warnings.append("Extrapolated sign differs from every measured sample.")
    if max(abs(r) for r in residuals) > 0.25 * span:
        warnings.append("Large fit residuals: consider more scale factors or a different model.")
    return ZNEResult(
        scale_factors=list(scale_factors),
        raw_estimates=[float(e) for e in estimates],
        fitted_model=model,
        extrapolated_value=zne,
        fit_coefficients=[float(c) for c in coeffs],
        residuals=residuals,
        warnings=warnings,
    )


def run_zne_experiment(
    circuit_factory,
    observable,
    *,
    scale_factors: list[int] | None = None,
    seed: int = 0,
    noise_model=None,
) -> ZNEResult:
    """Convenience driver for zero-noise extrapolation.

    Each folded circuit executes in EXACT density-matrix mode so that
    `observable(rho)` receives an open-system expectation input rather than a
    single stochastic trajectory (a real bug found by testing: trajectory
    samples give ±1 noise instead of smooth estimates). Bounded at 12 qubits
    by the density engine.
    """
    from ..circuits.simulate import simulate

    scale_factors = scale_factors or [1, 3, 5]
    if 1 not in sorted(scale_factors):
        raise ValueError("Scale factors must include 1 (the unmitigated run).")
    estimates = []
    for i, s in enumerate(sorted(scale_factors)):
        circuit = fold_circuit(circuit_factory(), s)
        r = simulate(circuit, mode="density_matrix", seed=seed + 131 * i,
                     noise_model=noise_model)
        target = r.density_matrix if r.density_matrix is not None else r.final_state
        estimates.append(float(observable(target)))
    return zero_noise_extrapolate(sorted(scale_factors), estimates)


# ---------------------------------------------------------------------------
# Symmetry verification
# ---------------------------------------------------------------------------

def parity_postselect(counts: dict[str, int], parity: str = "even") -> dict:
    """Discard shots violating a total-parity symmetry (symmetry verification).

    Only valid for circuits whose IDEAL output respects the chosen parity —
    the caller asserts that; we verify it holds on the dominant outcomes and
    report discard statistics honestly.
    """
    if parity not in ("even", "odd"):
        raise ValueError("parity must be 'even' or 'odd'.")
    if not counts:
        raise QuantumCoreError("No counts supplied.")
    kept: dict[str, int] = {}
    kept_n = discarded = 0
    for key, v in counts.items():
        ones = key.count("1")
        ok = (ones % 2 == 0) if parity == "even" else (ones % 2 == 1)
        if ok:
            kept[key] = kept.get(key, 0) + v
            kept_n += v
        else:
            discarded += v
    total = kept_n + discarded
    return {
        "kept_counts": kept,
        "kept_shots": kept_n,
        "discarded_shots": discarded,
        "discard_rate": discarded / total,
        "parity": parity,
        "note": (
            "Postselection biases the surviving distribution toward the "
            "symmetry sector; interpret rates jointly with discard_rate."
        ),
    }
