"""Versioned circuit serialization (directive §24, §122, §166).

Schema: ``quantumlab.circuit`` version 1. Unknown future versions are rejected
with a clear error rather than misinterpreted. Round-trip fidelity is tested.
"""
from __future__ import annotations

from .model import Circuit
from .validate import validate_circuit

SCHEMA_NAME = "quantumlab.circuit"
SCHEMA_VERSION = 1


def circuit_to_dict(circuit: Circuit) -> dict:
    return {
        "schema": SCHEMA_NAME,
        "version": SCHEMA_VERSION,
        "name": circuit.name,
        "num_qubits": circuit.num_qubits,
        "num_clbits": circuit.num_clbits,
        "operations": [op.to_dict() for op in circuit.operations],
        "metadata": dict(circuit.metadata),
    }


def circuit_from_dict(data: dict) -> Circuit:
    if not isinstance(data, dict):
        raise ValueError("Circuit payload must be a JSON object.")
    schema = data.get("schema")
    if schema != SCHEMA_NAME:
        raise ValueError(
            f"Expected schema {SCHEMA_NAME!r}, got {schema!r}. "
            "This does not look like a QuantumLab circuit document."
        )
    version = data.get("version")
    if version != SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported circuit schema version {version!r}; this build supports v{SCHEMA_VERSION}."
        )
    try:
        circuit = Circuit(
            num_qubits=int(data["num_qubits"]),
            num_clbits=int(data.get("num_clbits", 0)),
            name=str(data.get("name", "circuit")),
            operations=[],
            metadata=dict(data.get("metadata", {})),
        )
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"Circuit document is malformed: {e}") from e
    for raw in data.get("operations", []):
        try:
            circuit.operations.append(_operation_from_dict_lenient(raw))
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f"Malformed operation entry {raw!r}: {e}") from e
    return circuit


def _operation_from_dict_lenient(raw: dict):
    """Import operations without executing them; validation happens separately.

    This keeps load/validate separation clean: a saved-but-invalid circuit can
    be loaded and shown in the editor with issues displayed.
    """
    from .model import Operation, Condition

    cond = raw.get("condition")
    return Operation(
        kind=str(raw["kind"]),
        gate=raw.get("gate"),
        params=tuple(float(p) for p in raw.get("params", []) or []),
        qubits=tuple(int(q) for q in raw.get("qubits", []) or []),
        clbits=tuple(int(c) for c in raw.get("clbits", []) or []),
        condition=Condition.from_dict(cond) if cond else None,
        label=raw.get("label"),
    )
