"""Exact minimum-weight perfect matching (MWPM) for surface-code decoding.

Scope and honesty statement (directive §20-§24, §73-§74):

The decoder reduces syndrome decoding to minimum-weight perfect matching on a
graph with one vertex per syndrome defect plus one "boundary copy" vertex per
defect (edge weight = cheapest chain from that defect to a compatible
boundary; leftover copies pair among themselves at weight 0). This reduction
is EXACT: every valid correction (defect-defect chains and defect-boundary
chains, any number of the latter) is representable, and the optimal matching
weight equals the optimal correction weight. With k defects the graph has 2k
vertices, so a perfect matching always exists and no parity special-casing is
needed.

The matching itself is solved EXACTLY by dynamic programming over defect
subsets: for the smallest vertex i of a remaining set S, either i pairs with
another defect j (cost chain_weight[i][j]) or i takes its boundary copy
(cost exit_weight[i]). Memoization makes this exact enumeration feasible for
the defect counts of supported distances; a state-count guard fails loudly
(never silently) if an instance exceeds the budget. This is genuine
minimum-weight perfect matching on the decoder graph - NOT greedy
nearest-neighbour pairing (§74).

Determinism (§53): vertices are processed in sorted index order and ties
between equal-weight choices are resolved by that fixed order, so identical
inputs always produce identical matchings.
"""
from __future__ import annotations


class MatchingError(RuntimeError):
    """Raised when a matching instance exceeds the solver budget (§84-§85:

    an infrastructure limit, never reported as a logical outcome)."""


_MAX_STATES = 4_000_000


def min_weight_perfect_matching(
    weights: dict[tuple[int, int], int],
    exit_weights: dict[int, int],
) -> tuple[int, list[tuple[int, int]]]:
    """Exact MWPM over defects with optional boundary exit per defect.

    Args:
        weights: chain weight between each defect pair (complete graph on the
            defect indices present in this dict).
        exit_weights: per-defect cost of correcting via a boundary chain
            (a defect need not have an exit option if absent).

    Returns:
        (total_weight, pairs) where pairs are (defect, defect) or
        (defect, -1) for a boundary exit. Ties resolve deterministically by
        ascending vertex index.
    """
    defects = sorted(
        {u for u, _ in weights} | {v for _, v in weights} | set(exit_weights)
    )
    index = {v: i for i, v in enumerate(defects)}
    k = len(defects)
    if k == 0:
        return 0, []
    # Dense pair-weight matrix over compact indices (None = no edge).
    pair: list[list[int | None]] = [[None] * k for _ in range(k)]
    for (u, v), w in weights.items():
        i, j = index[u], index[v]
        pair[i][j] = pair[j][i] = w
    exit_cost: list[int | None] = [exit_weights.get(d) for d in defects]

    memo: dict[int, tuple[int, list[tuple[int, int]]] | None] = {}

    # Sentinel for subsets that admit no perfect matching; treated as a dead
    # branch by callers (a sibling pairing may still succeed).
    _UNMATCHABLE: tuple[int, list[tuple[int, int]]] | None = None

    def solve(mask: int):
        """Min weight to resolve the defect set `mask` (compact indices)."""
        if mask == 0:
            return (0, [])
        cached = memo.get(mask)
        if cached is not None:
            return cached if cached is not _UNMATCHABLE else None
        # smallest remaining defect
        i = (mask & -mask).bit_length() - 1
        rest = mask & ~(1 << i)
        best: tuple[int, list[tuple[int, int]]] | None = None
        # Option 1: boundary exit for defect i.
        ec = exit_cost[i]
        if ec is not None:
            sub = solve(rest)
            if sub is not None:
                w, pairs = sub
                cand = (ec + w, [(defects[i], -1)] + pairs)
                if best is None or cand[0] < best[0]:
                    best = cand
        # Option 2: pair with each other remaining defect j.
        m = rest
        while m:
            j = (m & -m).bit_length() - 1
            m &= m - 1
            w_ij = pair[i][j]
            if w_ij is None:
                continue
            sub = solve(rest & ~(1 << j))
            if sub is None:
                continue
            w, pairs = sub
            cand = (w_ij + w, [(defects[i], defects[j])] + pairs)
            if best is None or cand[0] < best[0]:
                best = cand
        if len(memo) >= _MAX_STATES:
            raise MatchingError(
                f"Matching instance exceeded {_MAX_STATES} memo states; "
                "decoding capacity limit reached."
            )
        memo[mask] = best if best is not None else _UNMATCHABLE
        return best

    solution = solve((1 << k) - 1)
    if solution is None:
        raise MatchingError(
            "Defect set admits no perfect matching (no pair or exit options)."
        )
    total, pairs = solution
    return total, sorted(pairs)


def brute_force_min_weight_perfect_matching(
    weights: dict[tuple[int, int], int],
    exit_weights: dict[int, int],
) -> tuple[int, list[tuple[int, int]]]:
    """Independent brute-force reference (validation only, §22).

    Enumerates every perfect matching of the defect+copy structure by plain
    recursion without memoization or ordering shortcuts. Exponential; use on
    small instances only.
    """
    defects = sorted(
        {u for u, _ in weights} | {v for _, v in weights} | set(exit_weights)
    )
    k = len(defects)
    if k == 0:
        return 0, []
    pair = {(u, v): w for (u, v), w in weights.items()}
    pair |= {(v, u): w for (u, v), w in weights.items()}

    best: tuple[int, list[tuple[int, int]]] | None = None

    def rec(remaining: list[int], acc_w: int, acc_pairs: list[tuple[int, int]]) -> None:
        nonlocal best
        if best is not None and acc_w >= best[0]:
            return
        if not remaining:
            best = (acc_w, list(acc_pairs))
            return
        i = remaining[0]
        rest = remaining[1:]
        # exit
        if i in exit_weights:
            acc_pairs.append((i, -1))
            rec(rest, acc_w + exit_weights[i], acc_pairs)
            acc_pairs.pop()
        # pair with any other remaining defect
        for pos, j in enumerate(rest):
            w = pair.get((i, j))
            if w is None:
                continue
            acc_pairs.append((i, j))
            rec(rest[:pos] + rest[pos + 1:], acc_w + w, acc_pairs)
            acc_pairs.pop()

    rec(defects, 0, [])
    if best is None:
        raise MatchingError("Brute force found no perfect matching.")
    return best[0], sorted(best[1])
