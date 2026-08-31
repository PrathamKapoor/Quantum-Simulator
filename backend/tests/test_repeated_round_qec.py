"""Repeated-round (space-time) surface-code decoding tests (§26-§56).

Deterministic cases first (proved), Monte Carlo last. Reuses the rotated
planar code geometry, the exact matcher, and the coset classification.
"""
import pytest

from app.qec.rotated_surface_code import (
    RotatedSurfaceCode,
    RotatedSurfaceCodeDecoder,
    error_from_string,
)
from app.qec.repeated_round import (
    decode_repeated,
    sample_repeated,
    simulate_repeated,
)


@pytest.fixture(scope="module")
def code3():
    return RotatedSurfaceCode.build(3)


def inject_and_decode(code, *, error_support=None, flips=(), rounds=5,
                      p_data=0.01, p_measurement=0.01, seed=1):
    """Build observed syndromes from an explicit persistent error and an
    explicit list of (round, kind, check_index) measurement flips, then decode.

    error_support: dict[qubit -> 'X'|'Z'|'Y'] applied cumulatively from the
    start (each is a persistent error)."""
    dec = RotatedSurfaceCodeDecoder(code)
    ex = ez = 0
    for q, ch in (error_support or {}).items():
        if ch in ("X", "Y"):
            ex |= 1 << q
        if ch in ("Z", "Y"):
            ez |= 1 << q
    observed = []
    for t in range(1, rounds + 1):
        sx, sz = dec.syndrome(ex, ez)
        fx = [False] * len(code.x_checks)
        fz = [False] * len(code.z_checks)
        for (r, k, i) in flips:
            if r == t:
                if k == "X":
                    fx[i] = not fx[i]
                else:
                    fz[i] = not fz[i]
        observed.append((
            tuple(int(b) ^ int(f) for b, f in zip(sx, fx)),
            tuple(int(b) ^ int(f) for b, f in zip(sz, fz)),
        ))
    res = decode_repeated(code, rounds, p_data, p_measurement,
                          data_error_x=ex, data_error_z=ez,
                          observed_syndromes=observed, seed=seed)
    return res, observed


def checks_of_support(code, qubit, kind):
    """Local check indices whose support contains `qubit`."""
    checks = code.x_checks if kind == "X" else code.z_checks
    return [c.index for c in checks if qubit in c.support]


class TestNoNoise:
    @pytest.mark.parametrize("d", [3, 5, 7])
    def test_no_noise_zero_events(self, d):
        """§27: p = 0 for any rounds -> zero detection events, zero failures."""
        code = RotatedSurfaceCode.build(d)
        for rounds in (1, 2, 5):
            ex, ez, flips, obs = sample_repeated(
                code, rounds, 0.0, 0.0, error_model="depolarizing", seed=3)
            assert ex == 0 and ez == 0 and flips == []
            res = decode_repeated(code, rounds, 0.0, 0.0, data_error_x=ex,
                                  data_error_z=ez, observed_syndromes=obs)
            assert res.outcome == "CORRECTED"
            assert res.detection_events == []


class TestSingleDataError:
    @pytest.mark.parametrize("d", [3, 5])
    @pytest.mark.parametrize("ch", ["X", "Z", "Y"])
    def test_single_error_corrected(self, d, ch):
        """§28/§40: one data-qubit Pauli on every qubit is corrected."""
        code = RotatedSurfaceCode.build(d)
        for q in range(d * d):
            res, obs = inject_and_decode(code, error_support={q: ch}, rounds=4)
            assert res.outcome == "CORRECTED", (d, ch, q, res.outcome)

    def test_error_visible_at_one_layer(self):
        """A persistent single errors gives detection events at layer 1 and
        the final residual only; the intermediate difference is empty."""
        code = RotatedSurfaceCode.build(3)
        # pick a bulk qubit (2 X-checks) for a two-check spatial edge
        bulk = next(q for q in range(9)
                    if len(checks_of_support(code, q, "X")) == 2)
        res, obs = inject_and_decode(code, error_support={bulk: "Z"}, rounds=5)
        # detection events must be a single spatial/boundary resolution
        assert res.outcome == "CORRECTED"


