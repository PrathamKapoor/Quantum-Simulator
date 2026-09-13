"""Stabilizer-measurement circuit templates for the rotated planar
surface code (milestone 13, Track A).

A circuit template specifies the exact gate sequence the simulator
runs for one stabilizer-measurement round: ancilla reset, ancilla
preparation, the sequence of CNOTs, ancilla measurement.

Currently implemented:

  BASELINE_H_CNOT_H  — the production model (preserved bit-for-bit
    for backwards compatibility). Z-check: ancilla |0>, CNOT(data->anc)
    for each data qubit, measure ancilla Z. X-check: ancilla |0>,
    H (->|+>), CNOT(anc->data) for each data qubit, H (back to Z
    basis), measure ancilla Z.

INVESTIGATED but REJECTED in the milestone 13 Track A process:

  DOUBLED_CNOT (Fowler 2012 §IV.B-inspired, the "hook-error safe"
  2-CNOT-per-data-qubit construction) — see note below.

Track A honest negative finding: the simple doubled-CNOT construction
(data->anc, anc->data) on the same data qubit does NOT preserve the
stabilizer measurement in the Pauli-frame formalism used by the
production simulator. The anc->data CNOT copies the ancilla's
accumulated Z value back to every data qubit in the support,
producing a multi-data syndrome for a single-qubit data error.
Investigation of a faithful 2-CNOT hook-error-safe construction
(flag-based, post-selection, or full Shor cat-state) is recorded
in SCIENTIFIC_MODELS as future work; implementing those would
require additional ancilla qubits and/or post-selection logic
beyond the current architecture.

Direction: BASELINE_H_CNOT_H is preserved. Future work (post-milestone
13) would extend the architecture to support flag-based or
cat-state extraction.
"""
from __future__ import annotations

from dataclasses import dataclass


EXTRACTION_BASELINE = "baseline_h_cnot_h"
EXTRACTION_SHOR = "shor_cat_state"
EXTRACTION_SHOR_VERIFIED = "shor_cat_state_verified"
EXTRACTION_FITTED = "fitted_pair"
SUPPORTED_EXTRACTIONS = (EXTRACTION_BASELINE, EXTRACTION_SHOR,
                         EXTRACTION_SHOR_VERIFIED, EXTRACTION_FITTED)


@dataclass(frozen=True)
class ExtractionModel:
    """One stabilizer-measurement template."""
    name: str
    description: str
    n_cnots_per_data: int
    build_z_cnot_specs: object
    build_x_cnot_specs: object
    # Multi-ancilla models (e.g. Shor cat-state) provide their own
    # measurement routine with the same contract as
    # circuit_level._measure_one_check:
    #   (code, check, kind, ax, az, rng, p_gate, p_reset, p_prep,
    #    p_readout, support_order=None, forced_faults=None)
    #   -> (outcome_bit, hooked_flag)
    # Baseline (single-ancilla) models leave this None and the
    # simulator dispatches to its own _measure_one_check.
    measure_check: object = None


def _baseline_z_cnot_specs(code, stabilizer_index: int) -> list[tuple[str, int, int]]:
    sup = code.z_checks[stabilizer_index].support
    return [("data->anc", q, 0) for q in sup]


def _baseline_x_cnot_specs(code, stabilizer_index: int) -> list[tuple[str, int, int]]:
    sup = code.x_checks[stabilizer_index].support
    return [("anc->data", 0, q) for q in sup]


