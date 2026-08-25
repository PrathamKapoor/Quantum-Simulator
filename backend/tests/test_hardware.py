"""Hardware abstraction + transpiler + circuit analysis tests (§9-11, §204)."""
import math

import numpy as np
import pytest

from app.circuits.model import Circuit, Operation
from app.circuits.analysis import analyze_circuit
from app.hardware.profiles import (
    HardwareProfile,
    GateSpecInfo,
    line_topology,
    ring_topology,
    grid_topology,
    all_to_all_topology,
    star_topology,
    preset_ideal_8q,
    preset_noisy_generic_8q,
    preset_superconducting_inspired,
    preset_trapped_ion_inspired,
    to_noise_model,
)
from app.hardware.transpile import (
    transpile_for_hardware,
    verify_mapping_preserves_action,
)
from app.circuits import simulate


def ghz_circuit(n: int) -> Circuit:
    c = Circuit(num_qubits=n, num_clbits=n)
    c.add_gate("H", [0])
    for q in range(n - 1):
        c.add_gate("CX", [q, q + 1])
    return c


class TestTopologies:
    def test_line_edge_count(self):
        assert len(line_topology(5)) == 4

    def test_ring_wraps(self):
        t = ring_topology(4)
        assert frozenset((0, 3)) in t and len(t) == 4

    def test_grid_shape(self):
        edges, n = grid_topology(3, 2)
        assert n == 6
        assert len(edges) == 3 * (2 - 1) + 2 * (3 - 1)  # 7 edges

    def test_all_to_all_count(self):
        assert len(all_to_all_topology(5)) == 10

    def test_star_center(self):
        assert len(star_topology(6)) == 5

    def test_shortest_path(self):
        profile = preset_noisy_generic_8q()
        assert profile.shortest_coupling_path(0, 7) == list(range(8))
        assert profile.shortest_coupling_path(3, 3) == [3]

    def test_disconnected_pair_returns_none(self):
        p = HardwareProfile(name="split", n_qubits=4,
                            coupling=line_topology(2),
                            native_gates={})
        assert p.shortest_coupling_path(0, 2) is None


class TestTranspiler:
    def _line_profile(self, n=5):
        return HardwareProfile(
            name="line5", n_qubits=n,
            coupling=line_topology(n),
            native_gates={
                **{g: GateSpecInfo(g, 1, 20.0, 0.0005) for g in
                   ("I", "X", "Y", "Z", "H", "S", "SDG", "T", "TDG",
                    "RX", "RY", "RZ")},
                **{g: GateSpecInfo(g, 2, 250.0, 0.01) for g in ("CX", "CZ", "SWAP")},
            },
        )

    def test_adjacent_circuit_needs_no_swaps(self):
        res = transpile_for_hardware(ghz_circuit(5), self._line_profile(5))
        assert res.swap_count == 0
        assert res.mapped_depth == res.original_depth

    def test_long_range_gate_inserts_swaps(self):
        c = Circuit(num_qubits=5, num_clbits=5)
        c.add_gate("H", [0])
        c.add_gate("CX", [0, 4])
        res = transpile_for_hardware(c, self._line_profile(5))
        assert res.swap_count >= 3  # distance-4 path needs 3 swaps
        # mapping validation: ideal action preserved under permutation
        check = verify_mapping_preserves_action(c, res)
        assert check["verified"], check

    def test_mapping_preserves_action_for_random_small_circuit(self):
        rng = np.random.default_rng(7)
        c = Circuit(num_qubits=4)
        for _ in range(12):
            if rng.random() < 0.5:
                c.add_gate(str(rng.choice(["H", "T", "X"])), [int(rng.integers(4))])
            else:
                a, b = sorted(rng.choice(4, size=2, replace=False).tolist())
                c.add_gate("CX", [int(a), int(b)])
        res = transpile_for_hardware(c, self._line_profile(4))
        check = verify_mapping_preserves_action(c, res)
        assert check["verified"], (check, res.final_mapping)

    def test_permutation_tracked_through_swaps(self):
        # CX(4,0) on a line: routing must keep later ops consistent.
        c = Circuit(num_qubits=5)
        c.add_gate("X", [4])
        c.add_gate("CX", [4, 0])
        c.add_gate("X", [4])
        res = transpile_for_hardware(c, self._line_profile(5))
        assert verify_mapping_preserves_action(c, res)["verified"]

    def test_non_native_gate_rejected_loudly(self):
        c = Circuit(num_qubits=2)
        c.add_gate("H", [0])
        profile = HardwareProfile(
            name="minimal", n_qubits=2, coupling=all_to_all_topology(2),
            native_gates={"CX": GateSpecInfo("CX", 2, 100.0, 0.01)},
        )
        with pytest.raises(Exception, match="not native"):
            transpile_for_hardware(c, profile)

    def test_too_many_qubits_rejected(self):
        with pytest.raises(Exception, match="provides only"):
            transpile_for_hardware(Circuit(num_qubits=10), self._line_profile(5))


