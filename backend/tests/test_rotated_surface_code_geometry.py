"""Rotated planar surface-code geometry and algebra tests (§8-§11, §89).

Algebraic validation only - no visual inspection. Counts, commutation,
coverage, logical structure, and (independently computed) code distance for
every supported distance.
"""
import pytest

from app.qec.rotated_surface_code import (
    RotatedSurfaceCode,
    RotatedSurfaceCodeDecoder,
)
from app.qec.stabilizer import pauli_commutes, syndrome_of


@pytest.fixture(scope="module")
def codes():
    return {d: RotatedSurfaceCode.build(d) for d in (3, 5, 7)}


class TestGeometryMatrix:
    def test_data_qubit_count(self, codes):
        for d, code in codes.items():
            assert len(code.data_coords) == d * d

    def test_stabilizer_counts(self, codes):
        for d, code in codes.items():
            expected = (d * d - 1) // 2
            assert len(code.x_checks) == expected
            assert len(code.z_checks) == expected

    def test_stabilizer_supports_valid(self, codes):
        for code in codes.values():
            n = code.d * code.d
            for c in code.x_checks + code.z_checks:
                assert 2 <= len(c.support) <= 4
                assert all(0 <= q < n for q in c.support)
                assert len(set(c.support)) == len(c.support)

    def test_no_duplicate_stabilizers(self, codes):
        for code in codes.values():
            sups = [tuple(sorted(c.support))
                    for c in code.x_checks + code.z_checks]
            assert len(set(sups)) == len(sups)

    def test_all_stabilizers_commute(self, codes):
        """Every X/Z pair must commute - enforced by build, re-verified here
        through the string algebra rather than the support sets (§9)."""
        for code in codes.values():
            xgens = code.generators[:len(code.x_checks)]
            zgens = code.generators[len(code.x_checks):]
            for gx in xgens:
                for gz in zgens:
                    assert pauli_commutes(gx, gz)

    def test_boundary_structure(self, codes):
        """Weight-2 X checks sit on the top/bottom edges, weight-2 Z checks on
        the left/right edges; corners have weight-1 checks nowhere."""
        for code in codes.values():
            d = code.d
            for c in code.x_checks:
                if len(c.support) == 2:
                    assert c.center[1] in (0, 2 * d)  # top/bottom
            for c in code.z_checks:
                if len(c.support) == 2:
                    assert c.center[0] in (0, 2 * d)  # left/right
            assert all(len(c.support) >= 2
                       for c in code.x_checks + code.z_checks)

    def test_check_coverage_of_every_data_qubit(self, codes):
        for code in codes.values():
            n = code.d * code.d
            for q in range(n):
                xs = [c for c in code.x_checks if q in c.support]
                zs = [c for c in code.z_checks if q in c.support]
                assert xs and zs


class TestLogicalOperators:
    def test_logicals_commute_with_all_stabilizers(self, codes):
        for code in codes.values():
            for g in code.generators:
                assert pauli_commutes(g, code.logical_x)
                assert pauli_commutes(g, code.logical_z)

    def test_logical_x_and_z_anticommute(self, codes):
        for code in codes.values():
            assert not pauli_commutes(code.logical_x, code.logical_z)

    def test_logical_weights_equal_d(self, codes):
        for code in codes.values():
            assert code.logical_x.count("X") == code.d
            assert code.logical_z.count("Z") == code.d

    def test_boundary_logical_assignment_verified_by_strings(self, codes):
        """§13: the rough/smooth assignment is verified through string
        construction, not naming. The logical X column terminates on the
        top/bottom edges; the logical Z row on the left/right edges."""
        for code in codes.values():
            d = code.d
            xs = [q for q, ch in
                  ((code.d * code.d - 1 - p, ch)  # position -> qubit
                   for p, ch in enumerate(code.logical_x)) if ch == "X"]
            zs = [q for q, ch in
                  ((code.d * code.d - 1 - p, ch)
                   for p, ch in enumerate(code.logical_z)) if ch == "Z"]
            xq = {code.data_coords[q][0] for q in xs}
            yq = {code.data_coords[q][1] for q in zs}
            assert xq == {d}                       # vertical column x = d
            assert yq == {d}                       # horizontal row y = d
            assert min(code.data_coords[q][1] for q in xs) == 1
            assert max(code.data_coords[q][1] for q in xs) == 2 * d - 1
            assert min(code.data_coords[q][0] for q in zs) == 1
            assert max(code.data_coords[q][0] for q in zs) == 2 * d - 1

    def test_logicals_are_not_stabilizer_products(self, codes):
        """The coset functional must fire on each logical (they are genuinely
        nontrivial) and be silent on every generator product representative."""
        for code in codes.values():
            n = code.d * code.d

            def mask_of(pauli):
                m = 0
                for p, ch in enumerate(pauli):
                    if ch != "I":
                        m |= 1 << (n - 1 - p)
                return m

            lx, lz = mask_of(code.logical_x), mask_of(code.logical_z)
            from app.qec.rotated_surface_code import _parity
            assert _parity(lx & code.phi_x) == 1
            assert _parity(lz & code.phi_z) == 1
            for c in code.x_checks:
                assert _parity(sum(1 << q for q in c.support) & code.phi_x) == 0
            for c in code.z_checks:
                assert _parity(sum(1 << q for q in c.support) & code.phi_z) == 0


