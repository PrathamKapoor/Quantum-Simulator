"""Distributed quantum computing: remote gates over entanglement (§28-29).

IMPLEMENTED SUBSET (honest scope):

    Remote CNOT via DOUBLE TELEPORTATION
    ------------------------------------
    Alice holds the control qubit c; Bob holds the target t. Two Bell pairs
    are consumed and four classical bits are exchanged:

        1. generate ebit1 (A1-B1) and ebit2 (A2-B2)
        2. teleport c -> t1 (Bob side)          [ebit1, 2 cbits]
        3. Bob applies LOCAL CNOT(t1 -> t)
        4. teleport t1 -> A2 (Alice side)       [ebit2, 2 cbits]

    The logical control returns to Alice; the target never left Bob.

    Resource cost is exactly: 2 ebits + 4 classical bits (+ 6 physical qubits
    of transient occupancy). Validated against centralized execution.

    Remote CNOT via SINGLE-EBIT GATE TELEPORTATION
    ----------------------------------------------
    The minimal-cost (in entanglement) remote CNOT. One Bell pair (1 ebit) and
    two classical bits are consumed; the control is teleported to Bob and Bob
    applies CNOT locally:

        1. share ebit (Alice a -- Bob b)
        2. Bell-measure Alice's control onto a   [a -> b, 2 cbits]
        3. Bob corrects b, then applies CNOT(b -> t)

    Resource cost is exactly: 1 ebit + 2 classical bits (+ 4 physical qubits
    of transient occupancy). The control ends up at Bob (both control and
    target co-located there) — an honest difference from the double-teleport
    variant, where the control returns to Alice. Validated against
    centralized execution including non-trivial target inputs.

    Multi-node circuit partitioner (app.distributed.partition)
    ----------------------------------------------------------
    Splits a circuit into node-local operations and cross-node remote gates and
    costs the remote interactions under both protocol choices. Analysis/costing
    only; it does not compile remote gates into per-node distributed circuits.

All circuits run on the standard simulator with mid-circuit measurement and
classical conditioning (no new engine features required).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..circuits.model import Circuit, Condition
from ..circuits.simulate import simulate
from ..quantum.density import DensityMatrix
from ..quantum.states import StateVector, QuantumCoreError


def build_remote_cnot_circuit(
    control_theta: float = 0.0,
    *,
    prepare_control_superposition: bool = True,
) -> tuple[Circuit, dict]:
    """Build the full distributed circuit.

    Qubit map (little-endian indices):
        0: c     Alice control (input; prepared RY(theta))
        1: t     Bob target (input |0>)
        2: A1    Alice half of ebit1
        3: B1    Bob half of ebit1
        4: B2    Bob half of ebit2
        5: A2    Alice half of ebit2 (receives teleported control)

    Returns (circuit, layout).
    """
    if not (0 <= control_theta <= 2 * np.pi):
        raise QuantumCoreError("control_theta must be within [0, 2pi].")
    c = Circuit(num_qubits=6, num_clbits=4, name="remote-cnot")

    # ---- inputs -----------------------------------------------------------
    if prepare_control_superposition or control_theta != 0:
        c.add_gate("RY", [0], params=[control_theta])

    # ---- step 1: entanglement distribution -------------------------------
    for a, b in ((2, 3), (5, 4)):      # (A1,B1) and (A2,B2)
        c.add_gate("H", [a])
        c.add_gate("CX", [a, b])

    # ---- step 2: teleport c (qubit 0) -> B1 side using ebit (A1=2,B1=3) --
    # Correction ORDER matters: Bob's pre-correction state is Z^mz X^mx |psi>,
    # so X must be applied BEFORE Z (the difference is only a global phase in
    # isolated teleportation, but it becomes observable when the teleported
    # wire later participates in entangling operations).
    c.add_gate("CX", [0, 2])           # Bell measurement part 1
    c.add_gate("H", [0])               # part 2
    c.add_measure([0], [0])            # m_z  -> clbit 0
    c.add_measure([2], [1])            # m_x  -> clbit 1
    c.add_gate("X", [3], condition=Condition(clbit=1, value=1))
    c.add_gate("Z", [3], condition=Condition(clbit=0, value=1))
    # control now lives on qubit 3 (Bob side)

    # ---- step 3: Bob-local CNOT(control=t1=q3 -> target=q1) ---------------
    c.add_gate("CX", [3, 1])

    # ---- step 4: teleport t1 (qubit 3) back -> A2 (qubit 5) --------------
    c.add_gate("CX", [3, 4])
    c.add_gate("H", [3])
    c.add_measure([3], [2])            # m_z' -> clbit 2
    c.add_measure([4], [3])            # m_x' -> clbit 3
    c.add_gate("X", [5], condition=Condition(clbit=3, value=1))
    c.add_gate("Z", [5], condition=Condition(clbit=2, value=1))

    layout = {
        "alice_control_output": 5,
        "bob_target": 1,
        "ebit_pairs": [(2, 3), (5, 4)],
        "classical_bits": 4,
        "ebits_consumed": 2,
        "classical_messages": 4,
    }
    return c, layout


def _reduced_two_qubit_state(state: StateVector, qa: int, qb: int) -> DensityMatrix:
    return DensityMatrix.pure(state).partial_trace([qa, qb])


@dataclass
class DistributedComparisonResult:
    theta: float
    fidelity_distributed_vs_ideal: float
    success: bool
    distributed_probabilities: dict[str, float]
    notes: list[str]


def compare_remote_cnot_vs_centralized(
    theta_values: list[float] | None = None,
    *,
    tolerance: float = 1e-8,
) -> dict:
    """Validate distributed remote CNOT against ideal centralized execution.

    Ideal reference: |psi> = RY(theta)|0> on control; CNOT(control -> target).
    Comparison: Uhlmann fidelity of the two-qubit reduced states on the
    (control-output, target) wires.
    """
    theta_values = theta_values or [0.0, math.pi / 2, math.pi, 3 * math.pi / 2]
    results = []
    worst = 1.0
    for theta in theta_values:
        dist_circuit, layout = build_remote_cnot_circuit(theta)
        dist_res = simulate(dist_circuit)
        ca = layout["alice_control_output"]
        tb = layout["bob_target"]
        rho_dist = _reduced_two_qubit_state(dist_res.final_state, tb, ca)

        central = Circuit(num_qubits=2)
        central.add_gate("RY", [0], params=[theta])
        central.add_gate("CX", [0, 1])
        rho_central = DensityMatrix.pure(simulate(central).final_state)

        fid = rho_dist.fidelity_with(rho_central)
        worst = min(worst, fid)
        results.append({
            "theta": round(theta, 6),
            "fidelity": round(fid, 12),
            "passed": fid >= 1 - tolerance,
        })
    return {
        "results": results,
        "worst_fidelity": round(worst, 12),
        "all_passed": bool(worst >= 1 - tolerance),
        "resources": {
            "ebits_consumed": 2,
            "classical_bits_exchanged": 4,
            "transient_physical_qubits": 6,
        },
        "notes": [
            "Double-teleportation construction; NOT the minimal single-ebit "
            "remote-CNOT (documented roadmap item).",
            "Ideal local operations assumed; noise injection can be layered "
            "via the standard NoiseModel on the same circuit.",
        ],
    }


def run_distributed_cnot_demo() -> dict:
    """Flagship demo payload (directive §103)."""
    comparison = compare_remote_cnot_vs_centralized()
    # Also demonstrate on computational basis inputs for readability.
    # RY(pi)|0> = |1>: prepares the control deterministically INSIDE the
    # circuit prefix (appending gates afterwards would place them after the
    # protocol, which is a real bug class caught by these checks).
    basis_checks = []
    for ctrl in (0, 1):
        c, layout = build_remote_cnot_circuit(math.pi if ctrl else 0.0)
        r = simulate(c)
        probs = r.final_state.probabilities()
        ca, tb = layout["alice_control_output"], layout["bob_target"]
        p_ctrl = sum(p for i, p in enumerate(probs) if (i >> ca) & 1)
        p_tgt = sum(p for i, p in enumerate(probs) if (i >> tb) & 1)
        expected_tgt = ctrl  # CNOT copies control value into |0> target
        basis_checks.append({
            "control_input": ctrl,
            "p_control_output_1": round(float(p_ctrl), 9),
            "p_target_output_1": round(float(p_tgt), 9),
            "passed": bool(abs(p_ctrl - ctrl) < 1e-9 and abs(p_tgt - expected_tgt) < 1e-9),
        })
    return {
        "comparison": comparison,
        "basis_checks": basis_checks,
        "all_passed": comparison["all_passed"] and all(b["passed"] for b in basis_checks),
    }


# ---------------------------------------------------------------------------
# Single-ebit remote CNOT via gate teleportation (minimal entanglement cost)
# ---------------------------------------------------------------------------

def build_single_ebit_remote_cnot_circuit(
    control_theta: float = 0.0,
    target_theta: float = 0.0,
    *,
    prepare_control_superposition: bool = True,
    prepare_target_superposition: bool = False,
) -> tuple[Circuit, dict]:
    """Build the single-ebit distributed remote-CNOT circuit.

    Gate-teleportation construction (Gottesman-Chuang style): one Bell pair is
    shared between Alice (a) and Bob (b); Alice Bell-measures her control onto
    a, Bob corrects b, then applies CNOT(b -> t) locally. The control is
    teleported to Bob, so after the protocol BOTH the control and the target
    reside at Bob.

    Qubit map (little-endian indices):
        0: c     Alice control (input; prepared RY(control_theta))
        1: a     Alice half of the ebit
        2: b     Bob half of the ebit (receives teleported control)
        3: t     Bob target (input |0>; prepared RY(target_theta) if requested)

    Returns (circuit, layout).
    """
    if not (0 <= control_theta <= 2 * np.pi):
        raise QuantumCoreError("control_theta must be within [0, 2pi].")
    if not (0 <= target_theta <= 2 * np.pi):
        raise QuantumCoreError("target_theta must be within [0, 2pi].")
    c = Circuit(num_qubits=4, num_clbits=2, name="remote-cnot-single-ebit")

    if prepare_control_superposition or control_theta != 0:
        c.add_gate("RY", [0], params=[control_theta])
    if prepare_target_superposition and target_theta != 0:
        c.add_gate("RY", [3], params=[target_theta])

    # ---- step 1: entanglement distribution (ebit a -- b) -------------------
    c.add_gate("H", [1])
    c.add_gate("CX", [1, 2])

    # ---- step 2: Bell measurement of control c onto a ----------------------
    # Correction ORDER: Bob's pre-correction state is Z^mz X^mx |psi>, so X
    # must be applied BEFORE Z (see AD-004 / double-teleport note).
    c.add_gate("CX", [0, 1])
    c.add_gate("H", [0])
    c.add_measure([0], [0])           # m_z  -> clbit 0
    c.add_measure([1], [1])           # m_x  -> clbit 1
    c.add_gate("X", [2], condition=Condition(clbit=1, value=1))
    c.add_gate("Z", [2], condition=Condition(clbit=0, value=1))
    # control now lives on qubit 2 (Bob side)

    # ---- step 3: Bob-local CNOT(control=b -> target=t) --------------------
    c.add_gate("CX", [2, 3])

    layout = {
        "alice_control_output": 2,
        "bob_target": 3,
        "ebit_pairs": [(1, 2)],
        "classical_bits": 2,
        "ebits_consumed": 1,
        "classical_messages": 2,
        "control_ends_at": "bob",
    }
    return c, layout


def compare_single_ebit_remote_cnot_vs_centralized(
    theta_values: list[float] | None = None,
    target_thetas: list[float] | None = None,
    *,
    tolerance: float = 1e-8,
) -> dict:
    """Validate the single-ebit remote CNOT against ideal centralized CNOT.

    Ideal reference: |psi> = RY(control_theta)|0> on control, optional
    RY(target_theta)|0> on target; CNOT(control -> target). Comparison is the
    Uhlmann fidelity of the two-qubit reduced states on the (control, target)
    wires, where the distributed control ends on qubit 2 and the target on
    qubit 3 (both at Bob). Unlike the double-teleport variant, the target is
    allowed to be a non-trivial input here, exercising the control/target roles
    asymmetrically.
    """
    theta_values = theta_values or [0.0, math.pi / 2, math.pi, 3 * math.pi / 2]
    target_thetas = target_thetas or [0.0]
    results = []
    worst = 1.0
    for theta in theta_values:
        for ttheta in target_thetas:
            dist_circuit, layout = build_single_ebit_remote_cnot_circuit(
                theta, ttheta,
                prepare_target_superposition=(ttheta != 0.0),
            )
            dist_res = simulate(dist_circuit)
            ca = layout["alice_control_output"]
            tb = layout["bob_target"]
            # NOTE: partial_trace([tb, ca]) yields a reduced qubit-0 == ca
            # (control) and qubit-1 == tb (target) under this package's
            # einsum output convention; this matches the centralized CNOT
            # reference (control=qubit0, target=qubit1). Using [ca, tb] would
            # transpose the reduced state and fail on non-symmetric targets.
            rho_dist = _reduced_two_qubit_state(dist_res.final_state, tb, ca)

            central = Circuit(num_qubits=2)
            central.add_gate("RY", [0], params=[theta])
            if ttheta != 0.0:
                central.add_gate("RY", [1], params=[ttheta])
            central.add_gate("CX", [0, 1])
            rho_central = DensityMatrix.pure(simulate(central).final_state)

            fid = rho_dist.fidelity_with(rho_central)
            worst = min(worst, fid)
            results.append({
                "control_theta": round(theta, 6),
                "target_theta": round(ttheta, 6),
                "fidelity": round(fid, 12),
                "passed": fid >= 1 - tolerance,
            })
    return {
        "results": results,
        "worst_fidelity": round(worst, 12),
        "all_passed": bool(worst >= 1 - tolerance),
        "resources": {
            "ebits_consumed": 1,
            "classical_bits_exchanged": 2,
            "transient_physical_qubits": 4,
        },
        "notes": [
            "Single-ebit gate-teleportation construction (1 ebit + 2 cbits).",
            "Control ends at Bob (co-located with target); differs from the "
            "double-teleport variant where control returns to Alice.",
            "Ideal local operations assumed; noise can be layered via the "
            "standard NoiseModel on the same circuit.",
        ],
    }


def run_single_ebit_demo() -> dict:
    """Flagship demo payload for the single-ebit remote CNOT."""
    comparison = compare_single_ebit_remote_cnot_vs_centralized()
    basis_checks = []
    for ctrl in (0, 1):
        c, layout = build_single_ebit_remote_cnot_circuit(math.pi if ctrl else 0.0)
        r = simulate(c)
        probs = r.final_state.probabilities()
        ca, tb = layout["alice_control_output"], layout["bob_target"]
        p_ctrl = sum(p for i, p in enumerate(probs) if (i >> ca) & 1)
        p_tgt = sum(p for i, p in enumerate(probs) if (i >> tb) & 1)
        expected_tgt = ctrl
        basis_checks.append({
            "control_input": ctrl,
            "p_control_output_1": round(float(p_ctrl), 9),
            "p_target_output_1": round(float(p_tgt), 9),
            "passed": bool(abs(p_ctrl - ctrl) < 1e-9 and abs(p_tgt - expected_tgt) < 1e-9),
        })
    return {
        "comparison": comparison,
        "basis_checks": basis_checks,
        "all_passed": comparison["all_passed"] and all(b["passed"] for b in basis_checks),
    }


from .partition import (  # noqa: E402
    partition_circuit,
    remote_gate_cost,
    PartitionResult,
    partition_circuit_full,
    heuristic_assignment,
    PartitionPlan,
)
from .remote_cnot import expand_remote_cnot, RemoteCNOTExpansion  # noqa: E402
from .network_bridge import NetworkBridge, topology_from_nodes_links  # noqa: E402
from .engine import DistributedExecutor, DistributedConfig  # noqa: E402
from .model import (  # noqa: E402
    DistributedResult,
    NodeSpec,
    LocalOp,
    RemoteOp,
    EbitGrant,
    ClassicalMessage,
    PartitionMetrics,
)

__all__ = [
    "build_remote_cnot_circuit",
    "compare_remote_cnot_vs_centralized",
    "run_distributed_cnot_demo",
    "build_single_ebit_remote_cnot_circuit",
    "compare_single_ebit_remote_cnot_vs_centralized",
    "run_single_ebit_demo",
    "partition_circuit",
    "remote_gate_cost",
    "PartitionResult",
    "partition_circuit_full",
    "heuristic_assignment",
    "PartitionPlan",
    "expand_remote_cnot",
    "RemoteCNOTExpansion",
    "NetworkBridge",
    "topology_from_nodes_links",
    "DistributedExecutor",
    "DistributedConfig",
    "DistributedResult",
    "NodeSpec",
    "LocalOp",
    "RemoteOp",
    "EbitGrant",
    "ClassicalMessage",
    "PartitionMetrics",
]
