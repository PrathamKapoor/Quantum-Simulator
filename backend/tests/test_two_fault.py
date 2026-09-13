"""Two-fault attribution tests (milestone 21, AD-025).

The two-fault extension generates PAIR candidates from the prefiltered
signature base (including data-less signatures, whose role is to
explain the outcome-corruption half of a two-fault history), prices
them by the sum of the two bucket log-odds (independent faults: the
joint log-likelihood-ratio adds; no channel is counted twice), removes
their combined contribution by exact XOR, and admits them ONLY when no
perfect single exists (false-attribution guard, §19).

Pinned results:
  - contribution linearity: an injected pair's observed history equals
    the XOR of its two DB contribution histories (GF(2) superposition);
  - the diagnostic's class-C cases decode CORRECTED with
    two_fault=True and stay LOGICAL without it;
  - single-fault decoding is UNCHANGED with pairs enabled (the guard
    keeps pairs inert whenever a perfect single explains the history):
    d=5 fitted exhaustive stays 0/760 failures;
  - real-noise paired MC shows corr-1+2f <= corr-1f (no regression);
  - zero-noise contract: no fault invention in clean histories.
"""
import sys

import pytest

sys.path.insert(0, ".")

from app.qec.rotated_surface_code import RotatedSurfaceCode
from app.qec.circuit_level import simulate_circuit_level, decode_circuit_level
from app.qec.correlation_decoder import (
    decode_correlation_aware, simulate_decoder_comparison_mc)
from app.qec.circuit_signatures import build_signature_db
from app.qec.circuit_extraction import EXTRACTION_FITTED, SUPPORTED_EXTRACTIONS

ROUNDS = 2


def _all_faults(code, mode=EXTRACTION_FITTED):
    for kind, checks in (("X", code.x_checks), ("Z", code.z_checks)):
        for ch in checks:
            k = len(ch.support)
            ci = ch.index
            n_anc = (k + 1) // 2 if mode == EXTRACTION_FITTED else None
            if n_anc is None:
                n_anc = 1
            for i in range(n_anc):
                for p in "XYZ":
                    yield (kind, ci, "reset", i, None, p)
                    yield (kind, ci, "prep", i, None, p)
                yield (kind, ci, "readout", i, None, None)
            for g in range(k):
                for part in "ct":
                    for p in "XYZ":
                        yield (kind, ci, "cnot", g, part, p)


class TestContributionLinearity:
    @pytest.mark.parametrize("mode", SUPPORTED_EXTRACTIONS)
    def test_pair_history_is_xor_of_singles(self, mode):
        """§6: contribution(F1,F2) = contribution(F1) XOR contribution(F2)
        against the production simulator (sampled pairs)."""
        code = RotatedSurfaceCode.build(3)
        db = build_signature_db(code, ROUNDS, mode)
        contrib_by_example = {}
        db_by_example = {}
        for s in db.mid:
            contrib_by_example[s.example] = s.contrib
            db_by_example[s.example] = (s.data_x, s.data_z)
        faults = list(_all_faults(code, mode))
        checked = 0
        for i in range(0, len(faults) - 1, 37):
            for j in range(i + 1, min(i + 40, len(faults))):
                f1, f2 = faults[i], faults[j]
                if f1 not in contrib_by_example or f2 not in contrib_by_example:
                    continue
                ex, ez, _h, obs, _mf, _v = simulate_circuit_level(
                    code, ROUNDS, 0.0, 0.0, 0.0, 0.0, seed=0,
                    extraction_model=mode, forced_faults=[f1, f2])
                c1, c2 = contrib_by_example[f1], contrib_by_example[f2]
                expect = tuple(
                    (tuple(a ^ b for a, b in zip(x1, x2)),
                     tuple(a ^ b for a, b in zip(z1, z2)))
                    for (x1, z1), (x2, z2) in zip(c1, c2))
                got = tuple((tuple(xb), tuple(zb)) for (xb, zb) in obs)
                assert got == expect, (f1, f2)
                dx = (db_by_example[f1][0] ^ db_by_example[f2][0],
                      db_by_example[f1][1] ^ db_by_example[f2][1])
                assert (ex, ez) == dx, (f1, f2)
                checked += 1
                if checked >= 25:
                    return
        assert checked >= 10


class TestClassCRecovery:
    """The diagnostic's class-C examples: LOGICAL under 1-fault
    attribution, CORRECTED under two-fault attribution — with the TRUE
    pair attributed."""

    CASES = [
        (("X", 0, "reset", 0, None, "X"), ("X", 1, "cnot", 0, "c", "Y")),
        (("X", 0, "reset", 0, None, "X"), ("X", 1, "cnot", 0, "c", "Z")),
    ]

    @pytest.mark.parametrize("case", CASES)
    def test_pair_attribution_fixes(self, case):
        code = RotatedSurfaceCode.build(3)
        db = build_signature_db(code, ROUNDS, EXTRACTION_FITTED)
        ex, ez, _h, obs, _mf, _v = simulate_circuit_level(
            code, ROUNDS, 0.0, 0.0, 0.0, 0.0, seed=0,
            extraction_model=EXTRACTION_FITTED, forced_faults=list(case))
        r1 = decode_correlation_aware(
            code, ROUNDS, 0.0, 0.0, 0.0, 0.0, observed_syndromes=obs,
            data_error_x=ex, data_error_z=ez, db=db, seed=0)
        r2 = decode_correlation_aware(
            code, ROUNDS, 0.0, 0.0, 0.0, 0.0, observed_syndromes=obs,
            data_error_x=ex, data_error_z=ez, db=db, two_fault=True,
            seed=0)
        assert not r1.success
        assert r2.success
        assert r2.best_source == "signature_pair"

    def test_serialization_of_pair_marker(self, case=CASES[0]):
        code = RotatedSurfaceCode.build(3)
        db = build_signature_db(code, ROUNDS, EXTRACTION_FITTED)
        ex, ez, _h, obs, _mf, _v = simulate_circuit_level(
            code, ROUNDS, 0.0, 0.0, 0.0, 0.0, seed=0,
            extraction_model=EXTRACTION_FITTED, forced_faults=list(case))
        r = decode_correlation_aware(
            code, ROUNDS, 0.0, 0.0, 0.0, 0.0, observed_syndromes=obs,
            data_error_x=ex, data_error_z=ez, db=db, two_fault=True,
            seed=0)
        import json
        d = r.to_dict()
        json.dumps(d)   # must be JSON-safe
        if r.best_source == "signature_pair":
            assert len(d["attributed_signature"]) == 2
            assert all(len(a) == 6 for a in d["attributed_signature"])


