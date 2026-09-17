"""Circuit-derived fault-signature database (milestone 20, AD-024).

For every elementary single fault of every supported extraction model,
this module records what the PRODUCTION simulator does with it:

    fault location --(forced-fault harness, zero background noise)-->
    per-round syndrome contribution (x_bits, z_bits per round)
    + net data error (Pauli frame)
    + whether cat verification flagged the round (verified mode)

At zero background noise the observed history IS the fault's
contribution, and the Pauli frame is linear over GF(2) — so a fault's
contribution to a noisy run is exactly this history (superposed with
the other faults' contributions). The database is therefore
NOISE-INDEPENDENT: the contribution pattern is deterministic circuit
propagation, while the likelihood comes from the noise configuration
at decode time through per-channel location counts. This separation is
what makes the database cacheable per (d, rounds, extraction_model)
(directive §34).

Time structure. The forced-fault harness injects in ROUND 1 (the
documented contract). Because every round re-runs the same per-check
circuit, a fault at round t (1 <= t <= R-1) has the SAME signature with
its contribution history shifted: contrib[u - t] applies to round u
(contrib[0] is the injection round's contribution). The FINAL round is
special (ideal reset/prep/readout by the established decode_repeated
contract; only gate faults exist), so final-round signatures are built
separately by injecting into a rounds=1 circuit (whose only round IS
the final round).

Why this exists (milestone-19 evidence, AD-023): the phenomenological
repeated-round MWPM explains detection events with independent
data-error and measurement-error edges. A single CIRCUIT fault that
corrupts a check's outcome AND leaves a data error produces an event
pattern the phenomenological model misprices as a pure measurement
flip — the data error goes uncorrected. The signature database is the
decoder-side representation of those correlated mechanisms, for ALL
extraction modes (the milestone-13 fault catalogue covered only the
baseline single-ancilla circuit).

Probability model (directive §17: no invented weights). Each signature
aggregates the count of fault LOCATIONS that produce it, per noise
channel:
    reset   : p_reset      (X fault on the ancilla, w.p. p_reset)
    prep    : p_prep / 3   (depolarizing: X, Y, or Z each p_prep/3)
    gate    : p_gate / 3   (per CNOT participant, depolarizing)
    readout : p_readout    (measurement-bit flip)
A signature produced by k alternative locations has first-order
probability sum(channel_count_i * channel_p_i) (exact union up to
O(p^2); documented approximation, consistent with the small-p regime
the simulator targets). The decoder converts to a log-odds cost
-ln(p/(1-p)) — the same convention as the phenomenological matcher's
edge weights, so candidate costs are directly comparable.
"""
from __future__ import annotations

from dataclasses import dataclass

from .circuit_extraction import (
    EXTRACTION_BASELINE, EXTRACTION_SHOR, EXTRACTION_SHOR_VERIFIED,
    EXTRACTION_FITTED, get_extraction_model,
)
from .circuit_level import simulate_circuit_level

# Module-level cache (§34): signatures depend only on (d, rounds,
# extraction) — never on noise or seeds. Bounded by construction:
# 3 distances x up to 64 rounds x 4 modes.
_CACHE: dict[tuple, "SignatureDB"] = {}

_CHANNELS = ("reset", "prep", "gate", "readout")