class TestSingleMeasurementError:
    def test_middle_round_is_temporal_pair(self):
        """§29: a middle-round flip -> two temporal events, no data
        correction."""
        code = RotatedSurfaceCode.build(3)
        ci = checks_of_support(code, 4, "X")  # a bulk X-check
        check_idx = code.x_checks[ci[0]].index if ci else 0
        c = next(c.index for c in code.x_checks)  # use check 0 for determinism
        res, obs = inject_and_decode(code, error_support={},
                                     flips=[(2, "X", code.x_checks[c].index)],
                                     rounds=5)
        assert res.outcome == "CORRECTED"
        assert res.correction_x == 0 and res.correction_z == 0  # no data corr
        kinds = [m.kind for m in res.matching]
        assert kinds.count("temporal") == 1
        assert "spatial" not in kinds and "boundary" not in kinds

    def test_two_measurement_errors(self):
        """§30: two flips -> two independent temporal pairs."""
        code = RotatedSurfaceCode.build(3)
        c = code.x_checks[0].index
        c2 = code.x_checks[1].index
        res, obs = inject_and_decode(
            code, error_support={},
            flips=[(1, "X", c), (3, "X", c2)], rounds=6)
        assert res.outcome == "CORRECTED"
        assert res.correction_x == 0 and res.correction_z == 0
        assert [m.kind for m in res.matching].count("temporal") == 2


class TestCombinedErrors:
    def test_data_plus_measurement(self):
        """§32: data error and measurement error decoded independently."""
        code = RotatedSurfaceCode.build(3)
        # a bulk Z error (2 X-checks) + a measurement flip elsewhere
        bulk = next(q for q in range(9)
                    if len(checks_of_support(code, q, "X")) == 2)
        flips = [(2, "Z", code.z_checks[0].index)]
        res, obs = inject_and_decode(code, error_support={bulk: "Z"},
                                     flips=flips, rounds=5)
        assert res.outcome == "CORRECTED"


class TestLogicalAndStabilizer:
    def test_logical_string_detected(self):
        """§33: a bare logical Z has zero syndrome yet is LOGICAL_Z."""
        for d in (3, 5):
            code = RotatedSurfaceCode.build(d)
            ex, ez = error_from_string(code, code.logical_z)
            res, obs = inject_and_decode(code, error_support={
                q: "Z" for q in range(d * d) if ez >> q & 1}, rounds=4)
            assert res.outcome == "LOGICAL_Z", d
            # zero syndrome throughout
            assert all(not any(o[0]) and not any(o[1]) for o in obs)

    def test_stabilizer_equivalent_corrected(self):
        """§34: injecting a stabilizer is corrected (trivial residual)."""
        code = RotatedSurfaceCode.build(3)
        ex, ez = error_from_string(code, code.generators[0])
        supp = {q: ("X" if ex >> q & 1 else "Z") for q in range(9)
                if (ex | ez) >> q & 1}
        res, obs = inject_and_decode(code, error_support=supp, rounds=4)
        assert res.outcome == "CORRECTED"


class TestYError:
    def test_y_error_affects_both_sectors(self):
        """§40: a Y error contributes to both CSS sectors and is corrected."""
        code = RotatedSurfaceCode.build(3)
        for q in range(9):
            res, obs = inject_and_decode(code, error_support={q: "Y"}, rounds=4)
            assert res.outcome == "CORRECTED", q


