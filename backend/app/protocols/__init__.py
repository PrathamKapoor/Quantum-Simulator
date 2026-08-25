"""Protocols package: communication, cryptography, information theory."""
from .communication import (
    run_bb84,
    BB84Result,
    run_e91,
    E91Result,
    run_qrng,
    run_chsh,
    shannon_entropy,
    mutual_information_from_joint,
    quantum_mutual_information,
    bell_state_metrics,
)

__all__ = [
    "run_bb84", "BB84Result",
    "run_e91", "E91Result",
    "run_qrng", "run_chsh",
    "shannon_entropy", "mutual_information_from_joint",
    "quantum_mutual_information", "bell_state_metrics",
]

from .network_bb84 import (
    run_network_bb84,
    NetworkBB84Result,
    run_bb84_distance_sweep,
    fiber_survival,
)

__all__ += [
    "run_network_bb84", "NetworkBB84Result", "run_bb84_distance_sweep", "fiber_survival",
]