# ---------------------------------------------------------------------------
# Shor cat-state measurement routine.
#
# Pauli-frame conventions (identical to circuit_level._measure_one_check;
# both are validated against the same algebraic syndrome oracle):
#   CNOT(c, t):  ax_t ^= ax_c ; az_c ^= az_t
#     (control X spreads to target; target Z spreads back to control)
#   H: swaps the ancilla's (ax, az) frame components.
#   Z-basis measurement outcome flips iff the frame has an X component
#   on the measured qubit (X anticommutes with the measured Z).
#
# Circuit (k = support weight, k MUST be even):
#   Z-check:  reset a_0..a_{k-1}; H(a_0); fan-out CNOT(a_i -> a_{i+1})
#             for i = 0..k-2; CNOT(data_i -> a_i) for each support
#             qubit; measure all ancillas in Z.
#   X-check:  same cat preparation, then H on ALL ancillas (Z-GHZ ->
#             X-GHZ), CNOT(a_i -> data_i) for each support qubit, H
#             on ALL ancillas (back to the Z basis), measure all.
#   Outcome = parity of the k ancilla measurement bits. The random
#   GHZ measurement offset b appears in every ancilla outcome, so
#   the parity over an EVEN number of ancillas cancels it; odd k
#   would leave the outcome random and is rejected.
#
# Noise (sampled from the SAME rng stream, in circuit order; every
# channel fires at most once per location exactly as in baseline):
#   reset  : X fault on each ancilla w.p. p_reset (per ancilla).
#   prep   : depolarizing on each ancilla w.p. p_prep right after
#            reset, BEFORE any H or fan-out gate (per-ancilla
#            preparation noise; the baseline applies p_prep to its
#            single ancilla after the initial H -- documented
#            convention difference).
#   gate   : after EVERY CNOT (fan-out AND data coupling),
#            depolarizing on each participating qubit w.p. p_gate
#            (control sampled first, then target). Cat preparation
#            gates are NOT magically ideal -- they participate in
#            the noise model.
#   readout: independent bit flip w.p. p_readout per ancilla
#            measurement, before the parity.
#   H gates: IDEAL (the existing documented contract -- the
#            simulator has no H noise channel; limitation recorded
#            in LIMITATIONS.md).
#
# `forced_faults` (test/validation hook; production passes None):
#   a list of (kind, check_index, stage, index, participant, pauli)
#   tuples injected deterministically when THAT check's circuit
#   reaches that location, bypassing the probability sampling:
#     ("X"|"Z", ci, "reset",   anc_idx,  None,  "X"|"Y"|"Z")
#     ("X"|"Z", ci, "prep",    anc_idx,  None,  "X"|"Y"|"Z")
#     ("X"|"Z", ci, "cnot",    gate_idx, "c"|"t", "X"|"Y"|"Z")
#     ("X"|"Z", ci, "readout", anc_idx,  None,  None)
#   gate_idx addresses the check's CNOTs in circuit order (fan-out
#   first, then data coupling; 0..2k-2). Faults for other checks
#   pass through untouched, so a single list can target any check.
#   This lets the exhaustive single-fault enumeration drive the
#   PRODUCTION routine deterministically (the oracle is not a
#   second implementation of the circuit).
# ---------------------------------------------------------------------------

_PAULI_AX_AZ = {"X": (1, 0), "Y": (1, 1), "Z": (0, 1)}


def _measure_check_shor(code, check, kind, ax, az, rng, p_gate, p_reset,
                        p_prep, p_readout, support_order=None,
                        forced_faults=None):
    """Unverified Shor cat-state measurement (AD-021). Thin wrapper
    over the shared core with verification disabled. Returns
    (outcome_bit, hooked_flag, vflag=0)."""
    out = _measure_check_shor_core(
        code, check, kind, ax, az, rng, p_gate, p_reset, p_prep,
        p_readout, support_order=support_order,
        forced_faults=forced_faults, verified=False)
    return out[0], out[1], 0


def _measure_check_shor_verified(code, check, kind, ax, az, rng, p_gate,
                                  p_reset, p_prep, p_readout,
                                  support_order=None, forced_faults=None):
    """Verified Shor cat-state measurement (AD-022). Returns
    (outcome_bit, hooked_flag, vflag) where vflag=1 means the cat
    verification REJECTED this round (flagged round: the outcome bit
    is still the measured parity and any data error still occurred —
    nothing is silently dropped; the caller accounts the rejection)."""
    out = _measure_check_shor_core(
        code, check, kind, ax, az, rng, p_gate, p_reset, p_prep,
        p_readout, support_order=support_order,
        forced_faults=forced_faults, verified=True)
    return out