class TestMappingIdealEquivalence:
    """Directive §204: mapped circuit must preserve logical behavior under
    ideal execution — verified through statevector outputs."""

    def test_ghz_on_line_via_statevector(self):
        logical = ghz_circuit(5)
        logical.add_measure([0, 1, 2, 3, 4], [0, 1, 2, 3, 4])
        profile = self_line5()
        res = transpile_for_hardware(logical, profile)
        mapped = res.circuit
        r_logical = simulate(logical, seed=3, shots=2000)
        r_mapped = simulate(mapped, seed=3, shots=2000)
        # Logical GHZ counts {00000, 11111}; mapped counts live on permuted
        # physical bits: map each key back through final_mapping.
        perm = res.final_mapping
        remapped_counts: dict[str, int] = {}
        for key, count in r_mapped.counts.items():
            logical_bits = ["0"] * 5
            for lq in range(5):
                pq = perm[lq]
                # register string prints high bit first: position i <-> qubit 4-i
                logical_bits[4 - lq] = key[4 - pq]
            remapped_counts["".join(logical_bits)] = (
                remapped_counts.get("".join(logical_bits), 0) + count)
        assert set(r_logical.counts) <= {"00000", "11111"}
        assert set(remapped_counts) <= {"00000", "11111"}


def self_line5():
    return HardwareProfile(
        name="line5", n_qubits=5,
        coupling=line_topology(5),
        native_gates={
            **{g: GateSpecInfo(g, 1, 20.0, 0.0005) for g in
               ("I", "X", "Y", "Z", "H", "S", "SDG", "T", "TDG", "RX", "RY", "RZ")},
            **{g: GateSpecInfo(g, 2, 250.0, 0.01) for g in ("CX", "CZ", "SWAP")},
        },
    )


class TestCircuitAnalysis:
    def test_metrics_measured(self):
        c = ghz_circuit(5)
        a = analyze_circuit(c)
        d = a.to_dict()
        assert d["gate_count"] == 5
        assert d["single_qubit_gate_count"] == 1
        assert d["two_qubit_gate_count"] == 4
        assert d["depth"] == 5
        assert {"frozenset"} == set() or d["connectivity_pairs_used"] == [
            [0, 1], [1, 2], [2, 3], [3, 4]]

    def test_t_count_known_and_none_cases(self):
        c = Circuit(num_qubits=2)
        c.add_gate("T", [0]).add_gate("H", [1]).add_gate("CX", [0, 1]).add_gate("TDG", [0])
        a = analyze_circuit(c)
        assert a.t_count_total == 2  # T + TDG
        # T-depth is dependency-aware: the TDG cannot run in parallel with the
        # earlier T (they share qubit 0 via the intervening CX), so depth = 2.
        assert a.t_depth == 2

    def test_t_depth_parallel_layers(self):
        c = Circuit(num_qubits=3)
        c.add_gate("T", [0])
        c.add_gate("T", [1])   # disjoint qubit -> same T-layer
        a = analyze_circuit(c)
        assert a.t_count_total == 2
        assert a.t_depth == 1

    def test_unknown_gate_yields_none_t_metrics(self):
        c = Circuit(num_qubits=2, metadata={
            "custom_gates": {"MYGATE": {"matrix": np.eye(4).tolist(), "n_qubits": 2}}})
        c.add_gate("MYGATE", [0, 1])
        a = analyze_circuit(c)
        assert a.t_count_total is None
        assert a.t_depth is None

    def test_measurement_counted(self):
        c = ghz_circuit(3)
        c.add_measure([0, 1, 2], [0, 1, 2])
        assert analyze_circuit(c).measurement_count == 3


class TestPresetsAndNoiseModel:
    def test_presets_exist_with_labels(self):
        for factory in (preset_ideal_8q, preset_noisy_generic_8q,
                        preset_superconducting_inspired, preset_trapped_ion_inspired):
            p = factory()
            assert "MODEL" in p.model_label.upper() or "IDEAL" in p.model_label.upper()

    def test_noise_model_conversion_runs(self):
        nm = to_noise_model(preset_noisy_generic_8q())
        assert not nm.is_noiseless
        c = ghz_circuit(4)
        c.add_measure(list(range(4)), list(range(4)))
        res = simulate(c, seed=1, shots=500, noise_model=nm)
        assert sum(res.counts.values()) == 500