@dataclass(frozen=True)
class FaultSignature:
    """One correlated single-fault mechanism of the production circuit.

    contrib   : the fault's EXACT contribution to the syndrome history,
                one (x_bits, z_bits) tuple per round of the injection
                simulation. A mid-round fault injected at absolute round
                t applies contrib[u - t] to round u (contrib[0] is the
                injection round's contribution); a final-round signature
                has exactly one entry.
    data_x/z  : net data-error bitmask the fault leaves on the data frame.
    flagged   : True if cat verification REJECTED the round (verified
                mode only); such rounds are confirmed outcome corruption.
    n_reset/n_prep/n_gate/n_readout : how many elementary fault
                locations produce exactly this signature, per channel
                (the likelihood aggregate; see module docstring).
    example   : the forced-fault tuple of one representative location
                (diagnostics/tests only).

    events    : derived property — detection events (layer, kind,
                check_index) = syndrome differences of contrib.
    """
    contrib: tuple
    data_x: int
    data_z: int
    flagged: bool
    n_reset: int
    n_prep: int
    n_gate: int
    n_readout: int
    example: tuple
    # Sub-parity contribution (fitted_pair only, milestone-20 §19-§20
    # experiment): per-round sparse entries ((kind, ci, pair_bits), ...)
    # recording which PAIR readout bits the fault flips — the
    # information the XOR into the stabilizer outcome discards. Empty
    # tuple for modes without sub-parity structure.
    pair_contrib: tuple = ()

    @property
    def events(self) -> tuple:
        """Detection-event pattern, derived from contrib once and
        cached (hot path: the decoder scans every translated signature
        on every Monte Carlo trial)."""
        cached = self.__dict__.get("_events")
        if cached is None:
            cached = _events_from_contrib(self.contrib)
            object.__setattr__(self, "_events", cached)
        return cached

    @property
    def events_set(self) -> frozenset:
        cached = self.__dict__.get("_events_set")
        if cached is None:
            cached = frozenset(self.events)
            object.__setattr__(self, "_events_set", cached)
        return cached

    @property
    def data_weight(self) -> int:
        return bin(self.data_x).count("1") + bin(self.data_z).count("1")

    def probability(self, p_gate: float, p_readout: float,
                    p_reset: float, p_prep: float) -> float:
        """First-order total probability over alternative locations."""
        return (self.n_reset * p_reset
                + self.n_prep * p_prep / 3.0
                + self.n_gate * p_gate / 3.0
                + self.n_readout * p_readout)

    def log_odds_cost(self, p_gate: float, p_readout: float,
                      p_reset: float, p_prep: float) -> float:
        """-ln(p/(1-p)) — comparable with the phenomenological matcher's
        quantized edge weights (same convention, unquantized here)."""
        import math
        p = min(max(self.probability(p_gate, p_readout, p_reset, p_prep),
                    1e-12), 1.0 - 1e-12)
        return -math.log(p / (1.0 - p))


@dataclass
class SignatureDB:
    """All single-fault signatures of one (code, rounds, extraction)."""
    d: int
    rounds: int
    extraction_model: str
    # Mid-round signatures (valid at injection rounds 1..rounds-1);
    # contrib covers rounds t..R for injection round t.
    mid: list[FaultSignature]
    # Final-round signatures (gate faults only; the final round has an
    # ideal reset/prep/readout). contrib has exactly one entry.
    final: list[FaultSignature]
    n_locations_mid: int
    n_locations_final: int
    # Fault locations whose aggregate effect is EMPTY (no events, no
    # data error): e.g. a fault that lands on the cat as its own
    # stabilizer and flips an even number of outcome bits, or a pure
    # verification false-rejection. They consume noise exposure but
    # there is nothing for a decoder to attribute.
    n_null_locations_mid: int
    n_null_locations_final: int

    @property
    def n_null_locations(self) -> int:
        return self.n_null_locations_mid + self.n_null_locations_final

    def translated_mid(self) -> list[tuple[FaultSignature, int]]:
        """(signature, injection_round) for every mid-round placement,
        with contribution histories translated. Injection rounds
        1..rounds-1 (the final round uses `final`). Cached — the
        translation is deterministic in the DB."""
        cached = getattr(self, "_translated", None)
        if cached is not None:
            return cached
        out = []
        for t in range(1, self.rounds):
            for s in self.mid:
                out.append((s if t == 1 else _shift(s, t - 1), t))
        self._translated = out
        return out


def _shift(s: FaultSignature, delta: int) -> FaultSignature:
    """Keep the injection transient and truncate the shorter history's tail."""
    return FaultSignature(
        contrib=tuple(s.contrib[:len(s.contrib) - delta]),
        data_x=s.data_x, data_z=s.data_z, flagged=s.flagged,
        n_reset=s.n_reset, n_prep=s.n_prep, n_gate=s.n_gate,
        n_readout=s.n_readout, example=s.example,
        pair_contrib=tuple(s.pair_contrib[:len(s.pair_contrib) - delta]))


