"""MWPM matcher tests: exactness against brute force (§22, §54, §91).

The production matcher (min_weight_perfect_matching) is exact minimum-weight
perfect matching over the decoder graph (defects + per-defect boundary
copies). The brute-force reference enumerates all perfect matchings plainly,
with no memoization or ordering shortcuts, so a broken matcher cannot
validate itself.
"""
import random

import pytest

from app.qec.matching import (
    MatchingError,
    brute_force_min_weight_perfect_matching,
    min_weight_perfect_matching,
)


def random_instance(rng: random.Random, k: int, *, max_w: int = 9,
                    p_exit: float = 0.7):
    """Random complete graph on k defects with random boundary exit options."""
    weights = {
        (i, j): rng.randint(1, max_w)
        for i in range(k) for j in range(i + 1, k)
    }
    exit_weights = {
        i: rng.randint(0, max_w)
        for i in range(k) if rng.random() < p_exit
    }
    return weights, exit_weights


class TestExactnessAgainstBruteForce:
    @pytest.mark.parametrize("k", [2, 4, 6])
    def test_random_instances_match_brute_force(self, k):
        rng = random.Random(1234 + k)
        for _ in range(300):
            weights, exits = random_instance(rng, k)
            got = min_weight_perfect_matching(weights, exits)
            ref = brute_force_min_weight_perfect_matching(weights, exits)
            assert got[0] == ref[0], (weights, exits, got, ref)

    def test_boundary_assignments_included(self):
        """Instances where the optimum uses boundary exits (§54)."""
        rng = random.Random(7)
        exits_used = 0
        for _ in range(200):
            weights, exits = random_instance(rng, 3, max_w=5, p_exit=0.9)
            got = min_weight_perfect_matching(weights, exits)
            ref = brute_force_min_weight_perfect_matching(weights, exits)
            assert got[0] == ref[0]
            if any(b == -1 for _a, b in got[1]):
                exits_used += 1
        assert exits_used > 0  # the cases were actually exercised

    def test_equal_weight_solutions_deterministic(self):
        """Ties must resolve identically under identical input (§53)."""
        weights = {(0, 1): 2, (2, 3): 2, (0, 2): 2, (1, 3): 2, (0, 3): 2, (1, 2): 2}
        exits = {}
        first = min_weight_perfect_matching(weights, exits)
        for _ in range(20):
            assert min_weight_perfect_matching(weights, exits) == first

    def test_empty_instance(self):
        assert min_weight_perfect_matching({}, {}) == (0, [])

    def test_single_defect_requires_exit(self):
        assert min_weight_perfect_matching({}, {0: 3}) == (3, [(0, -1)])

    def test_no_pair_edge_uses_exit(self):
        """A defect pair with no direct edge can still match via exits."""
        got = min_weight_perfect_matching({}, {0: 2, 1: 5})
        assert got == (7, [(0, -1), (1, -1)])

    def test_exit_cheaper_than_pairing(self):
        """Two far-apart defects both exiting the boundary beat their pair."""
        weights = {(0, 1): 10}
        exits = {0: 1, 1: 1}
        w, pairs = min_weight_perfect_matching(weights, exits)
        assert w == 2
        assert sorted(pairs) == [(0, -1), (1, -1)]
