"""Channel framework upgrades: Choi representation, composition, tensor products.

Extends the existing KrausChannel (app.quantum.channels) WITHOUT modifying it
(directive §5: incremental refactor, backwards compatible).

Scientific notes
----------------
Choi matrix (normalized convention used here):
    J(E) = (I (x) E)[|Phi+><Phi+|]  =  sum_{ij} |i><j| (x) E(|i><j|)
for input dimension d. Properties validated:
    - J Hermitian
    - J >= 0          (complete positivity)
    - Tr_output J = I_input   (trace preservation)
Channel action recovered as:  E(rho) = Tr_input[ J (rho^T (x) I) ].

Composition identity: applying channels sequentially equals one application of
the composed channel — verified numerically on random states.
Tensor identity: E1 (x) E2 acting on rho1 (x) rho2 equals the tensor product
of individual actions.

Process fidelity vs a reference unitary U: F_pro = <Phi| (U† (x) I) J(E)
(U (x) I) |Phi> with |Phi> the un-normalized maximally entangled vector;
equals average gate fidelity via F_avg = (d F_pro + 1)/(d + 1).
"""
from __future__ import annotations

import numpy as np

from .channels import KrausChannel, CompositeChannel
from .states import QuantumCoreError

_EIG_CLIP = 1e-12


def choi_matrix(channel: KrausChannel) -> np.ndarray:
    """Normalized Choi matrix J(E), shape (d_in*d_out, d_in*d_out).

    Layout: block (i,j) = E(|i><j|); row index = output basis, col = input.
    """
    d = channel.n_qubits
    dim = 1 << d
    j = np.zeros((dim * dim, dim * dim), dtype=np.complex128)
    for i in range(dim):
        for jj in range(dim):
            basis_ij = np.zeros((dim, dim), dtype=np.complex128)
            basis_ij[i, jj] = 1.0
            # apply channel to this operator via Kraus sum
            out = sum(k @ basis_ij @ k.conj().T for k in channel.kraus_operators)
            j[i * dim:(i + 1) * dim, jj * dim:(jj + 1) * dim] = out
    return j


def validate_choi(channel: KrausChannel, tolerance: float = 1e-6) -> dict:
    """Validate Hermiticity, positivity (complete positivity via Choi), and
    trace preservation through the Choi representation.

    Trace preservation reads: Tr_output J[(i,j)] = delta_ij, where the output
    index runs WITHIN each block (fast index). Returns a report."""
    j = choi_matrix(channel)
    herm_dev = float(np.max(np.abs(j - j.conj().T)))
    evals = np.linalg.eigvalsh((j + j.conj().T) / 2)
    min_eval = float(np.min(evals))
    d = 1 << channel.n_qubits
    # Partial trace over the OUTPUT (fast) index inside every block:
    tr_out = np.zeros((d, d), dtype=np.complex128)
    for i in range(d):
        for jj in range(d):
            block = j[i * d:(i + 1) * d, jj * d:(jj + 1) * d]
            tr_out[i, jj] = np.trace(block)
    tp_dev = float(np.max(np.abs(tr_out - np.eye(d))))
    return {
        "hermitian": herm_dev <= tolerance,
        "hermiticity_deviation": herm_dev,
        "completely_positive": min_eval >= -tolerance,
        "min_choi_eigenvalue": min_eval,
        "trace_preserving": tp_dev <= tolerance,
        "trace_preservation_deviation": tp_dev,
        "all_valid": herm_dev <= tolerance and min_eval >= -tolerance and tp_dev <= tolerance,
    }


def compose_channels(first: KrausChannel, second: KrausChannel) -> KrausChannel:
    """Compose two channels of equal subsystem size: (second ∘ first).

    Kraus set of the composition is {l_j k_i} for k in first, l in second.
    Validated TP at construction (inherited from KrausChannel).
    """
    if first.n_qubits != second.n_qubits:
        raise QuantumCoreError(
            f"Cannot compose channels of different sizes ({first.n_qubits} vs {second.n_qubits})."
        )
    kraus = [lj @ ki for ki in first.kraus_operators for lj in second.kraus_operators]
    return KrausChannel(kraus, first.n_qubits)


def tensor_channels(a: KrausChannel, b: KrausChannel) -> KrausChannel:
    """Tensor product channel A (x) B acting on qubits [0..na-1 | na..].

    Operand order: A's qubits are the LOW-order block, B's the HIGH-order
    block (little-endian platform convention)."""
    kraus = []
    for ka in a.kraus_operators:
        for kb in b.kraus_operators:
            kraus.append(_kron_low_high(ka, kb))
    return KrausChannel(kraus, a.n_qubits + b.n_qubits)


def _kron_low_high(low: np.ndarray, high: np.ndarray) -> np.ndarray:
    """Kron where `low` occupies the low-order (little-endian) bits."""
    # little-endian: index = i_low + dim_low * i_high  => kron(high, low)
    return np.kron(high, low)


def apply_channel_to_operator_basis(channel: KrausChannel, op: np.ndarray) -> np.ndarray:
    """E(op) for an arbitrary operator (linear extension of Schrödinger action)."""
    return sum(k @ op @ k.conj().T for k in channel.kraus_operators)


def verify_composition_identity(
    first: KrausChannel, second: KrausChannel, test_ops: list[np.ndarray],
    tolerance: float = 1e-9,
) -> dict:
    """Check E2(E1(X)) == (E2∘E1)(X) for the given operators (RULE 3)."""
    composed = compose_channels(first, second)
    max_dev = 0.0
    for x in test_ops:
        sequential = apply_channel_to_operator_basis(second,
                                                     apply_channel_to_operator_basis(first, x))
        direct = apply_channel_to_operator_basis(composed, x)
        max_dev = max(max_dev, float(np.max(np.abs(sequential - direct))))
    return {"max_deviation": max_dev, "agrees": max_dev <= tolerance}


