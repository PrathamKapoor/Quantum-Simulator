"""Hook-error forensic analysis (milestone 14, Phase B).

Programmatically enumerate every ancilla Pauli fault at every
interaction position for every stabilizer, propagate it through the
actual circuit, and report the data-side hook support with a danger
classification.

This is the EVIDENCE GATHERING step before any schedule design:
the forensic conclusions drive what a hook-safe schedule must
mitigate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .fault_catalogue import (
    build_catalogue_for_stabilizer,
    FAULT_ANCILLA_RESET,
    FAULT_ANCILLA_PREP,
    FAULT_CNOT_PRE,
    FAULT_READOUT,
)


@dataclass(frozen=True)
class HookReport:
    """One entry in the forensic catalogue: an ancilla fault at a
    specific CNOT position, with the resulting data support and
    classification."""
    stabilizer_type: str       # "X" or "Z"
    stabilizer_index: int
    round: int
    fault_location: str        # "ANCILLA_RESET" | "ANCILLA_PREP" | "CNOT_PRE" (ancilla fault)
    pauli: str                 # "X" | "Y" | "Z"
    gate_index: int            # 0..|support|-1; 0 for non-CNOT
    data_support_x: int
    data_support_z: int
    data_x_qubits: tuple
    data_z_qubits: tuple
    syndrome_kind: str
    syndrome_index: int
    syndrome_round: int
    n_detection_events: int
    n_z_checks_fired: int
    n_x_checks_fired: int
    danger: str                # "SAFE" | "DATA_HOOK" | "LOGICAL_RISK" | "STABILIZER_EQUIVALENT"
    is_boundary: bool
    logical_distance: int
    weight: int
    notes: str

    def to_dict(self) -> dict:
        return {
            "stabilizer": f"{self.stabilizer_type}{self.stabilizer_index}",
            "round": self.round,
            "fault_location": self.fault_location,
            "pauli": self.pauli,
            "gate_index": self.gate_index,
            "data_x_qubits": list(self.data_x_qubits),
            "data_z_qubits": list(self.data_z_qubits),
            "syndrome": {
                "kind": self.syndrome_kind,
                "index": self.syndrome_index,
                "round": self.syndrome_round,
            },
            "n_detection_events": self.n_detection_events,
            "n_z_checks_fired": self.n_z_checks_fired,
            "n_x_checks_fired": self.n_x_checks_fired,
            "danger": self.danger,
            "is_boundary": self.is_boundary,
            "logical_distance": self.logical_distance,
            "weight": self.weight,
            "notes": self.notes,
        }


def _boundary_data_qubits(code) -> set:
    """Data qubits with a SINGLE stabilizer of either kind
    (boundary data qubits; hook errors on them are at the
    geometric edge of the lattice)."""
    n = code.d * code.d
    out = set()
    for q in range(n):
        n_x = sum(1 for c in code.x_checks if q in c.support)
        n_z = sum(1 for c in code.z_checks if q in c.support)
        if n_x == 1 or n_z == 1:
            out.add(q)
    return out


def _classify_danger(code, data_x: int, data_z: int) -> tuple[str, int]:
    """Classify a data-frame hook.
    Returns (danger_label, logical_distance).
    - STABILIZER_EQUIVALENT: hook is a product of stabilizers (correctable by
      any decoder that knows the stabilizer group, weight 0 risk).
    - DATA_HOOK: hook has nonzero data support, may or may not form a logical.
    - LOGICAL_RISK: hook is a partial logical (logical_distance < d).
    """
    if data_x == 0 and data_z == 0:
        return "SAFE", 0
    # Check stabilizer-equivalence: is (data_x, data_z) a product of
    # generators? Compute the syndrome of the hook alone and check
    # if it is the trivial syndrome.
    from .rotated_surface_code import RotatedSurfaceCodeDecoder
    decoder = RotatedSurfaceCodeDecoder(code)
    syn_x, syn_z = decoder.syndrome(data_x, data_z)
    # STABILIZER_EQUIVALENT iff the syndrome of the hook is zero
    # (i.e. the hook is in the stabilizer group).
    is_stab = (not any(syn_x)) and (not any(syn_z))
    if is_stab:
        return "STABILIZER_EQUIVALENT", 0
    # Try to determine if the hook is a partial logical via the
    # coset functionals: project (data_x, data_z) onto the coset
    # functionals; if it has overlap with a logical, it is
    # logical-risk.
    has_x_log = bin(data_x & code.phi_x).count("1") % 2 == 1
    has_z_log = bin(data_z & code.phi_z).count("1") % 2 == 1
    if has_x_log or has_z_log:
        # Already a logical by itself.
        return "LOGICAL", 0
    # Compute the minimum additional weight to complete a logical.
    # For an X-sector hook (data_x != 0, data_z = 0), the distance
    # to the logical X coset is: d - |overlap(hook, logical_x_string)|.
    overlap_x = bin(data_x & code.phi_x).count("1")
    if data_z == 0 and data_x != 0:
        ld = max(0, code.d - overlap_x)
        if ld < code.d:
            return "LOGICAL_RISK", ld
        return "DATA_HOOK", code.d
    overlap_z = bin(data_z & code.phi_z).count("1")
    if data_x == 0 and data_z != 0:
        ld = max(0, code.d - overlap_z)
        if ld < code.d:
            return "LOGICAL_RISK", ld
        return "DATA_HOOK", code.d
    # Mixed hook: check both sectors.
    ld_x = max(0, code.d - overlap_x) if data_x else code.d
    ld_z = max(0, code.d - overlap_z) if data_z else code.d
    ld = min(ld_x, ld_z)
    if ld < code.d:
        return "LOGICAL_RISK", ld
    return "DATA_HOOK", code.d


def run_hook_forensics(code, round_index: int = 1,
                        interleave: str = "none"):
    """Enumerate every ancilla fault in the current extraction
    model and produce a per-fault report.

    `interleave`: "none" (default, all stabilizers every round) or
    "alternating" (only X in odd rounds, only Z in even rounds).
    The forensic is per-round; the round index selects which round
    the fault is injected at. In alternating mode, X-faults are
    only reported in odd rounds and Z-faults in even rounds.
    """
    boundary = _boundary_data_qubits(code)
    out: list[HookReport] = []
    for kind, checks in (("X", code.x_checks), ("Z", code.z_checks)):
        for ch in checks:
            cat = build_catalogue_for_stabilizer(
                code, kind, ch.index, round_index=round_index,
                total_rounds=round_index)
            for f in cat:
                # If alternating, only report faults for the family
                # that is measured this round.
                if interleave == "alternating":
                    if round_index % 2 == 1 and kind != "X":
                        continue
                    if round_index % 2 == 0 and kind != "Z":
                        continue
                has_data_hook = (f.propagated_data_x != 0
                                 or f.propagated_data_z != 0)
                if not has_data_hook and len(f.detection_events) != 1:
                    continue
                z_fired = sum(1 for ev in f.detection_events if ev[1] == "Z")
                x_fired = sum(1 for ev in f.detection_events if ev[1] == "X")
                danger, ld = _classify_danger(
                    code, f.propagated_data_x, f.propagated_data_z)
                local_event = None
                for ev in f.detection_events:
                    if ev[1] == ("X" if kind == "Z" else "Z"):
                        local_event = ev
                        break
                if local_event is None and f.detection_events:
                    local_event = f.detection_events[0]
                syn_kind = local_event[1] if local_event else ""
                syn_index = local_event[2] if local_event else -1
                syn_round = local_event[0] if local_event else -1
                is_b = any(q in boundary for q in f.affected_qubits)
                w = len(f.affected_qubits)
                out.append(HookReport(
                    stabilizer_type=kind,
                    stabilizer_index=ch.index,
                    round=round_index,
                    fault_location=f.fault_location,
                    pauli=f.pauli_fault,
                    gate_index=f.gate_index,
                    data_support_x=f.propagated_data_x,
                    data_support_z=f.propagated_data_z,
                    data_x_qubits=tuple(
                        q for q in range(code.d * code.d)
                        if (f.propagated_data_x >> q) & 1),
                    data_z_qubits=tuple(
                        q for q in range(code.d * code.d)
                        if (f.propagated_data_z >> q) & 1),
                    syndrome_kind=syn_kind,
                    syndrome_index=syn_index,
                    syndrome_round=syn_round,
                    n_detection_events=len(f.detection_events),
                    n_z_checks_fired=z_fired,
                    n_x_checks_fired=x_fired,
                    danger=danger,
                    is_boundary=is_b,
                    logical_distance=ld,
                    weight=w,
                    notes=(f"interleave={interleave}"),
                ))
    return out


def compare_forensic_modes(code):
    """Compare the forensic report under STANDARD vs
    TEMPORAL_INTERLEAVED for the SAME (d, round) configuration.
    The interleaving halves the number of measured stabilizers
    per round; this should be visible as a halving of the
    detection-event count per fault and a different
    logical-outcome distribution.

    Returns a dict with the comparison summary."""
    std_reports = run_hook_forensics(code, round_index=1, interleave="none")
    alt_reports = run_hook_forensics(code, round_index=1, interleave="alternating")
    std_summary = summarize_forensics(std_reports)
    alt_summary = summarize_forensics(alt_reports)
    return {
        "d": code.d, "round": 1,
        "standard": {
            "summary": std_summary,
            "n_reports": len(std_reports),
        },
        "alternating": {
            "summary": alt_summary,
            "n_reports": len(alt_reports),
        },
        "delta_logical_risk": (
            alt_summary["logical_risk_count"]
            - std_summary["logical_risk_count"]),
        "delta_data_hook": (
            alt_summary["data_hook_count"]
            - std_summary["data_hook_count"]),
        "note": (
            "Per-round comparison: alternating measures only ONE "
            "stabilizer family per round. A fault at round 1 in "
            "alternating mode fires only X-related events. The "
            "data-side hook is the same; the detection-event "
            "distribution differs."
        ),
    }


def summarize_forensics(reports: list[HookReport]) -> dict:
    """Aggregate forensic reports by danger classification."""
    summary = {
        "total_reports": len(reports),
        "by_danger": {},
        "by_stabilizer": {},
        "logical_risk_count": 0,
        "data_hook_count": 0,
        "safe_count": 0,
        "boundary_data_hook_count": 0,
        "max_hook_weight": 0,
    }
    for r in reports:
        summary["by_danger"].setdefault(r.danger, 0)
        summary["by_danger"][r.danger] += 1
        stb = f"{r.stabilizer_type}{r.stabilizer_index}"
        summary["by_stabilizer"].setdefault(stb, {"data_hook": 0,
                                                    "logical_risk": 0,
                                                    "weight_max": 0})
        if r.danger == "LOGICAL_RISK" or r.danger == "LOGICAL":
            summary["by_stabilizer"][stb]["logical_risk"] += 1
            summary["logical_risk_count"] += 1
        elif r.danger == "DATA_HOOK":
            summary["by_stabilizer"][stb]["data_hook"] += 1
            summary["data_hook_count"] += 1
        elif r.danger in ("SAFE", "STABILIZER_EQUIVALENT"):
            summary["safe_count"] += 1
        summary["by_stabilizer"][stb]["weight_max"] = max(
            summary["by_stabilizer"][stb]["weight_max"], r.weight)
        if r.is_boundary and r.danger in ("DATA_HOOK", "LOGICAL_RISK", "LOGICAL"):
            summary["boundary_data_hook_count"] += 1
        summary["max_hook_weight"] = max(summary["max_hook_weight"], r.weight)
    return summary


__all__ = [
    "HookReport", "run_hook_forensics", "summarize_forensics",
    "compare_forensic_modes",
]
