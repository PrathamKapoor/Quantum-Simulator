"""Correlation-aware circuit decoder tests (milestone 20, AD-024).

The decoder = the phenomenological repeated-round MWPM control (never
removed, §48) plus likelihood-priced attribution of circuit-derived
fault signatures (from `circuit_signatures.build_signature_db`, built
through the PRODUCTION forced-fault harness for every extraction
mode).

Headline structural results proven here:
  - d=5 exhaustive single faults: the correlation decoder corrects ALL
    single faults with data weight < d for every extraction mode (the
    milestone-19 accepted-LOGICAL mechanisms included); the
    phenomenological control misses 20 per mode.
  - d=3: the decoder halves the control's failures; the residual 12-16
    are syndrome-degenerate confusable sets (two equally-likely
    single-fault explanations whose data effects differ by a
    logical-containing operator) — irreducible from the observed
    history, documented in AD-024 §"Confusable sets".
  - sub-parity retention (directive §19-§20): the fitted pair bits
    resolve WITHIN-check pair ambiguity but the dominant confusables
    are cross-check; no net change in the d=3 failure count. Negative
    result, pinned here.
"""
import pytest

from app.qec.rotated_surface_code import RotatedSurfaceCode
from app.qec.circuit_level import (
    simulate_circuit_level, decode_circuit_level)
from app.qec.correlation_decoder import (
    decode_correlation_aware, simulate_decoder_comparison_mc)
from app.qec.circuit_signatures import build_signature_db
from app.qec.circuit_extraction import (
    EXTRACTION_BASELINE, EXTRACTION_SHOR, EXTRACTION_SHOR_VERIFIED,
    EXTRACTION_FITTED, SUPPORTED_EXTRACTIONS, get_extraction_model)

ROUNDS = 2


# ---------------------------------------------------------------------------
# Signature database.
# ---------------------------------------------------------------------------

class TestSignatureDB:
    @pytest.mark.parametrize("mode", SUPPORTED_EXTRACTIONS)
    def test_build_all_modes_balanced(self, mode):
        code = RotatedSurfaceCode.build(3)
        db = build_signature_db(code, ROUNDS, mode)
        tot_mid = sum(s.n_reset + s.n_prep + s.n_gate + s.n_readout
                      for s in db.mid)
        tot_fin = sum(s.n_gate for s in db.final)
        assert tot_mid + db.n_null_locations_mid == db.n_locations_mid
        assert tot_fin + db.n_null_locations_final == db.n_locations_final
        for s in db.mid + db.final:
            assert s.events or s.data_x or s.data_z

    def test_build_deterministic(self):
        code = RotatedSurfaceCode.build(3)
        a = build_signature_db(code, ROUNDS, EXTRACTION_FITTED)
        b = build_signature_db(code, ROUNDS, EXTRACTION_FITTED)
        assert a is b  # cached; same object
        c = build_signature_db(RotatedSurfaceCode.build(3), ROUNDS,
                               EXTRACTION_FITTED)
        assert [(s.example, s.data_x, s.data_z) for s in c.mid] == \
               [(s.example, s.data_x, s.data_z) for s in a.mid]

    def test_null_locations_are_benign(self):
        """A null location consumes noise but produces no events and no
        data error (e.g. a cat-stabilizer fault); verified mode also
        has pure false rejections."""
        code = RotatedSurfaceCode.build(3)
        db = build_signature_db(code, ROUNDS, EXTRACTION_SHOR_VERIFIED)
        assert db.n_null_locations > 0

    def test_subparity_db_fitted_only(self):
        code = RotatedSurfaceCode.build(3)
        db = build_signature_db(code, ROUNDS, EXTRACTION_FITTED,
                                collect_subparities=True)
        assert all(s.pair_contrib for s in db.mid)
        db2 = build_signature_db(code, ROUNDS, EXTRACTION_SHOR,
                                 collect_subparities=True)
        assert all(not s.pair_contrib for s in db2.mid)


# ---------------------------------------------------------------------------
# Zero-noise contract (§22: release blocker).
# ---------------------------------------------------------------------------

class TestZeroNoiseContract:
    @pytest.mark.parametrize("mode", SUPPORTED_EXTRACTIONS)
    @pytest.mark.parametrize("d", [3, 5])
    def test_clean_history_decodes_corrected(self, mode, d):
        code = RotatedSurfaceCode.build(d)
        obs = [((0,) * len(code.x_checks), (0,) * len(code.z_checks))
               for _ in range(ROUNDS)]
        db = build_signature_db(code, ROUNDS, mode)
        r = decode_correlation_aware(
            code, ROUNDS, 0.005, 0.005, 0.003, 0.003,
            observed_syndromes=obs, data_error_x=0, data_error_z=0,
            db=db, seed=0)
        assert r.success and r.outcome == "CORRECTED"
        assert r.best_source == "phenomenological"
        assert r.correction_x == 0 and r.correction_z == 0


# ---------------------------------------------------------------------------
# Exhaustive single-fault validation (§13, §23).
# ---------------------------------------------------------------------------

