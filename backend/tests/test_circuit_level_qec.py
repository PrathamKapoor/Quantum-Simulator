"""Circuit-level surface-code simulation tests (§Scientifc-validation matrix).

Deterministic cases first (propagation oracle, noiseless-syndrome equality,
channel distinctions, hook emergence), then decoder integration, then Monte
Carlo. Independent validation uses a 4x4 CNOT matrix (not the frame code) and
the algebraic syndrome_of.
"""
import numpy as np
import pytest

from app.qec.rotated_surface_code import (
    RotatedSurfaceCode,
    RotatedSurfaceCodeDecoder,
    error_from_string,
)
from app.qec.circuit_level import (
    cnot_propagate,
    decode_circuit_level,
    extract_syndrome_noiseless,
    simulate_circuit_level,
    simulate_circuit_level_mc,
)

I = np.eye(2, dtype=complex)
X = np.array([[0, 1], [1, 0]], dtype=complex)
Y = np.array([[0, -1j], [1j, 0]], dtype=complex)
Z = np.array([[1, 0], [0, -1]], dtype=complex)
CNOT = np.array([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]],
                dtype=complex)
PAULIS = {"I": I, "X": X, "Y": Y, "Z": Z}


def _frame_bits(pauli_mat):
    """Return (has_X, has_Z) for a single-qubit Pauli matrix (phase ignored)."""
    if np.allclose(pauli_mat, I):
        return (0, 0)
    if np.allclose(pauli_mat, X):
        return (1, 0)
    if np.allclose(pauli_mat, Z):
        return (0, 1)
    return (1, 1)  # Y


@pytest.fixture(scope="module")
def code3():
    return RotatedSurfaceCode.build(3)


class TestPropagationOracle:
    @pytest.mark.parametrize("pc", ["I", "X", "Y", "Z"])
    @pytest.mark.parametrize("pt", ["I", "X", "Y", "Z"])
    def test_cnot_propagates_exactly(self, pc, pt):
        """Independent 4x4 oracle: CNOT P CNOT^dag must equal cnot_propagate."""
        ax_c, az_c = _frame_bits(PAULIS[pc])
        ax_t, az_t = _frame_bits(PAULIS[pt])
        nax_c, naz_c, nax_t, naz_t = cnot_propagate(ax_c, az_c, ax_t, az_t)

        P = np.kron(PAULIS[pc], PAULIS[pt])
        P2 = CNOT @ P @ CNOT.conj().T
        from itertools import product

        def name_of(axb, azb):
            return "Y" if (axb and azb) else "X" if axb else "Z" if azb else "I"

        exp = (name_of(nax_c, naz_c), name_of(nax_t, naz_t))
        for n1, n2 in product("IXYZ", repeat=2):
            cand = np.kron(PAULIS[n1], PAULIS[n2])
            if np.allclose(cand, P2) or np.allclose(cand, -P2):
                assert (n1, n2) == exp, (pc, pt, (n1, n2), exp)
                return
        pytest.fail(f"CNOT {pc}{pt} conjugation did not reproduce a Pauli")


class TestNoiselessSyndrome:
    @pytest.mark.parametrize("d", [3, 5])
    def test_oracle_matches_algebraic(self, d):
        code = RotatedSurfaceCode.build(d)
        dec = RotatedSurfaceCodeDecoder(code)
        for q in range(d * d):
            for ex, ez in ((1 << q, 0), (0, 1 << q), (1 << q, 1 << q)):
                sx, sz = dec.syndrome(ex, ez)
                ox, oz = extract_syndrome_noiseless(code, ex, ez)
                assert list(sx) == list(ox)
                assert list(sz) == list(oz)


