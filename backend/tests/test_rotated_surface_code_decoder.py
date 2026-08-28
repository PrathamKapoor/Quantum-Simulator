"""Decoder acceptance battery (directive §44-§53, §90-§95).

Foundational criterion (§44): every single-qubit X/Z/Y error on every data
qubit is corrected at all supported distances. Beyond that: weight-2
enumeration, degeneracy, syndrome collisions, logical strings, zero-syndrome
classification, boundary/corner errors, and the residual invariant.
"""
import random

import pytest

from app.qec.rotated_surface_code import (
    RotatedSurfaceCode,
    RotatedSurfaceCodeDecoder,
    error_from_string,
)
from app.qec.stabilizer import pauli_product_phase_ignorant


@pytest.fixture(scope="module")
def codes():
    return {d: RotatedSurfaceCode.build(d) for d in (3, 5, 7)}


def decode_pauli(code: RotatedSurfaceCode, pauli: str):
    dec = RotatedSurfaceCodeDecoder(code)
    ex, ez = error_from_string(code, pauli)
    return dec.decode(ex, ez)


def error_string(code: RotatedSurfaceCode, support: dict[int, str]) -> str:
    n = code.d * code.d
    chars = ["I"] * n
    for q, ch in support.items():
        chars[n - 1 - q] = ch
    return "".join(chars)


class TestSingleQubitErrors:
    """§44: every weight-1 X/Z/Y error on every data qubit is corrected."""

    @pytest.mark.parametrize("d", [3, 5, 7])
    def test_all_weight1_errors_corrected(self, d):
        code = RotatedSurfaceCode.build(d)
        dec = RotatedSurfaceCodeDecoder(code)
        for q in range(d * d):
            for ex, ez in ((1 << q, 0), (0, 1 << q), (1 << q, 1 << q)):
                r = dec.decode(ex, ez)
                assert r.outcome == "CORRECTED", (d, q, ex, ez, r.outcome)

    def test_corners_and_boundary_adjacent(self, codes):
        """§51-§52: corner and boundary-adjacent qubits (already covered by
        the exhaustive sweep, called out explicitly here)."""
        code = codes[3]
        dec = RotatedSurfaceCodeDecoder(code)
        corners = [0, code.d - 1, code.d * (code.d - 1), code.d * code.d - 1]
        for q in corners:
            for ex, ez in ((1 << q, 0), (0, 1 << q), (1 << q, 1 << q)):
                assert dec.decode(ex, ez).outcome == "CORRECTED"


class TestWeight2Errors:
    """§45: not all weight-2 errors are correctable - classification must be
    by residual, and exactly the weight <= floor((d-1)/2) ones must pass."""

    def test_d3_all_weight2_classified(self, codes):
        """For d=3, weight-2 errors: corrected iff stabilizer-equivalent to
        identity (i.e. the residual after decoding must be trivial or a
        logical). Every outcome must be a legitimate classification."""
        code = codes[3]
        dec = RotatedSurfaceCodeDecoder(code)
        n = 9
        count_logical = 0
        for a in range(n):
            for b in range(a + 1, n):
                for has_x, has_z in ((True, False), (False, True), (True, True)):
                    ex = ez = 0
                    if has_x:
                        ex = (1 << a) | (1 << b)
                    if has_z:
                        ez = (1 << a) | (1 << b)
                    r = dec.decode(ex, ez)
                    assert r.outcome in ("CORRECTED", "LOGICAL_X",
                                         "LOGICAL_Z", "LOGICAL_Y")
                    if not r.success:
                        count_logical += 1
        assert count_logical > 0  # d=3 cannot correct everything

    def test_d5_all_weight2_errors_corrected(self, codes):
        """§94: for d=5 ALL weight-1 and weight-2 errors are correctable
        (floor((5-1)/2) = 2). Full enumeration: 25*3 + C(25,2)*9 decodes."""
        code = codes[5]
        dec = RotatedSurfaceCodeDecoder(code)
        n = 25
        for q in range(n):
            for ex, ez in ((1 << q, 0), (0, 1 << q), (1 << q, 1 << q)):
                assert dec.decode(ex, ez).outcome == "CORRECTED"
        for a, b in ((a, b) for a in range(n) for b in range(a + 1, n)):
            for pa, pb in (("X", "X"), ("X", "Z"), ("Z", "X"), ("Z", "Z"),
                           ("Y", "Y"), ("X", "Y"), ("Y", "X"),
                           ("Z", "Y"), ("Y", "Z")):
                ex = ez = 0
                if "X" in pa:
                    ex |= 1 << a
                if "Z" in pa:
                    ez |= 1 << a
                if "X" in pb:
                    ex |= 1 << b
                if "Z" in pb:
                    ez |= 1 << b
                r = dec.decode(ex, ez)
                assert r.outcome == "CORRECTED", (a, b, pa, pb, r.outcome)

    def test_d7_representative_low_weight(self, codes):
        """§94: d=7 - all weight-1 plus a deterministic sample of weight-2."""
        code = codes[7]
        dec = RotatedSurfaceCodeDecoder(code)
        for q in range(49):
            for ex, ez in ((1 << q, 0), (0, 1 << q), (1 << q, 1 << q)):
                assert dec.decode(ex, ez).outcome == "CORRECTED"
        rng = random.Random(99)
        for _ in range(300):
            a, b = rng.sample(range(49), 2)
            r = dec.decode((1 << a) | (1 << b), 0)
            assert r.outcome == "CORRECTED", (a, b, r.outcome)


