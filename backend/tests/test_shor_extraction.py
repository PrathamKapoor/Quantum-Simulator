"""Shor cat-state extraction tests (milestone 17).

Validation structure (directive Phases 1-5):
  1. Ideal correctness: the noiseless Shor syndrome must equal the
     algebraic syndrome for EVERY single-qubit data error (d=3, 5).
     The oracle is the existing RotatedSurfaceCodeDecoder.syndrome,
     NOT the production circuit called twice.
  2. Exhaustive single-fault enumeration via the deterministic
     forced_faults harness driving the PRODUCTION routine:
       - the baseline failure mode (weight-4 correlated hooks) is
         IMPOSSIBLE under Shor extraction;
       - the honest worst case is weight 2 (a Y fault on ancilla a_1
         back-propagates Z through the fan-out, then hooks two data
         qubits) -- unverified Shor does NOT achieve weight-1
         confinement; cat-state verification is the identified
         missing ingredient (documented in LIMITATIONS.md);
       - readout faults never produce data errors (pure syndrome
         errors).
  3. GHZ signature: a Z fault on a_0 right after reset is equivalent
     to the all-legs-X stabilizer of the cat -- completely benign
     (no data error, no syndrome flip). An independent-ancilla
     (non-cat) scheme would show a syndrome flip here, so this test
     distinguishes the genuine cat state from a degenerate product
     state.
  4. p=0 regression, determinism, even-k validation guard.
  5. Monte Carlo comparison vs baseline with Wilson intervals.
"""
import pytest

from app.qec.rotated_surface_code import RotatedSurfaceCode, RotatedSurfaceCodeDecoder
from app.qec.circuit_level import (
    extract_syndrome_noiseless,
    simulate_circuit_level,
    simulate_circuit_level_mc,
    decode_circuit_level,
)
from app.qec.circuit_extraction import (
    EXTRACTION_BASELINE, EXTRACTION_SHOR,
    get_extraction_model, list_extraction_models,
    _measure_check_shor,
)
from app.qec.pipeline import wilson_interval


@pytest.fixture(scope="module")
def code3():
    return RotatedSurfaceCode.build(3)


@pytest.fixture(scope="module")
def code5():
    return RotatedSurfaceCode.build(5)


def _all_single_faults(code):
    """Every elementary single fault of every Shor check, as API
    tuples (kind, check_index, stage, index, participant, pauli)."""
    for kind, checks in (("X", code.x_checks), ("Z", code.z_checks)):
        for ch in checks:
            k = len(ch.support)
            ci = ch.index
            for i in range(k):
                for p in "XYZ":
                    yield (kind, ci, "reset", i, None, p)
                    yield (kind, ci, "prep", i, None, p)
                yield (kind, ci, "readout", i, None, None)
            for g in range(2 * k - 1):
                for part in "ct":
                    for p in "XYZ":
                        yield (kind, ci, "cnot", g, part, p)


# ---------------------------------------------------------------------------
# Registry.
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_shor_registered(self):
        names = {m["name"] for m in list_extraction_models()}
        assert EXTRACTION_SHOR in names
        assert EXTRACTION_BASELINE in names

    def test_shor_has_measure_check(self):
        m = get_extraction_model(EXTRACTION_SHOR)
        assert callable(m.measure_check)

    def test_baseline_has_no_measure_check(self):
        m = get_extraction_model(EXTRACTION_BASELINE)
        assert m.measure_check is None


# ---------------------------------------------------------------------------
# Ideal correctness (independent oracle).
# ---------------------------------------------------------------------------

class TestIdealCorrectness:
    @pytest.mark.parametrize("d", [3, 5])
    def test_noiseless_syndrome_equals_algebraic(self, d):
        code = RotatedSurfaceCode.build(d)
        dec = RotatedSurfaceCodeDecoder(code)
        n = d * d
        for q in range(n):
            for ex, ez in ((1 << q, 0), (0, 1 << q), (1 << q, 1 << q)):
                ox, oz = extract_syndrome_noiseless(
                    code, ex, ez, extraction_model=EXTRACTION_SHOR)
                sx, sz = dec.syndrome(ex, ez)
                assert list(ox) == list(sx)
                assert list(oz) == list(sz)

    def test_logical_string_detected(self, code3):
        """A bare logical Z (zero algebraic syndrome) must still be
        flagged by the decoder residual classification when the
        Shor-extracted history is decoded."""
        from app.qec.rotated_surface_code import error_from_string
        ex, ez = error_from_string(code3, code3.logical_z)
        ox, oz = extract_syndrome_noiseless(
            code3, ex, ez, extraction_model=EXTRACTION_SHOR)
        assert not any(ox) and not any(oz)
        obs = [(ox, oz)] * 4
        res = decode_circuit_level(
            code3, 4, 0.0, 0.0, 0.0, 0.0,
            data_error_x=ex, data_error_z=ez, observed_syndromes=obs,
            seed=1)
        assert res.outcome == "LOGICAL_Z"

    def test_single_data_error_decodes_corrected(self, code3):
        dec_like = [(tuple(0 for _ in code3.x_checks),
                     tuple(0 for _ in code3.z_checks))]
        for q in range(9):
            for ex, ez in ((1 << q, 0), (0, 1 << q)):
                ox, oz = extract_syndrome_noiseless(
                    code3, ex, ez, extraction_model=EXTRACTION_SHOR)
                obs = [(ox, oz)] * 4
                res = decode_circuit_level(
                    code3, 4, 0.0, 0.0, 0.0, 0.0,
                    data_error_x=ex, data_error_z=ez,
                    observed_syndromes=obs, seed=1)
                assert res.outcome == "CORRECTED", (q, ex, ez, res.outcome)


