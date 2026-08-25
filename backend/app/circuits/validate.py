"""Structured circuit validation (directive §25).

Validation returns a list of structured issues instead of raising on the first
problem, so editors can display all problems at once. Each issue carries a
machine-readable code, human message, operation index, and suggestion.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .model import Circuit, Operation
from ..quantum.operators import build_gate, GATE_CATALOG


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    operation_index: int | None = None
    field: str | None = None
    suggestion: str | None = None

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "operation_index": self.operation_index,
            "field": self.field,
            "suggestion": self.suggestion,
        }


def validate_circuit(circuit: Circuit) -> list[ValidationIssue]:
    """Validate qubit/clbit references, gate names, parameters, dimensions."""
    issues: list[ValidationIssue] = []
    for i, op in enumerate(circuit.operations):
        issues.extend(_validate_operation(circuit, op, i))

    # Structural checks.
    n_measures = sum(1 for op in circuit.operations if op.kind == "measure")
    if len(circuit.operations) == 0:
        issues.append(
            ValidationIssue(
                code="EMPTY_CIRCUIT",
                message="The circuit contains no operations.",
                suggestion="Add gates or measurements before execution.",
            )
        )
    if circuit.num_qubits <= 0:
        issues.append(
            ValidationIssue(
                code="NO_QUBITS",
                message=f"Circuit declares {circuit.num_qubits} qubits.",
                field="num_qubits",
                suggestion="Use at least 1 qubit.",
            )
        )

    # Resource estimation warning surface is handled by the resource estimator;
    # here we only validate structural correctness.
    return issues


def _validate_operation(circuit: Circuit, op: Operation, index: int) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    def err(code, message, field=None, suggestion=None):
        issues.append(
            ValidationIssue(code=code, message=message, operation_index=index, field=field, suggestion=suggestion)
        )

    for q in op.qubits:
        if not isinstance(q, int) or isinstance(q, bool) or not (0 <= q < circuit.num_qubits):
            err(
                "BAD_QUBIT",
                f"Qubit index {q!r} out of range [0, {circuit.num_qubits}) in {op.kind} operation.",
                field="qubits",
                suggestion="Reference existing qubits only.",
            )
    if len(set(op.qubits)) != len(op.qubits):
        err("DUPLICATE_QUBIT", f"Duplicate qubit references {op.qubits}.", field="qubits")

    if op.condition is not None:
        c = op.condition.clbit
        if not (0 <= c < circuit.num_clbits):
            err(
                "BAD_CLBIT",
                f"Condition references classical bit {c}, but the circuit has "
                f"{circuit.num_clbits} classical bits.",
                field="condition",
            )
        if op.condition.value not in (0, 1):
            err("BAD_CONDITION_VALUE", "Classical condition value must be 0 or 1.", field="condition")

    if op.kind == "gate":
        if not op.gate:
            err("MISSING_GATE", "Gate operation has no gate name.", field="gate")
            return issues
        try:
            spec = _resolve_gate_for_validation(circuit, op.gate, list(op.params))
        except Exception as e:
            err(
                "BAD_GATE",
                str(e),
                field="gate",
                suggestion=f"Known gates include: {', '.join(g['name'] for g in GATE_CATALOG[:20])} ...",
            )
            return issues
        if len(op.qubits) != spec.n_qubits:
            err(
                "GATE_ARITY",
                f"Gate {spec.name} requires {spec.n_qubits} qubit operand(s), got {len(op.qubits)}.",
                field="qubits",
            )
        if any(not np.isfinite(p) for p in op.params):
            err("NON_FINITE_PARAM", f"Non-finite parameter in {spec.name}{list(op.params)}.", field="params")
    elif op.kind == "measure":
        if not op.qubits:
            err("EMPTY_MEASURE", "Measurement lists no qubits.", field="qubits")
        if len(op.clbits) != len(op.qubits):
            err(
                "MEASURE_MISMATCH",
                f"Measurement pairs {len(op.qubits)} qubit(s) with {len(op.clbits)} classical bit(s).",
                field="clbits",
            )
        for c in op.clbits:
            if not (0 <= c < circuit.num_clbits):
                err(
                    "BAD_CLBIT",
                    f"Measurement targets classical bit {c}, but the circuit has "
                    f"{circuit.num_clbits} classical bits.",
                    field="clbits",
                    suggestion=f"Increase num_clbits to at least {max(op.clbits) + 1 if op.clbits else 0}.",
                )
    elif op.kind == "reset":
        if not op.qubits:
            err("EMPTY_RESET", "Reset lists no qubits.", field="qubits")
    elif op.kind == "barrier":
        pass
    else:
        err(
            "UNKNOWN_KIND",
            f"Unknown operation kind {op.kind!r}.",
            field="kind",
            suggestion='Use one of "gate", "measure", "reset", "barrier".',
        )
    return issues


def _resolve_gate_for_validation(circuit: Circuit, gate_name: str, params: list[float]):
    """Resolve standard or circuit-declared custom gates for validation."""
    import numpy as np

    custom = (circuit.metadata.get("custom_gates") or {}).get(gate_name)
    if custom is not None:
        matrix = np.asarray(custom["matrix"], dtype=np.complex128)
        n_qubits = int(custom.get("n_qubits", 0)) or int(np.log2(matrix.shape[0]))
        from ..quantum.operators import GateSpec

        return GateSpec(gate_name, matrix, n_qubits)
    return build_gate(gate_name, params)


def assert_valid(circuit: Circuit) -> list[ValidationIssue]:
    """Validate and raise ValueError with all issues formatted if any exist."""
    issues = validate_circuit(circuit)
    if issues:
        lines = "\n".join(
            f"  [{iss.code}] op#{iss.operation_index}: {iss.message}"
            + (f" Suggestion: {iss.suggestion}" if iss.suggestion else "")
            for iss in issues
        )
        raise ValueError(f"Circuit validation failed with {len(issues)} issue(s):\n{lines}")
    return issues
