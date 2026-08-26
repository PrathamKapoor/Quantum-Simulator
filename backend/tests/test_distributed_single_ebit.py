"""Single-ebit (gate-teleportation) remote-CNOT tests (§28-29, §203)."""
import math

import pytest

from app.distributed import (
    build_single_ebit_remote_cnot_circuit,
    compare_single_ebit_remote_cnot_vs_centralized,
    run_single_ebit_demo,
)
from app.circuits import simulate
from app.quantum.states import QuantumCoreError


class TestSingleEbitRemoteCNOT:
    def test_basis_state_truth_table(self):
        demo = run_single_ebit_demo()
        assert len(demo["basis_checks"]) == 2
        assert all(b["passed"] for b in demo["basis_checks"]), demo

    def test_superposition_matches_centralized(self):
        out = compare_single_ebit_remote_cnot_vs_centralized()
        assert out["all_passed"], out
        assert out["worst_fidelity"] > 1 - 1e-8

    def test_target_superposition_role_is_correct(self):
        # Non-trivial target input exercises control/target asymmetry; the
        # single-ebit protocol must still reproduce CNOT(control -> target).
        out = compare_single_ebit_remote_cnot_vs_centralized(
            theta_values=[0.0, math.pi / 3, math.pi / 2, math.pi, 4 * math.pi / 3],
            target_thetas=[0.0, math.pi / 4, math.pi / 2],
        )
        assert out["all_passed"], out
        assert len(out["results"]) == 15

    def test_resource_accounting(self):
        _, layout = build_single_ebit_remote_cnot_circuit(0.5)
        assert layout["ebits_consumed"] == 1
        assert layout["classical_messages"] == 2
        assert layout["classical_bits"] == 2
        assert layout["control_ends_at"] == "bob"
        assert layout["alice_control_output"] == 2
        assert layout["bob_target"] == 3

    def test_theta_validation(self):
        with pytest.raises(QuantumCoreError):
            build_single_ebit_remote_cnot_circuit(-0.5)
        with pytest.raises(QuantumCoreError):
            build_single_ebit_remote_cnot_circuit(7.0)
        with pytest.raises(QuantumCoreError):
            build_single_ebit_remote_cnot_circuit(0.0, target_theta=9.0)

    def test_control_ends_at_bob_not_alice(self):
        """Structural check: Alice's original control qubit (0) is consumed by
        the Bell measurement and never again acts as a live wire; the teleported
        control lives on Bob's qubit 2 and drives the local CNOT(2 -> 3)."""
        circuit, layout = build_single_ebit_remote_cnot_circuit(0.7)
        ca = layout["alice_control_output"]
        assert ca == 2
        # Every gate touching the original control qubit 0 must precede its
        # measurement (it is measured into clbit 0).
        measured = [op for op in circuit.operations
                    if op.kind == "measure" and 0 in op.qubits]
        assert measured, "control must be measured"
        m_idx = circuit.operations.index(measured[0])
        later_touch = [op for op in circuit.operations[m_idx + 1:]
                       if op.kind == "gate" and 0 in op.qubits]
        assert not later_touch, "control qubit 0 is reused after measurement"

    def test_classical_bits_exercised(self):
        circuit, _ = build_single_ebit_remote_cnot_circuit(math.pi)
        res = simulate(circuit, seed=3)
        assert res.classical_registers and len(res.classical_registers[0]) == 2