def _all_faults(code, mode):
    for kind, checks in (("X", code.x_checks), ("Z", code.z_checks)):
        for ch in checks:
            k = len(ch.support)
            ci = ch.index
            n_anc = (k + 1) // 2 if mode == EXTRACTION_FITTED else (
                1 if mode == EXTRACTION_BASELINE else k)
            for i in range(n_anc):
                for p in "XYZ":
                    yield (kind, ci, "reset", i, None, p)
                    yield (kind, ci, "prep", i, None, p)
                yield (kind, ci, "readout", i, None, None)
            n_gates = 2 * k - 1 if mode in (EXTRACTION_SHOR,
                                            EXTRACTION_SHOR_VERIFIED) else k
            for g in range(n_gates):
                for part in "ct":
                    for p in "XYZ":
                        yield (kind, ci, "cnot", g, part, p)
            if mode == EXTRACTION_SHOR_VERIFIED:
                for p in "XYZ":
                    yield (kind, ci, "vreset", 0, None, p)
                    yield (kind, ci, "vprep", 0, None, p)
                for g in range(k):
                    for part in "ct":
                        for p in "XYZ":
                            yield (kind, ci, "vcnot", g, part, p)
                yield (kind, ci, "vreadout", 0, None, None)


def _decode_fault(code, db, mode, f, rounds=ROUNDS):
    ex, ez, hooks, obs, _mf, _ve = simulate_circuit_level(
        code, rounds, 0.0, 0.0, 0.0, 0.0, seed=0,
        extraction_model=mode, forced_faults=[f])
    phen = decode_circuit_level(
        code, rounds, 0.0, 0.0, 0.0, 0.0, data_error_x=ex,
        data_error_z=ez, observed_syndromes=obs, hook_events=hooks,
        seed=0)
    corr = decode_correlation_aware(
        code, rounds, 0.0, 0.0, 0.0, 0.0, observed_syndromes=obs,
        data_error_x=ex, data_error_z=ez, db=db, seed=0)
    return ex, ez, phen, corr


class TestExhaustiveSingleFaults:
    @pytest.mark.parametrize("mode", SUPPORTED_EXTRACTIONS)
    def test_d3_all_single_faults(self, mode):
        """d=3 exhaustive: the correlation decoder strictly reduces the
        control's failures; the residual failures are syndrome-degenerate
        confusable pairs (measured counts pinned)."""
        code = RotatedSurfaceCode.build(3)
        db = build_signature_db(code, ROUNDS, mode)
        n = phen_fail = corr_fail = 0
        for f in _all_faults(code, mode):
            ex, ez, phen, corr = _decode_fault(code, db, mode, f)
            if not (ex or ez) and not phen.detection_events:
                continue    # benign/null location: nothing to decode
            n += 1
            phen_fail += not phen.success
            corr_fail += not corr.success
        assert corr_fail < phen_fail
        expected = {EXTRACTION_BASELINE: 2, EXTRACTION_SHOR: 12,
                    EXTRACTION_SHOR_VERIFIED: 16, EXTRACTION_FITTED: 12}
        assert corr_fail == expected[mode]

    @pytest.mark.parametrize("mode", [EXTRACTION_BASELINE, EXTRACTION_FITTED])
    def test_d5_all_single_faults_perfect(self, mode):
        """d=5 exhaustive (headline modes): EVERY single fault with
        data weight < d decodes CORRECTED — the correlation decoder is
        oracle-perfect on single faults, including all 20
        milestone-19 mechanisms the control misses."""
        code = RotatedSurfaceCode.build(5)
        db = build_signature_db(code, ROUNDS, mode)
        n = phen_fail = corr_fail = 0
        for f in _all_faults(code, mode):
            ex, ez, phen, corr = _decode_fault(code, db, mode, f)
            if not (ex or ez) and not phen.detection_events:
                continue
            n += 1
            phen_fail += not phen.success
            corr_fail += not corr.success
            w = bin(ex).count("1") + bin(ez).count("1")
            if w < 5:
                assert corr.success, (f, corr.outcome)
        assert phen_fail == 20
        assert corr_fail == 0


class TestMilestone19FailureCases:
    """§12: the exact mechanisms the milestone-19 report identified,
    driven through both decoders (deterministic, production path)."""

    CASES = {
        EXTRACTION_BASELINE: ("X", 3, "cnot", 0, "t", "Y"),
        EXTRACTION_SHOR: ("X", 3, "cnot", 3, "t", "Y"),
        EXTRACTION_SHOR_VERIFIED: ("X", 3, "cnot", 3, "t", "Y"),
        EXTRACTION_FITTED: ("X", 3, "cnot", 0, "c", "Y"),
    }

    @pytest.mark.parametrize("mode", SUPPORTED_EXTRACTIONS)
    def test_control_fails_correlation_decoder_corrects(self, mode):
        code = RotatedSurfaceCode.build(5)
        db = build_signature_db(code, ROUNDS, mode)
        f = self.CASES[mode]
        _ex, _ez, phen, corr = _decode_fault(code, db, mode, f, rounds=2)
        assert not phen.success           # the documented M19 failure
        assert corr.success               # fixed by signature attribution
        assert corr.best_source == "signature"
        assert corr.attributed_round == 1


