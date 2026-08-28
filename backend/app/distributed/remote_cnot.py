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

Noisy ebits (Werner model)
    When an ebit fidelity F < 1 is supplied (from the NetworkBridge grant or
    an explicit fixed value), each consumed ebit is prepared as the canonical
    Werner state rho_W(F) = F|Phi+><Phi+| + (1-F)/3 (|Phi-| + |Psi+| + |Psi-|)
    (see DensityMatrix.werner for the exact convention). Under the engine's
    statevector trajectory semantics the mixed state is represented by
    sampling ONE Bell-state component per consumed ebit: applying the single-
    qubit Pauli P on the first (Alice) ebit half maps |Phi+> to
      I -> |Phi+> (probability F),  X -> |Psi+>,  Z -> |Phi->,  Y -> |Psi-|
    each with probability (1-F)/3, which reproduces rho_W(F) exactly in the
    trajectory aggregate. The sampled Pauli is inserted as an UNCONDITIONED
    gate right after ebit preparation and BEFORE the Bell measurement, so the
    X^{mx}-before-Z^{mz} correction ordering (AD-004) is untouched. The noise
    is applied exactly once: here, at protocol expansion; the network engine
    only computes and reports the fidelity, it never injects circuit noise.

Correction order is X^{mx} BEFORE Z^{mz} (AD-004); this is load-bearing for
entangling circuits, not merely a global-phase choice.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..circuits.model import Operation, Condition


@dataclass
class RemoteCNOTExpansion:
    operations: list[Operation]
    control_output_qubit: int
    target_output_qubit: int
    ebits: int
    classical_bits: int
    classical_messages: list[tuple[str, str, int]]  # (sender, receiver, bits)
    # Sampled Werner Pauli error per consumed ebit ("I" = ideal component).
    # Empty when the ebit is ideal (no fidelity below 1 supplied).
    ebit_noise: list[str] = field(default_factory=list)


def sample_ebit_pauli_error(fidelity: float, rng) -> str:
    """Sample one trajectory component of the Werner state rho_W(F).

    Returns the Pauli label ("I", "X", "Z", "Y") to apply on the first ebit
    half so the resulting pure state is the corresponding Bell state:
    I -> |Phi+> with probability F; X, Z, Y -> |Psi+>, |Phi->, |Psi-> each
    with probability (1-F)/3. ``rng`` needs a ``.random()`` method
    (numpy Generator or random.Random). F = 1 returns "I" without drawing.
    """
    f = float(fidelity)
    if not (0.0 <= f <= 1.0):
        raise ValueError(f"Ebit fidelity {fidelity} outside [0, 1].")
    if f >= 1.0:
        return "I"
    u = rng.random()
    p_err = (1.0 - f) / 3.0
    if u < f:
        return "I"
    if u < f + p_err:
        return "X"
    if u < f + 2.0 * p_err:
        return "Z"
    return "Y"


_NOISE_GATES = {"X": "X", "Z": "Z", "Y": "Y"}


def _ebit_prep(a: int, b: int, fidelity: float | None, rng, noise_log: list[str]) -> list[Operation]:
    """Ideal ebit preparation plus the sampled Werner Pauli error (if any)."""
    ops = [
        Operation(kind="gate", gate="H", qubits=(a,)),
        Operation(kind="gate", gate="CX", qubits=(a, b)),
    ]
    if fidelity is None or fidelity >= 1.0:
        return ops
    if rng is None:
        raise ValueError(
            "A noise RNG is required when an ebit fidelity < 1 is supplied."
        )
    pauli = sample_ebit_pauli_error(fidelity, rng)
    noise_log.append(pauli)
    if pauli != "I":
        ops.append(Operation(kind="gate", gate=_NOISE_GATES[pauli], qubits=(a,)))
    return ops


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
    ebit_noise_fidelity: float | None = None,
    ebit_noise_rng=None,
) -> RemoteCNOTExpansion:
    """Return the protocol operations that implement CNOT(control, target)
    between two nodes, plus resource metadata.

    ``get_ancilla`` / ``get_clbit`` yield fresh physical qubit / classical bit
    indices for the protocol's internal carriers.

    ``ebit_noise_fidelity`` (Werner fidelity F of each consumed ebit; None or
    >= 1 means ideal) and ``ebit_noise_rng`` drive the sampled Werner-noise
    trajectory; with ideal ebits the emitted operations are exactly the
    historical ideal ones.
    """
    if protocol == "single_ebit":
        return _expand_single_ebit(
            control_phys, target_phys, control_node, target_node, get_ancilla, get_clbit,
            ebit_noise_fidelity, ebit_noise_rng,
        )
    if protocol == "double_teleport":
        return _expand_double_teleport(
            control_phys, target_phys, control_node, target_node, get_ancilla, get_clbit,
            ebit_noise_fidelity, ebit_noise_rng,
        )
    raise ValueError(f"Unknown remote-CNOT protocol {protocol!r}.")


def _expand_single_ebit(control_phys, target_phys, control_node, target_node, get_ancilla, get_clbit,
                        ebit_noise_fidelity=None, ebit_noise_rng=None):
    a = get_ancilla()          # Alice half of ebit
    b = get_ancilla()          # Bob half of ebit
    mz = get_clbit()           # Alice -> Bob: m_z
    mx = get_clbit()           # Alice -> Bob: m_x
    noise: list[str] = []
    ops: list[Operation] = []
    # 1. entanglement distribution (ebit, Werner-noisy when F < 1)
    ops.extend(_ebit_prep(a, b, ebit_noise_fidelity, ebit_noise_rng, noise))
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
        ebit_noise=noise,
    )


def _expand_double_teleport(control_phys, target_phys, control_node, target_node, get_ancilla, get_clbit,
                            ebit_noise_fidelity=None, ebit_noise_rng=None):
    A1 = get_ancilla(); B1 = get_ancilla()
    A2 = get_ancilla(); B2 = get_ancilla()
    m0 = get_clbit(); m1 = get_clbit(); m2 = get_clbit(); m3 = get_clbit()
    noise: list[str] = []
    ops: list[Operation] = []
    # ebit 1 (A1-B1) and ebit 2 (A2-B2), each an independently sampled
    # Werner trajectory component of the SAME grant fidelity.
    ops.extend(_ebit_prep(A1, B1, ebit_noise_fidelity, ebit_noise_rng, noise))
    ops.extend(_ebit_prep(A2, B2, ebit_noise_fidelity, ebit_noise_rng, noise))
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
        ebit_noise=noise,
    )
