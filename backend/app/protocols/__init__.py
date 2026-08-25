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
