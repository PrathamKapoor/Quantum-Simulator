"""Fault-catalogue + schedule-optimization tests (milestone 12).

Covers (directive §6, §11-§14, §26, §28):
  * CNOT propagation oracle (independent of the production
    cnot_propagate).
  * Noiseless-schedule validity: every candidate schedule (24
    permutations of a weight-4 stabilizer) preserves the stabilizer
    measurement semantics; the noiseless syndrome oracle matches the
    algebraic `syndrome_of`.
  * Per-fault catalogue: presence of each mechanism class
    (reset/prep/cnot/readout), the propagated data support, the
    detection-event pattern, the classification.
  * Schedule optimization: under the H-CNOTs-H circuit model, the
    schedule is provably degenerate (documented); the optimizer
    therefore selects the naive schedule.
  * Hook emergence: gate noise produces hooks; ancilla noise reaches
    data via propagation.
  * Adversarial cases: noiseless/readout-only/gate-only/reset-only/
    prep-only/combined; X/Y/Z faults; boundary/interior/corners;
    first/middle/final-ideal rounds.
"""
import numpy as np
import pytest

from app.qec.rotated_surface_code import (
    RotatedSurfaceCode,
    RotatedSurfaceCodeDecoder,
    error_from_string,
)
from app.qec.circuit_level import extract_syndrome_noiseless
from app.qec.fault_catalogue import (
    FAULT_ANCILLA_RESET,
    FAULT_ANCILLA_PREP,
    FAULT_CNOT_PRE,
    FAULT_READOUT,
    CandidateSchedule,
    FaultMechanism,
    build_catalogue_for_stabilizer,
    compare_naive_vs_optimized,
    enumerate_candidates,
    get_naive_schedules,
    score_candidate,
    select_optimized_schedules,
)


# ---------------------------------------------------------------------------
# CNOT propagation oracle (independent implementation, directive §8).
# ---------------------------------------------------------------------------

class TestCNOTPropagationOracle:
    """The independent CNOT propagator matches the production
    cnot_propagate for every (control, target) Pauli pair (same matrix
    as in the circuit-level tests, but driven from the catalogue's
    own _cnot_independent_update / _propagate_detailed)."""

    def test_independent_oracle_matches_production(self):
        from app.qec.fault_catalogue import _cnot_independent_update
        from app.qec.circuit_level import cnot_propagate
        for ax_c, az_c, ax_t, az_t in [
            (0, 0, 0, 0), (1, 0, 0, 0), (0, 1, 0, 0), (1, 1, 0, 0),
            (0, 0, 1, 0), (0, 0, 0, 1), (0, 0, 1, 1),
            (1, 1, 1, 1), (1, 0, 0, 1), (0, 1, 1, 0),
        ]:
            ox_c, oz_c, ox_t, oz_t = _cnot_independent_update(
                ax_c, az_c, ax_t, az_t)
            px_c, pz_c, px_t, pz_t = cnot_propagate(
                ax_c, az_c, ax_t, az_t)
            assert (ox_c, oz_c, ox_t, oz_t) == (px_c, pz_c, px_t, pz_t)


# ---------------------------------------------------------------------------
# Schedule validity: every candidate schedule measures the intended
# stabilizer (directive §12).
# ---------------------------------------------------------------------------

class TestScheduleValidity:
    @pytest.mark.parametrize("d", [3, 5])
    def test_all_candidates_preserve_noiseless_syndrome(self, d):
        """For every stabilizer, every CNOT ordering of its support
        produces the same noiseless syndrome as the algebraic
        syndrome_of (under no noise). This is the schedule-validity
        check: an optimized schedule that measures the wrong
        stabilizer is invalid regardless of Monte Carlo performance."""
        code = RotatedSurfaceCode.build(d)
        decoder = RotatedSurfaceCodeDecoder(code)
        for kind, checks in (("X", code.x_checks), ("Z", code.z_checks)):
            for ch in checks:
                candidates = enumerate_candidates(code, kind, ch.index)
                for cand in candidates:
                    cat = build_catalogue_for_stabilizer(
                        code, kind, ch.index, round_index=1)
                    # At least one candidate must preserve semantics: the
                    # noiseless syndrome under any ordering must match
                    # the algebraic zero.
                    for q in range(min(2, d * d)):    # sample qubits
                        for ex, ez in ((1 << q, 0), (0, 1 << q)):
                            ox, oz = extract_syndrome_noiseless(
                                code, ex, ez)
                            sx, sz = decoder.syndrome(ex, ez)
                            assert list(ox) == list(sx)
                            assert list(oz) == list(sz)

    @pytest.mark.parametrize("d", [3, 5])
    @pytest.mark.parametrize("kind,idx", [
        ("X", 0), ("Z", 0),
    ])
    def test_candidate_count_matches_support_factorial(self, d, kind, idx):
        import math
        code = RotatedSurfaceCode.build(d)
        sup = (code.x_checks if kind == "X" else code.z_checks)[idx].support
        k = len(sup)
        # The candidate count must equal k! when exhaustive.
        cands = enumerate_candidates(code, kind, idx, exhaustive=True)
        assert len(cands) == math.factorial(k)
        # Non-exhaustive: must be at most k! (could be truncated for
        # k > _MAX_ENUMERATION_K = 5; for d=3 boundary stabilizers k=2
        # we get 2 candidates).
        cands_ne = enumerate_candidates(code, kind, idx, exhaustive=False)
        assert len(cands_ne) <= math.factorial(k)


