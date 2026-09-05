"""Stabilizer-measurement circuit templates for the rotated planar
surface code (milestone 13, Track A).

A circuit template specifies the exact gate sequence the simulator
runs for one stabilizer-measurement round: ancilla reset, ancilla
preparation, the sequence of CNOTs, ancilla measurement.

Currently implemented:

  BASELINE_H_CNOT_H  — the production model (preserved bit-for-bit
    for backwards compatibility). Z-check: ancilla |0>, CNOT(data->anc)
    for each data qubit, measure ancilla Z. X-check: ancilla |0>,
    H (->|+>), CNOT(anc->data) for each data qubit, H (back to Z
    basis), measure ancilla Z.

INVESTIGATED but REJECTED in the milestone 13 Track A process:

  DOUBLED_CNOT (Fowler 2012 §IV.B-inspired, the "hook-error safe"
  2-CNOT-per-data-qubit construction) — see note below.

Track A honest negative finding: the simple doubled-CNOT construction
(data->anc, anc->data) on the same data qubit does NOT preserve the
stabilizer measurement in the Pauli-frame formalism used by the
production simulator. The anc->data CNOT copies the ancilla's
accumulated Z value back to every data qubit in the support,
producing a multi-data syndrome for a single-qubit data error.
Investigation of a faithful 2-CNOT hook-error-safe construction
(flag-based, post-selection, or full Shor cat-state) is recorded
in SCIENTIFIC_MODELS as future work; implementing those would
require additional ancilla qubits and/or post-selection logic
beyond the current architecture.

Direction: BASELINE_H_CNOT_H is preserved. Future work (post-milestone
13) would extend the architecture to support flag-based or
cat-state extraction.
"""
from __future__ import annotations

from dataclasses import dataclass


EXTRACTION_BASELINE = "baseline_h_cnot_h"
SUPPORTED_EXTRACTIONS = (EXTRACTION_BASELINE,)


@dataclass(frozen=True)
class ExtractionModel:
    """One stabilizer-measurement template."""
    name: str
    description: str
    n_cnots_per_data: int
    build_z_cnot_specs: object
    build_x_cnot_specs: object


def _baseline_z_cnot_specs(code, stabilizer_index: int) -> list[tuple[str, int, int]]:
    sup = code.z_checks[stabilizer_index].support
    return [("data->anc", q, 0) for q in sup]


def _baseline_x_cnot_specs(code, stabilizer_index: int) -> list[tuple[str, int, int]]:
    sup = code.x_checks[stabilizer_index].support
    return [("anc->data", 0, q) for q in sup]


MODELS: dict[str, ExtractionModel] = {
    EXTRACTION_BASELINE: ExtractionModel(
        name=EXTRACTION_BASELINE,
        description=(
            "Baseline H-CNOT-H extraction: Z-check = CNOT(data->anc) "
            "for each support qubit; X-check = H, CNOT(anc->data) for "
            "each support qubit, H. Standard textbook circuit. "
            "Hook errors: weight-k (full support) for a single ancilla "
            "fault at the start of the schedule. Schedule is degenerate "
            "under the order-invariant primary_key."
        ),
        n_cnots_per_data=1,
        build_z_cnot_specs=_baseline_z_cnot_specs,
        build_x_cnot_specs=_baseline_x_cnot_specs,
    ),
}


def get_extraction_model(name: str) -> ExtractionModel:
    if name not in MODELS:
        raise ValueError(
            f"Unknown extraction model {name!r}; supported: {list(MODELS)}.")
    return MODELS[name]


def list_extraction_models() -> list[dict]:
    return [
        {"name": m.name, "description": m.description,
         "n_cnots_per_data": m.n_cnots_per_data}
        for m in MODELS.values()
    ]


__all__ = [
    "EXTRACTION_BASELINE", "SUPPORTED_EXTRACTIONS",
    "ExtractionModel", "MODELS",
    "get_extraction_model", "list_extraction_models",
]
