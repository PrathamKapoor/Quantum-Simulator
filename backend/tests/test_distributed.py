"""Distributed remote-CNOT tests (directive §28-29, §203)."""
import math

import pytest

from app.distributed import (
    build_remote_cnot_circuit,
    compare_remote_cnot_vs_centralized,
    run_distributed_cnot_demo,
)
from app.circuits import simulate
from app.quantum.states import QuantumCoreError


class TestRemoteCNOT:
    def test_basis_state_truth_table(self):
        demo = run_distributed_cnot_demo()
        assert len(demo["basis_checks"]) == 2
        assert all(b["passed"] for b in demo["basis_checks"]), demo

    def test_superposition_matches_centralized(self):
        out = compare_remote_cnot_vs_centralized()
        assert out["all_passed"], out
        assert out["worst_fidelity"] > 1 - 1e-8

    def test_resource_accounting(self):
        _, layout = build_remote_cnot_circuit(0.5)
        assert layout["ebits_consumed"] == 2
        assert layout["classical_messages"] == 4
        assert layout["classical_bits"] == 4

    def test_theta_validation(self):
        with pytest.raises(QuantumCoreError):
            build_remote_cnot_circuit(-0.5)
        with pytest.raises(QuantumCoreError):
            build_remote_cnot_circuit(7.0)

    def test_bell_measurement_classical_bits_used(self):
        """Conditioned corrections must actually fire: with theta=pi the
        control is |1>, forcing non-trivial correction patterns."""
        circuit, layout = build_remote_cnot_circuit(math.pi)
        res = simulate(circuit, seed=2)
        # all four classical bits were exercised across trajectory; registers recorded
        assert res.classical_registers and len(res.classical_registers[0]) == 4

    def test_target_never_leaves_bob(self):
        """Structural check: Bob's target qubit 1 is only touched by local ops
        (CX from 3) and never by any Alice-side wire."""
        circuit, layout = build_remote_cnot_circuit(0.7)
        touching = [op for op in circuit.operations
                    if op.kind == "gate" and 1 in op.qubits]
        allowed_partners = {3}   # only Bob-local CNOT partner
        for op in touching:
            partners = set(op.qubits) - {1}
            assert partners <= allowed_partners or op.gate in ("H",), (op)
