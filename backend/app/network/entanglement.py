"""Entanglement generation, swapping, and purification models.

Documented physical models (directive §154, §326 — see also
SCIENTIFIC_MODELS.md):

Generation attempt (per attempt):
  - survival probability eta = 10^(-alpha*d/10) * detector_efficiency (fiber)
  - on success the pair is a Werner state with parameter q0 = (4*F0-1)/3,
    F0 = link.base_fidelity
  - attempt duration: propagation 2*d*5us/km (round trip) + processing 10us

Swapping (idealized BSM at a repeater):
  - consumes two adjacent pairs (A-R, R-B)
  - output Werner parameter q_out = q_A * q_B (multiplied), i.e.
    F_out = (3 q_A q_B + 1)/4
  - swap success probability configurable (default 1.0 ideal); failure
    destroys both pairs
  - classical-communication latency added before the new pair is usable

Purification interface exists but returns NotImplemented honestly until a
protocol is implemented (§252).
"""
from __future__ import annotations

import math

from .resources import werner_parameter, fidelity_from_werner


def generation_success_probability(distance_km: float, attenuation_db_per_km: float, detector_efficiency: float) -> float:
    if distance_km < 0:
        raise ValueError("distance must be >= 0.")
    return float(min(1.0, 10 ** (-attenuation_db_per_km * distance_km / 10) * detector_efficiency))


def attempt_duration_ns(distance_km: float, processing_ns: float = 10_000.0) -> float:
    """Round-trip propagation (~5 us/km in fiber) plus station processing."""
    if distance_km < 0:
        raise ValueError("distance must be >= 0.")
    return 2.0 * distance_km * 5000.0 + processing_ns


def swap_fidelity(f_a: float, f_b: float) -> float:
    """Werner-parameter multiplication under ideal swapping.

    Limiting behavior (validated): perfect inputs (F=1 each) -> F=1;
    maximally mixed input (F=1/2, q=0) -> F=1/2.
    """
    q = werner_parameter(f_a) * werner_parameter(f_b)
    return fidelity_from_werner(max(q, 0.0))


def swap_classical_latency_ns(link_distance_km: float) -> float:
    """Classical BSM result announcement over ~fiber; simplified one-way."""
    return link_distance_km * 5000.0


class PurificationProtocol:
    """Interface for entanglement purification (NOT implemented yet).

    Per directive §252 we refuse to fake fidelity boosts: calling run() raises
    NotImplementedError with an explicit message until a real protocol (e.g.
    BBPSSW / DEJMPS with its own failure statistics) is implemented.
    """

    name = "interface"

    def run(self, pairs: list[tuple[float, float]]) -> None:
        raise NotImplementedError(
            "Purification protocols are not implemented yet; fidelity values are "
            "never adjusted without an implemented protocol."
        )
