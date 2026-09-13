"""Circuit-level surface-code syndrome extraction with fault-tolerant noise.

Replaces the PHENOMENOLOGICAL repeated-round syndrome generator with a real
stabilizer-measurement circuit simulator: explicit, disposable ancilla qubits,
a deterministic CNOT schedule per stabilizer, and gate-, reset-, preparation-,
and readout-channel noise. Tracks a Pauli (Gottesman-Knill) frame over data
qubits (persistent) and per-round ancillas, then feeds the measured syndrome
history plus the net data error into the EXISTING repeated-round decoder
(qec.repeated_round.decode_repeated).

Model assumptions (explicit; no hardware claims):
  * Geometry/decoder reuse: RotatedSurfaceCode + decode_repeated.
  * Ancillas: one per stabilizer per round, disposable; no logical info.
  * Schedules (support is already sorted -> deterministic):
      Z-check (measures Z on data, detects X-type data errors):
          reset ancilla |0> ; CNOT(data_q -> ancilla) ; measure Z.
      X-check (measures X on data, detects Z-type data errors):
          reset ancilla |0> ; H (->|+>) ; CNOT(ancilla -> data_q) ; H ; measure Z.
    Directions validated against syndrome_of in tests.
  * Noise (all independent, one seeded PRNG per trial):
      reset:   ancilla X w.p. p_reset.
      prep:    depolarizing on the ancilla w.p. p_prep (before any CNOT).
      gate:    after every CNOT, independent depolarizing on each participating
               qubit w.p. p_gate; single-qubit H is IDEAL (documented).
      readout: measured ancilla bit flips w.p. p_readout (the channel, distinct
               from data errors).
  * Hook errors: an ancilla fault (reset/prep/gate) propagates through the
    remaining CNOTs of its schedule onto data qubits -> correlated multi-qubit
    data errors. Emerges from schedule + propagation (orientation-aware);
    recorded explicitly, never injected separately.

Pauli-frame propagation through CNOT(control c, target t), bits (ax=has X,
az=has Z): az_c ^= az_t (target Z -> control Z); ax_t ^= ax_c (control X ->
target X). This is CNOT P CNOT^dag; validated against an independent 4x4
matrix CNOT in tests.
"""
from __future__ import annotations

import numpy as np

from .pipeline import wilson_interval
from .repeated_round import decode_repeated
from .rotated_surface_code import RotatedSurfaceCode

_SUPPORTED_DISTANCES = (3, 5, 7)
_MAX_ROUNDS = 64


def cnot_propagate(ax_c, az_c, ax_t, az_t):
    """Return (ax_c, az_c, ax_t, az_t) after CNOT(control=c, target=t)."""
    return ax_c, az_c ^ az_t, ax_t ^ ax_c, az_t


def _sample_pauli_depolarizing(rng, p: float) -> tuple[int, int]:
    """Sample one single-qubit depolarizing error channel: I w.p. 1-p, else
    X/Y/Z each w.p. p/3 (the project's established convention, matching
    stabilizer.random_pauli_errors). Returns (has_X, has_Z)."""
    u = rng.random()
    if u < 1.0 - p:
        return 0, 0          # I
    u = rng.random()
    if u < 1 / 3:
        return 1, 0          # X
    if u < 2 / 3:
        return 1, 1          # Y
    return 0, 1              # Z


_PAULI_AX_AZ = {"X": (1, 0), "Y": (1, 1), "Z": (0, 1)}


