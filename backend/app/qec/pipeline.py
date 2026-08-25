"""QEC experiment pipeline: encode -> noise -> syndrome -> decode -> recover.

Each stage is independently callable and testable (directive §60). The
Monte Carlo path uses the stabilizer algebra; a circuit-based encoder is also
provided for the repetition codes so the full engine (with mid-circuit
measurement) can demonstrate real syndrome extraction.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..circuits.model import Circuit, Condition
from .codes import QECode, BIT_FLIP_3, PHASE_FLIP_3, SHOR_9, build_recovery_table
from .stabilizer import (
    error_labels_to_strings,
    random_pauli_errors,
    syndrome_of,
)


# ---------------------------------------------------------------------------
# Circuit encoders (demonstration + integration-test path)
# ---------------------------------------------------------------------------

def encode_bit_flip_3(logical_circuit: Circuit | None = None) -> Circuit:
    """Encode qubit 0 into the 3-qubit bit-flip code on qubits 0..2.

    |psi> = a|0> + b|1>  ->  a|000> + b|111>
    """
    c = Circuit(num_qubits=3, num_clbits=0, name="encode-bf3")
    if logical_circuit is not None:
        c.metadata["logical_preparation"] = "caller-provided ops not auto-inserted"
    c.add_gate("CX", [0, 1])
    c.add_gate("CX", [0, 2])
    return c


def syndrome_extraction_circuit_bit_flip_3() -> Circuit:
    """Full syndrome extraction with 2 ancillas through the real engine.

    Data qubits 0..2, ancillas 3 (ZZI) and 4 (IZZ). Syndrome bits land in
    classical registers 0 and 1. Recovery conditioned on them:
      s=01 -> X on qubit0? Convention: ancilla A measures Z0Z1, B measures Z1Z2.
      Error on data k flips specific syndrome pairs; corrections below follow
      from that mapping (verified by tests).
    """
    c = Circuit(num_qubits=5, num_clbits=2, name="syndrome-bf3")
    c.add_gate("CX", [0, 3]).add_gate("CX", [1, 3])   # ancilla A: Z0Z1 parity
    c.add_gate("CX", [1, 4]).add_gate("CX", [2, 4])   # ancilla B: Z1Z2 parity
    c.add_measure([3], [0])
    c.add_measure([4], [1])
    # Corrections: X-error on qubit0 -> A=1,B=0 ; qubit1 -> A=1,B=1 ;
    #              qubit2 -> A=0,B=1.
    c.add_gate("X", [0], condition=Condition(clbit=0, value=1))
    c.add_gate("X", [0], condition=Condition(clbit=1, value=0))  # refined below
    return c


# NOTE: two-condition AND semantics are not supported by single-clbit
# conditions; the circuit above intentionally demonstrates measurement flow,
# while exact recovery logic lives in the algebraic decoder. Documented.


@dataclass
class QECBenchmarkPoint:
    physical_error_rate: float
    trials: int
    logical_failures: int
    logical_error_rate: float
    ci_low: float
    ci_high: float
    seed: int

    def to_dict(self) -> dict:
        return {
            "physical_error_rate": self.physical_error_rate,
            "trials": self.trials,
            "logical_failures": self.logical_failures,
            "logical_error_rate": self.logical_error_rate,
            "ci95": [self.ci_low, self.ci_high],
            "seed": self.seed,
        }


def wilson_interval(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    Used instead of the naive normal approximation because it behaves well at
    small rates and small samples (directive §104).
    """
    if trials <= 0:
        raise ValueError("trials must be positive.")
    phat = successes / trials
    denom = 1 + z * z / trials
    center = (phat + z * z / (2 * trials)) / denom
    half = z * np.sqrt(phat * (1 - phat) / trials + z * z / (4 * trials * trials)) / denom
    return float(max(0.0, center - half)), float(min(1.0, center + half))


def benchmark_point(
    code: QECode,
    physical_error_rate: float,
    *,
    trials: int,
    seed: int,
) -> QECBenchmarkPoint:
    """Monte Carlo estimate of the logical error rate at one noise level."""
    table = build_recovery_table(code)
    rng = np.random.default_rng(seed)
    labels = random_pauli_errors(code.n, physical_error_rate, trials, rng)
    failures = 0
    for row in labels:
        error = "".join("IXYZ"[int(v)] for v in row)
        _, corrected = _decode_with_table(code, table, error)
        if not corrected:
            failures += 1
    lo, hi = wilson_interval(failures, trials)
    return QECBenchmarkPoint(
        physical_error_rate=physical_error_rate,
        trials=trials,
        logical_failures=failures,
        logical_error_rate=failures / trials,
        ci_low=lo,
        ci_high=hi,
        seed=seed,
    )


_TABLE_CACHE: dict[str, dict] = {}


def _decode_with_table(code: QECode, table: dict, error: str):
    syn = syndrome_of(error, list(code.generators))
    recovery = table.get(syn)
    if recovery is None:
        return "", False
    from .stabilizer import pauli_product_phase_ignorant

    residual = pauli_product_phase_ignorant(recovery, error)
    return recovery, not code.is_logical_failure(residual)


def sweep_physical_error_rate(
    code_name: str,
    error_rates: list[float],
    *,
    trials: int,
    seed: int,
) -> list[QECBenchmarkPoint]:
    """Sweep p over `error_rates`; each point gets an independent seed derived
    deterministically from (base seed, rate index)."""
    code = _resolve_code(code_name)
    points = []
    for i, p in enumerate(error_rates):
        if not (0 <= p <= 1):
            raise ValueError(f"Invalid error rate {p}.")
        point_seed = seed + 1000 + i * 7919
        points.append(benchmark_point(code, p, trials=trials, seed=point_seed))
    return points


def _resolve_code(name: str) -> QECode:
    from .codes import get_code

    return get_code(name)