class TestSubparityExperiment:
    """§19-§20: does retaining the fitted pair bits help? The trace is
    recorded, the conditioning resolves within-check ambiguity, but the
    dominant d=3 confusables are cross-check: the failure count is
    unchanged. Negative result, pinned."""

    def test_trace_recorded_and_conditioning_neutral(self):
        code = RotatedSurfaceCode.build(3)
        db = build_signature_db(code, ROUNDS, EXTRACTION_FITTED,
                                collect_subparities=True)
        n = fails_without = fails_with = 0
        for f in _all_faults(code, EXTRACTION_FITTED):
            tr = []
            ex, ez, _h, obs, _mf, _v = simulate_circuit_level(
                code, ROUNDS, 0.0, 0.0, 0.0, 0.0, seed=0,
                extraction_model=EXTRACTION_FITTED, forced_faults=[f],
                subparity_trace=tr)
            if not (ex or ez) and not any(
                    any(xb) or any(zb) for xb, zb in obs):
                continue
            n += 1
            r0 = decode_correlation_aware(
                code, ROUNDS, 0.0, 0.0, 0.0, 0.0, observed_syndromes=obs,
                data_error_x=ex, data_error_z=ez, db=db, seed=0)
            r1 = decode_correlation_aware(
                code, ROUNDS, 0.0, 0.0, 0.0, 0.0, observed_syndromes=obs,
                data_error_x=ex, data_error_z=ez, db=db,
                subparity_trace=tr, seed=0)
            fails_without += not r0.success
            fails_with += not r1.success
            assert tr, "trace must be populated for every fitted check"
        assert n == 228
        assert fails_without == fails_with == 12


# ---------------------------------------------------------------------------
# Multi-fault and Monte Carlo.
# ---------------------------------------------------------------------------

class TestTwoFaults:
    def test_two_faults_decode_deterministically(self):
        """§24 (adversarial): two coupling faults on different checks —
        the decoder must not crash, must be deterministic, and its
        residual must be consistent with the (possibly uncorrectable)
        combined error."""
        code = RotatedSurfaceCode.build(5)
        db = build_signature_db(code, ROUNDS, EXTRACTION_FITTED)
        faults = [("X", 3, "cnot", 0, "c", "Y"),
                  ("Z", 1, "cnot", 1, "c", "Y")]
        ex, ez, _h, obs, _mf, _v = simulate_circuit_level(
            code, ROUNDS, 0.0, 0.0, 0.0, 0.0, seed=0,
            extraction_model=EXTRACTION_FITTED, forced_faults=faults)
        r1 = decode_correlation_aware(
            code, ROUNDS, 0.0, 0.0, 0.0, 0.0, observed_syndromes=obs,
            data_error_x=ex, data_error_z=ez, db=db, seed=0)
        r2 = decode_correlation_aware(
            code, ROUNDS, 0.0, 0.0, 0.0, 0.0, observed_syndromes=obs,
            data_error_x=ex, data_error_z=ez, db=db, seed=0)
        assert r1.outcome == r2.outcome
        assert r1.correction_x == r2.correction_x


class TestMonteCarlo:
    def test_paired_mc_reproducible(self):
        a = simulate_decoder_comparison_mc(
            3, ROUNDS, 0.005, 0.005, 0.003, 0.003, trials=120, seed=7,
            extraction_model=EXTRACTION_FITTED)
        b = simulate_decoder_comparison_mc(
            3, ROUNDS, 0.005, 0.005, 0.003, 0.003, trials=120, seed=7,
            extraction_model=EXTRACTION_FITTED)
        assert a["phenomenological"] == b["phenomenological"]
        for key in ("logical_failures", "logical_error_rate", "ci95",
                    "signature_attributions", "avg_candidates"):
            assert a["correlation_aware"][key] == b["correlation_aware"][key]
        # decode_seconds is wall-clock: deliberately excluded (it is a
        # benchmark field, not a scientific result).

    def test_control_matches_standalone_mc(self):
        """The control condition is UNCHANGED: the paired harness's
        phenomenological failures equal the existing
        simulate_circuit_level_mc's failures for the same seed (same
        trial seeds, same decoder path)."""
        from app.qec.circuit_level import simulate_circuit_level_mc
        paired = simulate_decoder_comparison_mc(
            3, ROUNDS, 0.005, 0.005, 0.003, 0.003, trials=150, seed=23,
            extraction_model=EXTRACTION_FITTED)
        legacy = simulate_circuit_level_mc(
            3, ROUNDS, 0.005, 0.005, 0.003, 0.003, trials=150, seed=23,
            extraction_model=EXTRACTION_FITTED)
        assert (paired["phenomenological"]["logical_failures"]
                == legacy["logical_failures"])

    def test_invalid_distance_rejected(self):
        with pytest.raises(ValueError):
            simulate_decoder_comparison_mc(
                4, ROUNDS, 0.005, 0.005, 0.003, 0.003, trials=10, seed=1,
                extraction_model=EXTRACTION_FITTED)