def _measure_check_shor_core(code, check, kind, ax, az, rng, p_gate,
                              p_reset, p_prep, p_readout,
                              support_order=None, forced_faults=None,
                              verified=False):
    """Shor cat-state stabilizer measurement (see the block comment
    above for the full circuit and noise conventions).

    Mutates the data frame ax/az in place; returns (outcome_bit,
    hooked_flag, verification_flag)."""
    from .circuit_level import _sample_pauli_depolarizing

    support = list(support_order) if support_order is not None \
        else list(check.support)
    k = len(support)
    if k == 0:
        return 0, False, 0
    if k % 2 != 0:
        raise ValueError(
            f"Shor cat-state extraction requires even support weight; "
            f"{kind}-check {check.index} has weight {k}. The random "
            f"GHZ measurement offset cancels only in the even-k "
            f"parity.")

    # Forced-fault lookup (test hook): only faults targeting THIS
    # (kind, check_index) are consumed here; others belong to other
    # checks and pass through untouched. Fault tuple format:
    #   (kind, check_index, stage, index, participant, pauli)
    #     ("X"|"Z", int, "reset"|"prep"|"readout", anc_idx, None, pauli|None)
    #     ("X"|"Z", int, "cnot", gate_idx, "c"|"t", "X"|"Y"|"Z")
    #   Verified mode adds verification locations (gate_idx 0..k-1
    #   addresses CNOT(a_i -> v) in chain order):
    #     ("X"|"Z", int, "vreset",  0,        None, "X"|"Y"|"Z")
    #     ("X"|"Z", int, "vprep",   0,        None, "X"|"Y"|"Z")
    #     ("X"|"Z", int, "vcnot",   gate_idx, "c"|"t", "X"|"Y"|"Z")
    #     ("X"|"Z", int, "vreadout",0,        None, None)
    my_faults = [f for f in (forced_faults or [])
                 if f[0] == kind and f[1] == check.index]
    forced: dict[tuple, list] = {}
    for f in my_faults:
        forced.setdefault((f[2], f[3], f[4]), []).append(f)

    def _take(stage, idx, participant):
        entries = forced.pop((stage, idx, participant), None)
        return entries or []

    n_anc = k + 1 if verified else k   # verification ancilla v = index k
    anc_x = [0] * n_anc
    anc_z = [0] * n_anc
    hooked = False

    # 1. Reset + preparation noise (per ancilla; v included when
    #    verified, addressed by the vreset/vprep stages at index 0).
    for i in range(n_anc):
        is_v = verified and i == k
        rst_stage = "vreset" if is_v else "reset"
        prep_stage = "vprep" if is_v else "prep"
        fidx = 0 if is_v else i
        if (p_reset > 0 and rng.random() < p_reset):
            anc_x[i] = 1
        for f in _take(rst_stage, fidx, None):
            fx, fz = _PAULI_AX_AZ[f[5]]
            anc_x[i] ^= fx
            anc_z[i] ^= fz
        if p_prep > 0:
            ex, ez = _sample_pauli_depolarizing(rng, p_prep)
            anc_x[i] ^= ex
            anc_z[i] ^= ez
        for f in _take(prep_stage, fidx, None):
            fx, fz = _PAULI_AX_AZ[f[5]]
            anc_x[i] ^= fx
            anc_z[i] ^= fz

    # 2. Cat-state preparation, first gate: H(a_0). In the frame this
    #    is a swap of a_0's components. Without it the "cat" would
    #    silently degenerate to independent |0> ancillas (a valid but
    #    different extraction scheme) -- the noiseless oracle cannot
    #    catch that (both measure the same stabilizer ideally), so
    #    the H is structural, not optional.
    anc_x[0], anc_z[0] = anc_z[0], anc_x[0]

    # Gate list built in circuit order; gate_index counts ALL CNOTs
    # (fan-out first, then data coupling) so forced ("cnot", g, ...)
    # faults address a unique gate.
    gates: list[tuple[str, int, int]] = []   # (kind, c, t)
    if kind == "Z":
        # Cat: H(a_0); CNOT(a_i -> a_{i+1}).
        for i in range(k - 1):
            gates.append(("anc->anc", i, i + 1))
        # Coupling: CNOT(data_q -> a_i), support order.
        for i, q in enumerate(support):
            gates.append(("data->anc", q, i))
    else:
        # Cat: H(a_0); CNOT(a_i -> a_{i+1})  [Z-GHZ].
        for i in range(k - 1):
            gates.append(("anc->anc", i, i + 1))
        # H on ALL ancillas (Z-GHZ -> X-GHZ); then coupling
        # CNOT(a_i -> data_q); then H on ALL ancillas. The H layers
        # are frame swaps applied inline below (ideal, documented).
        for i, q in enumerate(support):
            gates.append(("anc->data", i, q))

    # Track which H-swap layer points fall between gates: for the
    # X-check, the k-1 fan-out gates are followed by H-all, then the
    # k coupling gates, then H-all.
    if kind == "X":
        h_after = {k - 2, 2 * k - 2}   # gate indices after which H-all applies
    else:
        h_after = set()

    def _apply_h_all():
        nonlocal anc_x, anc_z
        for i in range(k):
            anc_x[i], anc_z[i] = anc_z[i], anc_x[i]

    vflag = 0  # verification outcome (verified mode): 1 = REJECT
    outcome_bits = [0] * k
    for g_idx, (gkind, c, t) in enumerate(gates):
        # Gate noise: depolarizing on each participant, control
        # first then target (same per-CNOT sampling order as the
        # baseline routine).
        if p_gate > 0 or forced:
            participants = []
            if gkind == "anc->anc":
                participants = [("anc", c), ("anc", t)]
            elif gkind == "data->anc":
                participants = [("data", c), ("anc", t)]
            else:  # anc->data
                participants = [("anc", c), ("data", t)]
            for part_kind, part_idx in participants:
                forced_here = _take(
                    "cnot", g_idx,
                    "c" if (part_kind, part_idx) == participants[0]
                    else "t")
                sampled = None
                if p_gate > 0:
                    sampled = _sample_pauli_depolarizing(rng, p_gate)
                if sampled:
                    ex, ez = sampled
                else:
                    ex, ez = 0, 0
                for f in forced_here:
                    fx, fz = _PAULI_AX_AZ[f[5]]
                    ex, ez = ex ^ fx, ez ^ fz
                if ex == 0 and ez == 0:
                    continue
                if part_kind == "anc":
                    anc_x[part_idx] ^= ex
                    anc_z[part_idx] ^= ez
                else:
                    ax[part_idx] ^= ex
                    az[part_idx] ^= ez

        # Apply the gate to the frames.
        if gkind == "anc->anc":
            # CNOT(a_c -> a_t): ax_t ^= ax_c ; az_c ^= az_t
            anc_x[t] ^= anc_x[c]
            anc_z[c] ^= anc_z[t]
        elif gkind == "data->anc":
            # CNOT(data_c -> a_t): anc X gains data X; data Z gains
            # ancilla Z. An ancilla Z reaching data is a hook.
            if anc_z[t]:
                hooked = True
            az[c] ^= anc_z[t]
            anc_x[t] ^= ax[c]
        else:  # anc->data
            # CNOT(a_c -> data_t): data X gains ancilla X; ancilla Z
            # gains data Z. An ancilla X reaching data is a hook.
            if anc_x[c]:
                hooked = True
            anc_z[c] ^= az[t]
            ax[t] ^= anc_x[c]

        # ---- Cat-state verification (AD-022, verified mode) ----
        # Runs once, immediately after the GHZ fan-out completes
        # (g_idx == k-2) and BEFORE the X-check H-all / data coupling,
        # so the cat is the Z-GHZ here for BOTH check kinds.
        # Circuit: H(v); CNOT(a_i -> v) for i = 0..k-1; measure v in Z.
        # The measured operator (pulled back) is X_v * Z^{tensor k}_cat:
        # the outcome flips iff the cat carries an ODD number of X
        # components -- exactly the harmful class (single-leg cat
        # errors, including the AD-021 worst-case reset/prep-Y on a_1
        # whose 3-leg X pattern fires). Even-X patterns (X^{tensor k}
        # = cat stabilizer) and all Z patterns commute -> accepted.
        # v's own Z fault anticommutes with X_v -> fires (a flagged
        # rejection); v's Z also back-propagates Z onto cat legs i..k-1
        # via az_c ^= az_t during the remaining vcnot gates -- a real
        # fault location the exhaustive enumeration must cover.
        # Every verification gate/reset/readout participates in the
        # noise model (nothing is free).
        if verified and g_idx == k - 2:
            # H(v): frame swap on the verification ancilla.
            anc_x[k], anc_z[k] = anc_z[k], anc_x[k]
            for vi in range(k):
                # Gate noise on both participants (control = cat leg,
                # target = v), sampled in the same order as every
                # other CNOT.
                if p_gate > 0 or forced:
                    forced_here = _take("vcnot", vi, "c")
                    sampled = None
                    if p_gate > 0:
                        sampled = _sample_pauli_depolarizing(rng, p_gate)
                    ex_c, ez_c = sampled if sampled else (0, 0)
                    for f in forced_here:
                        fx, fz = _PAULI_AX_AZ[f[5]]
                        ex_c, ez_c = ex_c ^ fx, ez_c ^ fz
                    forced_here = _take("vcnot", vi, "t")
                    sampled = None
                    if p_gate > 0:
                        sampled = _sample_pauli_depolarizing(rng, p_gate)
                    ex_t, ez_t = sampled if sampled else (0, 0)
                    for f in forced_here:
                        fx, fz = _PAULI_AX_AZ[f[5]]
                        ex_t, ez_t = ex_t ^ fx, ez_t ^ fz
                    if ex_c or ez_c:
                        anc_x[vi] ^= ex_c
                        anc_z[vi] ^= ez_c
                    if ex_t or ez_t:
                        anc_x[k] ^= ex_t
                        anc_z[k] ^= ez_t
                # CNOT(a_vi -> v): v's X gains the cat leg's X; the cat
                # leg's Z gains v's Z (back-propagation channel).
                anc_x[k] ^= anc_x[vi]
                anc_z[vi] ^= anc_z[k]
            # Readout of v (independent readout noise), then the
            # acceptance decision: vbit == 1 -> verification REJECTS
            # (flagged round). The outcome bit and any data errors are
            # recorded regardless -- nothing is silently dropped; the
            # caller accounts accept/reject separately.
            vbit = anc_x[k]
            if p_readout > 0 and rng.random() < p_readout:
                vbit ^= 1
            for f in _take("vreadout", 0, None):
                vbit ^= 1
            vflag = vbit

        # H-all layer after this gate?
        if g_idx in h_after:
            _apply_h_all()          # back to the Z basis before readout

    # 2. Readout: per-ancilla independent flip, then parity.
    parity = 0
    for i in range(k):
        bit = anc_x[i]
        if p_readout > 0 and rng.random() < p_readout:
            bit ^= 1
        for f in _take("readout", i, None):
            bit ^= 1
        outcome_bits[i] = bit
        parity ^= bit

    if forced:
        raise RuntimeError(
            f"Unconsumed forced faults (locations never reached): "
            f"{sorted(forced.keys())}")
    return parity, hooked, vflag


