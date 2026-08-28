"""QEC subsystem package."""
from .codes import (
    QECode,
    BIT_FLIP_3,
    PHASE_FLIP_3,
    SHOR_9,
    STEANE_7,
    FIVE_QUBIT,
    CODE_REGISTRY,
    get_code,
    build_recovery_table,
)
from .pipeline import (
    benchmark_point,
    sweep_physical_error_rate,
    wilson_interval,
    encode_bit_flip_3,
    syndrome_extraction_circuit_bit_flip_3,
)
from .surface_code import (
    ToricCodeLayout,
    simulate_surface_code,
    verify_toric_code,
)
from .matching import (
    min_weight_perfect_matching,
    brute_force_min_weight_perfect_matching,
    MatchingError,
)
from .rotated_surface_code import (
    RotatedSurfaceCode,
    RotatedSurfaceCodeDecoder,
    RotatedSurfaceCodeResult,
    RotatedSurfaceCodeSimResult,
    DetectionEvent,
    ChainMatch,
    StabilizerCheck,
    error_from_string,
    simulate_rotated_surface_code,
    sweep_rotated_surface_code,
)

__all__ = [
    "QECode", "BIT_FLIP_3", "PHASE_FLIP_3", "SHOR_9", "STEANE_7", "FIVE_QUBIT",
    "CODE_REGISTRY", "get_code", "build_recovery_table",
    "benchmark_point", "sweep_physical_error_rate", "wilson_interval",
    "encode_bit_flip_3", "syndrome_extraction_circuit_bit_flip_3",
    "ToricCodeLayout", "simulate_surface_code", "verify_toric_code",
    "min_weight_perfect_matching", "brute_force_min_weight_perfect_matching",
    "MatchingError",
    "RotatedSurfaceCode", "RotatedSurfaceCodeDecoder",
    "RotatedSurfaceCodeResult", "RotatedSurfaceCodeSimResult",
    "DetectionEvent", "ChainMatch", "StabilizerCheck",
    "error_from_string", "simulate_rotated_surface_code",
    "sweep_rotated_surface_code",
]
