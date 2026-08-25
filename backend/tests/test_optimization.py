"""Optimization and QML tests (directives §144-145, §308)."""
import math

import numpy as np
import pytest

from app.optimization import (
    Hamiltonian,
    h2_hamiltonian,
    transverse_field_ising,
    maxcut_cost,
    maxcut_brute_force,
    maxcut_hamiltonian,
    run_vqe,
    run_qaoa_maxcut,
    run_h2_experiment,
    two_local_h2_ansatz,
    evaluate_classifier,
    run_qml_experiment,
    run_kernel_experiment,
    load_csv_dataset,
)


class TestHamiltonians:
    def test_tfim_ground_state_known_limits(self):
        # Strong field: ground state ≈ all-spins-aligned-in-X, E ≈ -(n-1)*J - n*h
        n = 4
        big_field = transverse_field_ising(n, j_coupling=0.0, h_field=1.0)
        e_min = float(big_field.eigenvalues_exact()[0])
        assert e_min == pytest.approx(-n * 1.0, abs=1e-10)

        zero_field = transverse_field_ising(n, j_coupling=1.0, h_field=0.0)
        e_min2 = float(zero_field.eigenvalues_exact()[0])
        assert e_min2 == pytest.approx(-(n - 1) * 1.0, abs=1e-10)

    def test_hamiltonian_is_hermitian(self):
        h = transverse_field_ising(3)
        m = h.matrix()
        assert np.allclose(m, m.conj().T)

    def test_invalid_pauli_rejected(self):
        with pytest.raises(ValueError):
            Hamiltonian([("QB", 1.0)])


class TestMaxCut:
    def test_brute_force_triangle(self):
        edges = [(0, 1), (1, 2), (0, 2)]
        best_cut, _bits = maxcut_brute_force(3, edges)
        assert best_cut == 2

    def test_cost_function(self):
        edges = [(0, 1), (1, 2)]
        # Bitstrings print high qubit first (little-endian register value).
        assert maxcut_cost(edges, "100") == 1  # q0=0,q1=0,q2=1: only cut(1,2)
        assert maxcut_cost(edges, "110") == 1  # q0=0,q1=1,q2=1: only cut(0,1)
        assert maxcut_cost(edges, "010") == 2  # q0=0,q1=1,q2=0: both cuts cross
        assert maxcut_cost(edges, "000") == 0

    def test_square_optimum(self):
        edges = [(0, 1), (1, 2), (2, 3), (3, 0)]
        cut, _ = maxcut_brute_force(4, edges)
        assert cut == 4


class TestVQE:
    def test_vqe_converges_on_tfim(self):
        """§145: convergence against exact reference within tolerance."""
        h = transverse_field_ising(2, j_coupling=1.0, h_field=1.0)

        def ansatz(params):
            from app.circuits.model import Circuit

            c = Circuit(num_qubits=2)
            c.add_gate("RY", [0], params=[float(params[0])])
            c.add_gate("RY", [1], params=[float(params[1])])
            c.add_gate("CX", [0, 1])
            c.add_gate("RY", [0], params=[float(params[2])])
            return c

        res = run_vqe(h, ansatz, param_count=3, max_iter=200, seed=5)
        assert res.exact_energy is not None
        assert res.error < 0.05, f"VQE error {res.error}"
        assert len(res.energy_history) > 10

    def test_h2_energy_near_reference(self):
        """H2 at 0.735 A has known effective-model energy; VQE must approach it."""
        out = run_h2_experiment(0.735, seed=1)
        assert out.error_hartree < 0.05
        # Qualitative sanity: energy below -1 Hartree for the model.
        assert out.exact_energy_hartree < -1.0


class TestQAOA:
    def test_small_graph_beats_random_or_matches(self):
        """§144/§308: cost evaluation correct vs classical optimum."""
        edges = [(0, 1), (1, 2), (2, 3), (3, 0)]  # square, optimum 4
        res = run_qaoa_maxcut(edges, 4, p_layers=2, seed=7)
        assert res.exact_optimum == 4
        assert 0 < res.approximation_ratio <= 1.0 + 1e-9
        assert res.best_cut_value >= 2

    def test_two_node_trivial_graph(self):
        res = run_qaoa_maxcut([(0, 1)], 2, p_layers=1, seed=3)
        assert res.exact_optimum == 1
        assert res.best_cut_value == 1
        assert res.approximation_ratio == 1.0

    def test_bounds_enforced(self):
        with pytest.raises(ValueError):
            run_qaoa_maxcut([(0, 1)], 20, p_layers=1)
        with pytest.raises(ValueError):
            run_qaoa_maxcut([(0, 1)], 4, p_layers=9)


class TestMetricsAndData:
    def test_confusion_matrix_counts(self):
        preds = [1, 0, 1, 1, 0]
        truth = [1, 0, 0, 1, 1]
        m = evaluate_classifier(preds, truth)
        cm = m["confusion_matrix"]
        assert (cm["true_positive"], cm["true_negative"],
                cm["false_positive"], cm["false_negative"]) == (2, 1, 1, 1)
        assert m["accuracy"] == pytest.approx(0.6)

    def test_csv_validation_errors_are_actionable(self):
        with pytest.raises(ValueError, match="column count"):
            load_csv_dataset("a,b,label\n1,2,x\n3,4\n5,6,x\n")
        with pytest.raises(ValueError, match="Non-numeric"):
            load_csv_dataset("a,b,label\nx,2,a\n1,2,a\n1,2,b\n1,2,b\n")
        with pytest.raises(ValueError, match="exactly 2 label"):
            load_csv_dataset("a,b,l\n1,2,c1\n3,4,c2\n5,6,c3\n")

    def test_csv_valid_load(self):
        X, y, cols = load_csv_dataset("f1,f2,label\n1,2,a\n3,4,b\n2,1,a\n4,3,b\n")
        assert X.shape == (4, 2)
        assert set(y) == {0, 1}
        assert cols == ["f1", "f2"]


class TestQML:
    def test_blobs_ideal_accuracy_above_chance(self):
        out = run_qml_experiment("blobs", seed=2, max_iter=60, noise_label=None)
        assert out["ideal_metrics"]["accuracy"] >= 0.65

    def test_noisy_comparison_runs_and_reports(self):
        out = run_qml_experiment("blobs", seed=3, max_iter=40)
        assert "ideal_metrics" in out and "noisy_metrics" in out
        assert "noise_model" in out

    def test_kernel_experiment_runs(self):
        out = run_kernel_experiment("blobs", seed=4)
        assert out["train_accuracy"] >= 0.8