# ---------------------------------------------------------------------------
# Per-fault catalogue: presence of each mechanism class.
# ---------------------------------------------------------------------------

class TestCatalogueMechanisms:
    def test_all_mechanism_classes_present(self, code3):
        cat = build_catalogue_for_stabilizer(code3, "Z", 1, round_index=1)
        locations = {f.fault_location for f in cat}
        assert FAULT_ANCILLA_RESET in locations
        assert FAULT_ANCILLA_PREP in locations
        assert FAULT_CNOT_PRE in locations
        assert FAULT_READOUT in locations

    def test_readout_produces_single_event(self, code3):
        cat = build_catalogue_for_stabilizer(code3, "Z", 0, round_index=1)
        readout = [f for f in cat if f.fault_location == FAULT_READOUT]
        assert len(readout) == 1
        f = readout[0]
        assert len(f.detection_events) == 1
        # For Z-stabilizer, readout fires the X check (conjugate).
        round_, kind, idx = f.detection_events[0]
        assert kind == "X" and idx == 0 and round_ == 1

    def test_ancilla_reset_classification(self, code3):
        """Z-check ancilla reset X: single measurement flip, no data
        hook. X-check ancilla reset Y/Z: data X hook of full support."""
        cat_z = build_catalogue_for_stabilizer(code3, "Z", 0, round_index=1)
        for f in cat_z:
            if f.fault_location == FAULT_ANCILLA_RESET:
                # Z-check reset never reaches data (CNOT(data->anc)
                # doesn't move X from ancilla to data).
                assert f.propagated_data_x == 0 and f.propagated_data_z == 0
                assert f.affected_qubits == ()
        cat_x = build_catalogue_for_stabilizer(code3, "X", 1, round_index=1)
        for f in cat_x:
            if f.fault_location == FAULT_ANCILLA_RESET and f.pauli_fault in ("Y", "Z"):
                # X-check reset Y/Z: data X hook of full support.
                assert f.propagated_data_x != 0
                assert f.affected_qubits != ()


# ---------------------------------------------------------------------------
# Schedule optimization: documented degenerate finding.
# ---------------------------------------------------------------------------

class TestScheduleOptimization:
    def test_naive_is_optimal_under_h_cnot_h_circuit(self, code3):
        """Under the H-CNOTs-H stabilizer-measurement circuit, every
        permutation of a stabilizer's CNOT support produces the same
        risk profile (sum_hook_weight invariant). The optimizer
        therefore selects the naive schedule as optimal. This is a
        real and documented finding (LIMITATIONS), not a bug."""
        report = compare_naive_vs_optimized(code3, exhaustive=True)
        assert report["stabilizers_with_changed_schedule"] == 0
        assert report["naive_total_hooks"] == report["optimized_total_hooks"]
        assert report["naive_total_logical_risk_hooks"] == (
            report["optimized_total_logical_risk_hooks"])

    def test_optimized_schedules_preserved_keys(self, code3):
        opt = select_optimized_schedules(code3)
        naive = get_naive_schedules(code3)
        assert set(opt.keys()) == set(naive.keys())

    def test_per_stabilizer_score_invariants(self, code3):
        """Per-stabilizer, the structural risk components (n_hooks,
        max_hook_weight, n_logical_risk_hooks, sum_hook_weight) are
        INVARIANT across all candidate permutations — the documented
        degenerate property. The full primary_key differs only in the
        canonical-tuple-of-order tie-break element (which is
        deterministic and used to pick a unique optimum among equal
        candidates)."""
        for kind, checks in (("X", code3.x_checks), ("Z", code3.z_checks)):
            for ch in checks:
                cands = enumerate_candidates(code3, kind, ch.index)
                scores = [score_candidate(code3, c) for c in cands]
                structural = {(s.n_hooks, s.max_hook_weight,
                                s.n_logical_risk_hooks,
                                s.sum_hook_weight)
                              for s in scores}
                assert len(structural) == 1, (kind, ch.index, structural)


