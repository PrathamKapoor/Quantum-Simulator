"""Adiabatic quantum computation (McMahon chapter 14).

Implements the linear-interpolation Hamiltonian path used in the book,

    H(s) = (1 - s) H_initial + s H_final,   s in [0, 1],

with an optional nonlinear coupling term `s (1 - s) H_coupling`
(Exercise 14.4: supplied diagonal endpoints plus off-diagonal coupling
that opens avoided crossings),

and the adiabatic experiment: prepare an H_initial eigenstate,
evolve under H(s) with a time-dependent Schrodinger solver, and
measure the final eigenstate overlap, excitation probability, and
the minimum instantaneous spectral gap along the path.

Exactness classes (directive §79): the gap curve is EXACT diagonal-
ization of the interpolated Hamiltonian at each sampled s; the
evolution is NUMERICALLY EXACT within the Trotter step tolerance of
`scipy.linalg.expm` applied piecewise (documented approximation:
piecewise-constant H over `steps` intervals, first-order Trotter).

Size limits (§90): dense evolution is O(dim^3) per step — practical
for 2-8 qubits in tests; larger systems are possible but slow. The
API reports the dimension used.
"""
from __future__ import annotations

import numpy as np
from scipy.linalg import expm

from .states import QuantumCoreError, StateVector


def interpolated_hamiltonian(h_initial: np.ndarray, h_final: np.ndarray,
                             s: float,
                             coupling: np.ndarray | None = None) -> np.ndarray:
    """H(s) = (1 - s) H_initial + s H_final [+ s(1-s) H_coupling].

    Without `coupling` this is exactly the historical linear path.
    """
    if not (0.0 <= s <= 1.0):
        raise QuantumCoreError(f"s must be within [0, 1], got {s}.")
    hi = np.asarray(h_initial, dtype=np.complex128)
    hf = np.asarray(h_final, dtype=np.complex128)
    if hi.shape != hf.shape or hi.shape[0] != hi.shape[1]:
        raise QuantumCoreError("H_initial and H_final must be same-size square matrices.")
    checked = [(hi, "H_initial"), (hf, "H_final")]
    if coupling is not None:
        hc = np.asarray(coupling, dtype=np.complex128)
        if hc.shape != hi.shape:
            raise QuantumCoreError("H_coupling must match H_initial/H_final shape.")
        checked.append((hc, "H_coupling"))
    for h, name in checked:
        dev = float(np.max(np.abs(h - h.conj().T)))
        if dev > 1e-9:
            raise QuantumCoreError(f"{name} is not Hermitian (deviation {dev:.3e}).")
    out = (1.0 - s) * hi + s * hf
    if coupling is not None:
        out = out + s * (1.0 - s) * hc
    return out


def spectral_gap_curve(h_initial: np.ndarray, h_final: np.ndarray,
                       samples: int = 51,
                       coupling: np.ndarray | None = None) -> dict:
    """Instantaneous gap (E1 - E0) along the path — exact diagonalization."""
    if samples < 2:
        raise QuantumCoreError("samples must be >= 2.")
    ss = np.linspace(0.0, 1.0, samples)
    gaps, ground_overlaps_between = [], []
    prev_ground = None
    for s in ss:
        evals, evecs = np.linalg.eigh(
            interpolated_hamiltonian(h_initial, h_final, s, coupling=coupling))
        gaps.append(float(evals[1] - evals[0]))
        ground = evecs[:, 0]
        if prev_ground is not None:
            ground_overlaps_between.append(
                float(abs(np.vdot(prev_ground, ground)) ** 2))
        prev_ground = ground
    return {"s": ss.tolist(), "gap": gaps,
            "min_gap": min(gaps), "min_gap_s": float(ss[int(np.argmin(gaps))]),
            "ground_state_continuity_min": min(ground_overlaps_between)}


def adiabatic_evolution(h_initial: np.ndarray, h_final: np.ndarray,
                        total_time: float, steps: int = 200,
                        shots: int = 0, seed: int = 0,
                        coupling: np.ndarray | None = None,
                        initial_level: int = 0) -> dict:
    """Evolve under H(t) = H(s(t)), s = t/T, starting from the H_initial
    eigenstate `initial_level` (default ground). Returns the final state,
    its overlap with the H_final ground state, per-level overlaps with
    every H_final eigenstate, and (optionally) sampled outcomes."""
    if total_time <= 0:
        raise QuantumCoreError("total_time must be positive.")
    if steps < 1:
        raise QuantumCoreError("steps must be >= 1.")
    dim = np.asarray(h_initial).shape[0]
    if not isinstance(initial_level, int) or isinstance(initial_level, bool) \
            or not 0 <= initial_level < dim:
        raise QuantumCoreError("initial_level must index an eigenstate.")
    evals0, evecs0 = np.linalg.eigh(
        interpolated_hamiltonian(h_initial, h_final, 0.0, coupling=coupling))
    state = evecs0[:, initial_level].astype(np.complex128)
    dt = total_time / steps
    for k in range(steps):
        s = (k + 0.5) / steps           # midpoint rule
        h = interpolated_hamiltonian(h_initial, h_final, s, coupling=coupling)
        state = expm(-1j * h * dt) @ state
    evalsf, evecsf = np.linalg.eigh(
        interpolated_hamiltonian(h_initial, h_final, 1.0, coupling=coupling))
    ground = evecsf[:, 0]
    overlap = float(abs(np.vdot(ground, state)) ** 2)
    level_overlaps = [float(abs(np.vdot(evecsf[:, j], state)) ** 2)
                      for j in range(evecsf.shape[1])]
    excitation = 1.0 - overlap
    probabilities = np.abs(state) ** 2
    result = {
        "total_time": total_time, "steps": steps, "dimension": h_initial.shape[0],
        "min_gap": spectral_gap_curve(
            h_initial, h_final, 51, coupling=coupling)["min_gap"],
        "initial_level": initial_level,
        "ground_state_overlap": overlap,
        "level_overlaps": level_overlaps,
        "excitation_probability": excitation,
        "final_probabilities": probabilities.tolist(),
        "final_state": state.tolist(),
        "exactness": "piecewise-constant evolution (first-order, midpoint H); gap exact diagonalization",
    }
    if shots:
        rng = np.random.default_rng(seed)
        counts: dict[int, int] = {}
        for _ in range(int(shots)):
            idx = int(rng.choice(len(probabilities), p=probabilities / probabilities.sum()))
            counts[idx] = counts.get(idx, 0) + 1
        result["shot_counts"] = {str(k): v for k, v in sorted(counts.items())}
    return result


def adiabatic_scan(h_initial: np.ndarray, h_final: np.ndarray,
                   times: list[float], steps: int = 200,
                   coupling: np.ndarray | None = None) -> list[dict]:
    """Ground-state overlap as a function of total evolution time —
    the adiabaticity curve (slow enough -> overlap -> 1)."""
    return [adiabatic_evolution(h_initial, h_final, t, steps=steps,
                                coupling=coupling)
            for t in times]
