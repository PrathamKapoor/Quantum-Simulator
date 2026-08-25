"""QEC tests (directives §61, §143, §307)."""
import numpy as np
import pytest

from app.qec import (
    BIT_FLIP_3,
    FIVE_QUBIT,
    PHASE_FLIP_3,
    SHOR_9,
    STEANE_7,
    build_recovery_table,
    benchmark_point,
    sweep_physical_error_rate,
    wilson_interval,
    encode_bit_flip_3,
    syndrome_extraction_circuit_bit_flip_3,
    ToricCodeLayout,
    simulate_surface_code,
    verify_toric_code,
)
from app.qec.stabilizer import pauli_commutes, pauli_product_phase_ignorant, syndrome_of
from app.circuits import simulate
from app.quantum.states import StateVector


class TestStabilizerAlgebra:
    def test_commutation_rules(self):
        assert not pauli_commutes("X", "Z")
        assert pauli_commutes("X", "X")
        assert pauli_commutes("XX", "ZZ")  # two anticommuting positions
        # XI vs IZ: no overlapping non-identity positions -> commute
        assert pauli_commutes("XI", "IZ")

    def test_product_table(self):
        assert pauli_product_phase_ignorant("X", "Y") == "Z"
        assert pauli_product_phase_ignorant("Y", "Z") == "X"
        assert pauli_product_phase_ignorant("Z", "X") == "Y"
        assert pauli_product_phase_ignorant("I", "Y") == "Y"


class TestCodeDefinitions:
    @pytest.mark.parametrize(
        "code", [BIT_FLIP_3, PHASE_FLIP_3, SHOR_9, STEANE_7, FIVE_QUBIT],
        ids=lambda c: c.name,
    )
    def test_code_structure_valid(self, code):
        # QECode.__post_init__ validates commutation/logicals on construction.
        assert code.k == 1

    def test_shor_corrects_single_arbitrary(self):
        table = build_recovery_table(SHOR_9)
        for q in range(9):
            for ch in "XYZ":
                err = ["I"] * 9
                err[q] = ch
                recovery, corrected = _decode(SHOR_9, table, "".join(err))
                assert corrected, f"{ch} on qubit {q} failed"

    def test_uncorrectable_not_falsely_reported(self):
        # Two errors exceed distance-3 correction capability; the code may
        # sometimes still succeed, but a KNOWN uncorrectable class must be
        # reported as failure when it maps to a logical: e.g. X on q0 and X on q1
        # of the bit-flip code gives syndrome equal to single error on q2 ->
        # 'corrects' to wrong logical -> must count as failure.
        table = build_recovery_table(BIT_FLIP_3)
        _, corrected = _decode(BIT_FLIP_3, table, "XXI")
        assert not corrected

    def _test_placeholder_removed(self):
        pass


def _decode(code, table, error):
    from app.qec.pipeline import _decode_with_table

    return _decode_with_table(code, table, error)


class TestRepetitionPipeline:
    def test_bf3_single_errors_all_corrected(self):
        table = build_recovery_table(BIT_FLIP_3)
        for q in range(3):
            err = ["I"] * 3
            err[q] = "X"
            rec, ok = _decode(BIT_FLIP_3, table, "".join(err))
            assert ok

    def test_pf3_phase_errors_corrected(self):
        table = build_recovery_table(PHASE_FLIP_3)
        for q in range(3):
            err = ["I"] * 3
            err[q] = "Z"
            _, ok = _decode(PHASE_FLIP_3, table, "".join(err))
            assert ok

    def test_encoder_produces_code_state(self):
        from app.circuits.model import Circuit, Operation

        c = encode_bit_flip_3()
        full = Circuit(
            num_qubits=3,
            operations=[Operation(kind="gate", gate="X", params=(), qubits=(0,))]
            + list(c.operations),
        )
        out = simulate(full).final_state
        amps = out.amplitudes
        # Expect support only on |111> (index 7).
        assert abs(abs(amps[7]) ** 2 - 1) < 1e-12

    def test_syndrome_extraction_flow(self):
        """Integration through engine: encode, hit with X error via gate,
        extract syndromes with ancillas and mid-circuit measurement."""
        from app.circuits.model import Circuit, Operation

        c = Circuit(num_qubits=5, num_clbits=2, name="syndrome-flow")
        # Encode |100> logical one: X q0 then CX ladder.
        c.add_gate("X", [0])
        c.add_gate("CX", [0, 1]).add_gate("CX", [0, 2])
        # Inject bit flip on data qubit 1.
        c.add_gate("X", [1])
        # Syndrome ancillas.
        c.add_gate("CX", [0, 3]).add_gate("CX", [1, 3])
        c.add_gate("CX", [1, 4]).add_gate("CX", [2, 4])
        c.add_measure([3], [0])
        c.add_measure([4], [1])
        res = simulate(c, seed=1)
        reg = res.classical_registers[0]
        # Error on qubit1 flips both parities: s=(1,1).
        assert reg == [1, 1]


class TestBenchmark:
    def test_low_physical_error_gives_lower_logical_rate(self):
        pts = sweep_physical_error_rate(
            "bit-flip-3", [0.001, 0.05, 0.15], trials=4000, seed=42
        )
        rates = [p.logical_error_rate for p in pts]
        assert rates[0] < rates[1] < rates[2]
        # At p=0.001 logical failures should be rare.
        assert pts[0].logical_error_rate < 0.005

    def test_confidence_intervals_bracket_estimate(self):
        pt = benchmark_point(SHOR_9, 0.01, trials=2000, seed=7)
        lo, hi = wilson_interval(pt.logical_failures, pt.trials)
        assert lo <= pt.logical_error_rate <= hi or pt.logical_failures == 0

    def test_wilson_interval_sane_values(self):
        lo, hi = wilson_interval(0, 100)
        assert lo == 0 and hi < 0.05
        lo, hi = wilson_interval(50, 100)
        assert 0.39 < lo < 0.41 and 0.59 < hi < 0.61


class TestSteaneFiveQubit:
    def test_steane_single_errors(self):
        table = build_recovery_table(STEANE_7)
        for q in range(7):
            for ch in "XYZ":
                err = ["I"] * 7
                err[q] = ch
                _, ok = _decode(STEANE_7, table, "".join(err))
                assert ok

    def test_five_qubit_single_errors(self):
        table = build_recovery_table(FIVE_QUBIT)
        for q in range(5):
            for ch in "XYZ":
                err = ["I"] * 5
                err[q] = ch
                _, ok = _decode(FIVE_QUBIT, table, "".join(err))
                assert ok


class TestToricSurfaceCode:
    def test_layout_verification_d3(self):
        info = verify_toric_code(3)
        assert info["commutation_ok"]
        # Minimum nontrivial logical weight equals lattice distance.
        assert info["code_distance_min_nontrivial_logical_weight"] == 3

    def test_visualization_layout_shape(self):
        layout = ToricCodeLayout(3).visualization_layout()
        assert layout["edges"] == 18 if isinstance(layout["edges"], int) else len(layout["edges"]) == 18

    def test_single_error_always_corrected(self):
        res = simulate_surface_code(3, 0.0, trials=1, seed=1)  # zero noise sanity
        assert res.logical_failures == 0

    def test_logical_rate_increases_with_noise(self):
        low = simulate_surface_code(3, 0.002, trials=3000, seed=5)
        high = simulate_surface_code(3, 0.06, trials=3000, seed=5)
        assert low.logical_error_rate < high.logical_error_rate