def _measure_one_check(code, check, kind, ax, az, rng, p_gate, p_reset,
                       p_prep, p_readout, support_order=None,
                       cnot_specs=None, forced_faults=None):
    """Run one stabilizer's noisy measurement circuit on the shared data frame.

    Mutates ax/az in place (data-frame propagation for hook errors); returns
    (outcome_bit, hooked_flag).

    `support_order`: optional tuple of data qubits specifying the CNOT
    schedule (which qubit is visited first, etc.). Defaults to
    `check.support` (the production ordering).

    `cnot_specs`: optional list of (kind, control_q, target_q) tuples
    that fully specifies the stabilizer measurement circuit. If None,
    the BASELINE_H_CNOT_H schedule is used (CNOT per data qubit once).
    For DOUBLED_CNOT extraction each data qubit is touched by TWO
    consecutive CNOTs; the second CNOT undoes a single-qubit hook
    from an ancilla fault in the first.

    `forced_faults`: TEST/VALIDATION harness (production passes None).
    Same tuple convention as the multi-ancilla extraction cores in
    qec.circuit_extraction: (kind, check_index, stage, index,
    participant, pauli) with stages "reset"/"prep"/"readout"
    (index 0 — the single ancilla) and "cnot" (index = position in
    cnot_specs; participant "c"/"t" = control/target of that CNOT,
    so for "data->anc" the control is the data qubit and for
    "anc->data" it is the ancilla). Faults targeting other checks
    pass through untouched. Unconsumed faults raise (a location was
    never reached — the harness must not silently drop injections).
    """
    if cnot_specs is None:
        if support_order is None:
            support_order = check.support
        cnot_specs = [("data->anc", q, 0) for q in support_order] if kind == "Z" \
            else [("anc->data", 0, q) for q in support_order]
    my_faults = [f for f in (forced_faults or [])
                 if f[0] == kind and f[1] == check.index]
    forced: dict[tuple, list] = {}
    for f in my_faults:
        forced.setdefault((f[2], f[3], f[4]), []).append(f)

    def _take(stage, idx, participant):
        entries = forced.pop((stage, idx, participant), None)
        return entries or []

    aa_x, aa_z = 0, 0
    hooked = False
    if p_reset > 0 and rng.random() < p_reset:
        aa_x = 1
    for f in _take("reset", 0, None):
        fx, fz = _PAULI_AX_AZ[f[5]]
        aa_x ^= fx
        aa_z ^= fz
    if kind == "X":
        aa_x, aa_z = aa_z, aa_x            # H -> |+>
    if p_prep > 0:
        ex, ez = _sample_pauli_depolarizing(rng, p_prep)
        aa_x ^= ex
        aa_z ^= ez
    for f in _take("prep", 0, None):
        fx, fz = _PAULI_AX_AZ[f[5]]
        aa_x ^= fx
        aa_z ^= fz
    for g_idx, (spec_kind, c, t) in enumerate(cnot_specs):
        if p_gate > 0 or forced:
            # Baseline sampling order: the DATA participant first, then
            # the ancilla (historical convention, preserved bit-for-bit).
            # Participant naming follows CNOT control/target: for
            # "data->anc" the data qubit is the control ("c"); for
            # "anc->data" it is the target ("t").
            if spec_kind == "data->anc":
                participants = [(False, c, "c"), (True, None, "t")]
            else:
                participants = [(False, t, "t"), (True, None, "c")]
            for is_anc, q_idx, part in participants:
                forced_here = _take("cnot", g_idx, part)
                ex, ez = _sample_pauli_depolarizing(rng, p_gate) \
                    if p_gate > 0 else (0, 0)
                for f in forced_here:
                    ex, ez = _PAULI_AX_AZ[f[5]]
                if ex == 0 and ez == 0:
                    continue
                if is_anc:
                    aa_x ^= ex
                    aa_z ^= ez
                else:
                    ax[q_idx] ^= ex
                    az[q_idx] ^= ez
        if spec_kind == "data->anc":
            # CNOT(data_q=c, ancilla=t): az_c ^= az_t ; ax_t ^= ax_c
            if aa_z:
                hooked = True
            az[c] ^= aa_z
            aa_x ^= ax[c]
        else:
            # anc->data
            if aa_x:
                hooked = True
            aa_z ^= az[t]
            ax[t] ^= aa_x
    if kind == "X":
        aa_x, aa_z = aa_z, aa_x            # H (back to Z basis)
    outcome = aa_x
    if p_readout > 0 and rng.random() < p_readout:
        outcome ^= 1
    for f in _take("readout", 0, None):
        outcome ^= 1
    if forced:
        raise RuntimeError(
            f"Unconsumed forced faults (locations never reached): "
            f"{sorted(forced.keys())}")
    return outcome, hooked


def _run_check_measurement(code, check, kind, ax, az, rng, p_gate, p_reset,
                           p_prep, p_readout, support_order=None,
                           cnot_specs=None, extraction_model=None,
                           forced_faults=None, subparity_out=None):
    """Single dispatch point for stabilizer measurement: multi-ancilla
    extraction models (e.g. Shor cat-state) provide their own
    `measure_check` routine with the same contract as the baseline
    `_measure_one_check`; single-ancilla models fall through to it."""
    if extraction_model is not None and extraction_model.measure_check is not None:
        from .circuit_extraction import EXTRACTION_FITTED
        if extraction_model.name == EXTRACTION_FITTED and subparity_out is not None:
            return extraction_model.measure_check(
                code, check, kind, ax, az, rng, p_gate, p_reset, p_prep,
                p_readout, support_order=support_order,
                forced_faults=forced_faults, subparity_out=subparity_out)
        return extraction_model.measure_check(
            code, check, kind, ax, az, rng, p_gate, p_reset, p_prep,
            p_readout, support_order=support_order,
            forced_faults=forced_faults)
    outcome, hooked = _measure_one_check(
        code, check, kind, ax, az, rng, p_gate,
        p_reset, p_prep, p_readout,
        support_order=support_order,
        cnot_specs=cnot_specs,
        forced_faults=forced_faults)
    return outcome, hooked, 0   # no verification performed