def _events_from_contrib(contrib: tuple) -> tuple:
    """Detection events (layer, kind, check_index) = syndrome differences
    of a contribution history, layers 1..len(contrib)."""
    events: list[tuple[int, str, int]] = []
    prev_x = tuple(0 for _ in contrib[0][0])
    prev_z = tuple(0 for _ in contrib[0][1])
    for t, (xb, zb) in enumerate(contrib, start=1):
        for i, b in enumerate(xb):
            if b ^ prev_x[i]:
                events.append((t, "X", i))
        for i, b in enumerate(zb):
            if b ^ prev_z[i]:
                events.append((t, "Z", i))
        prev_x, prev_z = tuple(xb), tuple(zb)
    return tuple(sorted(events))


def _elementary_faults(code, em) -> list[tuple]:
    """Every elementary fault location of the extraction's checks
    (the same enumeration the exhaustive tests use)."""
    mode = em.name
    out = []
    for kind, checks in (("X", code.x_checks), ("Z", code.z_checks)):
        for ch in checks:
            k = len(ch.support)
            ci = ch.index
            if mode == EXTRACTION_FITTED:
                n_anc = (k + 1) // 2
            elif mode == EXTRACTION_BASELINE:
                n_anc = 1          # single shared ancilla (index 0)
            else:
                n_anc = k          # one cat ancilla per support qubit
            for i in range(n_anc):
                for p in "XYZ":
                    out.append((kind, ci, "reset", i, None, p))
                    out.append((kind, ci, "prep", i, None, p))
                out.append((kind, ci, "readout", i, None, None))
            n_gates = 2 * k - 1 if mode in (EXTRACTION_SHOR,
                                            EXTRACTION_SHOR_VERIFIED) else k
            for g in range(n_gates):
                for part in "ct":
                    for p in "XYZ":
                        out.append((kind, ci, "cnot", g, part, p))
            if mode == EXTRACTION_SHOR_VERIFIED:
                for p in "XYZ":
                    out.append((kind, ci, "vreset", 0, None, p))
                    out.append((kind, ci, "vprep", 0, None, p))
                for g in range(k):
                    for part in "ct":
                        for p in "XYZ":
                            out.append((kind, ci, "vcnot", g, part, p))
                out.append((kind, ci, "vreadout", 0, None, None))
    return out


def _channel_of(fault: tuple) -> str | None:
    """The noise channel a fault location is drawn from. The verified
    mode's v-stages map onto the same four channels (vreset/vprep are
    the verifier ancilla's reset/prep; vreadout its readout). v-stage
    locations do not exist in the final round, which the caller
    restricts to gate faults."""
    stage = fault[2]
    if stage in ("reset", "vreset"):
        return "reset"
    if stage in ("prep", "vprep"):
        return "prep"
    if stage in ("readout", "vreadout"):
        return "readout"
    if stage in ("cnot", "vcnot"):
        return "gate"
    return None


def _aggregate(agg: dict, key, counts, f, contrib, ex, ez, flagged,
               pair_contrib=()) -> None:
    prev = agg.get(key)
    if prev is None:
        agg[key] = FaultSignature(
            contrib=contrib, data_x=ex, data_z=ez, flagged=flagged,
            n_reset=counts[0], n_prep=counts[1], n_gate=counts[2],
            n_readout=counts[3], example=f, pair_contrib=pair_contrib)
    else:
        agg[key] = FaultSignature(
            contrib=prev.contrib, data_x=prev.data_x, data_z=prev.data_z,
            flagged=prev.flagged,
            n_reset=prev.n_reset + counts[0],
            n_prep=prev.n_prep + counts[1],
            n_gate=prev.n_gate + counts[2],
            n_readout=prev.n_readout + counts[3],
            example=prev.example, pair_contrib=prev.pair_contrib)