# ---------------------------------------------------------------------------
# Exhaustive single-fault enumeration (the FT evidence).
# ---------------------------------------------------------------------------

class TestExhaustiveFaultEnumeration:
    @pytest.mark.parametrize("d", [3, 5])
    def test_baseline_weight4_hooks_impossible(self, d):
        """The baseline's dominant failure mode -- one ancilla fault
        hooking to the full support (weight 4) -- cannot occur under
        Shor extraction, proven over EVERY elementary single fault."""
        code = RotatedSurfaceCode.build(d)
        for f in _all_single_faults(code):
            ex, ez, hooks, obs, _mf = simulate_circuit_level(
                code, 2, 0.0, 0.0, 0.0, 0.0, seed=0,
                extraction_model=EXTRACTION_SHOR, forced_faults=[f])
            w = bin(ex).count("1") + bin(ez).count("1")
            assert w <= 2, (f, w)

    @pytest.mark.parametrize("d", [3, 5])
    def test_honest_worst_case_is_weight2(self, d):
        """The worst case is exactly weight 2: reset-Y or prep-Y on
        ancilla a_1 (its Z back-propagates through the fan-out to
        a_0, then both legs hook to data after the H layers). This
        is the documented gap of UNVERIFIED Shor extraction."""
        code = RotatedSurfaceCode.build(d)
        max_w, worst = 0, None
        for f in _all_single_faults(code):
            ex, ez, hooks, obs, _mf = simulate_circuit_level(
                code, 2, 0.0, 0.0, 0.0, 0.0, seed=0,
                extraction_model=EXTRACTION_SHOR, forced_faults=[f])
            w = bin(ex).count("1") + bin(ez).count("1")
            if w > max_w:
                max_w, worst = w, f
        assert max_w == 2, (max_w, worst)
        assert worst[2] in ("reset", "prep") and worst[5] == "Y"
        assert worst[3] == 1  # ancilla a_1

    @pytest.mark.parametrize("d", [3, 5])
    def test_readout_faults_never_touch_data(self, d):
        """Readout faults are pure syndrome errors (the data frame is
        untouched) -- the data-vs-measurement fault separation the
        repeated-round decoder relies on."""
        code = RotatedSurfaceCode.build(d)
        n_readout = 0
        for f in _all_single_faults(code):
            if f[2] != "readout":
                continue
            n_readout += 1
            ex, ez, hooks, obs, _mf = simulate_circuit_level(
                code, 2, 0.0, 0.0, 0.0, 0.0, seed=0,
                extraction_model=EXTRACTION_SHOR, forced_faults=[f])
            assert ex == 0 and ez == 0, f
            assert hooks == [], f

    def test_forced_fault_accounting_is_exact(self, code3):
        """A fault targeting one check must not leak into other
        checks (each check consumes only its own tuple)."""
        f = ("X", 0, "reset", 0, None, "X")
        ex, ez, hooks, obs, _mf = simulate_circuit_level(
            code3, 2, 0.0, 0.0, 0.0, 0.0, seed=0,
            extraction_model=EXTRACTION_SHOR, forced_faults=[f])
        # Single weight-1 or -2 data error, NOT the 8-fault blowup a
        # leaky implementation would produce.
        w = bin(ex).count("1") + bin(ez).count("1")
        assert w <= 2

    def test_unreachable_fault_fails_loudly(self, code3):
        """A forced fault at a location the circuit never reaches
        (e.g. an out-of-range ancilla index) must raise, never
        silently vanish."""
        with pytest.raises(RuntimeError, match="Unconsumed forced"):
            simulate_circuit_level(
                code3, 2, 0.0, 0.0, 0.0, 0.0, seed=0,
                extraction_model=EXTRACTION_SHOR,
                forced_faults=[("X", 0, "reset", 9, None, "X")])


# ---------------------------------------------------------------------------
# Genuine-cat-state signature.
# ---------------------------------------------------------------------------

class TestGHZSignature:
    def test_reset_z_on_a0_is_stabilizer_equivalent(self, code3):
        """Z on a_0 right after reset == all-legs-X on the GHZ == a
        stabilizer of the cat. Completely benign: no data error, no
        hook, no syndrome flip. A product-state (non-cat) scheme
        would flip one measurement bit here."""
        for kind in ("X", "Z"):
            ch = (code3.x_checks if kind == "X" else code3.z_checks)[0]
            f = (kind, ch.index, "reset", 0, None, "Z")
            ex, ez, hooks, obs, _mf = simulate_circuit_level(
                code3, 2, 0.0, 0.0, 0.0, 0.0, seed=0,
                extraction_model=EXTRACTION_SHOR, forced_faults=[f])
            assert ex == 0 and ez == 0
            assert hooks == []
            for t in range(2):
                assert not any(obs[t][0]) and not any(obs[t][1])