def extract_syndrome_noiseless(code, ex, ez, schedules=None,
                                 extraction_model=None):
    """Run the NOISELESS stabilizer circuits on a known data error and
    return (x_check_bits, z_check_bits). Exists as the independent
    validation oracle: must equal RotatedSurfaceCodeDecoder.syndrome(ex, ez).

    `schedules` is an optional {(kind, index): order_tuple} override; the
    noiseless syndrome must equal the algebraic `syndrome_of` for ANY
    schedule AND any supported extraction model (directive §3A.2:
    Step A2 — ideal correctness for every candidate)."""
    from .circuit_extraction import get_extraction_model
    n = code.d * code.d
    ax = [1 if (ex >> q) & 1 else 0 for q in range(n)]
    az = [1 if (ez >> q) & 1 else 0 for q in range(n)]

    class _NoRng:
        def random(self):
            raise RuntimeError("noiseless oracle must not sample")
    x_out, z_out = [], []
    em = get_extraction_model(extraction_model) if extraction_model else None
    for kind, checks in (("X", code.x_checks), ("Z", code.z_checks)):
        for check in checks:
            order = None if schedules is None else schedules.get(
                (kind, check.index))
            cnot_specs = None
            if em is not None:
                cnot_specs = (em.build_z_cnot_specs(code, check.index)
                                if kind == "Z"
                                else em.build_x_cnot_specs(code, check.index))
            out, _hooked, _vflag = _run_check_measurement(
                code, check, kind, ax, az, _NoRng(),
                0.0, 0.0, 0.0, 0.0,
                support_order=order,
                cnot_specs=cnot_specs,
                extraction_model=em)
            (x_out if kind == "X" else z_out).append(out)
    return tuple(x_out), tuple(z_out)


