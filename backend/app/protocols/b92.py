"""B92 protocol (McMahon chapter 11): nonorthogonal-state QKD.

Alice sends |0> (bit 0) or |+> (bit 1), chosen uniformly at random.
Bob chooses a measurement basis at random: the H-basis (Z-measurement)
concludes bit 1 iff he measures |+> (outcome "+"), and the
diagonal basis (X-measurement) concludes bit 0 iff he measures |->.
An inconclusive result (Bob's Z-basis gives "0" for Alice's |0>, or
X-basis gives "+" for Alice's |+>) is discarded — this is the
protocol's signature inefficiency (~75% sifting loss ideal).

An eavesdropper (intercept-resend on the Z/X bases) collapses the
nonorthogonal states and produces errors in Bob's conclusive
detections; the QBER on the sifted key certifies the disturbance.

Exactness (directive §79): state preparation and detection
probabilities are exact Born-rule calculations per shot; the key
statistics are Monte Carlo over `shots` (seeded, reproducible).
"""
from __future__ import annotations

import numpy as np

from ..quantum.states import QuantumCoreError


def run_b92(shots: int = 4096, eve_intercept_prob: float = 0.0,
            channel_error: float = 0.0, *, seed: int = 0) -> dict:
    """Simulate one B92 run.

    Args mirror BB84's conventions: `shots` = number of Alice
    transmissions; `eve_intercept_prob` = per-qubit probability that
    Eve performs her Z/X measurement and resends the measured state;
    `channel_error` = symmetric bit/phase-flip probability on the way
    to Bob. Returns sifted-key length, error counts, QBER, and the
    inconclusive rate.
    """
    if shots <= 0:
        raise QuantumCoreError("shots must be positive.")
    if not (0.0 <= eve_intercept_prob <= 1.0):
        raise QuantumCoreError("eve_intercept_prob must be within [0, 1].")
    if not (0.0 <= channel_error <= 1.0):
        raise QuantumCoreError("channel_error must be within [0, 1].")
    rng = np.random.default_rng(seed)

    def apply_error(bit: int) -> int:
        return bit ^ (1 if rng.random() < channel_error else 0)

    sent_bits = []
    bob_bits = []
    conclusive = 0
    errors = 0
    inconclusive = 0
    eve_count = 0
    for _ in range(shots):
        bit = int(rng.integers(0, 2))          # 0 -> |0>, 1 -> |+>
        sent_bits.append(bit)
        state_z = bit                          # |0> has Z-outcome 0; |+> is
                                               # 50/50 in Z but Bob never uses
                                               # the mismatched basis
        eve_measure = rng.random() < eve_intercept_prob
        bob_basis_z = rng.random() < 0.5       # True: H-basis (Z-measurement)

        if eve_measure:
            eve_count += 1
            # Eve measures in Z or X uniformly; resends the inferred state.
            eve_basis_z = rng.random() < 0.5
            if eve_basis_z:
                # |0> -> outcome 0 surely; |+> -> 50/50, resends |0> or |1>
                outcome0 = True if bit == 0 else (rng.random() < 0.5)
                resent = 0 if outcome0 else 1  # 0 -> |0>, 1 -> |1> (Z-eigen)
            else:
                # X-measurement: |+> -> "+" surely; |0> -> 50/50
                outcome_plus = True if bit == 1 else (rng.random() < 0.5)
                resent = 1 if outcome_plus else 0  # 1 -> |+>, 0 -> |->
                # Bob's conclusive rule expects |0>/<+>; |->
                # ( resent==0 with Eve's X basis) is |->, not |0>
                if not outcome_plus:
                    resent = 2                          # marker: |-> state
            state = resent
        else:
            state = bit                                  # 0 -> |0>, 1 -> |+>

        # Bob's detection (Born rule realized per shot).
        detected = None
        if bob_basis_z:
            if state == 0:
                detected = None                          # |0> in H-basis: "-",
                                                         # inconclusive surely
            elif state == 1:
                # |+> in H-basis: +/- 50/50; "+" concludes bit 1
                detected = 1 if rng.random() < 0.5 else None
            else:                                        # Eve's |-> in H-basis
                detected = None                          # "-"/"+" 50/50
                if rng.random() < 0.5:
                    detected = 1
        else:
            if state == 1:
                detected = None                          # |+> in X-basis: "+"
            elif state == 0:
                if rng.random() < 0.5:
                    detected = 0                         # |0> in X-basis: "-"
                                                         # half the time
            else:                                        # Eve's |-> in X-basis
                detected = 0                             # "-" surely
        if detected is None:
            inconclusive += 1
            continue

        # Channel noise flips the decoded classical bit.
        final = apply_error(detected)
        conclusive += 1
        bob_bits.append(final)
        if final != bit:
            errors += 1

    qber = errors / conclusive if conclusive else 0.0
    ideal_qber = 0.0 if eve_intercept_prob == 0 else None
    return {
        "shots": shots,
        "eve_intercept_prob": eve_intercept_prob,
        "channel_error": channel_error,
        "conclusive": conclusive,
        "inconclusive": inconclusive,
        "sifted_key_length": conclusive,
        "sifting_rate": conclusive / shots,
        "errors": errors,
        "qber": qber,
        "ideal_sifting_rate": 0.25,          # documented protocol property
        "ideal_qber": ideal_qber,
        "eve_interceptions": eve_count,
        "note": ("B92 with |0>/|+> states, random Z/X basis choice at Bob, "
                 "intercept-resend Eve, symmetric channel noise. QBER on "
                 "the sifted key is the security statistic (Monte Carlo, "
                 "seeded)."),
    }
