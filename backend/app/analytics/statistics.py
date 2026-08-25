"""Reusable statistics subsystem (directive §46, §120, §26).

Every stochastic result should expose: N, estimator, interval. This module
centralizes the estimators so all labs report uncertainty consistently.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..quantum.states import QuantumCoreError


def mean(values: list[float]) -> float:
    if not values:
        raise QuantumCoreError("mean of empty sample.")
    return float(np.mean(values))


def std_dev(values: list[float], *, ddof: int = 1) -> float:
    if len(values) < ddof + 1:
        return 0.0
    return float(np.std(values, ddof=ddof))


def standard_error(values: list[float]) -> float:
    """SEM = s / sqrt(N) with sample std (ddof=1)."""
    if not values:
        raise QuantumCoreError("standard error of empty sample.")
    return std_dev(values) / math.sqrt(len(values))


@dataclass
class Interval:
    low: float
    high: float
    level: float
    method: str


def t_confidence_interval(values: list[float], *, level: float = 0.95) -> Interval:
    """Normal-approximation CI on the mean using the sample SEM.

    Honest scope (documented): uses the normal quantile rather than Student-t
    to avoid a scipy dependency; for N >= 30 the difference is negligible and
    smaller samples are flagged in the notes of callers. Assumptions:
    approximately normal sample mean (CLT), independent draws.
    """
    if not values:
        raise QuantumCoreError("confidence interval of empty sample.")
    z = {0.90: 1.6449, 0.95: 1.9600, 0.99: 2.5758}.get(round(level, 2))
    if z is None:
        raise ValueError(f"Unsupported confidence level {level}; use 0.90/0.95/0.99.")
    m = mean(values)
    se = standard_error(values)
    half = z * se
    return Interval(low=m - half, high=m + half, level=level,
                    method="normal-approximation on the mean (SEM)")


def bootstrap_confidence_interval(
    values: list[float],
    *,
    statistic="mean",
    level: float = 0.95,
    resamples: int = 2000,
    seed: int = 0,
) -> Interval:
    """Percentile bootstrap CI — robust when the sampling distribution is
    skewed or heavy-tailed. Deterministic under seed."""
    if not values:
        raise QuantumCoreError("bootstrap of empty sample.")
    stat_fn = {"mean": np.mean, "median": np.median}[statistic]
    rng = np.random.default_rng(seed)
    arr = np.asarray(values, dtype=float)
    stats = np.empty(resamples)
    for i in range(resamples):
        sample = rng.choice(arr, size=len(arr), replace=True)
        stats[i] = stat_fn(sample)
    alpha = (1 - level) / 2
    lo, hi = np.quantile(stats, [alpha, 1 - alpha])
    return Interval(low=float(lo), high=float(hi), level=level,
                    method=f"percentile bootstrap ({resamples} resamples)")


def summarize_samples(values: list[float], *, level: float = 0.95) -> dict:
    """Standard research summary: N never hidden (§46)."""
    n = len(values)
    m = mean(values)
    ci = t_confidence_interval(values, level=level)
    return {
        "n": n,
        "mean": round(m, 9),
        "median": float(np.median(values)) if n else None,
        "std": round(std_dev(values), 9),
        "sem": round(standard_error(values), 9),
        "ci_low": round(ci.low, 9),
        "ci_high": round(ci.high, 9),
        "ci_method": ci.method,
        "small_sample_warning": n < 30,
    }


def proportion_summary(successes: int, trials: int, *, level: float = 0.95) -> dict:
    """Proportion with Wilson interval; numerator/denominator explicit (§118)."""
    from ..qec.pipeline import wilson_interval as _wilson

    if trials <= 0:
        raise QuantumCoreError("trials must be positive.")
    lo, hi = _wilson(successes, trials)
    z = {0.90: 1.6449, 0.95: 1.96}.get(level)
    del z
    return {
        "successes": successes,
        "trials": trials,
        "proportion": successes / trials,
        "ci_low": lo,
        "ci_high": hi,
        "ci_method": "Wilson score interval",
    }