def simulate_circuit_level(code, rounds, p_gate, p_readout, p_reset, p_prep,
                           *, seed, schedules=None, extraction_model=None,
                           interleave: str = "none", forced_faults=None,
                           subparity_trace=None):
    """Run R rounds of noisy stabilizer-measurement circuits.

    `schedules` is an optional {(kind, index): order_tuple} override
    specifying the CNOT ordering for each stabilizer; default None uses
    the production `check.support` ordering (the naive schedule).

    `extraction_model`: optional name (e.g. "baseline_h_cnot_h",
    "doubled_cnot") selecting a fault-extraction template. Default
    None uses the production BASELINE_H_CNOT_H.

    `interleave`: the round-level interleaving schedule. "none"
    (default) measures all stabilizers in every round (the
    standard behavior). "alternating" measures only X-checks in
    even rounds and only Z-checks in odd rounds; the OTHER
    family's syndrome is carried forward (its value is the same
    as the previous round, with no detection events generated).
    "alternating_zx" measures Z in even rounds and X in odd rounds.

    `forced_faults`: TEST/VALIDATION harness only (production
    callers omit it). A list of extraction-specific fault tuples
    (see circuit_extraction._measure_check_shor) injected
    deterministically in ROUND 1 ONLY (a non-final round, so
    reset/preparation/readout faults are exercisable). Bypasses
    the probability sampling entirely; the rest of the circuit
    runs at the configured noise levels.

    Returns (data_error_x, data_error_z, hook_events, observed_syndromes).
    The 5th element `measured_families` is also returned as a
    5-tuple via the `return_families=True` flag; by default this
    is omitted for backwards compatibility.
    """
    from .circuit_extraction import get_extraction_model
    if rounds < 1 or rounds > _MAX_ROUNDS:
        raise ValueError(f"rounds must be within [1, {_MAX_ROUNDS}], got {rounds}.")
    if interleave not in ("none", "alternating", "alternating_zx"):
        raise ValueError(
            f"interleave must be one of 'none', 'alternating', 'alternating_zx'; got {interleave!r}.")
    for p, name in ((p_gate, "p_gate"), (p_readout, "p_readout"),
                    (p_reset, "p_reset"), (p_prep, "p_prep")):
        if not (0 <= p <= 1):
            raise ValueError(f"{name} must be within [0,1].")
    em = get_extraction_model(extraction_model) if extraction_model else None
    rng = np.random.default_rng(seed)
    n = code.d * code.d
    ax = [0] * n
    az = [0] * n
    hook_events: list[tuple[int, str, int]] = []
    observed: list[tuple[tuple[int, ...], tuple[int, ...]]] = []
    measured_families: list[str] = []
    verification_events: list[tuple[int, str, int]] = []

    for _round in range(1, rounds + 1):
        # Determine which families to measure this round.
        if interleave == "alternating":
            measure_x = (_round % 2 == 1)   # X in odd rounds
            measure_z = (_round % 2 == 0)   # Z in even rounds
        elif interleave == "alternating_zx":
            measure_x = (_round % 2 == 0)   # X in even rounds
            measure_z = (_round % 2 == 1)   # Z in odd rounds
        else:
            measure_x = True
            measure_z = True

        if measure_x and measure_z:
            measured_families.append("both")
        elif measure_x:
            measured_families.append("X")
        else:
            measured_families.append("Z")

        # Carry-forward for unmeasured family. We initialize x_out /
        # z_out to the previous round's syndrome for the unmeasured
        # family; the measured family's syndromes are written below.
        if _round == 1:
            prev_x = tuple(0 for _ in range(len(code.x_checks)))
            prev_z = tuple(0 for _ in range(len(code.z_checks)))
        else:
            prev_x, prev_z = observed[-1]
        x_out = list(prev_x) if not measure_x else None
        z_out = list(prev_z) if not measure_z else None
        if x_out is None:
            x_out = [0] * len(code.x_checks)
        if z_out is None:
            z_out = [0] * len(code.z_checks)

        # The FINAL round uses an IDEAL syndrome readout (p_reset / p_prep /
        # p_readout zeroed) so its outcome is exactly the net data syndrome —
        # honoring decode_repeated's documented ideal-final-round contract.
        # Gate faults (and their hooks) in the final round are still modeled,
        # so final-slice data errors propagate normally before the readout.
        is_final = _round == rounds
        r_reset = 0.0 if is_final else p_reset
        r_prep = 0.0 if is_final else p_prep
        r_readout = 0.0 if is_final else p_readout
        for kind, checks in (("X", code.x_checks), ("Z", code.z_checks)):
            if kind == "X" and not measure_x:
                continue
            if kind == "Z" and not measure_z:
                continue
            for check in checks:
                order = None if schedules is None else schedules.get(
                    (kind, check.index))
                cnot_specs = None
                if em is not None and em.measure_check is None:
                    cnot_specs = (em.build_z_cnot_specs(code, check.index)
                                    if kind == "Z"
                                    else em.build_x_cnot_specs(code, check.index))
                outcome, hooked, vflag = _run_check_measurement(
                    code, check, kind, ax, az, rng, p_gate, r_reset, r_prep,
                    r_readout, support_order=order,
                    cnot_specs=cnot_specs, extraction_model=em,
                    forced_faults=(forced_faults if _round == 1 else None),
                    subparity_out=(subparity_trace if subparity_trace
                                   is not None else None))
                (x_out if kind == "X" else z_out)[check.index] = outcome
                if hooked:
                    hook_events.append((_round, kind, check.index))
                if vflag:
                    # AD-022 flagged round: the cat verification
                    # REJECTED. Recorded explicitly; the outcome bit is
                    # the measured parity and any data error is counted
                    # -- nothing is silently dropped or postselected.
                    verification_events.append(
                        (_round, kind, check.index))
        observed.append((tuple(x_out), tuple(z_out)))

    data_ex = sum(1 << q for q in range(n) if ax[q])
    data_ez = sum(1 << q for q in range(n) if az[q])
    # 6-tuple return: (data_x, data_z, hook_events, observed_syndromes,
    # measured_families_per_round, verification_events). The last two
    # are [] for the baseline extraction.
    return (data_ex, data_ez, hook_events, observed,
            measured_families, verification_events)


def simulate_circuit_level_4tuple(code, rounds, p_gate, p_readout, p_reset, p_prep,
                                  *, seed, schedules=None, extraction_model=None,
                                  interleave: str = "none"):
    """Backward-compatible wrapper that returns the original 4-tuple
    (data_ex, data_ez, hook_events, observed_syndromes), discarding
    the `measured_families` trace. Use this if your code does not
    need the temporal-interleaving observation trace.
    """
    return simulate_circuit_level(
        code, rounds, p_gate, p_readout, p_reset, p_prep,
        seed=seed, schedules=schedules, extraction_model=extraction_model,
        interleave=interleave)[:4]


