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
    of transient occupancy). This is NOT the minimal-cost remote-CNOT
    protocol (single-ebit variants exist) — that optimization is roadmap work;
    this implementation is fully validated against centralized execution.

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