# ---------------------------------------------------------------------------
# Fitted pair-decomposed extraction (AD-023, milestone 19).
#
# Engineering definition (derived, not assumed — see the block evidence
# below): an extraction FITTED to the code's check-weight structure and to
# the measured single-fault mechanisms, defined by ONE rule:
#
#     cap every ancilla's data fan-in at 2.
#
# A weight-k check is measured as ceil(k/2) independent ancillas, each
# coupled to at most TWO data qubits (a weight-<=2 sub-parity); the check
# outcome is the XOR of the sub-parity bits. For k=2 this is BIT-FOR-BIT
# the baseline circuit (same gates, same noise-sampling order -- asserted
# by test). For k=4 it is 2 ancillas x (2 CNOTs) -- the SAME CNOT count as
# baseline (k) versus the cat's 2k-1, with 2 ancillas versus the cat's k
# (or k+1 verified).
#
# Why this and not a cat variant (the milestone's evidence chain):
#   1. Exhaustive enumeration (d=3, d=5, production path) shows every
#      DANGEROUS accepted weight-2 mechanism of the cat modes decomposes
#      into (a) a Z fault on a cat leg that back-propagates through the
#      fan-out onto exactly the leg pair {j-1, j} -- an EVEN Z-pattern,
#      invisible to any cat-parity verifier (a Z-parity verifier only
#      flags odd-Z patterns), and (b) coupling-gate faults, which occur
#      AFTER any pre-coupling verification. This FALSIFIES AD-022's
#      prediction that a second (Z-parity) verifier would close the
#      remaining accepted weight-2 mechanisms.
#   2. The dangerous hook cap equals the maximum ancilla data fan-in.
#      The cat achieves fan-in 1 per ancilla but pays k-1 fan-out CNOTs
#      to correlate the ancillas -- and those correlated fan-out edges
#      are themselves what produces the 2-leg correlated Z-patterns.
#      Capping fan-in at 2 directly (pair decomposition) reaches the
#      same coupling structure with NO entanglement between ancillas,
#      NO fan-out gates, and NO even-k constraint.
#   3. The verified cat's operational failure is its rejection load
#      (56%-94% of rounds flagged, AD-022). The pair decomposition has
#      NO verification pass and therefore NO rejection semantics at all.
#
# Circuit (per check, k = support weight, ANY k >= 1):
#   Ancilla a_p (p = 0..ceil(k/2)-1) measures sub-parity of
#   support[2p:2p+2]:
#   Z-check:  reset a_p ; CNOT(q_{2p} -> a_p) ; CNOT(q_{2p+1} -> a_p)
#             (a singleton last pair has one CNOT) ; readout.
#   X-check:  reset a_p ; H(a_p) ; CNOT(a_p -> q) for each member ;
#             H(a_p) ; readout.
#   outcome = XOR of the a_p readout bits = the full stabilizer eigenvalue.
#
# Noise (same channels and conventions as the Shor core; H ideal):
#   reset  : X fault per ancilla w.p. p_reset (all pairs first, pair
#            order).
#   prep   : depolarizing per ancilla w.p. p_prep AFTER that pair's
#            first H (X-check) -- exactly the baseline's reset/H/prep
#            relative order, so the k=2 case degenerates bit-for-bit to
#            the baseline routine under the same rng stream.
#   gate   : depolarizing on each CNOT participant w.p. p_gate, DATA
#            participant sampled first, then the ancilla (the
#            _measure_one_check order; keeps the k=2 equivalence
#            exact), in circuit order (pair-major).
#   readout: independent flip per ancilla w.p. p_readout, pair order,
#            before the XOR.
#
# Forced-fault tuple format (same convention as the Shor core):
#   ("X"|"Z", ci, "reset"|"prep"|"readout", pair_index, None, pauli|None)
#   ("X"|"Z", ci, "cnot", gate_idx, "c"|"t", "X"|"Y"|"Z")
# with gate_idx = 2*p + j (pair p, j-th CNOT of the pair), 0..k-1.
# ---------------------------------------------------------------------------

