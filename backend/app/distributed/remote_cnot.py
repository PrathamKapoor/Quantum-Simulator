"""Single-ebit (and double-teleport) remote-CNOT protocol expansion.

The distributed engine replaces each cross-node CNOT with its protocol
expansion (directive §REMOTE CNOT). The expansion is NOT a centralized CNOT
with a label: it genuinely teleports/entangles qubits, performs local gates,
measures, communicates classical bits, and applies Pauli corrections — exactly
the distributed operations a real implementation would perform. The ordinary
quantum simulator executes these operations, so the resulting logical state is
physically the distributed-computation output.

Protocol 1 — single-ebit gate teleportation (Gottesman-Chuang style)
    Shared 1 ebit between Alice (control) and Bob (target).
    Bell-measure Alice's control onto her ebit half -> 2 classical bits ->
    Bob corrects his half and applies CNOT locally. Cost: 1 ebit, 2 cbits.
    After the gate the control co-locates with the target at Bob.

Protocol 2 — double teleportation
    Shared 2 ebits, 4 classical bits; the control is returned to Alice.
    Cost: 2 ebits, 4 cbits.

Correction order is X^{mx} BEFORE Z^{mz} (AD-004); this is load-bearing for
entangling circuits, not merely a global-phase choice.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..circuits.model import Operation, Condition


@dataclass
class RemoteCNOTExpansion:
    operations: list[Operation]
    control_output_qubit: int
    target_output_qubit: int
    ebits: int
    classical_bits: int
    classical_messages: list[tuple[str, str, int]]  # (sender, receiver, bits)


def _alloc_pair(get_ancilla, get_clbit):
    return get_ancilla(), get_ancilla(), get_clbit(), get_clbit()


def expand_remote_cnot(
    control_phys: int,
    target_phys: int,
    control_node: str,
    target_node: str,
    protocol: str,
    get_ancilla,
    get_clbit,
) -> RemoteCNOTExpansion:
    """Return the protocol operations that implement CNOT(control, target)
    between two nodes, plus resource metadata.

    ``get_ancilla`` / ``get_clbit`` yield fresh physical qubit / classical bit
    indices for the protocol's internal carriers.
    """
    if protocol == "single_ebit":
        return _expand_single_ebit(
            control_phys, target_phys, control_node, target_node, get_ancilla, get_clbit
        )
    if protocol == "double_teleport":
        return _expand_double_teleport(
            control_phys, target_phys, control_node, target_node, get_ancilla, get_clbit
        )
    raise ValueError(f"Unknown remote-CNOT protocol {protocol!r}.")


def _expand_single_ebit(control_phys, target_phys, control_node, target_node, get_ancilla, get_clbit):
    a = get_ancilla()          # Alice half of ebit
    b = get_ancilla()          # Bob half of ebit
    mz = get_clbit()           # Alice -> Bob: m_z
    mx = get_clbit()           # Alice -> Bob: m_x
    ops: list[Operation] = []
    # 1. entanglement distribution (ebit)
    ops.append(Operation(kind="gate", gate="H", qubits=(a,)))
    ops.append(Operation(kind="gate", gate="CX", qubits=(a, b)))
    # 2. Bell measurement of control onto a
    ops.append(Operation(kind="gate", gate="CX", qubits=(control_phys, a)))
    ops.append(Operation(kind="gate", gate="H", qubits=(control_phys,)))
    ops.append(Operation(kind="measure", qubits=(control_phys,), clbits=(mz,)))
    ops.append(Operation(kind="measure", qubits=(a,), clbits=(mx,)))
    # 3. Bob corrects b, then local CNOT(b -> target)
    ops.append(Operation(kind="gate", gate="X", qubits=(b,),
                         condition=Condition(clbit=mx, value=1)))
    ops.append(Operation(kind="gate", gate="Z", qubits=(b,),
                         condition=Condition(clbit=mz, value=1)))
    ops.append(Operation(kind="gate", gate="CX", qubits=(b, target_phys)))
    return RemoteCNOTExpansion(
        operations=ops,
        control_output_qubit=b,
        target_output_qubit=target_phys,
        ebits=1,
        classical_bits=2,
        classical_messages=[(control_node, target_node, 2)],
    )


def _expand_double_teleport(control_phys, target_phys, control_node, target_node, get_ancilla, get_clbit):
    A1 = get_ancilla(); B1 = get_ancilla()
    A2 = get_ancilla(); B2 = get_ancilla()
    m0 = get_clbit(); m1 = get_clbit(); m2 = get_clbit(); m3 = get_clbit()
    ops: list[Operation] = []
    # ebit 1 (A1-B1) and ebit 2 (A2-B2)
    ops.append(Operation(kind="gate", gate="H", qubits=(A1,)))
    ops.append(Operation(kind="gate", gate="CX", qubits=(A1, B1)))
    ops.append(Operation(kind="gate", gate="H", qubits=(A2,)))
    ops.append(Operation(kind="gate", gate="CX", qubits=(A2, B2)))
    # teleport control -> B1 (Bob side)
    ops.append(Operation(kind="gate", gate="CX", qubits=(control_phys, A1)))
    ops.append(Operation(kind="gate", gate="H", qubits=(control_phys,)))
    ops.append(Operation(kind="measure", qubits=(control_phys,), clbits=(m0,)))
    ops.append(Operation(kind="measure", qubits=(A1,), clbits=(m1,)))
    ops.append(Operation(kind="gate", gate="X", qubits=(B1,),
                         condition=Condition(clbit=m1, value=1)))
    ops.append(Operation(kind="gate", gate="Z", qubits=(B1,),
                         condition=Condition(clbit=m0, value=1)))
    # Bob-local CNOT(B1 -> target)
    ops.append(Operation(kind="gate", gate="CX", qubits=(B1, target_phys)))
    # teleport B1 -> A2 (Alice side), returning control to Alice
    ops.append(Operation(kind="gate", gate="CX", qubits=(B1, B2)))
    ops.append(Operation(kind="gate", gate="H", qubits=(B1,)))
    ops.append(Operation(kind="measure", qubits=(B1,), clbits=(m2,)))
    ops.append(Operation(kind="measure", qubits=(B2,), clbits=(m3,)))
    ops.append(Operation(kind="gate", gate="X", qubits=(A2,),
                         condition=Condition(clbit=m3, value=1)))
    ops.append(Operation(kind="gate", gate="Z", qubits=(A2,),
                         condition=Condition(clbit=m2, value=1)))
    return RemoteCNOTExpansion(
        operations=ops,
        control_output_qubit=A2,
        target_output_qubit=target_phys,
        ebits=2,
        classical_bits=4,
        classical_messages=[(control_node, target_node, 2), (target_node, control_node, 2)],
    )
