"""Entanglement purification protocols: BBPSSW and DEJMPS (directive §21).

Mathematical model (documented exactly — see docs/NETWORK_MODELS.md)
--------------------------------------------------------------------
Inputs are assumed to be Werner-form pairs with fidelity F toward |Phi+>:
    rho_W(F) = F|Phi+><Phi+| + ((1-F)/3) (I - |Phi+><Phi+|)
Bell-diagonal weights: lam1=F, lam2=lam3=lam4=(1-F)/3.

BBPSSW recurrence for two IDENTICAL inputs:
    p_succ = F^2 + 2F(1-F)/3 + 5((1-F)/3)^2
    F'     = (F^2 + ((1-F)/3)^2) / p_succ
Fixed points: F=1 -> (p=1, F'=1); F=1/2 -> F'=1/2. Purification possible
iff F > 1/2.

DEJMPS recurrence (local bit flips pair lam1 with lam4):
    p_succ = (lam1 + lam4)^2
    F'     = (lam1^2 + lam4^2) / (lam1 + lam4)^2

Both models assume:
  * ideal local operations and Bell measurements,
  * identical input fidelities (asymmetric inputs are UNSUPPORTED here and
    rejected rather than silently approximated),
  * successful purification consumes BOTH input pairs; failure consumes them
    too (resource accounting is exact by construction).

Monte Carlo sampling uses a caller-provided seeded Generator so runs are
reproducible (directive §71-72).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..quantum.states import QuantumCoreError


PROTOCOLS = ("BBPSSW", "DEJMPS")


def bbpsw_recurrence(fidelity: float) -> tuple[float, float]:
    """Returns (F_next, p_success). Valid domain: 1/2 <= F <= 1."""
    _validate_fidelity(fidelity)
    l2 = (1 - fidelity) / 3
    p = fidelity ** 2 + 2 * fidelity * l2 + 5 * l2 ** 2
    f_next = (fidelity ** 2 + l2 ** 2) / p
    return float(min(1.0, f_next)), float(p)


def dejmps_recurrence(fidelity: float) -> tuple[float, float]:
    """Returns (F_next, p_success). Valid domain: 1/2 <= F <= 1."""
    _validate_fidelity(fidelity)
    l4 = (1 - fidelity) / 3
    denom = (fidelity + l4) ** 2
    p = denom
    f_next = (fidelity ** 2 + l4 ** 2) / denom
    return float(min(1.0, f_next)), float(p)


_RECURRENCES = {"BBPSSW": bbpsw_recurrence, "DEJMPS": dejmps_recurrence}


def _validate_fidelity(f: float) -> None:
    if not (0.5 - 1e-9 <= f <= 1.0 + 1e-9):
        raise QuantumCoreError(
            f"Purification requires input fidelity within [0.5, 1], got {f:.6f}. "
            "Below 1/2 the BBPSSW/DEJMPS maps do not purify."
        )


@dataclass
class PurificationOutcome:
    protocol: str
    success: bool
    input_fidelity: float
    output_fidelity: float | None   # deterministic-model fidelity on success
    success_probability: float
    consumed_pairs: int             # always 2 per attempt (exact accounting)
    rounds_performed: int = 1


def purify_once(
    protocol: str,
    input_fidelity: float,
    *,
    rng: np.random.Generator,
) -> PurificationOutcome:
    """One purification attempt on two identical pairs (consumes both).

    The OUTPUT fidelity is the protocol's deterministic recurrence value —
    this is the mathematical model, not a sampled state. Success/failure is
    Bernoulli-sampled from p_succ with the provided RNG.
    """
    if protocol not in _RECURRENCES:
        raise QuantumCoreError(
            f"Unknown purification protocol {protocol!r}; available {sorted(_RECURRENCES)}."
        )
    f_next, p = _RECURRENCES[protocol](input_fidelity)
    success = bool(rng.random() < p)
    return PurificationOutcome(
        protocol=protocol,
        success=success,
        input_fidelity=input_fidelity,
        output_fidelity=f_next if success else None,
        success_probability=p,
        consumed_pairs=2,
    )


@dataclass
class PurificationScheduleResult:
    protocol: str
    initial_fidelity: float
    target_fidelity: float
    achieved: bool
    final_fidelity: float | None
    rounds_requested: int
    rounds_succeeded: int
    pairs_consumed: int
    cumulative_success_probability: float
    expected_fidelity_trajectory: list[float]
    notes: list[str] = field(default_factory=list)


def purify_to_target(
    protocol: str,
    initial_fidelity: float,
    target_fidelity: float,
    *,
    max_rounds: int,
    rng: np.random.Generator,
) -> PurificationScheduleResult:
    """Iterate purification until target reached, budget exhausted, or the
    protocol stalls (success fails end the schedule — pairs are consumed).

    Honest accounting: every round consumes 2 pairs whether it succeeds or
    fails; a failed round terminates the chain (no surviving pair remains).
    """
    _validate_fidelity(initial_fidelity)
    if not (initial_fidelity <= target_fidelity <= 1.0):
        raise QuantumCoreError(
            f"Target fidelity {target_fidelity} must be >= initial {initial_fidelity}."
        )
    trajectory = [initial_fidelity]
    f = initial_fidelity
    consumed = 0
    succeeded_rounds = 0
    cum_p = 1.0
    achieved = False
    for _ in range(max_rounds):
        outcome = purify_once(protocol, f, rng=rng)
        consumed += outcome.consumed_pairs
        cum_p *= outcome.success_probability
        if not outcome.success:
            break
        f = outcome.output_fidelity
        trajectory.append(f)
        succeeded_rounds += 1
        if f >= target_fidelity:
            achieved = True
            break
    return PurificationScheduleResult(
        protocol=protocol,
        initial_fidelity=initial_fidelity,
        target_fidelity=target_fidelity,
        achieved=achieved,
        final_fidelity=f if succeeded_rounds > 0 and achieved else (
            f if succeeded_rounds > 0 else None),
        rounds_requested=max_rounds,
        rounds_succeeded=succeeded_rounds,
        pairs_consumed=consumed,
        cumulative_success_probability=cum_p,
        expected_fidelity_trajectory=trajectory,
        notes=[
            "Deterministic recurrence fidelities; success sampled per round.",
            "A failed round destroys both participating pairs and ends the "
            "chain (no surviving entanglement).",
        ],
    )


def compare_protocols(initial_fidelity: float, *, max_rounds: int = 6) -> dict:
    """Analytic comparison of BBPSSW vs DEJMPS trajectories (deterministic)."""
    out = {}
    for proto in PROTOCOLS:
        f = initial_fidelity
        traj = [f]
        probs = []
        for _ in range(max_rounds):
            f, p = _RECURRENCES[proto](f)
            traj.append(f)
            probs.append(p)
        out[proto] = {
            "expected_fidelity_trajectory": [round(x, 6) for x in traj],
            "per_round_success_probability": [round(x, 6) for x in probs],
            "pairs_consumed_if_all_succeed": 2 * max_rounds,
        }
    return {
        "initial_fidelity": initial_fidelity,
        "protocols": out,
        "note": (
            "Expected-value trajectories under ideal local operations; "
            "stochastic schedules will differ per seed (see purify_to_target)."
        ),
    }