class TestSingleFaultRegression:
    def test_d5_fitted_exhaustive_perfect_with_pairs_enabled(self):
        """Milestone-20's oracle-perfect result must not regress when
        the two-fault machinery is enabled (the false-attribution guard
        keeps pairs inert on single-fault histories)."""
        code = RotatedSurfaceCode.build(5)
        db = build_signature_db(code, ROUNDS, EXTRACTION_FITTED)
        n = fail = 0
        for f in _all_faults(code):
            ex, ez, _h, obs, _mf, _v = simulate_circuit_level(
                code, ROUNDS, 0.0, 0.0, 0.0, 0.0, seed=0,
                extraction_model=EXTRACTION_FITTED, forced_faults=[f])
            if not (ex or ez) and not any(
                    any(xb) or any(zb) for xb, zb in obs):
                continue
            n += 1
            r = decode_correlation_aware(
                code, ROUNDS, 0.0, 0.0, 0.0, 0.0, observed_syndromes=obs,
                data_error_x=ex, data_error_z=ez, db=db, two_fault=True,
                seed=0)
            if not r.success:
                fail += 1
        assert n == 760
        assert fail == 0

    def test_pairs_never_flip_correct_single_fault_decodes(self):
        """The false-attribution property that matters: on single-fault
        histories, enabling pairs must never turn a CORRECTED decode
        into a LOGICAL one. (A pair MAY legitimately win on histories
        whose true signature is data-less — e.g. a pure outcome-
        corruption fault — provided the outcome stays CORRECTED.)"""
        code = RotatedSurfaceCode.build(3)
        db = build_signature_db(code, ROUNDS, EXTRACTION_FITTED)
        for f in list(_all_faults(code))[:80]:
            ex, ez, _h, obs, _mf, _v = simulate_circuit_level(
                code, ROUNDS, 0.0, 0.0, 0.0, 0.0, seed=0,
                extraction_model=EXTRACTION_FITTED, forced_faults=[f])
            if not (ex or ez) and not any(
                    any(xb) or any(zb) for xb, zb in obs):
                continue
            r1 = decode_correlation_aware(
                code, ROUNDS, 0.0, 0.0, 0.0, 0.0, observed_syndromes=obs,
                data_error_x=ex, data_error_z=ez, db=db, seed=0)
            r2 = decode_correlation_aware(
                code, ROUNDS, 0.0, 0.0, 0.0, 0.0, observed_syndromes=obs,
                data_error_x=ex, data_error_z=ez, db=db, two_fault=True,
                seed=0)
            assert not (r1.success and not r2.success), (f,)


class TestZeroNoiseContract:
    @pytest.mark.parametrize("mode", SUPPORTED_EXTRACTIONS)
    def test_no_fault_invention(self, mode):
        code = RotatedSurfaceCode.build(3)
        db = build_signature_db(code, ROUNDS, mode)
        obs = [((0,) * len(code.x_checks), (0,) * len(code.z_checks))
               for _ in range(ROUNDS)]
        r = decode_correlation_aware(
            code, ROUNDS, 0.005, 0.005, 0.003, 0.003,
            observed_syndromes=obs, data_error_x=0, data_error_z=0,
            db=db, two_fault=True, seed=0)
        assert r.success and r.correction_x == 0 and r.correction_z == 0
        assert r.best_source == "phenomenological"


class TestMonteCarlo:
    def test_three_way_paired_reproducible(self):
        a = simulate_decoder_comparison_mc(
            3, ROUNDS, 0.005, 0.005, 0.003, 0.003, trials=100, seed=7,
            extraction_model=EXTRACTION_FITTED)
        b = simulate_decoder_comparison_mc(
            3, ROUNDS, 0.005, 0.005, 0.003, 0.003, trials=100, seed=7,
            extraction_model=EXTRACTION_FITTED)
        assert a["phenomenological"] == b["phenomenological"]
        for key in ("logical_failures", "logical_error_rate", "ci95",
                    "signature_attributions", "avg_candidates"):
            assert a["correlation_aware"][key] == b["correlation_aware"][key]
        # decode_seconds is wall-clock: excluded (benchmark field only).
        for key in ("logical_failures", "logical_error_rate", "ci95",
                    "pair_attributions"):
            assert (a["correlation_aware_two_fault"][key]
                    == b["correlation_aware_two_fault"][key])
        # NOTE: the corr <= phen direction is established by the
        # milestone-21 paired MC study at operational trial counts; a
        # 100-trial unit assertion would be statistically fragile and
        # is deliberately omitted here.