def decode_circuit_level(code, rounds, p_gate, p_readout, p_reset, p_prep,
                         *, data_error_x, data_error_z, observed_syndromes,
                         hook_events=(), seed=None):
    """Feed a circuit-level history into the existing repeated-round decoder."""
    result = decode_repeated(
        code, rounds, p_gate, p_readout,
        data_error_x=data_error_x, data_error_z=data_error_z,
        observed_syndromes=observed_syndromes, seed=seed,
        error_model="circuit_level")
    result.hook_events = list(hook_events)
    return result


def simulate_circuit_level_mc(d, rounds, p_gate, p_readout, p_reset, p_prep, *,
                              trials, seed, extraction_model=None):
    """Circuit-level Monte Carlo logical-error estimate (reuses decode_repeated
    + Wilson interval).

    `extraction_model`: optional extraction name (e.g.
    "shor_cat_state"); default None = the baseline H-CNOT-H
    circuit. The extraction choice is echoed in the result under
    "extraction_model" and included in the note."""
    if d not in _SUPPORTED_DISTANCES:
        raise ValueError(f"Unsupported distance {d}; use {list(_SUPPORTED_DISTANCES)}.")
    if rounds < 1 or rounds > _MAX_ROUNDS:
        raise ValueError(f"rounds must be within [1, {_MAX_ROUNDS}], got {rounds}.")
    for p, name in ((p_gate, "p_gate"), (p_readout, "p_readout"),
                    (p_reset, "p_reset"), (p_prep, "p_prep")):
        if not (0 <= p <= 1):
            raise ValueError(f"{name} must be within [0,1].")
    if trials <= 0:
        raise ValueError("trials must be positive.")
    em = None
    if extraction_model is not None:
        from .circuit_extraction import get_extraction_model
        em = get_extraction_model(extraction_model)
    code = RotatedSurfaceCode.build(d)
    failures = 0
    total_hooks = 0
    rejected_trials = 0
    conditional_failures = 0   # logical failures in ACCEPTED trials
    for t in range(trials):
        trial_seed = seed + t * 7919
        ex, ez, hooks, obs, _mf, ve = simulate_circuit_level(
            code, rounds, p_gate, p_readout, p_reset, p_prep,
            seed=trial_seed, extraction_model=extraction_model)
        total_hooks += len(hooks)
        rejected = len(ve) > 0
        if rejected:
            rejected_trials += 1
        res = decode_circuit_level(
            code, rounds, p_gate, p_readout, p_reset, p_prep,
            data_error_x=ex, data_error_z=ez, observed_syndromes=obs,
            hook_events=hooks, seed=trial_seed)
        if not res.success:
            failures += 1
            if not rejected:
                conditional_failures += 1
    lo, hi = wilson_interval(failures, trials)
    accepted_trials = trials - rejected_trials
    result = {
        "d": d, "rounds": rounds, "p_gate": p_gate, "p_readout": p_readout,
        "p_reset": p_reset, "p_prep": p_prep, "trials": trials,
        "logical_failures": failures, "logical_error_rate": failures / trials,
        "ci95": [lo, hi], "seed": seed, "decoder": "mwpm",
        "extraction_model": em.name if em is not None else "baseline_h_cnot_h",
        "hook_error_events": total_hooks,
        "accepted_trials": accepted_trials,
        "rejected_trials": rejected_trials,
        "acceptance_rate": accepted_trials / trials,
        "rejection_rate": rejected_trials / trials,
        "conditional_logical_failures": conditional_failures,
        "conditional_logical_error_rate": (
            conditional_failures / accepted_trials
            if accepted_trials > 0 else 0.0),
        "note": (
            "Circuit-level surface-code decoding: explicit ancilla stabilizer "
            "circuits with gate (p_gate), readout (p_readout), reset (p_reset), "
            "and preparation (p_prep) noise, decoded by the repeated-round MWPM. "
            "Single-qubit gates ideal; no hardware or threshold claims. "
            "For verified Shor extraction, rejection (flagged-round) statistics "
            "are reported: logical_error_rate is UNCONDITIONAL over all trials "
            "(the operational metric); conditional_logical_error_rate is over "
            "accepted trials only (a diagnostic, never substituted)."
        ),
    }
    return result