def _measure_check_fitted(code, check, kind, ax, az, rng, p_gate, p_reset,
                          p_prep, p_readout, support_order=None,
                          forced_faults=None, subparity_out=None):
    """Fitted pair-decomposed stabilizer measurement (AD-023). Same
    3-tuple contract as the Shor routines; the verification flag is
    always 0 (no verification pass exists).

    `subparity_out`: optional OUT-parameter (milestone-20 diagnostic).
    When a list is provided, this check's per-pair readout bits — the
    sub-parity values BEFORE the XOR collapses them into the stabilizer
    outcome — are appended as (kind, check_index, pair_bits_tuple).
    This is the information the fitted extraction computes and the
    current API discards; the milestone-20 sub-parity experiment
    (directive §19-§20) measures whether retaining it helps decoding.
    Production callers omit it."""
    from .circuit_level import _sample_pauli_depolarizing

    support = list(support_order) if support_order is not None \
        else list(check.support)
    k = len(support)
    if k == 0:
        return 0, False, 0
    n_anc = (k + 1) // 2

    my_faults = [f for f in (forced_faults or [])
                 if f[0] == kind and f[1] == check.index]
    forced: dict[tuple, list] = {}
    for f in my_faults:
        forced.setdefault((f[2], f[3], f[4]), []).append(f)

    def _take(stage, idx, participant):
        entries = forced.pop((stage, idx, participant), None)
        return entries or []

    aa_x = [0] * n_anc
    aa_z = [0] * n_anc
    hooked = False

    # 1. Reset noise per ancilla (pair order; BEFORE any H -- the
    #    baseline's reset-then-H relative order).
    for i in range(n_anc):
        if p_reset > 0 and rng.random() < p_reset:
            aa_x[i] = 1
        for f in _take("reset", i, None):
            fx, fz = _PAULI_AX_AZ[f[5]]
            aa_x[i] ^= fx
            aa_z[i] ^= fz

    # 2. Per pair: H (X-check), prep noise, coupling CNOTs, H.
    for p in range(n_anc):
        members = support[2 * p:2 * p + 2]
        if kind == "X":
            aa_x[p], aa_z[p] = aa_z[p], aa_x[p]   # H -> |+>
        if p_prep > 0:
            ex, ez = _sample_pauli_depolarizing(rng, p_prep)
            aa_x[p] ^= ex
            aa_z[p] ^= ez
        for f in _take("prep", p, None):
            fx, fz = _PAULI_AX_AZ[f[5]]
            aa_x[p] ^= fx
            aa_z[p] ^= fz
        for j, q in enumerate(members):
            g_idx = 2 * p + j
            if p_gate > 0 or forced:
                # DATA participant sampled first, then the ancilla
                # (the _measure_one_check sampling order; keeps the
                # k=2 bit-for-bit baseline equivalence exact).
                participants = [("data", q), ("anc", p)]
                for pi, (pkind, pidx) in enumerate(participants):
                    forced_here = _take(
                        "cnot", g_idx, "c" if pi == 0 else "t")
                    sampled = None
                    if p_gate > 0:
                        sampled = _sample_pauli_depolarizing(rng, p_gate)
                    ex, ez = sampled if sampled else (0, 0)
                    for f in forced_here:
                        fx, fz = _PAULI_AX_AZ[f[5]]
                        ex, ez = ex ^ fx, ez ^ fz
                    if ex == 0 and ez == 0:
                        continue
                    if pkind == "anc":
                        aa_x[pidx] ^= ex
                        aa_z[pidx] ^= ez
                    else:
                        ax[pidx] ^= ex
                        az[pidx] ^= ez
            if kind == "Z":
                # CNOT(data_q -> a_p): az[q] ^= aa_z[p]; aa_x[p] ^= ax[q]
                if aa_z[p]:
                    hooked = True
                az[q] ^= aa_z[p]
                aa_x[p] ^= ax[q]
            else:
                # CNOT(a_p -> data_q): aa_z[p] ^= az[q]; ax[q] ^= aa_x[p]
                if aa_x[p]:
                    hooked = True
                aa_z[p] ^= az[q]
                ax[q] ^= aa_x[p]
        if kind == "X":
            aa_x[p], aa_z[p] = aa_z[p], aa_x[p]   # H back to Z basis

    # 3. Readout per ancilla (pair order), XOR of the sub-parity bits.
    parity = 0
    pair_bits = []
    for i in range(n_anc):
        bit = aa_x[i]
        if p_readout > 0 and rng.random() < p_readout:
            bit ^= 1
        for f in _take("readout", i, None):
            bit ^= 1
        pair_bits.append(bit)
        parity ^= bit
    if subparity_out is not None:
        subparity_out.append((kind, check.index, tuple(pair_bits)))

    if forced:
        raise RuntimeError(
            f"Unconsumed forced faults (locations never reached): "
            f"{sorted(forced.keys())}")
    return parity, hooked, 0


