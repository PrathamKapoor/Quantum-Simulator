"""Fitted pair-decomposed extraction tests (milestone 19, AD-023).

The fitted mode measures a weight-k check with ceil(k/2) INDEPENDENT
ancillas, each coupled to at most TWO data qubits; the outcome is the
XOR of the sub-parity bits. It is NOT a cat state (no GHZ, no fan-out,
no verification, no rejection). The design rule -- cap every ancilla's
data fan-in at 2 -- was derived from the milestone-19 evidence chain:

  1. Exhaustive enumeration of the cat modes shows every DANGEROUS
     accepted weight-2 mechanism is either an EVEN correlated pattern
     on the cat (invisible to any cat-parity verifier, which only
     flags odd patterns -- this falsifies AD-022's two-verifier
     prediction) or a coupling-time fault (after any pre-coupling
     verification).
  2. The dangerous hook cap equals the maximum ancilla data fan-in;
     the cat's fan-out edges are themselves the source of the 2-leg
     correlated Z-patterns, so capping fan-in directly needs no cat.
  3. The verified cat's operational failure is its rejection load.

Structural results proven here (production path, forced_faults):
  - ideal syndrome == algebraic oracle (d=3, d=5, every single-qubit
    error);
  - weight-2 checks are BIT-FOR-BIT the baseline circuit (same rng
    stream -> same outcome, hooks, and data frame);
  - the fan-in cap: NO single fault of the fitted circuit produces a
    data error of weight > 2 (at either distance);
  - W_max_accepted (dangerous, LOGICAL outcome) = 2 at d=3 (as for
    every mode -- weight-2 is undetectable at d=3); at d=5 the
    accepted-LOGICAL count is measured and asserted.
"""
import numpy as np
import pytest

from app.qec.rotated_surface_code import RotatedSurfaceCode, RotatedSurfaceCodeDecoder
from app.qec.circuit_level import (
    extract_syndrome_noiseless,
    simulate_circuit_level,
    simulate_circuit_level_mc,
    decode_circuit_level,
    _measure_one_check,
)
from app.qec.circuit_extraction import (
    EXTRACTION_BASELINE, EXTRACTION_SHOR, EXTRACTION_SHOR_VERIFIED,
    EXTRACTION_FITTED, get_extraction_model, list_extraction_models,
)


@pytest.fixture(scope="module")
def code3():
    return RotatedSurfaceCode.build(3)


@pytest.fixture(scope="module")
def code5():
    return RotatedSurfaceCode.build(5)


def _all_faults_fitted(code):
    """Every elementary single fault of every fitted check: per pair
    ancilla (reset X/Y/Z, prep X/Y/Z, readout) and per CNOT gate
    (control/target X/Y/Z). Gates are indexed 0..k-1 in circuit order
    (pair-major)."""
    for kind, checks in (("X", code.x_checks), ("Z", code.z_checks)):
        for ch in checks:
            k = len(ch.support)
            ci = ch.index
            n_anc = (k + 1) // 2
            for i in range(n_anc):
                for p in "XYZ":
                    yield (kind, ci, "reset", i, None, p)
                    yield (kind, ci, "prep", i, None, p)
                yield (kind, ci, "readout", i, None, None)
            for g in range(k):
                for part in "ct":
                    for p in "XYZ":
                        yield (kind, ci, "cnot", g, part, p)


# ---------------------------------------------------------------------------
# Registry.
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_fitted_registered(self):
        names = {m["name"] for m in list_extraction_models()}
        assert EXTRACTION_FITTED in names
        assert len(names) == 4

    def test_fitted_has_measure_check(self):
        m = get_extraction_model(EXTRACTION_FITTED)
        assert callable(m.measure_check)

    def test_fitted_cnot_cost_matches_baseline(self):
        """The fitted mode's whole point: baseline CNOT count."""
        assert get_extraction_model(EXTRACTION_FITTED).n_cnots_per_data == 1
        assert get_extraction_model(EXTRACTION_BASELINE).n_cnots_per_data == 1


