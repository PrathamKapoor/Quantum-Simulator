"""Algorithms package: builders and runners for the standard suite."""
from .qft import build_qft, dft_matrix
from .core_algorithms import (
    OracleSpec,
    build_deutsch_jozsa_circuit,
    run_deutsch,
    run_deutsch_jozsa,
    build_bernstein_vazirani,
    run_bernstein_vazirani,
    SimonProblem,
    make_simon_problem,
    run_simon,
    GroverResult,
    build_grover_circuit,
    run_grover,
    grover_optimal_iterations,
    build_superdense,
    run_superdense,
)
from .phase_estimation_shor import (
    build_phase_estimation_circuit,
    run_phase_estimation,
    PhaseEstimationResult,
    modular_multiplication_matrix,
    find_order_classical,
    run_order_finding,
    OrderFindingResult,
    factorize_bounded,
    discrete_quantum_walk,
)

__all__ = [
    "build_qft", "dft_matrix",
    "OracleSpec", "build_deutsch_jozsa_circuit", "run_deutsch", "run_deutsch_jozsa",
    "build_bernstein_vazirani", "run_bernstein_vazirani",
    "SimonProblem", "make_simon_problem", "run_simon",
    "GroverResult", "build_grover_circuit", "run_grover", "grover_optimal_iterations",
    "build_superdense", "run_superdense",
    "build_phase_estimation_circuit", "run_phase_estimation", "PhaseEstimationResult",
    "modular_multiplication_matrix", "find_order_classical", "run_order_finding",
    "OrderFindingResult", "factorize_bounded", "discrete_quantum_walk",
]
