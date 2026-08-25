"""Experiment reproducibility service (directive §44, §162, §98).

A stored run is reproducible when re-executing its exact resolved
configuration and seed yields the same result document. Deterministic modules
(circuit_shots with fixed seed, qec_sweep, purification_study analytic parts)
must match BIT-FOR-BIT; stochastic-by-design outputs are compared with an
explicit tolerance classification.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_TOLERANCE = 1e-9


@dataclass
class ReproductionReport:
    run_id: int
    reproduced_run_id: int | None
    status: str                    # EXACT_MATCH | TOLERANCE_MATCH | MISMATCH | ERROR
    differences: list[str] = field(default_factory=list)
    original_metrics: dict = field(default_factory=dict)
    reproduced_metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "reproduced_run_id": self.reproduced_run_id,
            "status": self.status,
            "differences": self.differences,
            "metrics_original": self.original_metrics,
            "metrics_reproduced": self.reproduced_metrics,
        }


def _flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(_flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(_flatten(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = obj
    return out


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def compare_result_documents(original: dict, reproduced: dict) -> ReproductionReport:
    """Compare two result documents field-by-field.

    Classification:
      EXACT_MATCH     — every flattened scalar identical
      TOLERANCE_MATCH — numerics within 1e-9 relative; nothing else differs
      MISMATCH        — any structural difference or numeric beyond tolerance
    """
    a = _flatten(original.get("metrics", {}))
    b = _flatten(reproduced.get("metrics", {}))
    diffs: list[str] = []
    within_tolerance_only = True

    for key in sorted(set(a) | set(b)):
        va = a.get(key, "<missing>")
        vb = b.get(key, "<missing>")
        if va == vb:
            continue
        if _is_number(va) and _is_number(vb):
            scale = max(1.0, abs(float(va)))
            if abs(float(va) - float(vb)) > _TOLERANCE * scale:
                within_tolerance_only = False
                diffs.append(f"{key}: {va} != {vb} (beyond tolerance)")
            else:
                diffs.append(f"{key}: {va} vs {vb} (within tolerance)")
        else:
            within_tolerance_only = False
            diffs.append(f"{key}: {va!r} != {vb!r}")

    if not diffs:
        status = "EXACT_MATCH"
    elif within_tolerance_only:
        status = "TOLERANCE_MATCH"
    else:
        status = "MISMATCH"

    return ReproductionReport(
        run_id=-1,
        reproduced_run_id=None,
        status=status,
        differences=diffs,
        original_metrics=original.get("metrics", {}),
        reproduced_metrics=reproduced.get("metrics", {}),
    )
