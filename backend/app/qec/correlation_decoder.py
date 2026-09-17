"""Correlation-aware circuit decoder (milestone 20, AD-024).

Answers the milestone-19 hypothesis: the phenomenological repeated-round
MWPM is the bottleneck BECAUSE it explains detection events with
independent data-error and measurement-error edges, while a single
CIRCUIT fault can corrupt a check's outcome AND leave a data error —
an event pattern the phenomenological model misprices as a pure
measurement flip, so the data error goes uncorrected (AD-023 measured
20 such mismatched mechanisms per mode at d=5).

Algorithm (exact candidate scoring, hybrid per directive §47):

  1. CONTROL: decode the history with the existing phenomenological
     decoder (`decode_repeated`), cost = matching weight (quantized
     log-odds). This candidate is always available — the control is
     never removed (§48).
  2. CANDIDATES: every fault signature S (from the circuit-derived
     signature database, `circuit_signatures.build_signature_db`) whose
     event pattern is a SUBSET of the observed detection events, and
     whose data effect is non-trivial, proposes an alternative
     explanation: "this specific circuit fault fired at round t".
  3. EXACT RESIDUAL: a candidate's total contribution — its per-round
     syndrome contribution history (superposed: the Pauli frame is
     linear over GF(2)) — is XOR-REMOVED from the observed history and
     the modified history is re-decoded with the same control decoder.
     The candidate's total cost = -ln(p_S/(1-p_S)) + residual matching
     weight; its total correction = S.data_effect XOR residual
     correction.
  4. SELECTION: minimum total cost; ties broken by fewer logical
     failures (the established AD-019 convention). The winner's
     `best_source` records whether the control or a signature won.

The removal is EXACT, not an approximation: at zero background noise
the observed history IS the fault's contribution, and contributions
superpose linearly.

Capacity guards (§41): candidate signatures are prefiltered by price
(their -ln-odds must be below the control's price for the events they
touch) and capped at `_MAX_CANDIDATES` per decode. A malformed history
raises ValueError from the underlying decoder rather than crashing a
worker (the caller converts to a failed result).
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from .circuit_signatures import FaultSignature, SignatureDB, build_signature_db
from .repeated_round import RepeatedRoundResult, decode_repeated

_WEIGHT_PRECISION = 1_000_000.0
_MAX_CANDIDATES = 8
# Two-fault attribution (AD-025): pairs are generated from the K_PAIR_BASE
# cheapest prefiltered single candidates (<= K_PAIR_BASE*(K_PAIR_BASE-1)/2
# pairs), compete with singles in ONE price-sorted candidate space, and
# share the same residual-decode budget (branch-and-bound + cap).
K_PAIR_BASE = 6
_MAX_PAIR_CANDIDATES = 3
_MAX_SINGLE_DECODES = 8   # the milestone-20 single-fault budget (regression-pinned)
_MAX_PAIR_DECODES = 3


@dataclass
class CorrelationDecoderResult:
    d: int
    rounds: int
    correction_x: int
    correction_z: int
    residual_x: int
    residual_z: int
    outcome: str
    success: bool
    matching_weight: int            # residual weight of the winning explanation
    total_cost: float               # log-odds cost of the winning explanation
    best_source: str                # "phenomenological" | "signature"
    attributed_signature: tuple | None   # winning signature's example fault
    attributed_round: int | None
    n_candidates: int
    phen_weight: int
    seed: int | None = None
    data_error_x: int = 0
    data_error_z: int = 0
    # control-decoder detail (rendering/inspection; same shape as MWPM)
    detection_events: list = field(default_factory=list)
    matching: list = field(default_factory=list)
    hook_events: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "d": self.d, "rounds": self.rounds,
            "data_error": {"X": _support(self.data_error_x),
                           "Z": _support(self.data_error_z)},
            "correction": {"X": _support(self.correction_x),
                           "Z": _support(self.correction_z)},
            "residual": {"X": _support(self.residual_x),
                         "Z": _support(self.residual_z)},
            "outcome": self.outcome, "success": self.success,
            "hook_events": list(self.hook_events),
            "detection_events": [e.to_dict() for e in self.detection_events],
            "matching": [m.to_dict() for m in self.matching],
            "matching_weight": self.matching_weight,
            "total_cost": self.total_cost,
            "best_source": self.best_source,
            "attributed_signature": _serialize_signature(
                self.attributed_signature),
            "attributed_round": self.attributed_round,
            "n_candidates": self.n_candidates,
            "phen_weight": self.phen_weight,
            "seed": self.seed, "decoder": "correlation_aware",
        }


def _support(mask: int) -> list[int]:
    return [q for q in range(mask.bit_length()) if (mask >> q) & 1]


def _serialize_signature(sig) -> list | None:
    """JSON-safe attribution marker: a single fault's location tuple, or
    a two-fault marker as [[...], [...]]."""
    if sig is None:
        return None
    if isinstance(sig, tuple) and len(sig) == 3 and sig[0] == "PAIR":
        return [list(sig[1]), list(sig[2])]
    return list(sig)


def decode_correlation_aware(code, rounds: int, p_gate: float,
                             p_readout: float, p_reset: float, p_prep: float,
                             *, observed_syndromes, data_error_x: int = 0,
                             data_error_z: int = 0,
                             db: SignatureDB | None = None,
                             subparity_trace=None,
                             two_fault: bool = False,
                             seed: int | None = None) -> CorrelationDecoderResult:
    """Decode one circuit-level history with circuit-derived correlated
    fault signatures on top of the phenomenological control.

    `subparity_trace`: the fitted_pair extraction's per-pair readout
    bits (the flat list `simulate_circuit_level` appends to when given
    a `subparity_trace` list). When provided with a sub-parity DB, a
    candidate whose pair-level contribution contradicts the observed
    trace is ranked below consistent candidates — this resolves
    syndrome-degenerate explanations that the full outcomes cannot
    distinguish (directive §19-§20).

    `two_fault` (AD-025): additionally generate TWO-fault candidates —
    pairs of signatures whose XORed contribution is consistent with the
    observed history, priced by the sum of the two bucket log-odds
    (independent faults: the joint log-likelihood-ratio adds; no channel
    is counted twice). Pairs compete with singles in one price-sorted
    candidate space under the same decode budget. The milestone-20
    single-fault behaviour is the two_fault=False default and is
    regression-pinned."""
    if db is None:
        db = build_signature_db(code, rounds, "baseline_h_cnot_h")
    phen = decode_repeated(
        code, rounds, p_gate, p_readout,
        data_error_x=data_error_x, data_error_z=data_error_z,
        observed_syndromes=observed_syndromes, seed=seed,
        error_model="correlation_aware")
    best_cx, best_cz = phen.correction_x, phen.correction_z
    best_weight = phen.matching_weight
    best_cost = best_weight / _WEIGHT_PRECISION
    best_source, best_sig, best_round = "phenomenological", None, None
    n_candidates = 0

    if best_weight > 0:
        checks_by = {}
        for kind, checks in (("X", code.x_checks), ("Z", code.z_checks)):
            for ch in checks:
                checks_by[(kind, ch.index)] = ch

        events = _event_set(phen)
        touched = _touched_weight(phen)
        candidates = []
        for sig, t in db.translated_mid():
            if not sig.data_x and not sig.data_z:
                continue
            sig_events = {(layer + t - 1, kind, index)
                          for layer, kind, index in sig.events}
            if not sig_events.issubset(events):
                continue
            price = sig.log_odds_cost(p_gate, p_readout, p_reset, p_prep)
            if price < touched(sig_events):
                candidates.append((price, sig, t))
        for sig in db.final:
            if not sig.data_x and not sig.data_z:
                continue
            sig_events = {(layer + rounds - 1, kind, index)
                          for layer, kind, index in sig.events}
            if not sig_events.issubset(events):
                continue
            price = sig.log_odds_cost(p_gate, p_readout, p_reset, p_prep)
            if price < touched(sig_events):
                candidates.append((price, sig, rounds))

        # ---- two-fault candidates (AD-025) ----
        pair_candidates = []
        if two_fault:
            # The pair BASE includes data-less signatures (e.g. a pure
            # outcome-corruption fault): useless alone — they propose no
            # correction — but essential pair components that explain
            # the corruption half of a two-fault history.
            base_sigs = []
            for sig, t in db.translated_mid():
                sig_events = {(layer + t - 1, kind, index)
                              for layer, kind, index in sig.events}
                if not sig_events.issubset(events):
                    continue
                price = sig.log_odds_cost(p_gate, p_readout, p_reset, p_prep)
                if price < touched(sig_events):
                    base_sigs.append((price, sig, t))
            for sig in db.final:
                sig_events = {(layer + rounds - 1, kind, index)
                              for layer, kind, index in sig.events}
                if not sig_events.issubset(events):
                    continue
                price = sig.log_odds_cost(p_gate, p_readout, p_reset, p_prep)
                if price < touched(sig_events):
                    base_sigs.append((price, sig, rounds))
            base = sorted(base_sigs, key=lambda c: c[0])[:K_PAIR_BASE]
            for (p1, s1, t1), (p2, s2, t2) in itertools.combinations(base, 2):
                # Combined contribution = XOR per round (the Pauli frame
                # is linear; this is NOT set union — overlapping
                # contributions cancel). Both signatures at the same
                # injection round have equal-length contributions.
                if t1 != t2:
                    continue     # different injection rounds: skip (the
                                 # common two-fault case is same-round)
                comb = tuple(
                    (tuple(xa ^ xb for xa, xb in zip(x1, x2)),
                     tuple(za ^ zb for za, zb in zip(z1, z2)))
                    for (x1, z1), (x2, z2) in zip(s1.contrib, s2.contrib))
                comb_sig = FaultSignature(
                    contrib=comb, data_x=s1.data_x ^ s2.data_x,
                    data_z=s1.data_z ^ s2.data_z, flagged=False,
                    n_reset=0, n_prep=0, n_gate=0, n_readout=0,
                    example=("PAIR", s1.example, s2.example))
                combined_events = {(layer + t1 - 1, kind, index)
                                   for layer, kind, index in comb_sig.events}
                if not combined_events.issubset(events):
                    continue
                if not (comb_sig.data_x or comb_sig.data_z):
                    continue
                price12 = p1 + p2
                if price12 < touched(combined_events):
                    pair_candidates.append((price12, comb_sig, t1))
        candidates = candidates + pair_candidates

        # Price-ascending order enables exact branch-and-bound below:
        # a candidate whose price already reaches the best total cost
        # cannot win (the residual matching weight is non-negative), so
        # the decode loop stops at the first such candidate. Within
        # equal prices, sub-parity consistency then perfection break
        # ties. All quantities are decoder-observable; the selection
        # never consults the true data error (directive §46).
        obs_chunks = None
        if subparity_trace is not None:
            per_round = len(code.x_checks) + len(code.z_checks)
            obs_chunks = [subparity_trace[i:i + per_round]
                          for i in range(0, len(subparity_trace), per_round)]
        ranked = []
        for price, sig, t in candidates:
            modified = _remove_contribution(observed_syndromes, sig, t)
            perfect = not _has_events(modified)
            mism = (_pair_mismatches(sig, t, obs_chunks, rounds)
                    if obs_chunks is not None else 0)
            is_pair = sig.example[0] == "PAIR"
            ranked.append((mism, not perfect, price, is_pair, sig, t,
                           modified))
        # Budget reservation (AD-025 §18): singles and pairs compete in
        # one price-sorted space, but pairs get a guaranteed small slot
        # count so cheap singles cannot crowd them out entirely (on a
        # two-fault history the singles cannot explain it and the pairs
        # are the only adequate explanations). Branch-and-bound below
        # still bounds the actual decode count by price.
        singles = sorted((c for c in ranked if not c[3]),
                         key=lambda c: (c[2], c[0], c[1]))[:_MAX_CANDIDATES]
        # FALSE-ATTRIBUTION GUARD (AD-025 §19): a PERFECT single — one
        # whose removal leaves a completely clean history — fully
        # explains the observed data with ONE fault. Two faults is then
        # strictly less likely a priori (P(single) > P(pair) for
        # independent small-p channels), so pairs are admitted only when
        # NO perfect single exists. This is decoder-observable (perfect
        # is computed from the history alone) and eliminates the
        # single-vs-pair tie that degenerate prices cannot resolve.
        perfect_single = any(not c[1] for c in singles)
        pairs = ([] if perfect_single else
                 sorted((c for c in ranked if c[3]),
                        key=lambda c: (c[2], c[0], c[1]))[:_MAX_PAIR_CANDIDATES])
        ranked = sorted(singles + pairs, key=lambda c: (c[2], c[0], c[1]))
        n_candidates = len(ranked)

        # Reserved decode budgets per class (AD-025 §18): cheap singles
        # decode first, but pairs keep their own allowance — on a
        # two-fault history the singles cannot explain it and the pairs
        # are the only adequate explanations. Branch-and-bound applies
        # within each class.
        n_single_decodes = 0
        n_pair_decodes = 0
        for _mism, _imperfect, price, is_pair, sig, t, modified in ranked:
            if is_pair:
                if n_pair_decodes >= _MAX_PAIR_DECODES or price >= best_cost:
                    continue
                n_pair_decodes += 1
            else:
                if (n_single_decodes >= _MAX_SINGLE_DECODES
                        or price >= best_cost):
                    continue
                n_single_decodes += 1
            resid = decode_repeated(
                code, rounds, p_gate, p_readout,
                data_error_x=data_error_x, data_error_z=data_error_z,
                observed_syndromes=modified, seed=seed,
                error_model="correlation_aware_residual")
            total = price + resid.matching_weight / _WEIGHT_PRECISION
            cx = resid.correction_x ^ sig.data_x
            cz = resid.correction_z ^ sig.data_z
            # Selection: minimum total cost; ties by the residual
            # matching weight (decoder-observable). The logical class of
            # the residual is deliberately NOT used for selection — it
            # would peek at the true data error (§46).
            if (total, resid.matching_weight) < (best_cost, best_weight):
                best_cx, best_cz = cx, cz
                best_weight = resid.matching_weight
                best_cost = total
                best_source = ("signature_pair"
                               if sig.example[0] == "PAIR" else "signature")
                best_sig, best_round = sig.example, t

    rx = best_cx ^ data_error_x
    rz = best_cz ^ data_error_z
    x_log = bin(rx & code.phi_x).count("1") & 1
    z_log = bin(rz & code.phi_z).count("1") & 1
    outcome = ("LOGICAL_Y" if x_log and z_log else
               "LOGICAL_X" if x_log else "LOGICAL_Z" if z_log else "CORRECTED")
    return CorrelationDecoderResult(
        d=code.d, rounds=rounds, correction_x=best_cx, correction_z=best_cz,
        residual_x=rx, residual_z=rz, outcome=outcome,
        success=outcome == "CORRECTED", matching_weight=best_weight,
        total_cost=best_cost, best_source=best_source,
        attributed_signature=best_sig, attributed_round=best_round,
        n_candidates=n_candidates, phen_weight=phen.matching_weight,
        seed=seed, data_error_x=data_error_x, data_error_z=data_error_z,
        detection_events=phen.detection_events,
        matching=phen.matching)


def _has_events(history) -> bool:
    """True if any syndrome bit is set anywhere in the history."""
    return any(any(xb) or any(zb) for (xb, zb) in history)


def _pair_mismatches(sig, t_inj: int, obs_chunks, rounds: int) -> int:
    """Count how often the candidate's pair-level contribution claims a
    flipped sub-parity bit that the observed trace shows as 0. Each
    mismatch requires ANOTHER fault to have cancelled the flip, so a
    candidate with more mismatches is a less plausible explanation."""
    mism = 0
    for r, entries in enumerate(sig.pair_contrib):
        u = t_inj + r          # absolute round (1-based)
        if u > rounds:
            break
        chunk = obs_chunks[u - 1]
        obs_by = {(kind, ci): tuple(bits) for (kind, ci, bits) in chunk}
        for (kind, ci, bits) in entries:
            obs_bits = obs_by.get((kind, ci), ())
            for j, b in enumerate(bits):
                if b and (j >= len(obs_bits) or not obs_bits[j]):
                    mism += 1
    return mism


def _event_set(phen: RepeatedRoundResult) -> set:
    """All detection events of the control explanation, including the
    final-residual sentinel layer R+1."""
    return {(e.layer, e.check_kind, e.check_index) for e in phen.detection_events}


def _touched_weight(phen: RepeatedRoundResult):
    """map: events -> control weight of the matches touching ANY of
    those events (a strict over-estimate when one match explains
    several events, so the prefilter can only under-propose, never
    mis-score)."""
    cache: dict[frozenset, int] = {}

    def lookup(events) -> int:
        key = frozenset(events)
        if key in cache:
            return cache[key]
        total = 0
        for m in phen.matching:
            m_events = {(m.a.layer, m.a.check_kind, m.a.check_index)}
            if m.b is not None:
                m_events.add((m.b.layer, m.b.check_kind, m.b.check_index))
            if m_events & key:
                total += m.weight
        cache[key] = total
        return total
    return lookup


def _remove_contribution(observed_syndromes, sig, t_inj: int):
    """Exact removal of one fault's contribution from the history:
    modified[u] = observed[u] XOR contrib[u - t_inj] for u >= t_inj
    (contrib[0] is the injection round's contribution). The Pauli
    frame is linear, so this removes the fault's total contribution —
    outcome corruption AND data-error syndrome — in one step."""
    L = len(sig.contrib)
    modified = []
    for u, (xb, zb) in enumerate(observed_syndromes, start=1):
        if u < t_inj:
            modified.append((tuple(xb), tuple(zb)))
            continue
        cx, cz = sig.contrib[u - t_inj]
        nx = tuple(b ^ c for b, c in zip(xb, cx))
        nz = tuple(b ^ c for b, c in zip(zb, cz))
        modified.append((nx, nz))
    assert L == len(observed_syndromes) - t_inj + 1
    return modified


def simulate_decoder_comparison_mc(d, rounds, p_gate, p_readout: float,
                                   p_reset: float, p_prep: float, *,
                                   trials: int, seed: int,
                                   extraction_model: str):
    """Paired Monte Carlo: the phenomenological control and the
    correlation-aware decoder on IDENTICAL trials (same seeds, same
    circuit sampling — directive §27). Returns per-decoder failure
    counts, Wilson 95% intervals, and decoder diagnostics.

    This is the milestone-20 headline instrument: any p_L difference
    between the two decoders on the same trials is attributable to the
    decoder alone."""
    from .pipeline import wilson_interval
    from .circuit_level import simulate_circuit_level, decode_circuit_level
    from .rotated_surface_code import RotatedSurfaceCode

    if d not in (3, 5, 7):
        raise ValueError(f"Unsupported distance {d}; use [3, 5, 7].")
    if trials <= 0:
        raise ValueError("trials must be positive.")
    code = RotatedSurfaceCode.build(d)
    db = build_signature_db(code, rounds, extraction_model)
    phen_fail = corr_fail = pair_fail = 0
    n_attributed = 0
    n_pair_attributed = 0
    n_candidates_total = 0
    import time
    decode_time = 0.0
    for t in range(trials):
        trial_seed = seed + t * 7919
        ex, ez, hooks, obs, _mf, _ve = simulate_circuit_level(
            code, rounds, p_gate, p_readout, p_reset, p_prep,
            seed=trial_seed, extraction_model=extraction_model)
        rp = decode_circuit_level(
            code, rounds, p_gate, p_readout, p_reset, p_prep,
            data_error_x=ex, data_error_z=ez, observed_syndromes=obs,
            hook_events=hooks, seed=trial_seed)
        t0 = time.perf_counter()
        rc = decode_correlation_aware(
            code, rounds, p_gate, p_readout, p_reset, p_prep,
            observed_syndromes=obs, data_error_x=ex, data_error_z=ez,
            db=db, seed=trial_seed)
        r2 = decode_correlation_aware(
            code, rounds, p_gate, p_readout, p_reset, p_prep,
            observed_syndromes=obs, data_error_x=ex, data_error_z=ez,
            db=db, two_fault=True, seed=trial_seed)
        decode_time += time.perf_counter() - t0
        if not rp.success:
            phen_fail += 1
        if not rc.success:
            corr_fail += 1
        if not r2.success:
            pair_fail += 1
        if rc.best_source == "signature":
            n_attributed += 1
        if r2.best_source == "signature_pair":
            n_pair_attributed += 1
        n_candidates_total += rc.n_candidates
    plo, phi = wilson_interval(phen_fail, trials)
    clo, chi = wilson_interval(corr_fail, trials)
    tlo, thi = wilson_interval(pair_fail, trials)
    return {
        "d": d, "rounds": rounds, "p_gate": p_gate, "p_readout": p_readout,
        "p_reset": p_reset, "p_prep": p_prep, "trials": trials,
        "seed": seed, "extraction_model": extraction_model,
        "phenomenological": {
            "logical_failures": phen_fail,
            "logical_error_rate": phen_fail / trials,
            "ci95": [plo, phi],
        },
        "correlation_aware": {
            "logical_failures": corr_fail,
            "logical_error_rate": corr_fail / trials,
            "ci95": [clo, chi],
            "signature_attributions": n_attributed,
            "avg_candidates": n_candidates_total / trials,
            "decode_seconds": decode_time,
        },
        "correlation_aware_two_fault": {
            "logical_failures": pair_fail,
            "logical_error_rate": pair_fail / trials,
            "ci95": [tlo, thi],
            "pair_attributions": n_pair_attributed,
        },
        "note": (
            "Paired decoder comparison on identical circuit-level trials "
            "(same seeds, same noise sampling). phenomenological = "
            "repeated-round MWPM (the milestone control); "
            "correlation_aware = the control plus likelihood-priced "
            "circuit-fault signature attribution (AD-024). Wilson 95% "
            "intervals; no threshold or hardware claims."),
    }


def simulate_correlation_mc(d, rounds, p_gate, p_readout: float,
                            p_reset: float, p_prep: float, *,
                            trials: int, seed: int,
                            extraction_model: str):
    """Monte Carlo with the correlation-aware decoder alone (the
    experiment-runner entry point). Same trial-seed convention as
    `simulate_circuit_level_mc` so results are directly comparable."""
    from .pipeline import wilson_interval
    from .circuit_level import simulate_circuit_level
    from .rotated_surface_code import RotatedSurfaceCode

    if d not in (3, 5, 7):
        raise ValueError(f"Unsupported distance {d}; use [3, 5, 7].")
    if trials <= 0:
        raise ValueError("trials must be positive.")
    code = RotatedSurfaceCode.build(d)
    db = build_signature_db(code, rounds, extraction_model)
    failures = 0
    total_hooks = 0
    rejected_trials = 0
    conditional_failures = 0
    attributions = 0
    candidates_total = 0
    for t in range(trials):
        trial_seed = seed + t * 7919
        ex, ez, hooks, obs, _mf, ve = simulate_circuit_level(
            code, rounds, p_gate, p_readout, p_reset, p_prep,
            seed=trial_seed, extraction_model=extraction_model)
        total_hooks += len(hooks)
        rejected = len(ve) > 0
        if rejected:
            rejected_trials += 1
        res = decode_correlation_aware(
            code, rounds, p_gate, p_readout, p_reset, p_prep,
            observed_syndromes=obs, data_error_x=ex, data_error_z=ez,
            db=db, seed=trial_seed)
        if res.best_source == "signature":
            attributions += 1
        candidates_total += res.n_candidates
        if not res.success:
            failures += 1
            if not rejected:
                conditional_failures += 1
    lo, hi = wilson_interval(failures, trials)
    accepted = trials - rejected_trials
    return {
        "d": d, "rounds": rounds, "p_gate": p_gate, "p_readout": p_readout,
        "p_reset": p_reset, "p_prep": p_prep, "trials": trials,
        "logical_failures": failures, "logical_error_rate": failures / trials,
        "ci95": [lo, hi], "seed": seed, "decoder": "correlation_aware",
        "extraction_model": extraction_model,
        "hook_error_events": total_hooks,
        "accepted_trials": accepted,
        "rejected_trials": rejected_trials,
        "acceptance_rate": accepted / trials,
        "rejection_rate": rejected_trials / trials,
        "conditional_logical_failures": conditional_failures,
        "conditional_logical_error_rate": (
            conditional_failures / accepted if accepted > 0 else 0.0),
        "signature_attributions": attributions,
        "avg_candidates": candidates_total / trials,
        "note": (
            "Circuit-level decoding with the CORRELATION-AWARE decoder "
            "(AD-024): the repeated-round MWPM control plus "
            "likelihood-priced circuit-fault signature attribution derived "
            "from the production forced-fault harness. All acceptance/"
            "rejection accounting matches the phenomenological runner. "
            "No hardware or threshold claims."),
    }