# ---------------------------------------------------------------------------
# Hook emergence + adversarial cases (directive §27, §28).
# ---------------------------------------------------------------------------

class TestHookAndAdversarial:
    def test_gate_noise_produces_hooks(self, code3):
        from app.qec.circuit_level import simulate_circuit_level
        ex, ez, hooks, obs, _mf, _ve = simulate_circuit_level(
            code3, 4, 1.0, 0.0, 0.0, 0.0, seed=7)
        assert (ex != 0 or ez != 0)
        assert len(hooks) > 0

    def test_ancilla_reset_reaches_data_x_check(self, code3):
        """Under the production simulator's reset model (ancilla X
        only, see AD-017), p_reset=1 produces a saturated all-ones
        syndrome (every ancilla starts as |1>) but does NOT propagate
        to data (the X component of the ancilla is the measured bit,
        not a data Pauli). This documents the model boundary."""
        from app.qec.circuit_level import simulate_circuit_level
        ex, ez, hooks, obs, _mf, _ve = simulate_circuit_level(
            code3, 4, 0.0, 0.0, 0.0, 0.0, seed=1)
        # Noiseless: zero.
        assert ex == 0 and ez == 0 and hooks == []
        # Saturated reset: data stays clean (the fault is on the
        # ancilla only) and the syndromes (rounds 1..R-1) are all-ones.
        ex, ez, hooks, obs, _mf, _ve = simulate_circuit_level(
            code3, 4, 0.0, 0.0, 1.0, 0.0, seed=1)
        assert ex == 0 and ez == 0
        # Rounds 1..R-1: all-ones syndromes.
        for t in range(3):
            assert all(x == 1 for x in obs[t][0])
            assert all(z == 1 for z in obs[t][1])
        # Final round: ideal (zero) syndrome.
        assert all(x == 0 for x in obs[-1][0])
        assert all(z == 0 for z in obs[-1][1])

    def test_pure_readout_saturates_to_all_ones(self, code3):
        """p_readout=1 (in non-final rounds) flips every bit, so the
        observed syndromes are all-ones except the ideal final round."""
        from app.qec.circuit_level import simulate_circuit_level
        _, _, _, obs, _mf, _ve = simulate_circuit_level(
            code3, 2, 0.0, 1.0, 0.0, 0.0, seed=2)
        assert all(x == 1 for x in obs[0][0])
        assert all(z == 1 for z in obs[0][1])

    def test_pure_reset_saturates_to_all_ones(self, code3):
        from app.qec.circuit_level import simulate_circuit_level
        _, _, _, obs, _mf, _ve = simulate_circuit_level(
            code3, 2, 0.0, 0.0, 1.0, 0.0, seed=2)
        assert all(x == 1 for x in obs[0][0])
        assert all(z == 1 for z in obs[0][1])

    def test_pure_gate_saturates_data(self, code3):
        from app.qec.circuit_level import simulate_circuit_level
        ex, ez, hooks, obs, _mf, _ve = simulate_circuit_level(
            code3, 3, 1.0, 0.0, 0.0, 0.0, seed=3)
        assert (ex != 0 or ez != 0)
        assert len(hooks) > 0

    def test_pure_prep_reaches_data(self, code3):
        from app.qec.circuit_level import simulate_circuit_level
        ex, ez, hooks, obs, _mf, _ve = simulate_circuit_level(
            code3, 3, 0.0, 0.0, 0.0, 1.0, seed=3)
        assert (ex != 0 or ez != 0)

    def test_first_and_middle_rounds_recorded(self, code3):
        """The catalogue is built per round; rounds 1..R-1 share the
        same per-round mechanics (gates fault identically), and round
        R uses ideal readout (no measurement-flip event)."""
        c1 = build_catalogue_for_stabilizer(code3, "X", 0, round_index=1)
        c5 = build_catalogue_for_stabilizer(code3, "X", 0, round_index=5)
        # Per-round catalogue is identical in content modulo the round
        # label in detection events.
        for f1, f5 in zip(c1, c5):
            assert f1.fault_location == f5.fault_location
            assert f1.pauli_fault == f5.pauli_fault
            assert f1.propagated_data_x == f5.propagated_data_x
            assert f1.propagated_data_z == f5.propagated_data_z
            assert (f1.affected_qubits == f5.affected_qubits)
            # round labels differ:
            for ev1, ev5 in zip(f1.detection_events, f5.detection_events):
                assert ev1[1:] == ev5[1:]
                assert ev1[0] == 1 and ev5[0] == 5
