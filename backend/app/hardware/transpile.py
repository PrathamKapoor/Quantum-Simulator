"""Transpiler: hardware mapping with SWAP insertion (directive §10, §22).

Strategy: trivial initial mapping (logical i -> physical i) + on-demand SWAP
insertion along the coupling-graph shortest path when a two-qubit gate's
operands are not adjacent. Logical-to-physical permutation is tracked so final
measurement results can be interpreted.

Correctness contract (validated by tests): under IDEAL execution, the mapped
circuit's action equals the logical circuit's action up to the recorded final
permutation — checked by comparing full unitaries for small qubit counts and
by statevector output comparison generally.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..circuits.model import Circuit, Operation
from ..quantum.states import QuantumCoreError
from .profiles import HardwareProfile


@dataclass
class TranspileResult:
    circuit: Circuit                    # hardware-mapped circuit (physical qubits)
    initial_mapping: dict[int, int]     # logical -> physical at start
    final_mapping: dict[int, int]       # logical -> physical at end
    swap_count: int
    original_depth: int
    mapped_depth: int
    original_gate_count: int
    mapped_gate_count: int
    added_two_qubit_gates: int
    warnings: list[str] = field(default_factory=list)


def _swap_decomposition(circuit: Circuit, a: int, b: int) -> None:
    """Append a SWAP(a,b) as three CX gates (CX native on all profiles here)."""
    circuit.add_gate("CX", [a, b])
    circuit.add_gate("CX", [b, a])
    circuit.add_gate("CX", [a, b])


def transpile_for_hardware(
    logical_circuit: Circuit,
    profile: HardwareProfile,
    *,
    decompose_swap: bool = True,
) -> TranspileResult:
    """Map a logical circuit onto the profile's coupling graph.

    - 1-qubit native gates pass through unchanged.
    - CX/CZ/SWAP on non-coupled pairs insert shortest-path SWAPs; the running
      permutation is updated so later operations stay consistent.
    - Non-native gate names are rejected with an actionable message (§142 no
      silent fallbacks).
    """
    if logical_circuit.num_qubits > profile.n_qubits:
        raise QuantumCoreError(
            f"Circuit uses {logical_circuit.num_qubits} qubits but profile "
            f"{profile.name!r} provides only {profile.n_qubits}."
        )

    issues = []
    from ..circuits.validate import validate_circuit

    issues = validate_circuit(logical_circuit)
    blocking = [i for i in issues if i.code not in ("EMPTY_CIRCUIT",)]
    if blocking:
        raise ValueError("Logical circuit failed validation: " +
                         "; ".join(i.code for i in blocking))

    out = Circuit(num_qubits=profile.n_qubits,
                  num_clbits=logical_circuit.num_clbits,
                  name=f"{logical_circuit.name}-mapped")
    # inherit custom gate matrices (unitary-validated on use)
    out.metadata["custom_gates"] = dict(logical_circuit.metadata.get("custom_gates", {}))

    perm = {q: q for q in range(logical_circuit.num_qubits)}   # logical -> physical
    swap_count = 0

    def emit_native(op: Operation, physical_qubits: list[int]) -> None:
        out.operations.append(Operation(
            kind="gate", gate=op.gate, params=op.params,
            qubits=tuple(physical_qubits), clbits=(), condition=None,
            label=op.label,
        ))

    for op in logical_circuit.operations:
        if op.kind == "measure":
            phys = [perm[q] for q in op.qubits]
            out.operations.append(Operation(
                kind="measure", qubits=tuple(phys), clbits=tuple(op.clbits)))
            continue
        if op.kind == "barrier":
            out.add_barrier([perm[q] for q in op.qubits])
            continue
        if op.kind == "reset":
            out.operations.append(Operation(kind="reset", qubits=tuple(perm[q] for q in op.qubits)))
            continue
        if op.kind != "gate":
            raise QuantumCoreError(f"Unsupported operation kind {op.kind!r}.")

        name = (op.gate or "").upper()
        spec = profile.native_gates.get(name)
        if spec is None:
            raise QuantumCoreError(
                f"Gate {name!r} is not native to profile {profile.name!r}. "
                f"Native set: {sorted(profile.native_gates)}. "
                "Add a decomposition rule or extend the profile."
            )
        arity = len(op.qubits)

        if arity != spec.arity:
            raise QuantumCoreError(
                f"Gate {name!r} expects {spec.arity} operand(s), got {arity}."
            )

        if arity == 1:
            emit_native(op, [perm[op.qubits[0]]])
            continue

        # two-qubit native gate: operands must be coupled after permutation
        la, lb = op.qubits[0], op.qubits[1]
        pa, pb = perm[la], perm[lb]
        if pa == pb:
            raise QuantumCoreError("Two-qubit gate operands collided after routing.")
        if profile.are_coupled(pa, pb):
            if name == "SWAP" and decompose_swap:
                _swap_decomposition(out, pa, pb)
            else:
                emit_native(op, [pa, pb])
            continue

        path = profile.shortest_coupling_path(pa, pb)
        if path is None:
            raise QuantumCoreError(
                f"No coupling path between physical qubits {pa} and {pb}; "
                "topology is disconnected for this pair."
            )
        # Walk SWAPs along the path moving lb toward pa (keeps chains short).
        for step in range(len(path) - 2):
            x, y = path[step], path[step + 1]
            if decompose_swap or "SWAP" not in profile.native_gates:
                _swap_decomposition(out, x, y)
            else:
                out.add_gate("SWAP", [x, y])
            swap_count += 1
            # update permutation: logical qubits currently sitting on x/y trade places
            log_x = next((l for l, p in perm.items() if p == x), None)
            log_y = next((l for l, p in perm.items() if p == y), None)
            if log_x is not None:
                perm[log_x] = y
            if log_y is not None:
                perm[log_y] = x
        pa_new, pb_new = perm[la], perm[lb]
        if not profile.are_coupled(pa_new, pb_new):
            raise QuantumCoreError("Routing failed to couple operands; internal error.")
        if name == "SWAP" and decompose_swap:
            _swap_decomposition(out, pa_new, pb_new)
        else:
            emit_native(op, [pa_new, pb_new])

    return TranspileResult(
        circuit=out,
        initial_mapping={q: q for q in range(logical_circuit.num_qubits)},
        final_mapping=dict(perm),
        swap_count=swap_count,
        original_depth=logical_circuit.depth(),
        mapped_depth=out.depth(),
        original_gate_count=len(logical_circuit.operations),
        mapped_gate_count=len(out.operations),
        added_two_qubit_gates=swap_count * (3 if decompose_swap else 1),
    )


def verify_mapping_preserves_action(
    logical: Circuit, result: TranspileResult,
) -> dict:
    """Compare ideal unitary of mapped circuit with logical circuit under the
    final permutation (small n only — explicit reference method, RULE 3).

    Returns max deviation over basis columns."""
    from ..circuits.simulate import simulate as sim
    from .profiles import preset_ideal_8q

    n = logical.num_qubits
    if n > 7:
        return {"verified": False, "reason": "n too large for dense verification"}

    ideal_engine = type("E", (), {"name": "ideal"})()

    def matrix_of(circuit: Circuit) -> np.ndarray:
        dim = 1 << n
        cols = []
        for i in range(dim):
            ops = [
                Operation(kind="gate", gate="X", params=(), qubits=(q,))
                for q in range(n)
                if (i >> q) & 1
            ]
            probe = Circuit(num_qubits=n,
                            operations=ops + list(circuit.operations),
                            metadata=dict(circuit.metadata))
            res = sim(probe)
            cols.append(res.final_state.amplitudes)
        return np.column_stack(cols)

    m_logical = matrix_of(logical)
    m_mapped = matrix_of(result.circuit)
    # Derivation: routing inserts wire permutations before later gates, so the
    # mapped unitary relates to the logical one as
    #     M_mapped[:, c] = P_end · M_logical[:, c]   for every basis column,
    # where (P_end v) places component v_l at physical position final_mapping[l].
    # We therefore scatter every logical column through the permutation and
    # compare against the mapped columns directly.
    dim = 1 << n
    scattered = np.zeros_like(m_mapped)
    for col in range(dim):
        v = m_logical[:, col]
        out_v = np.zeros_like(v)
        # scatter components of v: component l moves to position perm[l]
        for r in range(dim):
            r_phys = sum(
                ((r >> lq) & 1) << int(result.final_mapping[lq]) for lq in range(n)
            )
            out_v[r_phys] = v[r]
        scattered[:, col] = out_v
    dev = float(np.max(np.abs(m_mapped - scattered)))
    return {
        "verified": bool(dev < 1e-8),
        "max_deviation": dev,
        "method": "dense unitary column-scatter through final permutation (reference path)",
    }