# ---------------------------------------------------------------------------
# Ideal correctness.
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
                    code, ex, ez, extraction_model=EXTRACTION_FITTED)
                sx, sz = dec.syndrome(ex, ez)
                assert list(ox) == list(sx)
                assert list(oz) == list(sz)

    @pytest.mark.parametrize("d", [3, 5])
    @pytest.mark.parametrize("rounds", [1, 2, 4])
    def test_p0_no_errors_no_hooks(self, d, rounds):
        code = RotatedSurfaceCode.build(d)
        ex, ez, hooks, obs, _mf, ve = simulate_circuit_level(
            code, rounds, 0.0, 0.0, 0.0, 0.0, seed=1,
            extraction_model=EXTRACTION_FITTED)
        assert ex == 0 and ez == 0 and hooks == [] and ve == []

    def test_no_even_weight_constraint(self, code3):
        """Unlike the cat modes, fitted has no even-k requirement: a
        synthetic odd-weight (3) support runs as pair + singleton
        (2 ancillas), and an X error on a support qubit flips exactly
        its sub-parity bit (the XOR over 2+1 ancillas still equals the
        weight-3 Z-parity eigenvalue change)."""
        ch = code3.z_checks[0]
        em = get_extraction_model(EXTRACTION_FITTED)
        n = 9
        sup3 = tuple(ch.support[:3])
        ax = [1 if q == sup3[0] else 0 for q in range(n)]
        az = [0] * n
        out, hooked, vf = em.measure_check(
            code3, ch, "Z", ax, az, np.random.default_rng(0),
            0.0, 0.0, 0.0, 0.0, support_order=sup3)
        assert vf == 0 and out == 1 and not hooked


# ---------------------------------------------------------------------------
# k=2 bit-for-bit baseline equivalence.
# ---------------------------------------------------------------------------

class TestWeight2BaselineEquivalence:
    @pytest.mark.parametrize("kind", ["X", "Z"])
    @pytest.mark.parametrize("seed", [999, 1234, 4242])
    def test_k2_identical_to_baseline(self, code3, kind, seed):
        """For weight-2 checks the fitted circuit IS the baseline
        circuit: same gates, same noise-sampling order -> under the
        same rng stream the outcome, hook flag, and mutated data frame
        are identical."""
        em = get_extraction_model(EXTRACTION_FITTED)
        n = 9
        for ch in (code3.x_checks if kind == "X" else code3.z_checks):
            if len(ch.support) != 2:
                continue
            ax = [(q * 7 + 3) % 2 for q in range(n)]
            az = [(q * 5 + 1) % 2 for q in range(n)]
            ax_f, az_f = list(ax), list(az)
            out_b, hook_b = _measure_one_check(
                code3, ch, kind, ax, az, np.random.default_rng(seed),
                0.02, 0.01, 0.01, 0.03)
            out_f, hook_f, _vf = em.measure_check(
                code3, ch, kind, ax_f, az_f, np.random.default_rng(seed),
                0.02, 0.01, 0.01, 0.03)
            assert out_b == out_f and hook_b == hook_f
            assert ax == ax_f and az == az_f


# ---------------------------------------------------------------------------
# Exhaustive single-fault enumeration (structural results).
# ---------------------------------------------------------------------------

