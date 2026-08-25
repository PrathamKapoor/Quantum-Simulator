"""Circuit model: operations, registers, metadata.

A circuit is a linear sequence of operations over quantum/classical registers.
Operations support mid-circuit measurement and conditioning on classical bits,
which teleportation, QEC, and networking protocols require (directive §28-29).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Condition:
    """Execute an operation only if the classical register bit equals `value`."""

    clbit: int
    value: int

    def to_dict(self) -> dict:
        return {"clbit": self.clbit, "value": self.value}

    @classmethod
    def from_dict(cls, d: dict) -> "Condition":
        return cls(clbit=int(d["clbit"]), value=int(d["value"]))


@dataclass(frozen=True)
class Operation:
    """One circuit operation.

    kind: "gate" | "measure" | "reset" | "barrier"
    gate: canonical gate name for kind == "gate" (e.g. "H", "CX", "RZ").
    params: gate parameters in radians (floats).
    qubits: operand qubit indices, first operand = most-significant local bit.
    clbits: target classical bits for kind == "measure" (parallel to qubits).
    condition: optional classical condition gating this operation.
    """

    kind: str
    gate: str | None = None
    params: tuple[float, ...] = ()
    qubits: tuple[int, ...] = ()
    clbits: tuple[int, ...] = ()
    condition: Condition | None = None
    label: str | None = None

    def to_dict(self) -> dict:
        d: dict = {
            "kind": self.kind,
            "qubits": list(self.qubits),
            "clbits": list(self.clbits),
            "condition": self.condition.to_dict() if self.condition else None,
            "label": self.label,
        }
        if self.kind == "gate":
            d["gate"] = self.gate
            d["params"] = list(self.params)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Operation":
        cond = d.get("condition")
        return cls(
            kind=str(d["kind"]),
            gate=d.get("gate"),
            params=tuple(float(p) for p in d.get("params", [])),
            qubits=tuple(int(q) for q in d.get("qubits", [])),
            clbits=tuple(int(c) for c in d.get("clbits", [])),
            condition=Condition.from_dict(cond) if cond else None,
            label=d.get("label"),
        )


@dataclass
class Circuit:
    """Quantum circuit with explicit register sizes."""

    num_qubits: int
    num_clbits: int = 0
    operations: list[Operation] = field(default_factory=list)
    name: str = "circuit"
    metadata: dict = field(default_factory=dict)

    # ---------- builder helpers ----------

    def add_gate(
        self,
        gate: str,
        qubits: list[int],
        params: list[float] | None = None,
        *,
        condition: Condition | None = None,
        label: str | None = None,
    ) -> "Circuit":
        self.operations.append(
            Operation(
                kind="gate",
                gate=gate.upper(),
                params=tuple(params or []),
                qubits=tuple(qubits),
                condition=condition,
                label=label,
            )
        )
        return self

    def add_measure(self, qubits: list[int], clbits: list[int]) -> "Circuit":
        if len(qubits) != len(clbits):
            raise ValueError("measure requires parallel qubit/clbit lists.")
        self.operations.append(Operation(kind="measure", qubits=tuple(qubits), clbits=tuple(clbits)))
        return self

    def add_reset(self, qubits: list[int]) -> "Circuit":
        self.operations.append(Operation(kind="reset", qubits=tuple(qubits)))
        return self

    def add_barrier(self, qubits: list[int]) -> "Circuit":
        self.operations.append(Operation(kind="barrier", qubits=tuple(qubits)))
        return self

    def depth(self) -> int:
        """Circuit depth ignoring barriers; measures act as gates."""
        frontier = [0] * max(self.num_qubits, 1)
        cfrontier = [0] * max(self.num_clbits, 1)
        for op in self.operations:
            if op.kind == "barrier":
                continue
            touched = list(op.qubits)
            level = max((frontier[q] for q in touched), default=0) + 1
            if op.clbits:
                level = max(level, max((cfrontier[c] for c in op.clbits), default=0) + 1)
                for c in op.clbits:
                    cfrontier[c] = level
            for q in touched:
                frontier[q] = level
        return max(frontier + [0])

    def count_gates(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for op in self.operations:
            if op.kind == "gate":
                key = op.gate or "?"
                counts[key] = counts.get(key, 0) + 1
        return counts

    def has_mid_circuit_measurement(self) -> bool:
        seen_measure = False
        for op in self.operations:
            if op.kind == "measure":
                seen_measure = True
            elif seen_measure and op.kind in ("gate", "reset") :
                # A gate/reset after a measurement could depend on it; treat as
                # mid-circuit unless it precedes all measurements conservatively.
                return True
        return False

    def has_conditions(self) -> bool:
        return any(op.condition is not None for op in self.operations)

    def copy(self) -> "Circuit":
        return Circuit(
            num_qubits=self.num_qubits,
            num_clbits=self.num_clbits,
            operations=list(self.operations),
            name=self.name,
            metadata=dict(self.metadata),
        )
