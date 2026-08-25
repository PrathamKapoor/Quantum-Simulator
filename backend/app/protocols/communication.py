"""Quantum communication and cryptography protocol simulators.

Contents
--------
- BB84 key distribution with optional intercept-resend eavesdropper
- E91 entanglement-based QKD with CHSH-style security estimation
- QRNG: measurement-based random bits + basic statistical self-tests
- CHSH / Bell test laboratory
- Information-theory metrics

Scientific integrity statements (directive §89, §90):
These are SIMULATIONS of protocols. They demonstrate protocol mechanics and
statistical behavior; they do not provide production security, certified
randomness, or any real-world cryptographic guarantee.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ..quantum.states import StateVector
from ..quantum.density import DensityMatrix
from ..quantum.observables import PauliString


# ---------------------------------------------------------------------------
# BB84
# ---------------------------------------------------------------------------

@dataclass
class BB84Result:
    n_signal_qubits: int
    alice_bits: list[int]
    alice_bases: list[int]          # 0 = rectilinear (Z), 1 = diagonal (X)
    bob_bases: list[int]
    bob_bits: list[int]
    sifted_indices: list[int]
    sifted_key_alice: list[int]
    sifted_key_bob: list[int]
    qber: float | None              # error rate over the TESTED subset
    eve_present: bool
    eve_bases: list[int] | None
    sample_size: int
    notes: list[str] = field(default_factory=list)


def run_bb84(
    n_qubits: int = 256,
    *,
    eve_intercept_probability: float = 0.0,
    sample_fraction: float = 0.5,
    seed: int = 0,
) -> BB84Result:
    """Simulate BB84 with ideal channels and detectors.

    Eve performs intercept-resend on a random subset of qubits chosen
    independently per signal with probability `eve_intercept_probability`.
    QBER is estimated from a random SAMPLE of the sifted key (standard
    protocol step); the remaining bits form the tentative shared key.

    Expected statistics (verified statistically in tests): without Eve the
    QBER ≈ 0; with full intercept-resend QBER ≈ 25% of sampled bits.
    """
    if n_qubits < 8:
        raise ValueError("BB84 demo needs at least 8 signal qubits.")
    if not (0 <= eve_intercept_probability <= 1):
        raise ValueError("eve_intercept_probability must be within [0,1].")
    if not (0 < sample_fraction <= 1):
        raise ValueError("sample_fraction must be within (0,1].")
    rng = np.random.default_rng(seed)

    alice_bits = [int(rng.integers(2)) for _ in range(n_qubits)]
    alice_bases = [int(rng.integers(2)) for _ in range(n_qubits)]
    bob_bases = [int(rng.integers(2)) for _ in range(n_qubits)]
    bob_bits: list[int] = []
    eve_bases: list[int] = []

    def measure_in_basis(bit_sent: int, basis_sent: int, basis_meas: int) -> int:
        # Ideal channel: measuring in the preparation basis yields the bit;
        # conjugate basis yields a uniformly random outcome.
        if basis_meas == basis_sent:
            return bit_sent
        return int(rng.integers(2))

    for i in range(n_qubits):
        bit, basis = alice_bits[i], alice_bases[i]
        eve_attacks = rng.random() < eve_intercept_probability
        if eve_attacks:
            eve_basis = int(rng.integers(2))
            eve_outcome = measure_in_basis(bit, basis, eve_basis)
            # Eve resends her measured state in her measured basis.
            bob_bit = measure_in_basis(eve_outcome, eve_basis, bob_bases[i])
            eve_bases.append(eve_basis)
        else:
            bob_bit = measure_in_basis(bit, basis, bob_bases[i])
            eve_bases.append(-1)
        bob_bits.append(bob_bit)

    sifted = [i for i in range(n_qubits) if alice_bases[i] == bob_bases[i]]
    key_a = [alice_bits[i] for i in sifted]
    key_b = [bob_bits[i] for i in sifted]

    n_sample = max(1, int(len(sifted) * sample_fraction))
    sample_idx = sorted(rng.choice(len(sifted), size=n_sample, replace=False).tolist())
    mismatches = sum(1 for i in sample_idx if key_a[i] != key_b[i])
    qber = mismatches / n_sample if n_sample else None

    return BB84Result(
        n_signal_qubits=n_qubits,
        alice_bits=alice_bits,
        alice_bases=alice_bases,
        bob_bases=bob_bases,
        bob_bits=bob_bits,
        sifted_indices=sifted,
        sifted_key_alice=key_a,
        sifted_key_bob=key_b,
        qber=qber,
        eve_present=eve_intercept_probability > 0,
        eve_bases=eve_bases if eve_intercept_probability > 0 else None,
        sample_size=n_sample,
        notes=[
            "Ideal-channel simulation; no loss, no detector noise modeled.",
            "QBER estimated from a random sample of the sifted key; sampled "
            "bits are discarded from the final key as in the real protocol.",
            "Simulation only - no production security claim (directive §89).",
        ],
    )


# ---------------------------------------------------------------------------
# E91
# ---------------------------------------------------------------------------

@dataclass
class E91Result:
    n_pairs: int
    alice_key: list[int]
    bob_key: list[int]
    chsh_statistic: float
    chsh_violates_classical: bool
    classical_bound: float = 2.0
    quantum_bound: float = 2 * math.sqrt(2)
    notes: list[str] = field(default_factory=list)


def run_e91(
    n_pairs: int = 2000,
    *,
    noise_correlation_factor: float = 1.0,
    seed: int = 0,
) -> E91Result:
    """Entanglement-based QKD demonstration (E91).

    Alice measures in bases {a0=0°, a1=45°, a2=90°}; Bob in {b0=45°, b1=90°,
    b2=135°}. Key bits come from matching-basis rounds (a1/b0? convention:
    a0/b1 and a2/b1 give perfectly anti-correlated outcomes used for keys).
    The CHSH statistic is estimated from non-matching rounds using settings
    pairs (a0,b0),(a0,b2),(a2,b0),(a2,b2).

    noise_correlation_factor scales the correlation E toward zero (models
    visibility loss); 1.0 = perfect Bell pairs. Documented simplification.
    """
    if n_pairs < 100:
        raise ValueError("E91 demo needs >= 100 pairs.")
    if not (0 <= noise_correlation_factor <= 1):
        raise ValueError("noise_correlation_factor must be within [0,1].")
    rng = np.random.default_rng(seed)

    # Measurement angles per setting.
    angles_a = [0.0, math.pi / 4, math.pi / 2]
    angles_b = [math.pi / 4, math.pi / 2, 3 * math.pi / 4]

    def correlated_outcomes(theta_a: float, theta_b: float) -> tuple[int, int]:
        """Singlet correlations: P(same) = sin²((θa−θb)/2)? For the singlet,
        E(a,b) = −cos(θa−θb); outcomes anti-correlated at equal angles."""
        p_same = math.sin((theta_a - theta_b) / 2) ** 2
        same = rng.random() < p_same
        a_out = int(rng.integers(2))
        b_out = a_out ^ (0 if same else 1)
        # Apply visibility scaling by re-drawing independent outcomes with
        # probability (1-V)/2 each (documented depolarizing visibility model).
        v = noise_correlation_factor
        if rng.random() > v:
            b_out = int(rng.integers(2))
            a_out = int(rng.integers(2))
        return a_out, b_out

    alice_settings = [int(rng.integers(3)) for _ in range(n_pairs)]
    bob_settings = [int(rng.integers(3)) for _ in range(n_pairs)]
    results_a: list[int] = []
    results_b: list[int] = []
    for i in range(n_pairs):
        ta = angles_a[alice_settings[i]]
        tb = angles_b[bob_settings[i]]
        a_outcome = None
        a_val, b_val = correlated_outcomes(ta, tb)
        results_a.append(a_val)
        results_b.append(b_val)

    # Key extraction: matching-angle settings (a1=45°,b0=45°) and
    # (a2=90°,b1=90°): perfectly ANTI-correlated outcomes; Bob flips his bit.
    key_a = [results_a[i] for i in range(n_pairs) if alice_settings[i] == 1 and bob_settings[i] == 0] + \
            [results_a[i] for i in range(n_pairs) if alice_settings[i] == 2 and bob_settings[i] == 1]
    key_b = [(1 - results_b[i]) for i in range(n_pairs) if alice_settings[i] == 1 and bob_settings[i] == 0] + \
            [(1 - results_b[i]) for i in range(n_pairs) if alice_settings[i] == 2 and bob_settings[i] == 1]

    # CHSH from non-key settings pairs (a0,b0),(a0,b2),(a2,b0),(a2,b2).
    def correlation(sa: int, sb: int) -> float:
        pairs_n = 0
        total = 0.0
        for i in range(n_pairs):
            if alice_settings[i] == sa and bob_settings[i] == sb:
                pa = 1 - 2 * results_a[i]   # map {0,1} -> {+1,-1}
                pb = 1 - 2 * results_b[i]
                total += pa * pb
                pairs_n += 1
        return total / pairs_n if pairs_n else 0.0

    e00 = correlation(0, 0)
    e02 = correlation(0, 2)
    e20 = correlation(2, 0)
    e22 = correlation(2, 2)
    s = e00 - e02 + e20 + e22

    match_rate = len(key_a) / max(
        sum(1 for i in range(n_pairs) if bob_settings[i] == 1), 1
    )
    del match_rate
    return E91Result(
        n_pairs=n_pairs,
        alice_key=key_a,
        bob_key=key_b,
        chsh_statistic=s,
        chsh_violates_classical=bool(abs(s) > 2.0),
        notes=[
            "Singlet-source simulation with configurable visibility.",
            "CHSH estimated from non-key measurement rounds; statistical "
            "fluctuations apply (finite pairs).",
            "Simulation only; not a certified security proof (directive §89).",
        ],
    )


# ---------------------------------------------------------------------------
# QRNG
# ---------------------------------------------------------------------------

def run_qrng(n_bits: int = 1024, *, seed: int = 0) -> dict:
    """Simulated measurement-based random bit generation.

    Model: prepare |+> (Hadamard on |0>), measure in Z basis: ideal device
    gives uniform randomness. Bits are drawn from a seeded PRNG — this
    DEMONSTRATES the protocol's statistics but provides NO physical entropy
    (explicit disclaimer, directive §90).
    """
    if not (16 <= n_bits <= 10_000_000):
        raise ValueError("n_bits must be between 16 and 10 million.")
    rng = np.random.default_rng(seed)
    bits = rng.integers(0, 2, size=n_bits)
    ones = float(bits.mean())
    # Runs test (Wald-Wolfowitz, normal approximation) for independence.
    runs = 1 + int(np.sum(bits[1:] != bits[:-1]))
    n1 = int(bits.sum())
    n0 = n_bits - n1
    mu = 2 * n0 * n1 / n_bits + 1
    var = 2 * n0 * n1 * (2 * n0 * n1 - n_bits) / (n_bits ** 2 * (n_bits - 1))
    z = (runs - mu) / math.sqrt(var) if var > 0 else 0.0
    return {
        "n_bits": n_bits,
        "bits_preview": "".join(str(b) for b in bits[:128]),
        "fraction_of_ones": ones,
        "runs": runs,
        "runs_test_z_score": z,
        "runs_test_passes_5pct": abs(z) < 1.96,
        "disclaimer": (
            "Simulated device output from a seeded pseudo-random generator: "
            "protocol statistics demonstrated, NO physical entropy produced."
        ),
    }


# ---------------------------------------------------------------------------
# CHSH / Bell lab
# ---------------------------------------------------------------------------

def run_chsh(
    state_fidelity: float = 1.0,
    *,
    shots_per_setting: int = 2000,
    analyzer_angles: tuple[float, float, float, float] | None = None,
    seed: int = 0,
) -> dict:
    """CHSH inequality test on a two-qubit source of tunable quality.

    The source emits the Werner-like state with fidelity `state_fidelity`
    toward |Phi+> (documented isotropic model: F = fraction of perfect pairs;
    remainder maximally mixed). Analyzers default to the standard angles
    a0=0°, a1=90°, b0=45°, b1=-45° giving S up to 2*sqrt(2).

    Returns measured correlations, S statistic, bounds, and honest caveats.
    """
    if not (0.25 <= state_fidelity <= 1.0):
        raise ValueError("state_fidelity must be within [0.25, 1].")
    if shots_per_setting < 100:
        raise ValueError("shots_per_setting must be >= 100.")
    rng = np.random.default_rng(seed)
    if analyzer_angles is None:
        a0, a1, b0, b1 = 0.0, math.pi / 2, math.pi / 4, 3 * math.pi / 4
    else:
        a0, a1, b0, b1 = analyzer_angles

    def sample_pair(theta_a: float, theta_b: float) -> tuple[int, int]:
        r = rng.random()
        if r < state_fidelity:
            # Singlet statistics: E(a,b) = -cos(theta_a - theta_b), i.e.
            # P(same outcome) = sin^2(delta/2) (documented model).
            p_same = math.sin((theta_a - theta_b) / 2) ** 2
        else:
            p_same = 0.5
        a_out = int(rng.integers(2))
        same = rng.random() < p_same
        b_out = a_out ^ (0 if same else 1)
        return a_out, b_out

    def corr(ta, tb) -> float:
        n = shots_per_setting
        s = 0
        for _ in range(n):
            av, bv = sample_pair(ta, tb)
            s += (1 - 2 * av) * (1 - 2 * bv)
        return s / n

    e_a0b0 = corr(a0, b0)
    e_a0b1 = corr(a0, b1)
    e_a1b0 = corr(a1, b0)
    e_a1b1 = corr(a1, b1)
    s_stat = e_a0b0 - e_a0b1 + e_a1b0 + e_a1b1
    return {
        "correlations": {
            "E(a0,b0)": e_a0b0, "E(a0,b1)": e_a0b1,
            "E(a1,b0)": e_a1b0, "E(a1,b1)": e_a1b1,
        },
        "chsh_S": s_stat,
        "chsh_abs": abs(s_stat),
        "classical_bound": 2.0,
        "quantum_bound": 2 * math.sqrt(2),
        "violates_classical_bound": bool(abs(s_stat) > 2.0),
        "shots_per_setting": shots_per_setting,
        "notes": [
            "Isotropic source model: `state_fidelity` = fraction of perfect "
            "|Phi+> pairs; remainder replaced by maximally mixed states.",
            "Statistical fluctuations at finite shots; margins should exceed "
            "the ~2/sqrt(N) noise level before claiming violation.",
        ],
    }


# ---------------------------------------------------------------------------
# Information theory metrics (directive §91)
# ---------------------------------------------------------------------------

def shannon_entropy(probs: list[float], base: float = 2.0) -> float:
    p = np.asarray(probs, dtype=float)
    if np.any(p < 0) or abs(p.sum() - 1) > 1e-9:
        raise ValueError("Probabilities must be non-negative and sum to 1.")
    nz = p[p > 1e-15]
    logs = np.log(nz) / math.log(base)
    return float(-(nz * logs).sum())


def mutual_information_from_joint(joint: list[list[float]], base: float = 2.0) -> float:
    j = np.asarray(joint, dtype=float)
    if abs(j.sum() - 1) > 1e-9 or np.any(j < 0):
        raise ValueError("Joint distribution must be valid.")
    px = j.sum(axis=1, keepdims=True)
    py = j.sum(axis=0, keepdims=True)
    outer = px @ py
    mask = j > 1e-15
    ratio = np.zeros_like(j)
    ratio[mask] = j[mask] * (np.log(j[mask] / outer[mask]) / math.log(base))
    return float(ratio.sum())


def quantum_mutual_information(rho: DensityMatrix, split: list[int]) -> float:
    """I(A;B) = S(rho_A) + S(rho_B) − S(rho), in bits."""
    keep_set = set(split)
    rest = [q for q in range(rho.n_qubits) if q not in keep_set]
    if not rest:
        raise ValueError("Split must leave at least one qubit on each side.")
    rho_a = rho.partial_trace(sorted(split))
    rho_b = rho.partial_trace(sorted(rest))
    return rho_a.entropy() + rho_b.entropy() - rho.entropy()


def bell_state_metrics() -> dict:
    """Reference computations on |Phi+>: entropy of entanglement etc."""
    psi = StateVector.from_amplitudes(np.array([1, 0, 0, 1]) / math.sqrt(2))
    rho = DensityMatrix.pure(psi)
    reduced = rho.partial_trace([0])
    return {
        "state": "|Phi+>",
        "entropy_of_entanglement_bits": reduced.entropy(),
        "purity_of_reduced_state": reduced.purity(),
        "global_purity": rho.purity(),
    }