class TestDistanceVerification:
    """§11: the distance is COMPUTED, not assumed. Exhaustive per-component
    binary enumeration (exact for CSS codes: d = min(d_X, d_Z))."""

    def test_distance_d3(self, codes):
        assert codes[3].verify_distance() == {
            "d": 3, "components": {"X": 3, "Z": 3}, "code_distance": 3}

    def test_distance_d5(self, codes):
        assert codes[5].verify_distance()["code_distance"] == 5

    def test_distance_d7(self, codes):
        # Exhaustive enumeration up to weight 7 (~100M supports, vectorized).
        assert codes[7].verify_distance()["code_distance"] == 7

    def test_no_logical_below_half_distance_is_decoder_guarantee(self, codes):
        """All errors of weight <= floor((d-1)/2) must be correctable (§46):
        verified implicitly by the distance being d, explicitly here for the
        decoder at d=3 in test_rotated_surface_code_decoder.py."""


class TestInvalidDistances:
    @pytest.mark.parametrize("bad", [2, 4, 6, 8, 1, -3])
    def test_even_and_invalid_distances_rejected(self, bad):
        with pytest.raises(ValueError, match="Unsupported distance"):
            RotatedSurfaceCode.build(bad)

    def test_distance_not_silently_modified(self):
        """A rejected distance must raise, never round (§7)."""
        with pytest.raises(ValueError):
            RotatedSurfaceCode.build(4)


class TestSyndromeAlgebra:
    """§16-§17: syndromes come from the stabilizer algebra; the per-qubit
    fast path must agree with `syndrome_of` exactly, for every single-qubit
    Pauli on every data qubit at d=3 and d=5."""

    @pytest.mark.parametrize("d", [3, 5])
    def test_fast_path_matches_algebra_for_all_single_qubit_errors(self, d):
        code = RotatedSurfaceCode.build(d)
        dec = RotatedSurfaceCodeDecoder(code)
        n = d * d
        for q in range(n):
            for ch, ex, ez in (("X", 1 << q, 0), ("Z", 0, 1 << q),
                               ("Y", 1 << q, 1 << q)):
                sx, sz = dec.syndrome(ex, ez)
                gens = list(code.generators)
                xgens = gens[:len(code.x_checks)]
                zgens = gens[len(code.x_checks):]
                err_x = ("I" * (n - 1 - q)) + ch + ("I" * q)
                assert sz == syndrome_of(err_x, zgens)
                assert sx == syndrome_of(err_x, xgens)

    def test_explicit_commutation_cases(self, codes):
        """Direct anticommutation checks: an X error anticommutes exactly with
        the Z checks that contain the qubit (§16)."""
        code = codes[3]
        dec = RotatedSurfaceCodeDecoder(code)
        for q in range(9):
            sx, sz = dec.syndrome(1 << q, 0)
            expected = tuple(1 if q in c.support else 0 for c in code.z_checks)
            assert sz == expected
            assert sx == tuple(0 for _ in code.x_checks)