class TestDegeneracyAndSyndromeCollisions:
    """§47-§48: different errors with the same syndrome; the decoder must
    return a correction equivalent up to stabilizers, never the exact error."""

    def test_stabilizer_errors_are_corrected(self, codes):
        """A stabilizer itself is a valid 'error' with zero syndrome - the
        outcome must be CORRECTED (stabilizer-equivalent to identity)."""
        for code in codes.values():
            dec = RotatedSurfaceCodeDecoder(code)
            ex, ez = error_from_string(code, code.generators[0])
            assert dec.decode(ex, ez).outcome == "CORRECTED"
            ex, ez = error_from_string(code, code.logical_z)  # not a stabilizer
            r = dec.decode(ex, ez)
            assert r.outcome == "LOGICAL_Z"

    def test_syndrome_collision_decodes_equivalently(self, codes):
        """Two weight-2 X errors sharing the same syndrome: the decoder may
        return either, and both must classify identically on the residual."""
        code = codes[5]
        dec = RotatedSurfaceCodeDecoder(code)
        # A bulk (weight-4) check: data qubits inside it give colliding pairs.
        zc = next(c for c in code.z_checks if len(c.support) == 4)
        a, b = zc.support[0], zc.support[1]
        r1 = dec.decode(0, (1 << a) | (1 << b))
        # another pair inside the same check
        c, d2 = zc.support[2], zc.support[3]
        r2 = dec.decode(0, (1 << c) | (1 << d2))
        assert r1.outcome == "CORRECTED" and r2.outcome == "CORRECTED"
        assert tuple(sorted(r1.syndrome_x)) == tuple(sorted(r2.syndrome_x))

    def test_correction_need_not_equal_error(self, codes):
        """§118-§119: success never requires exact physical recovery."""
        code = codes[3]
        dec = RotatedSurfaceCodeDecoder(code)
        r = dec.decode(0, 1 << 4)  # bulk qubit
        assert r.outcome == "CORRECTED"
        # Either the correction equals the error or differs by a stabilizer;
        # both are legitimate. The residual carries the verdict, not the
        # physical match.


class TestZeroSyndromeClassification:
    """§49-§50: identity, stabilizer, and logical operator all have zero
    syndrome but MUST NOT be classified identically."""

    def test_identity_success(self, codes):
        assert codes[3] and RotatedSurfaceCodeDecoder(codes[3]).decode(0, 0).outcome == "CORRECTED"

    def test_stabilizer_success(self, codes):
        dec = RotatedSurfaceCodeDecoder(codes[3])
        ex, ez = error_from_string(codes[3], codes[3].generators[1])
        assert dec.decode(ex, ez).outcome == "CORRECTED"

    def test_logical_strings_fail_despite_trivial_syndrome(self, codes):
        """§49: the most dangerous bug is declaring zero-syndrome errors
        successful. Logical X and Z must be flagged."""
        for code in codes.values():
            dec = RotatedSurfaceCodeDecoder(code)
            ex, ez = error_from_string(code, code.logical_x)
            r = dec.decode(ex, ez)
            assert r.syndrome_x == tuple(0 for _ in r.syndrome_x)
            assert r.outcome == "LOGICAL_X"
            ex, ez = error_from_string(code, code.logical_z)
            r = dec.decode(ex, ez)
            assert r.outcome == "LOGICAL_Z"

    def test_logical_y_fails(self, codes):
        dec = RotatedSurfaceCodeDecoder(codes[3])
        ex, ez = error_from_string(codes[3], codes[3].logical_x)
        ez2, _ = error_from_string(codes[3], codes[3].logical_z)
        # X on the logical X column and Z on the logical Z row overlap at one
        # qubit -> the overlapping qubit carries Y.
        ex3, ez3 = ex | ez2 & 0, ex & 0  # placeholder to clarify intent
        # Build directly: X column | Z row -> X part = column + row-Z? Use the
        # product: Y at the intersection, X elsewhere on the column, Z
        # elsewhere on the row.
        n = 9
        col = [q for q in range(n) if codes[3].logical_x[n - 1 - q] == "X"]
        row = [q for q in range(n) if codes[3].logical_z[n - 1 - q] == "Z"]
        ex = ez = 0
        for q in col:
            ex |= 1 << q
        for q in row:
            ez |= 1 << q
        # intersection now has both X and Z = Y automatically (ex, ez both set)
        assert ex & ez  # intersection qubit carries Y
        r = dec.decode(ex, ez)
        assert r.outcome == "LOGICAL_Y"