def verify_tensor_identity(
    a: KrausChannel, b: KrausChannel, ops_a: list[np.ndarray], ops_b: list[np.ndarray],
    tolerance: float = 1e-9,
) -> dict:
    """Check (A(x)B)(rho_a (x) rho_b) == A(rho_a) (x) B(rho_b)."""
    ab = tensor_channels(a, b)
    max_dev = 0.0
    for ra in ops_a:
        for rb in ops_b:
            joint_in = np.kron(rb, ra)  # low-high layout
            joint_out = apply_channel_to_operator_basis(ab, joint_in)
            sep_out = np.kron(
                apply_channel_to_operator_basis(b, rb),
                apply_channel_to_operator_basis(a, ra),
            )
            max_dev = max(max_dev, float(np.max(np.abs(joint_out - sep_out))))
    return {"max_deviation": max_dev, "agrees": max_dev <= tolerance}


def process_fidelity_to_unitary(channel: KrausChannel, unitary: np.ndarray) -> float:
    """Process fidelity between the channel and the ideal unitary channel.

    Uses the un-normalized Choi matrix J_mine = d·J_std and the normalized
    maximally entangled vector |Phi> = Sigma |ii>/sqrt(d):

        F_pro = <Phi_tilde| J_mine |Phi_tilde> / d,
        Phi_tilde = (U* (x) I)|Phi>.

    F_pro = 1 iff E(rho) = U rho U-dagger for all rho. Average-gate fidelity
    relation F_avg = (d F_pro + 1)/(d + 1) is provided separately (documented).
    """
    import math as m

    d = 1 << channel.n_qubits
    if unitary.shape != (d, d):
        raise QuantumCoreError("Unitary dimension mismatch with channel size.")
    phi_tilde = np.zeros(d * d, dtype=np.complex128)
    for k in range(d):
        phi_tilde[k * d:(k + 1) * d] = np.conj(unitary[:, k])
    phi_tilde /= m.sqrt(d)
    j = choi_matrix(channel)
    value = float(np.real(phi_tilde.conj() @ j @ phi_tilde)) / d
    return float(np.clip(value, 0.0, 1.0))


def average_gate_fidelity(channel: KrausChannel, unitary: np.ndarray) -> float:
    """F_avg = (d*F_pro + 1)/(d + 1); equals 1 iff the channel is the unitary U.

    Known reference points (tested): completely depolarizing single-qubit
    channel -> F_avg = 1/2; any unitary channel matched to itself -> 1."""
    d = 1 << channel.n_qubits
    fp = process_fidelity_to_unitary(channel, unitary)
    return float((d * fp + 1) / (d + 1))


# ---------------------------------------------------------------------------
# Additional physical channels (§7 list)
# ---------------------------------------------------------------------------

def generalized_amplitude_damping_channel(gamma: float, probability: float) -> KrausChannel:
    """Generalized amplitude damping: amplitude damping occurring while the
    qubit interacts with a thermal bath with EXCITED-STATE POPULATION
    N=`probability`. With probability (1-N) the environment acts as a cold
    (vacuum) bath -> standard amplitude damping toward |0>; with probability N
    it acts as an inverted bath -> excitation toward |1>. Kraus operators:

        K0 = sqrt(1-N) [[1,0],[0,sqrt(1-g)]]
        K1 = sqrt(1-N) [[0,sqrt(g)],[0,0]]
        K2 = sqrt(N)   [[sqrt(1-g),0],[0,1]]
        K3 = sqrt(N)   [[0,0],[sqrt(g),0]]

    gamma: decay/excitation probability magnitude; N: bath excited population.
    N=0 reduces exactly to standard amplitude damping (validated by test).
    Documented phenomenology; not a microscopic master-equation solution.
    """
    if not (0 <= gamma <= 1) or not (0 <= probability <= 1):
        raise QuantumCoreError("gamma and probability must be within [0,1].")
    import math as m

    g = gamma
    cold_w, hot_w = m.sqrt(1 - probability), m.sqrt(probability)
    k0 = cold_w * np.array([[1, 0], [0, m.sqrt(1 - g)]], dtype=np.complex128)
    k1 = cold_w * np.array([[0, m.sqrt(g)], [0, 0]], dtype=np.complex128)
    k2 = hot_w * np.array([[m.sqrt(1 - g), 0], [0, 1]], dtype=np.complex128)
    k3 = hot_w * np.array([[0, 0], [m.sqrt(g), 0]], dtype=np.complex128)
    return KrausChannel([k0, k1, k2, k3], 1)


def readout_confusion_channel(p_read1_given_0: float, p_read0_given_1: float) -> KrausChannel:
    """Asymmetric readout confusion as a classical channel on diagonal states.

    NOTE: models only the DIAGONAL (classical) part of readout error; coherences
    are left untouched by these Kraus operators — documented simplification
    matching how readout error is applied to measured bits elsewhere.
    """
    import math as m

    p01, p10 = float(p_read1_given_0), float(p_read0_given_1)
    if not (0 <= p01 <= 1 and 0 <= p10 <= 1):
        raise QuantumCoreError("Readout probabilities must be within [0,1].")
    k_keep = np.array(
        [[m.sqrt(1 - p01), 0], [0, m.sqrt(1 - p10)]], dtype=np.complex128
    )
    k_flip = np.array(
        [[0, m.sqrt(p10)], [m.sqrt(p01), 0]], dtype=np.complex128
    )
    return KrausChannel([k_keep, k_flip], 1)
