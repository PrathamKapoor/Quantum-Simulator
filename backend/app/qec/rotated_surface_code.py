"""Rotated planar surface code with an exact MWPM decoder (code capacity).

Geometry (directive §6, §116 - derived and algebraically validated, never
hand-drawn):
  * Data qubits sit at odd integer coordinates (x, y) with 1 <= x, y <= 2d-1
    on the doubled lattice; index q = ((y-1)//2)*d + ((x-1)//2).
  * Stabilizer centers sit at even coordinates (x, y) in [0, 2d]^2. Type is
    X if (x+y) % 4 == 0 else Z. Support = the data qubits diagonally adjacent
    (x±1, y±1) that exist.
  * Kept checks: every interior check (weight 4); on the top/bottom edges
    only the weight-2 X checks; on the left/right edges only the weight-2 Z
    checks; the four weight-1 corners are dropped. This yields exactly
    (d^2-1)/2 X checks and (d^2-1)/2 Z checks, all pairs commuting, every
    data qubit covered by >= 1 check of each type (validated at build).
  * Logical X is a vertical column of X at x = d (connecting top to bottom);
    logical Z is a horizontal row of Z at y = d (connecting left to right).
    X chains therefore terminate on the top/bottom boundaries and Z chains on
    the left/right boundaries (§13: the assignment is verified through the
    logical-string construction and the exit-point algebra, not naming).

Decoding is CSS (§42): Z-type errors are decoded from the X-check syndrome
via Z-correction chains on the X-check graph, and X-type errors from the
Z-check syndrome, as two independent exact MWPM problems (matching.py). A Y
error contributes to both components and is handled correctly by the split.
Syndromes come from the stabilizer algebra (anticommutation); a fast
per-qubit bitmask path is validated against `syndrome_of` in tests.

Code-capacity model only (§19): the syndrome is assumed measured perfectly in
a single round. Detection events carry a `round` field (fixed 0) so temporal
extension can be added later; no circuit-level fault tolerance is claimed.

Every reported quantity comes from actual computation (§106); distances are
independently verified via exhaustive per-component enumeration (§11); the
matcher is exact MWPM validated against brute force (§22).
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, islice

import numpy as np

from .matching import MatchingError, min_weight_perfect_matching
from .pipeline import wilson_interval
from .stabilizer import pauli_commutes, random_pauli_errors, validate_pauli_string

_SUPPORTED_DISTANCES = (3, 5, 7)
_ERROR_MODELS = ("depolarizing", "x_only", "z_only")


# ---------------------------------------------------------------------------
# GF(2) helpers (bitmask over data qubits; bit q = data qubit q)
# ---------------------------------------------------------------------------

def _parity(mask: int) -> int:
    return bin(mask).count("1") % 2


def _find_coset_functional(generators: list[int], logical: int) -> int:
    """Bitmask w with parity(w & g) = 0 for every generator g and
    parity(w & logical) = 1.

    For a CSS code with k=1 the zero-syndrome operators split into exactly two
    cosets of the rowspace: stabilizer products and the logical coset. This
    functional distinguishes them in O(1), replacing stabilizer-group
    enumeration (§29)."""
    rows: list[tuple[int, int]] = [(g, 0) for g in generators] + [(logical, 1)]
    basis: dict[int, tuple[int, int]] = {}   # pivot (lowest set bit) -> row
    for mask, rhs in rows:
        m, r = mask, rhs
        while m:
            b = (m & -m).bit_length() - 1
            if b in basis:
                pm, pr = basis[b]
                m ^= pm
                r ^= pr
            else:
                basis[b] = (m, r)
                break
        else:
            if r:
                raise ValueError("Inconsistent GF(2) system in functional solve.")
    # Back-substitute from the highest pivot down (pivot = lowest bit of its
    # row, so all other bits in a row are higher and already assigned).
    w = 0
    for b in sorted(basis, reverse=True):
        m, r = basis[b]
        w |= (r ^ _parity(w & (m & ~(1 << b)))) << b
    for g in generators:
        if _parity(w & g) != 0:
            raise ValueError("Functional does not annihilate a generator.")
    if _parity(w & logical) != 1:
        raise ValueError("Functional does not detect the logical operator.")
    return w


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StabilizerCheck:
    index: int
    kind: str            # "X" or "Z"
    center: tuple[int, int]
    support: tuple[int, ...]   # data qubit indices

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "kind": self.kind,
            "center": list(self.center),
            "support": list(self.support),
        }


@dataclass
class RotatedSurfaceCode:
    """Rotated planar surface code of odd distance d (3 <= d <= 7+)."""

    d: int
    data_coords: list[tuple[int, int]]
    x_checks: list[StabilizerCheck]
    z_checks: list[StabilizerCheck]
    generators: tuple[str, ...]      # X-checks then Z-checks, Pauli strings
    logical_x: str
    logical_z: str
    phi_x: int                        # X-type logical detector (bitmask)
    phi_z: int                        # Z-type logical detector (bitmask)
    z_correction_graph: dict          # defects = X-checks, chains = Z Paulis
    x_correction_graph: dict          # defects = Z-checks, chains = X Paulis

    # -- construction -------------------------------------------------------

    @classmethod
    def build(cls, d: int) -> "RotatedSurfaceCode":
        if d not in _SUPPORTED_DISTANCES:
            raise ValueError(
                f"Unsupported distance {d}; supported distances are "
                f"{list(_SUPPORTED_DISTANCES)} (odd distances only)."
            )
        data = [(x, y) for y in range(1, 2 * d, 2) for x in range(1, 2 * d, 2)]
        didx = {p: i for i, p in enumerate(data)}
        n = d * d

        raw: list[tuple[str, tuple[int, int], tuple[int, ...]]] = []
        for y in range(0, 2 * d + 1, 2):
            for x in range(0, 2 * d + 1, 2):
                kind = "X" if (x + y) % 4 == 0 else "Z"
                sup = tuple(sorted(
                    didx[(x + dx, y + dy)]
                    for dx in (-1, 1) for dy in (-1, 1)
                    if (x + dx, y + dy) in didx
                ))
                interior = 2 <= x <= 2 * d - 2 and 2 <= y <= 2 * d - 2
                keep = len(sup) >= 2 and (
                    interior
                    or (kind == "X" and y in (0, 2 * d))
                    or (kind == "Z" and x in (0, 2 * d))
                )
                if keep:
                    raw.append((kind, (x, y), sup))

        x_checks = [StabilizerCheck(i, "X", c, s)
                    for i, (k, c, s) in enumerate(raw) if k == "X"]
        z_checks = [StabilizerCheck(i, "Z", c, s)
                    for i, (k, c, s) in enumerate(raw) if k == "Z"]
        # Re-index contiguously per type: check.index is both the syndrome
        # bit position within its component and the list position.
        x_checks = [StabilizerCheck(i, "X", c.center, c.support)
                    for i, c in enumerate(x_checks)]
        z_checks = [StabilizerCheck(i, "Z", c.center, c.support)
                    for i, c in enumerate(z_checks)]
        expected = (d * d - 1) // 2
        if len(x_checks) != expected or len(z_checks) != expected:
            raise ValueError(
                f"Geometry error at d={d}: got {len(x_checks)} X / "
                f"{len(z_checks)} Z checks, expected {expected} each."
            )

        def _string(kind: str, sup: tuple[int, ...]) -> str:
            chars = ["I"] * n
            for q in sup:
                chars[n - 1 - q] = kind   # leftmost char = highest qubit
            return "".join(chars)

        generators = tuple(
            [_string("X", c.support) for c in x_checks]
            + [_string("Z", c.support) for c in z_checks]
        )
        lx_qubits = tuple(q for q, (x, _y) in enumerate(data) if x == d)
        lz_qubits = tuple(q for q, (_x, y) in enumerate(data) if y == d)
        logical_x = _string("X", lx_qubits)
        logical_z = _string("Z", lz_qubits)

        code = cls(
            d=d, data_coords=data, x_checks=x_checks, z_checks=z_checks,
            generators=generators, logical_x=logical_x, logical_z=logical_z,
            phi_x=0, phi_z=0, z_correction_graph={}, x_correction_graph={},
        )
        code._validate()
        xgen_masks = [sum(1 << q for q in c.support) for c in x_checks]
        zgen_masks = [sum(1 << q for q in c.support) for c in z_checks]
        lx_mask = sum(1 << q for q in lx_qubits)
        lz_mask = sum(1 << q for q in lz_qubits)
        # The X-type functional annihilates X-stabilizer products and fires on
        # the logical X; it classifies zero-Z-syndrome X-operators.
        code.phi_x = _find_coset_functional(xgen_masks, lx_mask)
        code.phi_z = _find_coset_functional(zgen_masks, lz_mask)
        code.z_correction_graph = code._build_chain_graph(x_checks,
                                                          code._x_supports)
        code.x_correction_graph = code._build_chain_graph(z_checks,
                                                          code._z_supports)
        return code

    # -- algebra helpers ----------------------------------------------------

    def _x_supports(self, q: int) -> list[int]:
        return [c.index for c in self.x_checks if q in c.support]

    def _z_supports(self, q: int) -> list[int]:
        return [c.index for c in self.z_checks if q in c.support]

    def _validate(self) -> None:
        n = self.d * self.d
        # Commutation: every X check commutes with every Z check (§9).
        for xc in self.x_checks:
            for zc in self.z_checks:
                overlap = len(set(xc.support) & set(zc.support))
                if overlap % 2:
                    raise ValueError(
                        f"Stabilizers {xc.center} (X) and {zc.center} (Z) "
                        f"anticommute (overlap {overlap})."
                    )
        # No duplicate stabilizers (§8).
        sups = [tuple(sorted(c.support)) for c in self.x_checks + self.z_checks]
        if len(set(sups)) != len(sups):
            raise ValueError("Duplicate stabilizer supports in geometry.")
        # Every data qubit covered by >= 1 check of each type (§8).
        for q in range(n):
            if not self._x_supports(q) or not self._z_supports(q):
                raise ValueError(f"Data qubit {q} lacks X or Z check coverage.")
        # Logical operators commute with all stabilizers and anticommute
        # with each other (§10).
        for g in self.generators:
            if not pauli_commutes(g, self.logical_x) or not pauli_commutes(
                g, self.logical_z
            ):
                raise ValueError("Logical operator anticommutes with a check.")
        if pauli_commutes(self.logical_x, self.logical_z):
            raise ValueError("Logical X and Z must anticommute.")

    def _build_chain_graph(self, checks: list[StabilizerCheck], support_of) -> dict:
        """Chain graph for one CSS component.

        `checks` carry the syndrome (defects); corrections are Pauli chains on
        data qubits. A data qubit whose support contains exactly one check is
        a boundary exit (the point where a chain leaves the lattice).
        Precomputes BFS distances and ACTUAL chain paths (data-qubit lists)
        between all check pairs and from every check to every exit (§26).
        BFS expands supports in sorted order -> deterministic (§53).
        """
        n = self.d * self.d
        exits = {q for q in range(n) if len(support_of(q)) == 1}
        dist: dict[tuple[int, int], int] = {}
        path: dict[tuple[int, int], tuple[int, ...]] = {}
        dist_exit: dict[tuple[int, int], int] = {}
        path_exit: dict[tuple[int, int], tuple[int, ...]] = {}
        for c in checks:
            start = c.index
            frontier = [(start, ())]
            visited = {start}
            reached_exits: set[int] = set()
            depth = 0
            while frontier:
                depth += 1
                nxt: list[tuple[int, tuple[int, ...]]] = []
                for cidx, chain in frontier:
                    for q in checks[cidx].support:   # sorted -> deterministic
                        if q in exits and q not in reached_exits:
                            reached_exits.add(q)
                            dist_exit[(start, q)] = depth
                            path_exit[(start, q)] = chain + (q,)
                        for c2 in support_of(q):
                            if c2 != cidx and c2 not in visited:
                                visited.add(c2)
                                nxt.append((c2, chain + (q,)))
                for cidx, chain in nxt:
                    if (start, cidx) not in dist:
                        dist[(start, cidx)] = depth
                        path[(start, cidx)] = chain
                frontier = nxt
        return {
            "exits": exits,
            "dist": dist,
            "path": path,
            "dist_exit": dist_exit,
            "path_exit": path_exit,
        }

    # -- distance verification (§11) -----------------------------------------

    def min_logical_weight(self, component: str, *, max_weight: int) -> int | None:
        """Minimum weight of a nontrivial logical Pauli of one CSS component.

        component="X": X-type operators v commuting with every Z check
        (v in ker H_Z) that are NOT X-stabilizer products, detected via the
        precomputed coset functional. Per-component binary enumeration is
        exact for CSS codes: d = min(d_X, d_Z). Returns None if no logical
        exists at weight <= max_weight."""
        n = self.d * self.d
        if component == "X":
            pmasks = [sum(1 << ci for ci in self._z_supports(q)) for q in range(n)]
            functional = self.phi_x
        else:
            pmasks = [sum(1 << ci for ci in self._x_supports(q)) for q in range(n)]
            functional = self.phi_z
        table = np.array(pmasks, dtype=np.uint64)
        wmask = np.uint64(functional)

        for w in range(1, max_weight + 1):
            it = combinations(range(n), w)
            while True:
                chunk = list(islice(it, 1_000_000))
                if not chunk:
                    break
                sup = np.array(chunk, dtype=np.int64)
                ker = np.bitwise_xor.reduce(table[sup], axis=1)
                candidates = sup[ker == 0]
                if candidates.size:
                    masks = np.bitwise_or.reduce(
                        np.uint64(1) << candidates.astype(np.uint64), axis=1)
                    if ((np.bitwise_count(masks & wmask) & 1) != 0).any():
                        return w
        return None

    def verify_distance(self) -> dict:
        """Independently verify the code distance (§11): the minimum weight of
        a nontrivial logical must equal d for both CSS components."""
        out: dict = {"d": self.d, "components": {}}
        for comp in ("X", "Z"):
            mw = self.min_logical_weight(comp, max_weight=self.d)
            if mw != self.d:
                raise ValueError(
                    f"Distance verification failed: {comp}-component minimum "
                    f"logical weight {mw} != requested distance {self.d}."
                )
            out["components"][comp] = mw
        out["code_distance"] = self.d
        return out

    # -- layout for visualization (§57) ---------------------------------------

    def layout(self) -> dict:
        scale = 2 * self.d
        return {
            "d": self.d,
            "topology": "rotated planar (open boundaries)",
            "data_qubits": [
                {"index": q, "x": x / scale, "y": y / scale}
                for q, (x, y) in enumerate(self.data_coords)
            ],
            "checks": [
                {**c.to_dict(), "x": c.center[0] / scale,
                 "y": c.center[1] / scale}
                for c in self.x_checks + self.z_checks
            ],
            "logical_x": "vertical column x = d (top-bottom)",
            "logical_z": "horizontal row y = d (left-right)",
        }


# ---------------------------------------------------------------------------
# Detection events and decoding
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DetectionEvent:
    """One syndrome defect, located in the matching graph (§18)."""

    check_index: int
    check_kind: str            # the check that flipped ("X" or "Z")
    center: tuple[int, int]
    round: int = 0             # single-round code-capacity model (§19)

    def to_dict(self) -> dict:
        return {
            "check_index": self.check_index,
            "check_kind": self.check_kind,
            "center": list(self.center),
            "round": self.round,
        }


@dataclass
class ChainMatch:
    """One matched pair from the MWPM solution, with its actual correction."""

    kind: str                    # "pair" or "boundary"
    pauli: str                   # correction chain type ("X" or "Z")
    a: DetectionEvent
    b: DetectionEvent | None     # None for boundary matches
    exit_qubit: int | None       # boundary exit data qubit, if boundary
    weight: int
    chain: tuple[int, ...]       # data qubits carrying the correction Pauli

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "pauli": self.pauli,
            "a": self.a.to_dict(),
            "b": self.b.to_dict() if self.b else None,
            "exit_qubit": self.exit_qubit,
            "weight": self.weight,
            "chain": list(self.chain),
        }


@dataclass
class RotatedSurfaceCodeResult:
    """Structured result of one surface-code decoding run (§32)."""

    d: int
    error_model: str
    error_x: int                # X-component support bitmask
    error_z: int                # Z-component support bitmask
    syndrome_x: tuple[int, ...]  # X-check syndrome (flipped by Z errors)
    syndrome_z: tuple[int, ...]  # Z-check syndrome (flipped by X errors)
    events: list[DetectionEvent]
    matching: list[ChainMatch]
    matching_weight: int
    correction_x: int
    correction_z: int
    residual_x: int
    residual_z: int
    outcome: str                 # CORRECTED | LOGICAL_X | LOGICAL_Z | LOGICAL_Y
    success: bool
    decoder: str = "mwpm"
    seed: int | None = None
    error: str | None = None     # decoder failure message (§84-85)

    def support_list(self, mask: int) -> list[int]:
        n = self.d * self.d
        return [q for q in range(n) if mask >> q & 1]

    def to_dict(self) -> dict:
        return {
            "d": self.d,
            "error_model": self.error_model,
            "decoder": self.decoder,
            "error_support": {
                "X": self.support_list(self.error_x),
                "Z": self.support_list(self.error_z),
            },
            "syndrome_x": list(self.syndrome_x),
            "syndrome_z": list(self.syndrome_z),
            "events": [e.to_dict() for e in self.events],
            "matching": [m.to_dict() for m in self.matching],
            "matching_weight": self.matching_weight,
            "correction": {
                "X": self.support_list(self.correction_x),
                "Z": self.support_list(self.correction_z),
            },
            "residual": {
                "X": self.support_list(self.residual_x),
                "Z": self.support_list(self.residual_z),
            },
            "outcome": self.outcome,
            "success": self.success,
            "seed": self.seed,
            "decoder_error": self.error,
        }


def error_from_string(code: RotatedSurfaceCode, pauli: str) -> tuple[int, int]:
    """Split a Pauli string (project convention: leftmost char = highest
    qubit) into (X-component, Z-component) support bitmasks."""
    pauli = validate_pauli_string(pauli)
    n = code.d * code.d
    if len(pauli) != n:
        raise ValueError(f"Pauli string length {len(pauli)} != {n} data qubits.")
    ex = ez = 0
    for p, ch in enumerate(pauli):
        q = n - 1 - p
        if ch in ("X", "Y"):
            ex |= 1 << q
        if ch in ("Z", "Y"):
            ez |= 1 << q
    return ex, ez


def _sample_errors(code: RotatedSurfaceCode, model: str, p: float,
                   trials: int, rng: np.random.Generator) -> list[tuple[int, int]]:
    """Sample physical errors with the existing conventions (§14-15):
    depolarizing = I w.p. 1-p, else X/Y/Z equally (stabilizer.py model)."""
    if model not in _ERROR_MODELS:
        raise ValueError(f"Unsupported error model {model!r}.")
    n = code.d * code.d
    if model == "depolarizing":
        labels = random_pauli_errors(n, p, trials, rng)
    elif model == "x_only":
        labels = np.where(rng.random((trials, n)) < p, 1, 0)
    else:  # z_only
        labels = np.where(rng.random((trials, n)) < p, 3, 0)
    out = []
    for row in labels:
        ex = ez = 0
        for q, v in enumerate(row):
            if v in (1, 2):
                ex |= 1 << int(q)
            if v in (2, 3):
                ez |= 1 << int(q)
        out.append((ex, ez))
    return out


def sample_single_error(code: RotatedSurfaceCode, model: str, p: float,
                        seed: int) -> tuple[int, int]:
    """Sample ONE physical error from (model, p, seed) - public API helper
    for the decode endpoint (deterministic in seed, §33)."""
    rng = np.random.default_rng(seed)
    return _sample_errors(code, model, p, 1, rng)[0]


class RotatedSurfaceCodeDecoder:
    """Exact MWPM decoder over a fixed RotatedSurfaceCode (§30: pure domain
    object, not coupled to HTTP)."""

    def __init__(self, code: RotatedSurfaceCode):
        self.code = code
        # Per-qubit syndrome masks: xmask[q] = X-checks containing q (flipped
        # by Z components); zmask[q] = Z-checks containing q (flipped by X
        # components). Validated against the algebraic `syndrome_of` in tests.
        n = code.d * code.d
        self.xmask = [sum(1 << c.index for c in code.x_checks if q in c.support)
                      for q in range(n)]
        self.zmask = [sum(1 << c.index for c in code.z_checks if q in c.support)
                      for q in range(n)]

    def syndrome(self, ex: int, ez: int) -> tuple[tuple[int, ...], tuple[int, ...]]:
        """(X-check syndrome from Z components, Z-check syndrome from X
        components), via the per-qubit mask fast path (§16)."""
        syn_z = 0
        m = ex
        while m:
            q = (m & -m).bit_length() - 1
            m &= m - 1
            syn_z ^= self.zmask[q]
        syn_x = 0
        m = ez
        while m:
            q = (m & -m).bit_length() - 1
            m &= m - 1
            syn_x ^= self.xmask[q]
        return (
            tuple((syn_x >> c.index) & 1 for c in self.code.x_checks),
            tuple((syn_z >> c.index) & 1 for c in self.code.z_checks),
        )

    def _match_component(
        self, defect_indices: list[int], graph: dict,
        checks: list[StabilizerCheck],
    ) -> tuple[int, list[ChainMatch], int, str]:
        """Exact MWPM + chain reconstruction for one CSS component. Returns
        (weight, matches, correction bitmask, chain pauli type)."""
        kind = checks[0].kind
        k = len(defect_indices)
        if k == 0:
            return 0, [], 0, kind
        dist, path = graph["dist"], graph["path"]
        dist_exit, path_exit = graph["dist_exit"], graph["path_exit"]
        pair_weights: dict[tuple[int, int], int] = {}
        for i in range(k):
            for j in range(i + 1, k):
                a, b = defect_indices[i], defect_indices[j]
                w = dist.get((a, b), dist.get((b, a)))
                if w is not None:
                    pair_weights[(a, b)] = w
        exit_weights: dict[int, int] = {}
        exit_choice: dict[int, int] = {}
        for a in defect_indices:
            options = sorted((w, q) for (c, q), w in dist_exit.items() if c == a)
            if options:
                exit_weights[a] = options[0][0]   # min weight; ties -> smallest
                exit_choice[a] = options[0][1]    # exit qubit index (§53)
        weight, pairs = min_weight_perfect_matching(pair_weights, exit_weights)

        pauli = "Z" if kind == "X" else "X"
        correction = 0
        matches: list[ChainMatch] = []
        for a, b in pairs:
            if b == -1:
                q = exit_choice[a]
                ch = path_exit[(a, q)]
                correction ^= sum(1 << x for x in ch)
                matches.append(ChainMatch(
                    kind="boundary", pauli=pauli, a=_event(checks, a),
                    b=None, exit_qubit=q, weight=dist_exit[(a, q)], chain=ch,
                ))
            else:
                ch = path.get((a, b)) or path.get((b, a))
                if ch is None:
                    raise MatchingError(f"No precomputed chain for {(a, b)}.")
                correction ^= sum(1 << x for x in ch)
                matches.append(ChainMatch(
                    kind="pair", pauli=pauli, a=_event(checks, a),
                    b=_event(checks, b), exit_qubit=None,
                    weight=dist.get((a, b), dist.get((b, a))), chain=ch,
                ))
        return weight, matches, correction, pauli

    def decode(self, ex: int, ez: int, *, seed: int | None = None,
               error_model: str = "explicit") -> RotatedSurfaceCodeResult:
        code = self.code
        syn_x, syn_z = self.syndrome(ex, ez)
        events = [DetectionEvent(c.index, "X", c.center)
                  for c, s in zip(code.x_checks, syn_x) if s]
        events += [DetectionEvent(c.index, "Z", c.center)
                   for c, s in zip(code.z_checks, syn_z) if s]
        # Z errors flip X-checks -> Z-correction chains on the X-check graph.
        z_defects = [c.index for c, s in zip(code.x_checks, syn_x) if s]
        # X errors flip Z-checks -> X-correction chains on the Z-check graph.
        x_defects = [c.index for c, s in zip(code.z_checks, syn_z) if s]
        try:
            wz, mz, cz, _ = self._match_component(
                z_defects, code.z_correction_graph, code.x_checks)
            wx, mx, cx, _ = self._match_component(
                x_defects, code.x_correction_graph, code.z_checks)
        except MatchingError as e:
            return _decoder_error_result(code, ex, ez, syn_x, syn_z, events,
                                         str(e), seed, error_model)
        rx, rz = ex ^ cx, ez ^ cz
        # The correction must cancel the syndrome exactly (§27).
        rsyn_x, rsyn_z = self.syndrome(rx, rz)
        if any(rsyn_x) or any(rsyn_z):
            return _decoder_error_result(
                code, ex, ez, syn_x, syn_z, events,
                "Correction did not cancel the syndrome.", seed, error_model,
                matching=mz + mx, weight=wz + wx, cx=cx, cz=cz, rx=rx, rz=rz)
        # Logical classification of the residual modulo stabilizers (§28):
        # zero-syndrome residuals are stabilizer products iff their coset
        # functional is 0; a firing functional means a genuine logical.
        x_logical = _parity(rx & code.phi_x) == 1
        z_logical = _parity(rz & code.phi_z) == 1
        if x_logical and z_logical:
            outcome = "LOGICAL_Y"
        elif x_logical:
            outcome = "LOGICAL_X"
        elif z_logical:
            outcome = "LOGICAL_Z"
        else:
            outcome = "CORRECTED"
        return RotatedSurfaceCodeResult(
            d=code.d, error_model=error_model,
            error_x=ex, error_z=ez,
            syndrome_x=syn_x, syndrome_z=syn_z,
            events=events, matching=mz + mx, matching_weight=wz + wx,
            correction_x=cx, correction_z=cz, residual_x=rx, residual_z=rz,
            outcome=outcome, success=outcome == "CORRECTED", seed=seed,
        )


def _decoder_error_result(code, ex, ez, syn_x, syn_z, events, message, seed,
                          error_model, *, matching=None, weight=0, cx=0, cz=0,
                          rx=0, rz=0):
    """Honest decoder failure: never reported as success (§84-§85)."""
    return RotatedSurfaceCodeResult(
        d=code.d, error_model=error_model, error_x=ex, error_z=ez,
        syndrome_x=syn_x, syndrome_z=syn_z, events=events,
        matching=matching or [], matching_weight=weight,
        correction_x=cx, correction_z=cz, residual_x=rx, residual_z=rz,
        outcome="DECODER_ERROR", success=False, seed=seed, error=message,
    )


def _event(checks: list[StabilizerCheck], index: int) -> DetectionEvent:
    c = next(c for c in checks if c.index == index)
    return DetectionEvent(c.index, c.kind, c.center)


# ---------------------------------------------------------------------------
# Monte Carlo (reuses the existing Wilson interval; §34-35)
# ---------------------------------------------------------------------------

@dataclass
class RotatedSurfaceCodeSimResult:
    d: int
    physical_error_rate: float
    error_model: str
    trials: int
    logical_failures: int
    logical_error_rate: float
    ci95: tuple[float, float]
    decoder: str
    seed: int
    note: str

    def to_dict(self) -> dict:
        return {
            "d": self.d,
            "physical_error_rate": self.physical_error_rate,
            "error_model": self.error_model,
            "trials": self.trials,
            "logical_failures": self.logical_failures,
            "logical_error_rate": self.logical_error_rate,
            "ci95": list(self.ci95),
            "decoder": self.decoder,
            "seed": self.seed,
            "note": self.note,
        }


_SIM_NOTE = (
    "Code-capacity MWPM decoding of the rotated planar surface code under "
    "independent Pauli data-qubit noise with PERFECT syndrome measurement "
    "(single round). Logical error rate p_L = failures/trials with Wilson 95% "
    "interval; p_L is distinct from the physical error rate p. Bounded "
    "simulator study - not a hardware threshold determination."
)


def simulate_rotated_surface_code(
    d: int,
    physical_error_rate: float,
    *,
    trials: int,
    seed: int,
    error_model: str = "depolarizing",
) -> RotatedSurfaceCodeSimResult:
    """Monte Carlo logical-error estimate at one (d, p) point (§34)."""
    if not (0 <= physical_error_rate <= 1):
        raise ValueError(
            f"Physical error rate must be within [0,1], got {physical_error_rate}.")
    if trials <= 0:
        raise ValueError("trials must be positive.")
    code = RotatedSurfaceCode.build(d)
    decoder = RotatedSurfaceCodeDecoder(code)
    rng = np.random.default_rng(seed)
    failures = 0
    for ex, ez in _sample_errors(code, error_model, physical_error_rate,
                                 trials, rng):
        res = decoder.decode(ex, ez, seed=seed, error_model=error_model)
        if res.outcome == "DECODER_ERROR":
            raise RuntimeError(f"Decoder failed during simulation: {res.error}")
        if not res.success:
            failures += 1
    lo, hi = wilson_interval(failures, trials)
    return RotatedSurfaceCodeSimResult(
        d=d, physical_error_rate=physical_error_rate,
        error_model=error_model, trials=trials,
        logical_failures=failures,
        logical_error_rate=failures / trials,
        ci95=(lo, hi), decoder="mwpm", seed=seed, note=_SIM_NOTE,
    )


def sweep_rotated_surface_code(
    distances: list[int],
    error_rates: list[float],
    *,
    trials: int,
    seed: int,
    error_model: str = "depolarizing",
) -> list[dict]:
    """Bounded p_L(d, p) sweep (§37, §80). Each point derives its seed
    deterministically from (base seed, distance, rate index), following the
    existing sweep conventions."""
    points = []
    for di, d in enumerate(distances):
        for i, p in enumerate(error_rates):
            if not (0 <= p <= 1):
                raise ValueError(f"Invalid error rate {p}.")
            point_seed = seed + 1000 + di * 7919 + i * 104729
            points.append(simulate_rotated_surface_code(
                d, p, trials=trials, seed=point_seed,
                error_model=error_model).to_dict())
    return points