# ---------------------------------------------------------------------------
# p=0 regression + determinism.
# ---------------------------------------------------------------------------

class TestCleanAndDeterminism:
    @pytest.mark.parametrize("d", [3, 5])
    @pytest.mark.parametrize("rounds", [1, 2, 4])
    def test_p0_zero_everything(self, d, rounds):
        code = RotatedSurfaceCode.build(d)
        ex, ez, hooks, obs, _mf = simulate_circuit_level(
            code, rounds, 0.0, 0.0, 0.0, 0.0, seed=1,
            extraction_model=EXTRACTION_SHOR)
        assert ex == 0 and ez == 0 and hooks == []
        assert all(not any(o[0]) and not any(o[1]) for o in obs)

    def test_p0_mc_zero_failures(self):
        r = simulate_circuit_level_mc(
            3, 4, 0.0, 0.0, 0.0, 0.0, trials=200, seed=5,
            extraction_model=EXTRACTION_SHOR)
        assert r["logical_failures"] == 0

    def test_same_seed_reproducible(self, code3):
        a = simulate_circuit_level(
            code3, 4, 0.005, 0.005, 0.003, 0.003, seed=42,
            extraction_model=EXTRACTION_SHOR)
        b = simulate_circuit_level(
            code3, 4, 0.005, 0.005, 0.003, 0.003, seed=42,
            extraction_model=EXTRACTION_SHOR)
        assert a == b

    def test_mode_changes_stream(self, code3):
        """The extraction mode legitimately consumes the rng stream
        differently (more gates); same seed + different mode is
        ALLOWED to differ, but each mode is independently
        reproducible."""
        s = simulate_circuit_level(
            code3, 4, 0.005, 0.005, 0.003, 0.003, seed=42,
            extraction_model=EXTRACTION_BASELINE)
        t = simulate_circuit_level(
            code3, 4, 0.005, 0.005, 0.003, 0.003, seed=42,
            extraction_model=EXTRACTION_SHOR)
        assert s[:2] == s[:2]  # sanity
        # Both reproduce under their own mode:
        s2 = simulate_circuit_level(
            code3, 4, 0.005, 0.005, 0.003, 0.003, seed=42,
            extraction_model=EXTRACTION_BASELINE)
        t2 = simulate_circuit_level(
            code3, 4, 0.005, 0.005, 0.003, 0.003, seed=42,
            extraction_model=EXTRACTION_SHOR)
        assert s == s2 and t == t2


# ---------------------------------------------------------------------------
# Even-k validation guard.
# ---------------------------------------------------------------------------

class TestEvenKGuard:
    def test_odd_weight_support_rejected(self, code3):
        """All rotated-code supports are weight 2 or 4 (even); a
        hypothetical odd-weight check must be rejected loudly rather
        than silently measuring a random-offset stabilizer."""

        class _FakeCheck:
            index = 99
            support = (0, 1, 2)   # weight 3

        ax = [0] * 9
        az = [0] * 9

        class _NoRng:
            def random(self):
                raise RuntimeError("must not sample")

        with pytest.raises(ValueError, match="even support weight"):
            _measure_check_shor(code3, _FakeCheck(), "Z", ax, az,
                                 _NoRng(), 0.0, 0.0, 0.0, 0.0)

    def test_all_real_supports_are_even(self):
        for d in (3, 5, 7):
            code = RotatedSurfaceCode.build(d)
            for ch in code.x_checks + code.z_checks:
                assert len(ch.support) % 2 == 0


# ---------------------------------------------------------------------------
# Monte Carlo comparison (honest, bounded).
# ---------------------------------------------------------------------------

class TestMonteCarloComparison:
    def test_mc_reports_extraction_model(self):
        r = simulate_circuit_level_mc(
            3, 4, 0.005, 0.005, 0.003, 0.003, trials=200, seed=11,
            extraction_model=EXTRACTION_SHOR)
        assert r["extraction_model"] == EXTRACTION_SHOR
        assert 0.0 <= r["ci95"][0] <= r["logical_error_rate"] <= r["ci95"][1] <= 1.0

    def test_mc_reproducible(self):
        a = simulate_circuit_level_mc(
            3, 4, 0.005, 0.005, 0.003, 0.003, trials=150, seed=7,
            extraction_model=EXTRACTION_SHOR)
        b = simulate_circuit_level_mc(
            3, 4, 0.005, 0.005, 0.003, 0.003, trials=150, seed=7,
            extraction_model=EXTRACTION_SHOR)
        assert a == b

    def test_invalid_extraction_rejected(self):
        with pytest.raises(ValueError, match="Unknown extraction"):
            simulate_circuit_level_mc(
                3, 4, 0.005, 0.005, 0.003, 0.003, trials=10, seed=1,
                extraction_model="bogus_mode")
