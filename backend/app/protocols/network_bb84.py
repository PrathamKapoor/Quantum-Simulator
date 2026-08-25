"""Network-integrated BB84 with physical channel loss (directive §33).

Model (documented):
  - Each prepared signal traverses a fiber of length `distance_km` with
    attenuation alpha dB/km; photon survival eta = 10^(-alpha*d/10).
  - Detector inefficiency multiplies survival: eta_total = eta * det_eff.
  - Lost signals produce NO detection: they are removed from sifting entirely
    (Bob never measures them) — matching real passive-loss behavior.
  - Optional dark-count approximation: with probability p_dark per signal,
    Bob registers a RANDOM bit in his chosen basis even when the photon was
    lost (documented crude approximation; no time-window modeling).
  - Eve intercept-resend as in the ideal-channel simulator.

Outputs include detection statistics, sifted length, QBER over the sifted key
(with counts, not just a rate), and estimated secret fraction using the
standard one-way asymptotic bound for BB84:
    r >= 1 - 2 h2(QBER),  h2 = binary entropy (bits)
reported as an ESTIMATE under the documented model assumptions only.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


def fiber_survival(distance_km: float, attenuation_db_per_km: float,
                   detector_efficiency: float) -> float:
    """eta = 10^(-alpha d / 10) * detector_efficiency. d=0 -> det_eff."""
    if distance_km < 0 or attenuation_db_per_km < 0:
        raise ValueError("Distance and attenuation must be non-negative.")
    if not (0 < detector_efficiency <= 1):
        raise ValueError("detector_efficiency must be within (0, 1].")
    return float(min(1.0, 10 ** (-attenuation_db_per_km * distance_km / 10)
                     * detector_efficiency))


def _h2(p: float) -> float:
    if p <= 0 or p >= 1:
        return 0.0
    return -p * math.log2(p) - (1 - p) * math.log2(1 - p)


@dataclass
class NetworkBB84Result:
    n_signal_qubits: int
    distance_km: float
    attenuation_db_per_km: float
    detector_efficiency: float
    dark_count_probability: float
    eve_intercept_probability: float
    detected: int
    lost: int
    sifted_bits: int
    errors_in_sampled: int
    sample_size: int
    qber: float | None
    key_rate_fraction_estimate: float | None   # max(0, 1 - 2 h2(Q))
    notes: list[str] = field(default_factory=list)


def run_network_bb84(
    n_signals: int,
    *,
    distance_km: float = 25.0,
    attenuation_db_per_km: float = 0.2,
    detector_efficiency: float = 0.9,
    dark_count_probability: float = 0.0,
    eve_intercept_probability: float = 0.0,
    sample_fraction: float = 0.5,
    seed: int = 0,
) -> NetworkBB84Result:
    if n_signals < 16:
        raise ValueError("Need at least 16 signals for meaningful statistics.")
    if not (0 <= dark_count_probability <= 1):
        raise ValueError("dark_count_probability must be within [0,1].")
    rng = np.random.default_rng(seed)
    eta = fiber_survival(distance_km, attenuation_db_per_km, detector_efficiency)

    alice_bits = [int(rng.integers(2)) for _ in range(n_signals)]
    alice_bases = [int(rng.integers(2)) for _ in range(n_signals)]
    bob_bases = [int(rng.integers(2)) for _ in range(n_signals)]

    bob_bits: list[int | None] = []
    detected = 0
    for i in range(n_signals):
        survives = rng.random() < eta
        eve_attacks = eve_intercept_probability > 0 and rng.random() < eve_intercept_probability
        sent_bit = alice_bits[i]
        sent_basis = alice_bases[i]
        if eve_attacks:
            eve_basis = int(rng.integers(2))
            measured = sent_bit if eve_basis == sent_basis else int(rng.integers(2))
            sent_bit, sent_basis = measured, eve_basis
        if survives:
            detected += 1
            bit = sent_bit if bob_bases[i] == sent_basis else int(rng.integers(2))
            bob_bits.append(bit)
        elif rng.random() < dark_count_probability:
            bob_bits.append(int(rng.integers(2)))  # dark count: random registration
        else:
            bob_bits.append(None)

    # Sift on DETECTED signals with matching bases.
    sifted_a: list[int] = []
    sifted_b: list[int] = []
    for i in range(n_signals):
        if bob_bits[i] is not None and alice_bases[i] == bob_bases[i]:
            sifted_a.append(alice_bits[i])
            sifted_b.append(bob_bits[i])

    n_sample = max(1, int(len(sifted_a) * sample_fraction)) if sifted_a else 0
    errors = 0
    if n_sample:
        idx = rng.choice(len(sifted_a), size=n_sample, replace=False)
        for k in idx:
            if sifted_a[k] != sifted_b[k]:
                errors += 1
    qber = errors / n_sample if n_sample else None
    key_rate = max(0.0, 1.0 - 2 * _h2(qber)) if qber is not None else None

    return NetworkBB84Result(
        n_signal_qubits=n_signals,
        distance_km=distance_km,
        attenuation_db_per_km=attenuation_db_per_km,
        detector_efficiency=detector_efficiency,
        dark_count_probability=dark_count_probability,
        eve_intercept_probability=eve_intercept_probability,
        detected=detected,
        lost=n_signals - detected,
        sifted_bits=len(sifted_a),
        errors_in_sampled=errors,
        sample_size=n_sample,
        qber=qber,
        key_rate_fraction_estimate=key_rate,
        notes=[
            f"Channel model: eta = 10^(-{attenuation_db_per_km} dB/km * {distance_km} km) "
            f"* detector({detector_efficiency}) = {eta:.5f}.",
            "Lost photons are silently absent from sifting (passive loss).",
            "Dark counts register uniformly random bits when modeled.",
            "Secret-fraction estimate uses asymptotic one-way bound "
            "r >= 1 - 2 h2(QBER); NOT a finite-key security proof.",
            "Simulation only — no production security claim.",
        ],
    )


def run_bb84_distance_sweep(
    distances_km: list[float],
    *,
    n_signals: int = 4096,
    eve_intercept_probability: float = 0.0,
    seed: int = 0,
) -> dict:
    rows = []
    for i, d in enumerate(distances_km):
        r = run_network_bb84(
            n_signals, distance_km=float(d),
            eve_intercept_probability=eve_intercept_probability,
            seed=seed + 31 * i)
        rows.append({
            "distance_km": r.distance_km,
            "detected": r.detected,
            "sifted_bits": r.sifted_bits,
            "qber": r.qber,
            "key_rate_fraction_estimate": r.key_rate_fraction_estimate,
            "sample_size": r.sample_size,
        })
    return {
        "distances_km": distances_km,
        "table": rows,
        "notes": [
            "Higher distance strictly reduces detection via the fiber model; "
            "QBER stays near zero without Eve but key rate collapses with loss.",
        ],
    }