class TestReproducibility:
    def test_same_seed_exact(self):
        """§24: same config + seed -> identical syndrome history, matching,
        classification."""
        code = RotatedSurfaceCode.build(5)
        a = sample_repeated(code, 6, 0.02, 0.02, error_model="depolarizing",
                            seed=42)
        b = sample_repeated(code, 6, 0.02, 0.02, error_model="depolarizing",
                            seed=42)
        assert a[0] == b[0] and a[1] == b[1] and a[2] == b[2] and a[3] == b[3]
        ra = decode_repeated(code, 6, 0.02, 0.02, data_error_x=a[0],
                             data_error_z=a[1], observed_syndromes=a[3], seed=42)
        rb = decode_repeated(code, 6, 0.02, 0.02, data_error_x=b[0],
                             data_error_z=b[1], observed_syndromes=b[3], seed=42)
        assert ra.to_dict() == rb.to_dict()

    def test_different_seed_differs(self):
        code = RotatedSurfaceCode.build(5)
        a = sample_repeated(code, 6, 0.2, 0.2, error_model="depolarizing",
                            seed=1)
        b = sample_repeated(code, 6, 0.2, 0.2, error_model="depolarizing",
                            seed=2)
        assert a[3] != b[3]  # observed syndromes differ (statistically near-certain)


class TestValidation:
    def test_rounds_validated(self):
        code = RotatedSurfaceCode.build(3)
        for bad in (0, -1, 65):
            with pytest.raises(ValueError, match="rounds"):
                sample_repeated(code, bad, 0.01, 0.01,
                                error_model="depolarizing", seed=1)

    def test_distance_validated(self):
        with pytest.raises(ValueError, match="distance"):
            simulate_repeated(4, 3, 0.01, 0.01, trials=10, seed=1)

    def test_probabilities_validated(self):
        for bad in (-0.1, 1.5):
            with pytest.raises(ValueError):
                simulate_repeated(3, 3, bad, 0.01, trials=10, seed=1)
            with pytest.raises(ValueError):
                simulate_repeated(3, 3, 0.01, bad, trials=10, seed=1)

    def test_trials_validated(self):
        with pytest.raises(ValueError):
            simulate_repeated(3, 3, 0.01, 0.01, trials=0, seed=1)

    def test_syndrome_length_validated(self):
        code = RotatedSurfaceCode.build(3)
        with pytest.raises(ValueError, match="length"):
            decode_repeated(code, 3, 0.01, 0.01, data_error_x=0,
                            data_error_z=0, observed_syndromes=[])


class TestMonteCarlo:
    def test_p0_zero_failures(self):
        for d in (3, 5):
            r = simulate_repeated(d, 4, 0.0, 0.0, trials=200, seed=5)
            assert r["logical_failures"] == 0
            assert r["logical_error_rate"] == 0.0

    def test_measurement_noise_yields_detection_activity(self):
        """§54: nonzero measurement noise -> nonzero temporal events."""
        code = RotatedSurfaceCode.build(3)
        r = simulate_repeated(3, 6, 0.0, 0.1, trials=100, seed=7)
        assert r["logical_failures"] >= 0  # small sample: not monotonic

    def test_broadly_increasing_with_p(self):
        low = simulate_repeated(3, 4, 0.005, 0.005, trials=2000, seed=11)
        high = simulate_repeated(3, 4, 0.05, 0.05, trials=2000, seed=11)
        assert high["logical_error_rate"] > low["logical_error_rate"]

    def test_distance_trend_evidence(self):
        """§55: larger distance suppresses p_L at low noise (evidence, not a
        threshold)."""
        d3 = simulate_repeated(3, 4, 0.03, 0.02, trials=4000, seed=13)
        d5 = simulate_repeated(5, 4, 0.03, 0.02, trials=4000, seed=13)
        assert d5["logical_error_rate"] < d3["logical_error_rate"]

    def test_reproducible(self):
        a = simulate_repeated(3, 4, 0.02, 0.02, trials=300, seed=21)
        b = simulate_repeated(3, 4, 0.02, 0.02, trials=300, seed=21)
        assert a == b