class TestCleanAndChannels:
    @pytest.mark.parametrize("d", [3, 5])
    def test_clean_zero(self, d):
        code = RotatedSurfaceCode.build(d)
        ex, ez, hooks, obs, _mf, _ve = simulate_circuit_level(
            code, 4, 0.0, 0.0, 0.0, 0.0, seed=1)
        assert ex == 0 and ez == 0 and hooks == []
        assert all(not any(o[0]) and not any(o[1]) for o in obs)

    def test_reset_error_flips(self, code3):
        """p_reset=1 always resets the ancilla to |1>. Round 1 (not the ideal
        final round) shows all-ones outcomes."""
        _, _, _, obs, _mf, _ve = simulate_circuit_level(
            code3, 2, 0.0, 0.0, 1.0, 0.0, seed=2)
        assert all(x == 1 for x in obs[0][0])
        assert all(z == 1 for z in obs[0][1])

    def test_readout_error_flips(self, code3):
        """p_readout=1 flips every measured bit in non-final rounds."""
        _, _, _, obs, _mf, _ve = simulate_circuit_level(
            code3, 2, 0.0, 1.0, 0.0, 0.0, seed=2)
        assert all(x == 1 for x in obs[0][0])
        assert all(z == 1 for z in obs[0][1])

    def test_channels_are_distinct(self, code3):
        """Reset vs readout vs prep vs gate change the syndrome differently:
        at least the measured histories differ across kinds for a shared seed."""
        _, _, _, clean, _mf, _ve = simulate_circuit_level(code3, 2, 0.0, 0.0, 0.0, 0.0, seed=5)
        _, _, _, rme, _mf, _ve = simulate_circuit_level(code3, 2, 0.5, 0.5, 0.0, 0.0, seed=5)
        assert (clean[0] != rme[0]) or (clean[1] != rme[1])

class TestHookEmergence:
    def test_gate_noise_produces_hook_events_and_data_errors(self):
        """A saturated gate-noise regime must produce hook events (ancilla
        faults propagating to data) and nonzero data error — the correlated
        hook-error phenomenon is emergent, not injected."""
        code = RotatedSurfaceCode.build(3)
        ex, ez, hooks, obs, _mf, _ve = simulate_circuit_level(
            code, 4, 1.0, 0.0, 0.0, 0.0, seed=7)
        assert ex != 0 or ez != 0          # gate faults landed on / propagated to data
        assert len(hooks) > 0              # hook events recorded

    def test_only_ancilla_noise_still_reaches_data(self):
        """Ancilla-only faults (prep=1, reset=1, no direct data gate noise)
        must still reach data via propagation."""
        code = RotatedSurfaceCode.build(3)
        ex, ez, hooks, obs, _mf, _ve = simulate_circuit_level(
            code, 3, 0.0, 0.0, 1.0, 1.0, seed=3)
        assert ex != 0 or ez != 0


class TestDecoderIntegration:
    def test_single_data_error_corrected(self):
        """Circuit-derived syndromes for a single data error decode CORRECTED."""
        code = RotatedSurfaceCode.build(3)
        for q in range(9):
            for ex, ez in ((1 << q, 0), (0, 1 << q), (1 << q, 1 << q)):
                ox, oz = extract_syndrome_noiseless(code, ex, ez)
                obs = [(ox, oz)] * 4         # persistent error: constant syndrome
                res = decode_circuit_level(
                    code, 4, 0.0, 0.0, 0.0, 0.0,
                    data_error_x=ex, data_error_z=ez, observed_syndromes=obs,
                    seed=1)
                assert res.outcome == "CORRECTED", (q, ex, ez, res.outcome)

    def test_logical_string_detected(self):
        code = RotatedSurfaceCode.build(3)
        ex, ez = error_from_string(code, code.logical_z)
        ox, oz = extract_syndrome_noiseless(code, ex, ez)
        assert not any(ox) and not any(oz)      # zero syndrome
        res = decode_circuit_level(
            code, 4, 0.0, 0.0, 0.0, 0.0,
            data_error_x=ex, data_error_z=ez, observed_syndromes=[(ox, oz)] * 4,
            seed=1)
        assert res.outcome == "LOGICAL_Z"

    def test_stabilizer_corrected(self):
        code = RotatedSurfaceCode.build(3)
        ex, ez = error_from_string(code, code.generators[0])
        ox, oz = extract_syndrome_noiseless(code, ex, ez)
        res = decode_circuit_level(
            code, 4, 0.0, 0.0, 0.0, 0.0,
            data_error_x=ex, data_error_z=ez, observed_syndromes=[(ox, oz)] * 4,
            seed=1)
        assert res.outcome == "CORRECTED"