class TestExhaustiveFittedFaults:
    @pytest.mark.parametrize("d", [3, 5])
    def test_fan_in_cap_data_weight_le_2(self, d):
        """THE structural property: no single fault anywhere in the
        fitted circuit produces a data error of weight > 2 (each
        ancilla touches at most 2 data qubits and pairs never
        interact)."""
        code = RotatedSurfaceCode.build(d)
        for f in _all_faults_fitted(code):
            ex, ez, _hooks, _obs, _mf, ve = simulate_circuit_level(
                code, 2, 0.0, 0.0, 0.0, 0.0, seed=0,
                extraction_model=EXTRACTION_FITTED, forced_faults=[f])
            w = bin(ex).count("1") + bin(ez).count("1")
            assert w <= 2, (f, w)
            assert ve == []   # no verification -> nothing is ever rejected

    @pytest.mark.parametrize("d", [3, 5])
    def test_dangerous_accepted_weight_is_2(self, d):
        """W_max_accepted (LOGICAL outcome) = 2: at d=3 every weight-2
        accepted fault is undetectable; the count of accepted-LOGICAL
        faults is asserted as measured (deterministic enumeration)."""
        code = RotatedSurfaceCode.build(d)
        acc_logical = []
        for f in _all_faults_fitted(code):
            ex, ez, hooks, obs, _mf, ve = simulate_circuit_level(
                code, 2, 0.0, 0.0, 0.0, 0.0, seed=0,
                extraction_model=EXTRACTION_FITTED, forced_faults=[f])
            w = bin(ex).count("1") + bin(ez).count("1")
            res = decode_circuit_level(
                code, 2, 0.0, 0.0, 0.0, 0.0, data_error_x=ex,
                data_error_z=ez, observed_syndromes=obs,
                hook_events=hooks, seed=0)
            if res.outcome.startswith("LOGICAL"):
                acc_logical.append((f, w))
        assert max(w for _, w in acc_logical) == 2
        # Measured deterministic enumeration pins (see AD-023 mechanism
        # inventory): d=3 -> 36 accepted-LOGICAL (30 weight-2 + 6
        # weight-1-with-corrupted-outcome); d=5 -> 20 (10 weight-2 +
        # 10 weight-1). The weight-1 cases are single faults that
        # corrupt BOTH one data qubit and the same check's outcome
        # bit, so the decoder misattributes the error -- the same
        # outcome-correlation mechanism the cat modes have.
        assert len(acc_logical) == (36 if d == 3 else 20)

    def test_smaller_fault_surface_than_cat_modes_at_d5(self, code5):
        """The fitted mode's structural advantage at equal outcome
        semantics: a strictly SMALLER single-fault surface than either
        cat mode (fewer noisy locations per round), because it has no
        fan-out and no verification pass. The accepted-LOGICAL COUNT
        happens to equal unverified Shor's (20 = 20, different
        mechanisms) -- exposure, not this count, is what differs in
        Monte Carlo."""
        def surface(mode):
            em = get_extraction_model(mode)
            n = 0
            for kind, checks in (("X", code5.x_checks), ("Z", code5.z_checks)):
                for ch in checks:
                    k = len(ch.support)
                    n_anc = (k + 1) // 2 if mode == EXTRACTION_FITTED else k
                    n += n_anc * 7          # reset x3, prep x3, readout
                    n += (k if mode == EXTRACTION_FITTED
                          else 2 * k - 1) * 6   # cnot cx2 x3
                    if mode == EXTRACTION_SHOR_VERIFIED:
                        n += 6 + k * 6 + 1   # v reset/prep, vcnot, vreadout
            return n
        assert surface(EXTRACTION_FITTED) < surface(EXTRACTION_SHOR)
        assert surface(EXTRACTION_FITTED) < surface(EXTRACTION_SHOR_VERIFIED)


# ---------------------------------------------------------------------------
# §13 mechanism regression: the exact AD-021 failure mode across modes.
# ---------------------------------------------------------------------------