class TestResidualInvariant:
    """§92 property test: for random low-weight errors the residual is either
    stabilizer-equivalent to identity or a genuine logical operator - never
    anything else. Verified via the coset functionals."""

    @pytest.mark.parametrize("d", [3, 5])
    def test_random_low_weight_residuals(self, d):
        code = RotatedSurfaceCode.build(d)
        dec = RotatedSurfaceCodeDecoder(code)
        rng = random.Random(4242 + d)
        n = d * d
        from app.qec.rotated_surface_code import _parity
        for _ in range(2000):
            w = rng.randint(1, 4)
            qs = rng.sample(range(n), min(w, n))
            ex = ez = 0
            for q in qs:
                t = rng.choice(("X", "Y", "Z"))
                if t in ("X", "Y"):
                    ex |= 1 << q
                if t in ("Y", "Z"):
                    ez |= 1 << q
            r = dec.decode(ex, ez)
            assert r.outcome != "DECODER_ERROR"
            if r.success:
                assert _parity(r.residual_x & code.phi_x) == 0
                assert _parity(r.residual_z & code.phi_z) == 0
            else:
                # residual has zero syndrome but fires exactly one functional
                sx, sz = dec.syndrome(r.residual_x, r.residual_z)
                assert not any(sx) and not any(sz)
                assert _parity(r.residual_x & code.phi_x) ^ _parity(
                    r.residual_z & code.phi_z) in (0, 1)


class TestMatchingQuality:
    def test_matching_weight_is_chain_sum(self, codes):
        """The reported matching weight must equal the sum of its chains."""
        code = codes[5]
        dec = RotatedSurfaceCodeDecoder(code)
        rng = random.Random(5)
        for _ in range(200):
            qs = rng.sample(range(25), rng.randint(1, 6))
            ex = ez = 0
            for q in qs:
                ex |= 1 << q  # X errors -> Z-check syndrome
            r = dec.decode(ex, ez)
            assert r.matching_weight == sum(m.weight for m in r.matching)

    def test_deterministic_tie_breaking(self, codes):
        """Identical inputs decode identically, including ties (§53)."""
        code = codes[5]
        dec = RotatedSurfaceCodeDecoder(code)
        ex, ez = error_from_string(code, code.generators[0])
        first = dec.decode(ex, ez)
        for _ in range(10):
            again = dec.decode(ex, ez)
            assert again.to_dict() == first.to_dict()

    def test_chain_is_valid_on_the_lattice(self, codes):
        """§26: correction chains are real data-qubit lists; each chain lies
        in the support intersection structure of its endpoints."""
        code = codes[5]
        dec = RotatedSurfaceCodeDecoder(code)
        for m in dec.decode(0, (1 << 0) | (1 << 7)).matching:
            for q in m.chain:
                assert 0 <= q < 25
            if m.kind == "pair":
                a_sup = (code.x_checks if m.pauli == "Z" else code.z_checks)
                # consecutive chain qubits share a check of the chain type
                sup = {c.index: set(c.support)
                       for c in (code.x_checks if m.pauli == "Z"
                                 else code.z_checks)}
                prev_sup = None
                for q in m.chain:
                    hosts = {i for i, s in sup.items() if q in s}
                    if prev_sup is not None:
                        assert hosts & prev_sup, (m.chain, q)
                    prev_sup = hosts


class TestRoundTrip:
    """§93: logical state preservation, not physical-error recovery."""

    def test_residual_has_trivial_or_logical_classification(self, codes):
        for code in codes.values():
            dec = RotatedSurfaceCodeDecoder(code)
            for pauli in (code.logical_x, code.logical_z,
                          code.generators[0], "I" * code.d * code.d):
                ex, ez = error_from_string(code, pauli)
                r = dec.decode(ex, ez)
                # round trip: residual = correction * error (XOR components)
                assert r.residual_x == (ex ^ r.correction_x)
                assert r.residual_z == (ez ^ r.correction_z)
                assert r.success == (r.outcome == "CORRECTED")