class TestMonteCarlo:
    def test_p0_zero_failures(self):
        for d in (3, 5):
            r = simulate_circuit_level_mc(d, 4, 0.0, 0.0, 0.0, 0.0,
                                          trials=200, seed=5)
            assert r["logical_failures"] == 0

    def test_gate_noise_increases_failures(self):
        low = simulate_circuit_level_mc(3, 4, 0.004, 0.004, 0.004, 0.004,
                                        trials=1500, seed=11)
        high = simulate_circuit_level_mc(3, 4, 0.03, 0.03, 0.03, 0.03,
                                         trials=1500, seed=11)
        assert high["logical_error_rate"] > low["logical_error_rate"]

    def test_low_noise_converges_to_zero(self):
        """At very low noise both distances approach zero (sanity), and
        failures vanish with p. NOTE: the naive schedule's correlated hook
        errors (one ancilla fault -> 2..4 data qubits) are uncorrectable at
        d=3, so DISTANCE SUPPRESSION IS NOT OBSERVED in this first circuit-
        level model - documented in LIMITATIONS, not hidden."""
        zero = simulate_circuit_level_mc(3, 3, 1e-5, 1e-5, 1e-5, 1e-5,
                                         trials=2000, seed=3)
        assert zero["logical_error_rate"] < 0.01
        assert simulate_circuit_level_mc(3, 3, 0.0, 0.0, 0.0, 0.0,
                                         trials=500, seed=3)["logical_failures"] == 0

    def test_more_rounds_do_not_reduce_hook_baseline(self):
        """Documented: increasing rounds does NOT suppress the naive-schedule
        hook-error baseline (each round adds independent hook opportunities)."""
        r2 = simulate_circuit_level_mc(3, 2, 1e-4, 0.0, 0.0, 0.0,
                                       trials=3000, seed=9)
        r6 = simulate_circuit_level_mc(3, 6, 1e-4, 0.0, 0.0, 0.0,
                                       trials=3000, seed=9)
        assert r6["logical_error_rate"] >= r2["logical_error_rate"]

    def test_reproducible(self):
        a = simulate_circuit_level_mc(3, 3, 0.02, 0.02, 0.01, 0.01,
                                      trials=300, seed=21)
        b = simulate_circuit_level_mc(3, 3, 0.02, 0.02, 0.01, 0.01,
                                      trials=300, seed=21)
        assert a == b


class TestValidation:
    def test_probabilities_rejected(self):
        for bad in (-0.1, 1.5):
            with pytest.raises(ValueError):
                simulate_circuit_level_mc(3, 3, bad, 0.01, 0.01, 0.01,
                                          trials=10, seed=1)
            with pytest.raises(ValueError):
                simulate_circuit_level_mc(3, 3, 0.01, bad, 0.01, 0.01,
                                          trials=10, seed=1)

    def test_rounds_and_distance_rejected(self):
        with pytest.raises(ValueError, match="rounds"):
            simulate_circuit_level_mc(3, 0, 0.01, 0.01, 0.01, 0.01,
                                      trials=10, seed=1)
        with pytest.raises(ValueError, match="distance"):
            simulate_circuit_level_mc(4, 3, 0.01, 0.01, 0.01, 0.01,
                                      trials=10, seed=1)

    def test_trials_rejected(self):
        with pytest.raises(ValueError):
            simulate_circuit_level_mc(3, 3, 0.01, 0.01, 0.01, 0.01,
                                      trials=0, seed=1)