class TestMechanismRegression:
    def test_ad021_mechanism_across_modes(self, code3):
        """The AD-021 dangerous mechanism (reset-Y on the 2nd ancilla
        of a weight-4 X-check) driven through every mode that has that
        location. Fitted's analogue (reset-Y on the pair ancilla
        holding support[1]) is ACCEPTED with weight exactly 2 (the
        fan-in cap) -- dangerous at d=3 like every mode, but from a
        strictly smaller fault surface."""
        ch = next(c for c in code3.x_checks if len(c.support) == 4)
        # unverified Shor: accepted, weight 2, LOGICAL at d=3
        ex, ez, hooks, obs, _mf, ve = simulate_circuit_level(
            code3, 2, 0.0, 0.0, 0.0, 0.0, seed=0,
            extraction_model=EXTRACTION_SHOR,
            forced_faults=[("X", ch.index, "reset", 1, None, "Y")])
        assert bin(ex).count("1") + bin(ez).count("1") == 2
        assert ve == []
        # verified Shor: the same fault is REJECTED (AD-022 result)
        ex, ez, hooks, obs, _mf, ve = simulate_circuit_level(
            code3, 2, 0.0, 0.0, 0.0, 0.0, seed=0,
            extraction_model=EXTRACTION_SHOR_VERIFIED,
            forced_faults=[("X", ch.index, "reset", 1, None, "Y")])
        assert len(ve) == 1
        # fitted: pair ancilla 0 (holds support[0:2]): accepted, weight 2
        ex, ez, hooks, obs, _mf, ve = simulate_circuit_level(
            code3, 2, 0.0, 0.0, 0.0, 0.0, seed=0,
            extraction_model=EXTRACTION_FITTED,
            forced_faults=[("X", ch.index, "reset", 0, None, "Y")])
        w = bin(ex).count("1") + bin(ez).count("1")
        assert w == 2 and ve == []


# ---------------------------------------------------------------------------
# Monte Carlo.
# ---------------------------------------------------------------------------

class TestMonteCarlo:
    def test_p0_no_failures(self):
        r = simulate_circuit_level_mc(
            3, 4, 0.0, 0.0, 0.0, 0.0, trials=50, seed=5,
            extraction_model=EXTRACTION_FITTED)
        assert r["logical_failures"] == 0
        assert r["rejected_trials"] == 0   # no verification, ever

    def test_reproducible(self):
        a = simulate_circuit_level_mc(
            3, 4, 0.005, 0.005, 0.003, 0.003, trials=150, seed=7,
            extraction_model=EXTRACTION_FITTED)
        b = simulate_circuit_level_mc(
            3, 4, 0.005, 0.005, 0.003, 0.003, trials=150, seed=7,
            extraction_model=EXTRACTION_FITTED)
        assert a == b

    def test_invalid_extraction_rejected(self):
        with pytest.raises(ValueError, match="Unknown extraction"):
            simulate_circuit_level_mc(
                3, 4, 0.005, 0.005, 0.003, 0.003, trials=10, seed=1,
                extraction_model="fitted_nope")

    def test_d3_ordering_baseline_fitted_unverified(self):
        """Measured ordering at d=3 combined-mid (2000 trials, seed 23):
        baseline < fitted < unverified Shor. The fitted mode pays a
        little more measurement noise than baseline (extra reset/prep/
        readout on weight-4 checks) and buys nothing at d=3 (weight-2
        is undetectable), but stays well below the cat modes."""
        def p_L(mode):
            return simulate_circuit_level_mc(
                3, 4, 0.005, 0.005, 0.003, 0.003, trials=2000,
                seed=23, extraction_model=mode)["logical_error_rate"]
        assert p_L(EXTRACTION_BASELINE) < p_L(EXTRACTION_FITTED)
        assert p_L(EXTRACTION_FITTED) < p_L(EXTRACTION_SHOR)

    def test_d5_fitted_beats_unverified_and_verified(self):
        """At d=5 the fan-in cap pays: fitted beats BOTH cat modes
        (which carry strictly more exposure for the same coupling
        structure). 2000 trials, seed 23, combined-mid."""
        def p_L(mode):
            return simulate_circuit_level_mc(
                5, 4, 0.005, 0.005, 0.003, 0.003, trials=2000,
                seed=23, extraction_model=mode)["logical_error_rate"]
        assert p_L(EXTRACTION_FITTED) < p_L(EXTRACTION_SHOR)
        assert p_L(EXTRACTION_FITTED) < p_L(EXTRACTION_SHOR_VERIFIED)