def build_signature_db(code, rounds: int, extraction_model: str,
                       collect_subparities: bool = False) -> SignatureDB:
    """Enumerate every elementary single fault through the PRODUCTION
    circuit (forced-fault harness, zero background noise) and aggregate
    the resulting signatures. Deterministic; cached per
    (d, rounds, extraction_model, collect_subparities). With
    `collect_subparities` (fitted_pair only) each signature also
    records which PAIR readout bits it flips (directive §19-§20)."""
    key = (code.d, rounds, extraction_model, collect_subparities)
    if key in _CACHE:
        return _CACHE[key]
    em = get_extraction_model(extraction_model)
    trace_pairs = collect_subparities and extraction_model == EXTRACTION_FITTED

    agg_mid: dict = {}
    agg_final: dict = {}
    n_mid = n_final = n_null_mid = n_null_final = 0
    for f in _elementary_faults(code, em):
        channel = _channel_of(f)
        # ---- mid-round placement (injection round 1 of R rounds) ----
        sub_tr = [] if trace_pairs else None
        ex, ez, _hooks, obs, _mf, ve = simulate_circuit_level(
            code, rounds, 0.0, 0.0, 0.0, 0.0, seed=0,
            extraction_model=extraction_model, forced_faults=[f],
            subparity_trace=sub_tr)
        contrib = tuple((tuple(xb), tuple(zb)) for (xb, zb) in obs)
        pc = _sparse_pair_contrib(sub_tr, code) if trace_pairs else ()
        if not _events_from_contrib(contrib) and not ex and not ez:
            # Benign for CORRECTION purposes: either nothing detectable
            # happened (a cat-stabilizer fault), or the fault only
            # triggered a verification flag without corrupting the
            # syndrome or data (a pure false rejection — it explains
            # rejection statistics, never a correction).
            n_null_mid += 1
        else:
            counts = [0, 0, 0, 0]
            if channel is not None:
                counts[_CHANNELS.index(channel)] = 1
            _aggregate(agg_mid, ((f[0], f[1]), contrib, ex, ez), counts,
                       f, contrib, ex, ez, len(ve) > 0, pc)
        n_mid += 1
        # ---- final-round placement (gate faults only; the final round
        # has an ideal reset/prep/readout) ----
        if channel == "gate":
            ex1, ez1, _h1, obs1, _mf1, ve1 = simulate_circuit_level(
                code, 1, 0.0, 0.0, 0.0, 0.0, seed=0,
                extraction_model=extraction_model, forced_faults=[f])
            contrib1 = tuple((tuple(xb), tuple(zb)) for (xb, zb) in obs1)
            if not _events_from_contrib(contrib1) and not ex1 and not ez1:
                n_null_final += 1
            else:
                _aggregate(agg_final, ((f[0], f[1]), contrib1, ex1, ez1),
                           [0, 0, 1, 0], f, contrib1, ex1, ez1,
                           len(ve1) > 0)
            n_final += 1

    db = SignatureDB(
        d=code.d, rounds=rounds, extraction_model=extraction_model,
        mid=sorted(agg_mid.values(), key=lambda s: (s.data_weight, s.example)),
        final=sorted(agg_final.values(), key=lambda s: (s.data_weight, s.example)),
        n_locations_mid=n_mid, n_locations_final=n_final,
        n_null_locations_mid=n_null_mid, n_null_locations_final=n_null_final)
    _CACHE[key] = db
    return db


def _sparse_pair_contrib(trace, code) -> tuple:
    """Compact a flat sub-parity trace into per-round sparse entries:
    tuple over rounds of ((kind, ci, pair_bits), ...), keeping only
    entries where some pair bit is 1. The flat trace holds
    (len(x_checks) + len(z_checks)) entries per round, in the
    simulation loop's order (all X-checks then all Z-checks)."""
    per_round = len(code.x_checks) + len(code.z_checks)
    rounds_out = []
    for r in range(0, len(trace), per_round):
        entries = tuple((kind, ci, tuple(bits))
                        for (kind, ci, bits) in trace[r:r + per_round]
                        if any(bits))
        rounds_out.append(entries)
    return tuple(rounds_out)


__all__ = ["FaultSignature", "SignatureDB", "build_signature_db"]
