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
SUPPORTED_EXTRACTIONS = (EXTRACTION_BASELINE, EXTRACTION_SHOR)


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
    """Shor cat-state stabilizer measurement (see the block comment
    above for the full circuit and noise conventions).

    Mutates the data frame ax/az in place; returns (outcome_bit,
    hooked_flag) where outcome is the parity of all k ancilla
    measurements and hooked is True iff any ancilla fault propagated
    onto a data qubit."""
    from .circuit_level import _sample_pauli_depolarizing

    support = list(support_order) if support_order is not None \
        else list(check.support)
    k = len(support)
    if k == 0:
        return 0, False
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
    my_faults = [f for f in (forced_faults or [])
                 if f[0] == kind and f[1] == check.index]
    forced: dict[tuple, list] = {}
    for f in my_faults:
        forced.setdefault((f[2], f[3], f[4]), []).append(f)

    def _take(stage, idx, participant):
        entries = forced.pop((stage, idx, participant), None)
        return entries or []

    anc_x = [0] * k
    anc_z = [0] * k
    hooked = False

    # 1. Reset + preparation noise (per ancilla).
    for i in range(k):
        if (p_reset > 0 and rng.random() < p_reset):
            anc_x[i] = 1
        for f in _take("reset", i, None):
            fx, fz = _PAULI_AX_AZ[f[5]]
            anc_x[i] ^= fx
            anc_z[i] ^= fz
        if p_prep > 0:
            ex, ez = _sample_pauli_depolarizing(rng, p_prep)
            anc_x[i] ^= ex
            anc_z[i] ^= ez
        for f in _take("prep", i, None):
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
                    ex, ez = fx, fz
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
    return parity, hooked


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
    "EXTRACTION_BASELINE", "SUPPORTED_EXTRACTIONS",
    "ExtractionModel", "MODELS",
    "get_extraction_model", "list_extraction_models",
]