MODELS: dict[str, ExtractionModel] = {
    EXTRACTION_BASELINE: ExtractionModel(
        name=EXTRACTION_BASELINE,
        description=(
            "Baseline H-CNOT-H extraction: Z-check = CNOT(data->anc) "
            "for each support qubit; X-check = H, CNOT(anc->data) for "
            "each support qubit, H. Standard textbook circuit. "
            "Hook errors: weight-k (full support) for a single ancilla "
            "fault at the start of the schedule. Schedule is degenerate "
            "under the order-invariant primary_key."
        ),
        n_cnots_per_data=1,
        build_z_cnot_specs=_baseline_z_cnot_specs,
        build_x_cnot_specs=_baseline_x_cnot_specs,
    ),
    EXTRACTION_SHOR: ExtractionModel(
        name=EXTRACTION_SHOR,
        description=(
            "Shor cat-state extraction: one ancilla per support data "
            "qubit, prepared as a GHZ cat state (H on a_0, CNOT "
            "fan-out a_i -> a_i+1), each ancilla coupled to exactly "
            "ONE data qubit, all ancillas measured, stabilizer "
            "outcome = parity of the k measurement bits. REQUIRES "
            "even support weight (the random GHZ measurement offset "
            "cancels only in the even-k parity); odd-weight supports "
            "are rejected loudly. X-checks add an H layer before and "
            "after the data coupling (Z-GHZ -> X-GHZ -> Z basis). "
            "Fault-tolerance property (proven by exhaustive "
            "single-fault enumeration in the test suite): each "
            "ancilla couples to one data qubit, so no single fault "
            "produces a data error of weight > 1 -- versus the "
            "baseline where one ancilla fault hooks to up to k data "
            "qubits. Ancilla faults during cat preparation are "
            "either stabilizer-equivalent on the cat (benign, e.g. "
            "a Z fault on a_0 right after reset is equivalent to "
            "the all-legs X stabilizer of the GHZ) or flip exactly "
            "one measurement bit (a syndrome error, never a data "
            "error). Gate cost: 2k-1 CNOTs vs k for baseline, plus "
            "k resets/readouts vs 1 -- the extra noise exposure is "
            "the honest trade-off the Monte Carlo comparison "
            "measures."
        ),
        n_cnots_per_data=2,   # 1 fan-out share + 1 coupling (2k-1 total)
        build_z_cnot_specs=_baseline_z_cnot_specs,  # unused for Shor
        build_x_cnot_specs=_baseline_x_cnot_specs,  # unused for Shor
        measure_check=_measure_check_shor,
    ),
    EXTRACTION_SHOR_VERIFIED: ExtractionModel(
        name=EXTRACTION_SHOR_VERIFIED,
        description=(
            "Verified Shor cat-state extraction (AD-022): the AD-021 "
            "cat state plus ONE verification ancilla v. After the GHZ "
            "fan-out and BEFORE the X-check H-all / data coupling, v "
            "is prepared |0>, coupled via CNOT(a_i -> v) for all k cat "
            "legs, and measured in Z. The pulled-back measured "
            "operator is X_v * Z^{tensor k}_cat: the outcome flips iff "
            "the cat carries an ODD number of X components (single-leg "
            "cat errors, including the AD-021 worst-case reset/prep-Y "
            "on a_1) or v carries a Z error. Rejection semantics: "
            "FLAGGED ROUND (Option 1) -- the outcome bit is still the "
            "measured parity, data errors still occur and are counted, "
            "and the rejection is reported explicitly; no retry, no "
            "postselection, logical statistics are UNCONDITIONAL over "
            "all trials (conditional-on-accept reported separately as "
            "a diagnostic). Verification cost: k+1 ancillas, (k-1)+k "
            "CNOTs + k verification CNOTs = 3k-1 total, k+1 resets and "
            "readouts. Verification is not modeled as free: every "
            "verification reset/prep/CNOT/readout is a real fault "
            "location in the noise model."
        ),
        n_cnots_per_data=3,   # fan-out share + verification + coupling
        build_z_cnot_specs=_baseline_z_cnot_specs,  # unused for Shor
        build_x_cnot_specs=_baseline_x_cnot_specs,  # unused for Shor
        measure_check=_measure_check_shor_verified,
    ),
    EXTRACTION_FITTED: ExtractionModel(
        name=EXTRACTION_FITTED,
        description=(
            "Fitted pair-decomposed extraction (AD-023): a weight-k "
            "check is measured by ceil(k/2) INDEPENDENT ancillas, "
            "each coupled to at most TWO data qubits (a weight-<=2 "
            "sub-parity); the outcome is the XOR of the sub-parity "
            "bits. This is NOT a cat state: no GHZ, no fan-out gates, "
            "no verification pass, no rejection semantics, no even-k "
            "constraint. Design rule derived from the milestone-19 "
            "evidence chain: (1) the dangerous hook cap equals the "
            "maximum ancilla data fan-in, so capping fan-in at 2 "
            "caps hooks at 2 -- the same confinement the cat modes "
            "reach; (2) every dangerous accepted weight-2 mechanism "
            "of the cat modes is either an EVEN correlated pattern "
            "on the cat (invisible to any cat-parity verifier -- "
            "this falsifies AD-022's two-verifier prediction) or a "
            "coupling-time fault (after any pre-coupling "
            "verification); (3) the verified cat's operational "
            "failure is its 56%-94% rejection load, which this mode "
            "does not have. For weight-2 checks the circuit is "
            "BIT-FOR-BIT the baseline (asserted by test under the "
            "same rng stream); only weight-4 checks differ, and "
            "there the cost is 1 extra reset/prep/readout versus "
            "baseline at the SAME CNOT count (k), in exchange for "
            "hook cap 2 instead of 4."
        ),
        n_cnots_per_data=1,   # k CNOTs for k data qubits (as baseline)
        build_z_cnot_specs=_baseline_z_cnot_specs,  # unused for fitted
        build_x_cnot_specs=_baseline_x_cnot_specs,  # unused for fitted
        measure_check=_measure_check_fitted,
    ),
}


def get_extraction_model(name: str) -> ExtractionModel:
    if name not in MODELS:
        raise ValueError(
            f"Unknown extraction model {name!r}; supported: {list(MODELS)}.")
    return MODELS[name]


def list_extraction_models() -> list[dict]:
    return [
        {"name": m.name, "description": m.description,
         "n_cnots_per_data": m.n_cnots_per_data}
        for m in MODELS.values()
    ]


__all__ = [
    "EXTRACTION_BASELINE", "EXTRACTION_FITTED", "SUPPORTED_EXTRACTIONS",
    "ExtractionModel", "MODELS",
    "get_extraction_model", "list_extraction_models",
]
