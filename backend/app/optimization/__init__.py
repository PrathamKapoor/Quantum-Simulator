"""Optimization lab package: Hamiltonians, VQE, QAOA, H2, QML."""
from .hamiltonians import (
    Hamiltonian,
    h2_hamiltonian,
    transverse_field_ising,
    maxcut_cost,
    maxcut_brute_force,
    maxcut_hamiltonian,
)
from .variational import (
    run_vqe,
    VQEResult,
    run_qaoa_maxcut,
    QAOAResult,
    qaoa_circuit,
    run_h2_experiment,
    H2Result,
    h2_dissociation_curve,
    optimize_spsa,
    optimize_coordinate_descent,
    hardware_efficient_ansatz,
    two_local_h2_ansatz,
)
from .qml import (
    make_blobs_binary,
    make_circles,
    load_iris_subset,
    load_csv_dataset,
    evaluate_classifier,
    run_qml_experiment,
    run_kernel_experiment,
    quantum_kernel_entry,
)

__all__ = [
    "Hamiltonian", "h2_hamiltonian", "transverse_field_ising",
    "maxcut_cost", "maxcut_brute_force", "maxcut_hamiltonian",
    "run_vqe", "VQEResult", "run_qaoa_maxcut", "QAOAResult", "qaoa_circuit",
    "run_h2_experiment", "H2Result", "h2_dissociation_curve",
    "optimize_spsa", "optimize_coordinate_descent",
    "hardware_efficient_ansatz", "two_local_h2_ansatz",
    "make_blobs_binary", "make_circles", "load_iris_subset", "load_csv_dataset",
    "evaluate_classifier", "run_qml_experiment", "run_kernel_experiment",
    "quantum_kernel_entry",
]
