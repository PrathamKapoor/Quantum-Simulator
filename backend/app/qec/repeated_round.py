"""Repeated-round (space-time) surface-code decoding (phenomenological).

Extends the single-shot rotated planar surface code to TEMPORAL decoding via
a two-stage decoder (explicit, validated model; §7-§8, §17-§19).

Model
-----
* Geometry: the existing RotatedSurfaceCode (d = 3, 5, 7); CSS split into an
  X sector (Z data errors detected by X checks) and a Z sector (X data errors
  detected by Z checks), decoded independently (§39).
* R measurement rounds, known-clean start (pre-round syndrome 0).
* Data errors (§9): at each of R "slots" (slot t = the interval immediately
  before measurement t), every data qubit takes an independent depolarizing
  error with probability p_d (I w.p. 1-p_d, else X/Y/Z each p_d/3). Errors are
  PERSISTENT: each new error XORs onto the cumulative data error. Reused:
  stabilizer.random_pauli_errors.
* Measurement errors (§10): every stabilizer measurement in rounds 1..R-1 has
  an independent bit flip w.p. p_m. The FINAL round R is assumed IDEAL (a
  standard, documented choice: without it a final measurement flip is
  indistinguishable from a final data error and would corrupt inference).
  A measurement flip is a TEMPORAL fault, never a data correction (§22).

Decoding: two stages.
  Stage A — temporal: detection events are syndrome differences
      d_t = o_t XOR o_{t-1}  (o_0 = 0), layers 1..R. A persistent data error
      introduced at slot t appears exactly once (layer t); a measurement flip
      at round t in 1..R-1 appears as a pair at (S,t) and (S,t+1). MWPM on a
      space-time graph reconstructs both. Edges (per sector):
        SPATIAL   (S1,t)-(S2,t) same layer, cost chain_len * w_s  (data error)
        LATERAL   (S,t)->boundary, cost exit_len * w_s (every layer; data exit)
        TEMPORAL  (S,t)-(S,t+1), cost w_m (measurement flip)
  Stage B — final residual: the last observed syndrome o_R minus the syndrome
      already explained by Stage A's data correction is one final data
      residual, decoded with the EXISTING single-shot decoder (spatial +
      lateral only), returning the final data correction.

Residual & classification (§20-§22): correction = Stage A data correction XOR
Stage B final correction; the residual = correction XOR cumulative true data
error is classified with the existing coset functionals into CORRECTED /
LOGICAL_X / LOGICAL_Z / LOGICAL_Y, exactly as single-shot. Zero-syndrome
logical operators (a bare logical string) still fire the functional (§33).

Weights (§15): w_s = -ln((p_d/3)/(1-p_d)), w_m = -ln(p_m/(1-p_m)),
integer-quantized to 1e-6 so the existing EXACT integer matcher is reused and
matching stays deterministic. Under the independent per-location model this
is maximum-likelihood decoding (for THAT model only).

Limits: bounded rounds (1..64), bounded distances, no dense states (§44),
matcher capacity guard retained, no threshold / hardware / circuit-level
claims (§45-§50 are deferred).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .matching import MatchingError, min_weight_perfect_matching
from .pipeline import wilson_interval
from .rotated_surface_code import RotatedSurfaceCode, RotatedSurfaceCodeDecoder
from .stabilizer import random_pauli_errors

_SUPPORTED_DISTANCES = (3, 5, 7)
_MAX_ROUNDS = 64
_WEIGHT_PRECISION = 1_000_000.0
_INF = 10 ** 12


def _quantized(p: float) -> int:
    if p <= 0.0 or p >= 1.0:
        return _INF
    llr = -math.log(p / (1.0 - p))
    return max(1, int(round(llr * _WEIGHT_PRECISION)))


@dataclass
class RepeatedDetectionEvent:
    check_index: int
    check_kind: str
    center: tuple[int, int]
    layer: int

    def to_dict(self) -> dict:
        return {"check_index": self.check_index, "check_kind": self.check_kind,
                "center": list(self.center), "layer": self.layer}


@dataclass
class RepeatedMatch:
    kind: str           # "spatial" | "boundary" | "temporal"
    pauli: str          # correction chain type ("X"/"Z"); "" for temporal
    a: RepeatedDetectionEvent
    b: RepeatedDetectionEvent | None
    exit_qubit: int | None
    weight: int
    chain: tuple[int, ...]

    def to_dict(self) -> dict:
        return {"kind": self.kind, "pauli": self.pauli,
                "a": self.a.to_dict(), "b": self.b.to_dict() if self.b else None,
                "exit_qubit": self.exit_qubit, "weight": self.weight,
                "chain": list(self.chain)}


@dataclass
class RepeatedRoundResult:
    d: int
    rounds: int
    p_data: float
    p_measurement: float
    error_model: str
    seed: int | None
    data_error_x: int
    data_error_z: int
    measurement_flips: list[tuple[int, str, int]]
    observed_syndromes: list[tuple[tuple[int, ...], tuple[int, ...]]]
    detection_events: list[RepeatedDetectionEvent]
    matching: list[RepeatedMatch]
    matching_weight: int
    correction_x: int
    correction_z: int
    residual_x: int
    residual_z: int
    outcome: str
    success: bool
    error: str | None = None
    hook_events: list = field(default_factory=list)  # circuit-level only

    def _support(self, mask: int) -> list[int]:
        n = self.d * self.d
        return [q for q in range(n) if mask >> q & 1]

    def to_dict(self) -> dict:
        return {
            "d": self.d, "rounds": self.rounds, "p_data": self.p_data,
            "p_measurement": self.p_measurement, "error_model": self.error_model,
            "seed": self.seed,
            "data_error": {"X": self._support(self.data_error_x),
                           "Z": self._support(self.data_error_z)},
            "measurement_flips": [
                {"round": r, "check_kind": k, "check_index": i}
                for (r, k, i) in self.measurement_flips],
            "observed_syndromes": [
                {"round": t + 1,
                 "x_check_bits": list(self.observed_syndromes[t][0]),
                 "z_check_bits": list(self.observed_syndromes[t][1])}
                for t in range(self.rounds)],
            "detection_events": [e.to_dict() for e in self.detection_events],
            "matching": [m.to_dict() for m in self.matching],
            "matching_weight": self.matching_weight,
            "correction": {"X": self._support(self.correction_x),
                           "Z": self._support(self.correction_z)},
            "residual": {"X": self._support(self.residual_x),
                         "Z": self._support(self.residual_z)},
            "outcome": self.outcome, "success": self.success,
            "decoder": "mwpm", "decoder_error": self.error,
        }


def sample_repeated(code, rounds, p_data, p_measurement, *, error_model, seed):
    """Sample one persistent error + measurement history (deterministic).

    Returns (cumulative X error, cumulative Z error, measurement flips
    [(round, check_kind, check_index)], observed syndromes [(x_bits, z_bits)]).
    """
    if rounds < 1 or rounds > _MAX_ROUNDS:
        raise ValueError(f"rounds must be within [1, {_MAX_ROUNDS}], got {rounds}.")
    n = code.d * code.d
    n_x = len(code.x_checks)
    n_z = len(code.z_checks)
    rng = np.random.default_rng(seed)
    if error_model == "depolarizing":
        labels = random_pauli_errors(n, p_data, rounds, rng)
    elif error_model == "x_only":
        labels = np.where(rng.random((rounds, n)) < p_data, 1, 0)
    elif error_model == "z_only":
        labels = np.where(rng.random((rounds, n)) < p_data, 3, 0)
    else:
        raise ValueError(f"Unsupported error model {error_model!r}.")

    decoder = RotatedSurfaceCodeDecoder(code)
    ex = ez = 0
    flips: list[tuple[int, str, int]] = []
    observed: list[tuple[tuple[int, ...], tuple[int, ...]]] = []
    for t in range(1, rounds + 1):
        # slot-t data error accumulates onto the persistent error.
        for q in range(n):
            v = int(labels[t - 1][q])
            if v in (1, 2):
                ex ^= 1 << q
            if v in (2, 3):
                ez ^= 1 << q
        syn_x, syn_z = decoder.syndrome(ex, ez)
        # measurement flips on rounds 1..R-1 only (final round is ideal).
        fx = np.zeros(n_x, dtype=bool)
        fz = np.zeros(n_z, dtype=bool)
        if t < rounds:
            fx = rng.random(n_x) < p_measurement
            fz = rng.random(n_z) < p_measurement
            for i, flag in enumerate(fx):
                if flag:
                    flips.append((t, "X", i))
            for i, flag in enumerate(fz):
                if flag:
                    flips.append((t, "Z", i))
        observed.append((
            tuple(int(b) ^ int(f) for b, f in zip(syn_x, fx)),
            tuple(int(b) ^ int(f) for b, f in zip(syn_z, fz)),
        ))
    return ex, ez, flips, observed


def _diff_events_sector(checks, observed_bits):
    """Detection events (layers 1..R) = syndrome differences for one sector."""
    n_c = len(checks)
    prev = tuple(0 for _ in range(n_c))
    events: list[tuple[int, int]] = []
    for t, bits in enumerate(observed_bits):
        layer = t + 1
        for i in range(n_c):
            if bits[i] ^ prev[i]:
                events.append((layer, i))
        prev = tuple(bits)
    return events


def _match_sector(checks, graph, events, pauli, w_s, w_m):
    """MWPM over one CSS sector's space-time layers (Stage A).

    Returns (RepeatedDetectionEvent list, RepeatedMatch list, correction
    bitmask, weight)."""
    dist = graph["dist"]
    path = graph["path"]
    dist_exit = graph["dist_exit"]
    path_exit = graph["path_exit"]
    cells = sorted(events)
    vertex = {c: k for k, c in enumerate(cells)}

    weights: dict[tuple[int, int], int] = {}
    exit_weights: dict[int, int] = {}
    for k, (layer, ci) in enumerate(cells):
        # spatial: same layer (cells are sorted; same-layer neighbours follow k)
        for k2 in range(k + 1, len(cells)):
            layer2, cj = cells[k2]
            if layer2 != layer:
                break
            w = dist.get((ci, cj), dist.get((cj, ci)))
            if w is not None:
                weights[(k, k2)] = w * w_s
        # temporal: same check, next layer
        nxt = (layer + 1, ci)
        if nxt in vertex:
            weights[(k, vertex[nxt])] = w_m
        # lateral boundary exit
        opts = sorted((w, q) for (cc, q), w in dist_exit.items() if cc == ci)
        if opts:
            exit_weights[k] = opts[0][0] * w_s

    if not cells:
        return [], [], 0, 0
    weight, pairs = min_weight_perfect_matching(weights, exit_weights)

    corr = 0
    matches: list[RepeatedMatch] = []
    det_events = [RepeatedDetectionEvent(checks[ci].index, checks[ci].kind,
                                         checks[ci].center, layer)
                  for (layer, ci) in cells]
    for a, b in pairs:
        _, ci = cells[a]
        if b == -1:
            opts = sorted((w, q) for (cc, q), w in dist_exit.items() if cc == ci)
            q = opts[0][1]
            ch = path_exit[(ci, q)]
            corr ^= sum(1 << x for x in ch)
            matches.append(RepeatedMatch(
                kind="boundary", pauli=pauli, a=det_events[a], b=None,
                exit_qubit=q, weight=opts[0][0] * w_s, chain=ch))
        else:
            layer_a, ci_a = cells[a]
            layer_b, cj = cells[b]
            if layer_a == layer_b:
                ch = path.get((ci, cj)) or path.get((cj, ci))
                if ch is None:
                    raise MatchingError(f"No spatial chain {(ci, cj)}.")
                w = dist.get((ci, cj), dist.get((cj, ci)))
                corr ^= sum(1 << x for x in ch)
                matches.append(RepeatedMatch(
                    kind="spatial", pauli=pauli, a=det_events[a],
                    b=det_events[b], exit_qubit=None, weight=w * w_s, chain=ch))
            else:
                matches.append(RepeatedMatch(
                    kind="temporal", pauli="", a=det_events[a],
                    b=det_events[b], exit_qubit=None, weight=w_m, chain=()))
    return det_events, matches, corr, weight


def _parity(mask: int) -> int:
    return bin(mask).count("1") % 2


def decode_repeated(code, rounds, p_data, p_measurement, *, data_error_x,
                    data_error_z, observed_syndromes, seed=None,
                    error_model="explicit"):
    """Decode a repeated-round history (explicit injected case)."""
    if rounds < 1 or rounds > _MAX_ROUNDS:
        raise ValueError(f"rounds must be within [1, {_MAX_ROUNDS}], got {rounds}.")
    if len(observed_syndromes) != rounds:
        raise ValueError("observed_syndromes length must equal rounds.")
    decoder = RotatedSurfaceCodeDecoder(code)
    w_s, w_m = _weights(p_data, p_measurement)
    obs_x = [o[0] for o in observed_syndromes]
    obs_z = [o[1] for o in observed_syndromes]

    events_all: list[RepeatedDetectionEvent] = []
    matches_all: list[RepeatedMatch] = []
    total_weight = 0
    cx = cz = 0

    # Stage A: temporal MWPM over difference layers.
    for sector in ("x", "z"):
        if sector == "x":
            checks, graph, bits, pauli = (code.x_checks,
                                          code.z_correction_graph, obs_x, "Z")
        else:
            checks, graph, bits, pauli = (code.z_checks,
                                          code.x_correction_graph, obs_z, "X")
        events = _diff_events_sector(checks, bits)
        evs, ms, corr, wt = _match_sector(checks, graph, events, pauli, w_s, w_m)
        events_all.extend(evs)
        matches_all.extend(ms)
        total_weight += wt
        if sector == "x":
            cz |= corr
        else:
            cx |= corr

    # Stage B: final residual syndrome decoded single-shot as data.
    rsx, rsz = decoder.syndrome(cx, cz)
    final_x = tuple(int(o) ^ int(s) for o, s in zip(obs_x[-1], rsx))
    final_z = tuple(int(o) ^ int(s) for o, s in zip(obs_z[-1], rsz))
    for sector, defects_bits, checks, graph, attr in (
        ("x", final_x, code.x_checks, code.z_correction_graph, "cz"),
        ("z", final_z, code.z_checks, code.x_correction_graph, "cx"),
    ):
        defects = [c.index for c, b in zip(checks, defects_bits) if b]
        if not defects:
            continue
        wt, ms, corr, _ = decoder._match_component(defects, graph, checks)
        total_weight += wt
        for cm in ms:
            layer = rounds + 1
            if getattr(cm, "kind", None) == "pair":
                b = RepeatedDetectionEvent(cm.b.check_index, cm.b.check_kind,
                                           cm.b.center, layer)
            else:
                b = None
            matches_all.append(RepeatedMatch(
                kind="spatial" if cm.kind == "pair" else "boundary",
                pauli=cm.pauli,
                a=RepeatedDetectionEvent(cm.a.check_index, cm.a.check_kind,
                                         cm.a.center, layer),
                b=b, exit_qubit=cm.exit_qubit, weight=cm.weight, chain=cm.chain))
        if attr == "cz":
            cz ^= corr
        else:
            cx ^= corr

    rx = cx ^ data_error_x
    rz = cz ^ data_error_z
    x_log = _parity(rx & code.phi_x) == 1
    z_log = _parity(rz & code.phi_z) == 1
    if x_log and z_log:
        outcome = "LOGICAL_Y"
    elif x_log:
        outcome = "LOGICAL_X"
    elif z_log:
        outcome = "LOGICAL_Z"
    else:
        outcome = "CORRECTED"

    return RepeatedRoundResult(
        d=code.d, rounds=rounds, p_data=p_data, p_measurement=p_measurement,
        error_model=error_model, seed=seed, data_error_x=data_error_x,
        data_error_z=data_error_z, measurement_flips=[],
        observed_syndromes=observed_syndromes, detection_events=events_all,
        matching=matches_all, matching_weight=total_weight, correction_x=cx,
        correction_z=cz, residual_x=rx, residual_z=rz, outcome=outcome,
        success=outcome == "CORRECTED",
    )


def _weights(p_data, p_measurement):
    return _quantized(p_data / 3.0), _quantized(p_measurement)


def simulate_repeated(d, rounds, p_data, p_measurement, *, trials, seed,
                      error_model="depolarizing"):
    """Monte Carlo logical-error estimate for repeated-round decoding (§52)."""
    if d not in _SUPPORTED_DISTANCES:
        raise ValueError(f"Unsupported distance {d}; use {list(_SUPPORTED_DISTANCES)}.")
    if rounds < 1 or rounds > _MAX_ROUNDS:
        raise ValueError(f"rounds must be within [1, {_MAX_ROUNDS}], got {rounds}.")
    if not (0 <= p_data <= 1) or not (0 <= p_measurement <= 1):
        raise ValueError("p_data and p_measurement must be within [0,1].")
    if trials <= 0:
        raise ValueError("trials must be positive.")
    code = RotatedSurfaceCode.build(d)
    failures = 0
    for t in range(trials):
        trial_seed = seed + t * 7919
        ex, ez, flips, obs = sample_repeated(
            code, rounds, p_data, p_measurement, error_model=error_model,
            seed=trial_seed)
        res = decode_repeated(code, rounds, p_data, p_measurement,
                              data_error_x=ex, data_error_z=ez,
                              observed_syndromes=obs, seed=trial_seed,
                              error_model=error_model)
        if not res.success:
            failures += 1
    lo, hi = wilson_interval(failures, trials)
    return {
        "d": d, "rounds": rounds, "p_data": p_data, "p_measurement": p_measurement,
        "error_model": error_model, "trials": trials,
        "logical_failures": failures, "logical_error_rate": failures / trials,
        "ci95": [lo, hi], "seed": seed, "decoder": "mwpm",
        "note": (
            "Repeated-round (space-time) MWPM decoding of the rotated planar "
            "surface code under the PHENOMENOLOGICAL model: independent "
            "per-slot depolarizing data noise (p_data, persistent errors), "
            "independent per-round measurement flips (p_measurement, rounds "
            "1..R-1), and an IDEAL final round. PERFECT stabilizer circuits "
            "(no circuit-level noise). p_L with Wilson 95% interval; no "
            "threshold is claimed."
        ),
    }