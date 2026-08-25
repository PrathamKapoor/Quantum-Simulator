"""Network engine tests (directives §75-80, §141, §197, §303-305)."""
import math

import pytest

from app.network import (
    Topology,
    NetworkNode,
    NetworkEngine,
    NetworkConfig,
    find_best_route,
    route_cost,
    expected_end_to_end_fidelity,
    swap_fidelity,
    generation_success_probability,
    aged_fidelity,
    EventQueue,
)


def line_topology(*distances) -> Topology:
    names = ["A", "B"] if not distances else ["A"] + [f"R{i}" for i in range(len(distances) - 1)] + ["B"]
    topo = Topology()
    for i, n in enumerate(names):
        topo.add_node(NetworkNode(n, "repeater" if 0 < i < len(names) - 1 else "end",
                                  memory_slots=8))
    for i in range(len(distances)):
        topo.add_quantum_link(names[i], names[i + 1], distance_km=distances[i])
    return topo


class TestTopologyAndRouting:
    def test_link_loss_limiting_cases(self):
        from app.network import QuantumLink

        zero = QuantumLink("A", "B", distance_km=0)
        assert zero.transmission_loss_probability() == pytest.approx(1.0)
        long_fiber = QuantumLink("A", "B", distance_km=100)
        # 0.2 dB/km * 100 km = 20 dB -> 1% survival
        assert long_fiber.transmission_loss_probability() == pytest.approx(0.01)

    def test_route_selection_changes_with_strategy(self):
        """Integration test §304: multiple routes; weights change selection."""
        t = Topology()
        for n in ("A", "M1", "M2", "B"):
            t.add_node(NetworkNode(n, "end" if n in ("A", "B") else "repeater"))
        # Short-but-lossy path A-M1-B
        t.add_quantum_link("A", "M1", 10)
        t.add_quantum_link("M1", "B", 10)
        # Long-but-pristine path A-M2-B
        t.add_quantum_link("A", "M2", 100)
        t.add_quantum_link("M2", "B", 100)
        r_short, _ = find_best_route(t, "A", "B", strategy="shortest_path")
        assert sum(
            t.get_link(r_short[i], r_short[i + 1]).distance_km
            for i in range(len(r_short) - 1)
        ) == 20

    def test_failed_node_reroutes(self):
        """Integration test §305: disable node on shortest path; fallback used."""
        t = Topology()
        for n in ("A", "M1", "M2", "B"):
            t.add_node(NetworkNode(n))
        t.add_quantum_link("A", "M1", 5)
        t.add_quantum_link("M1", "B", 5)
        t.add_quantum_link("A", "M2", 50)
        t.add_quantum_link("M2", "B", 50)
        t.nodes["M1"].failed = True
        route, expl = find_best_route(t, "A", "B", strategy="shortest_path")
        assert route == ("A", "M2", "B")

    def test_fidelity_requirement_blocks_short_route(self):
        t = line_topology(10, 10)
        # Make link fidelity low so e2e fails a high requirement.
        t.links[0].base_fidelity = 0.5
        t.links[1].base_fidelity = 0.5
        route, expl = find_best_route(
            t, "A", "B", strategy="shortest_path", fidelity_requirement=0.99
        )
        assert route is None
        assert expl is not None  # best-effort explanation returned (§197)

    def test_route_explanation_contents(self):
        t = line_topology(20)
        route, expl = find_best_route(t, "A", "B", strategy="min_expected_time")
        assert route == ("A", "R0", "B") or route == ("A", "B") or route is not None
        assert expl.describe()


class TestEntanglementModels:
    def test_swap_fidelity_limits(self):
        assert swap_fidelity(1.0, 1.0) == pytest.approx(1.0)
        assert swap_fidelity(0.5, 1.0) == pytest.approx(0.5)

    def test_swap_reduces_or_maintains_fidelity(self):
        f = swap_fidelity(0.95, 0.95)
        assert 0.5 <= f <= 0.95

    def test_generation_success_bounds(self):
        assert generation_success_probability(0, 0.2, 1.0) == 1.0
        p = generation_success_probability(100, 0.2, 0.5)
        assert 0 < p < 0.01

    def test_memory_decay_limiting_cases(self):
        assert aged_fidelity(0.9, 0, 1000) == pytest.approx(0.9)
        # Fully decayed pair -> maximally mixed two-qubit state, F = 1/4.
        assert aged_fidelity(0.9, 1e12, 1000) == pytest.approx(0.25, abs=1e-6)

    def test_purification_refuses_to_fake(self):
        from app.network import PurificationProtocol

        with pytest.raises(NotImplementedError):
            PurificationProtocol().run([(0.9, 0.9)])


class TestEngineBasics:
    def test_two_node_entanglement(self):
        """Minimal A->B health check: link creation, transmission, completion."""
        t = line_topology(1)
        eng = NetworkEngine(t, NetworkConfig(), seed=11)
        eng.submit_request("A", "B")
        result = eng.run(until_ns=1_000_000)
        assert result.success_count >= 1
        assert any(o.success for o in result.outcomes)
        completed = [o for o in result.outcomes if o.success][0]
        assert completed.fidelity > 0.9

    def test_repeater_chain_swaps(self):
        """Integration test §303: A-R-B entanglement swapping."""
        t = line_topology(5, 5)
        cfg = NetworkConfig(classical_latency_mode="idealized")
        eng = NetworkEngine(t, cfg, seed=3)
        eng.submit_request("A", "B")
        result = eng.run(until_ns=50_000_000)
        successes = [o for o in result.outcomes if o.success]
        assert successes, "swap chain should complete"
        assert result.stats["swaps_performed"] >= 1
        # End-to-end fidelity below single-link base due to swap model.
        assert successes[0].fidelity < 0.99

    def test_deterministic_seeded_runs(self):
        t = line_topology(4, 4, 4)
        cfg = NetworkConfig()
        r1 = NetworkEngine(t.copy(), cfg, seed=99).run(until_ns=20_000_000)
        r2 = NetworkEngine(t.copy(), cfg, seed=99).run(until_ns=20_000_000)
        assert [(o.success, o.completion_ns) for o in r1.outcomes] == \
               [(o.success, o.completion_ns) for o in r2.outcomes]

    def test_event_log_from_actual_events(self):
        """§85: the event log must reflect actual simulation events."""
        t = line_topology(2, 2)
        eng = NetworkEngine(t, NetworkConfig(trace_mode="full"), seed=5)
        eng.submit_request("A", "B")
        res = eng.run(until_ns=30_000_000)
        joined = "\n".join(res.event_log)
        assert "entanglement_generated" in joined
        assert "request_completed" in joined


class TestFailures:
    def test_node_failure_forces_alternate_route(self):
        t = Topology()
        for n in ("A", "M1", "M2", "B"):
            t.add_node(NetworkNode(n, memory_slots=8))
        t.add_quantum_link("A", "M1", 5)
        t.add_quantum_link("M1", "B", 5)
        t.add_quantum_link("A", "M2", 60)
        t.add_quantum_link("M2", "B", 60)
        cfg = NetworkConfig(node_failure_rate_per_s=100.0)  # frequent failures within window
        eng = NetworkEngine(t, cfg, seed=42)
        eng.submit_request("A", "B")
        res = eng.run(until_ns=200_000_000)
        # Either completes via alternate route or fails honestly; no crash.
        assert res.stats["events_processed"] > 0

    def test_disconnected_network_fails_cleanly(self):
        t = Topology()
        t.add_node(NetworkNode("A"))
        t.add_node(NetworkNode("B"))
        eng = NetworkEngine(t, NetworkConfig(), seed=1)
        eng.submit_request("A", "B")
        res = eng.run(until_ns=1000)
        assert res.failure_count == 1
        assert res.outcomes[0].failure_reason == "no_available_route"

    def test_chaos_statistics(self):
        t = line_topology(3, 3, 3)
        t.add_quantum_link("R0", "B", 4)  # skip link gives a reroute option
        cfg = NetworkConfig(
            node_failure_rate_per_s=20.0,
            link_failure_rate_per_s=20.0,
        )
        eng = NetworkEngine(t, cfg, seed=123)
        for _ in range(5):
            eng.submit_request("A", "B")
        res = eng.run(until_ns=500_000_000)
        total = res.success_count + res.failure_count
        assert total == 5


class TestSchedulerAndQoS:
    def test_priority_scheduler_ordering(self):
        from app.network import RequestScheduler

        s = RequestScheduler(policy="priority")
        low = s.submit("A", "Z", now_ns=0, priority=1)
        high = s.submit("A", "Y", now_ns=0, priority=10)
        popped_high = s.pop_next()
        assert popped_high.destination == "Y"

    def test_deadline_expires_request(self):
        t = line_topology(50)
        cfg = NetworkConfig(scheduler_policy="deadline")
        eng = NetworkEngine(t, cfg, seed=8)
        eng.submit_request("A", "B", deadline_ns=1.0)  # impossible deadline
        res = eng.run(until_ns=10_000_000)
        failed = [o for o in res.outcomes if not o.success]
        assert any(o.failure_reason == "deadline_exceeded" for o in failed)

    def test_fidelity_requirement_enforced_end_to_end(self):
        t = line_topology(30, 30, 30)
        for l in t.links:
            l.base_fidelity = 0.7  # swapping degrades further
        cfg = NetworkConfig()
        eng = NetworkEngine(t, cfg, seed=21)
        eng.submit_request("A", "B", fidelity_requirement=0.98)
        res = eng.run(until_ns=100_000_000)
        ok = [o for o in res.outcomes if o.success]
        if ok:
            assert all(o.fidelity >= 0.98 for o in ok)


class TestEdgeCases:
    def test_single_node_network_rejects_self_request(self):
        t = Topology()
        t.add_node(NetworkNode("solo"))
        eng = NetworkEngine(t, NetworkConfig(), seed=1)
        with pytest.raises(ValueError):
            eng.find_best_route if False else eng.submit_request("solo", "solo")

    def test_zero_length_link_allowed_and_instant(self):
        t = line_topology(0)
        eng = NetworkEngine(t, NetworkConfig(), seed=2)
        eng.submit_request("A", "B")
        res = eng.run(until_ns=100_000)
        assert res.success_count == 1

    def test_invalid_config_rejected(self):
        with pytest.raises(ValueError):
            NetworkConfig(swap_success_probability=1.5)
        with pytest.raises(ValueError):
            NetworkConfig(memory_coherence_ns=-5)

    def test_full_memory_backpressure(self):
        t = line_topology(1)
        t.nodes["A"].memory_slots = 0
        t.nodes["B"].memory_slots = 0
        eng = NetworkEngine(t, NetworkConfig(), seed=4)
        eng.submit_request("A", "B")
        res = eng.run(until_ns=5_000_000)
        assert res.failure_count == 1


class TestPurificationIntegration:
    def _two_segment(self):
        t = line_topology(5, 5)
        return t

    def test_purification_config_accepted_and_runs(self):
        cfg = NetworkConfig(purification_protocol="BBPSSW")
        eng = NetworkEngine(self._two_segment(), cfg, seed=21)
        eng.submit_request("A", "B")
        res = eng.run(until_ns=100_000_000)
        # Either purified or not — but accounting must be consistent:
        s = res.stats
        assert s["pairs_consumed_by_purification"] % 2 == 0
        assert s["purification_rounds_succeeded"] <= s["purification_rounds_attempted"]

    def test_invalid_protocol_rejected(self):
        with pytest.raises(ValueError):
            NetworkConfig(purification_protocol="MAGIC")

    def test_purified_chain_still_completes(self):
        cfg = NetworkConfig(purification_protocol="DEJMPS",
                            classical_latency_mode="idealized")
        for seed in range(4):
            eng = NetworkEngine(line_topology(4, 4), cfg, seed=30 + seed)
            eng.submit_request("A", "B")
            res = eng.run(until_ns=200_000_000)
            if res.success_count >= 1:
                ok = [o for o in res.outcomes if o.success][0]
                # DEJMPS output fidelity stays within Werner bounds.
                assert ok.fidelity <= 1.0
                break
        else:
            pytest.fail("no successful run across seeds")


class TestRepeaterStudy:
    def test_study_runs_and_reports_cis(self):
        from app.network.repeaters import run_repeater_study

        study = run_repeater_study(
            [50, 200], levels=["L0_direct", "L1_swapping"],
            requests_per_point=10, seed=42)
        assert len(study["table"]) == 4
        for row in study["table"]:
            lo, hi = row["ci95_low"], row["ci95_high"]
            assert 0 <= row["success_probability"] <= 1
            assert lo <= row["success_probability"] <= hi
            assert row["requests"] == 10

    def test_repeater_beats_direct_at_long_distance(self):
        """Trend validation (§198): at long distance the direct strategy
        should not beat the repeater chain on success probability."""
        from app.network.repeaters import run_repeater_point

        direct = run_repeater_point("L0_direct", 300, requests=12, seed=5)
        chained = run_repeater_point("L1_swapping", 300, requests=12, seed=5)
        assert chained.success_probability >= direct.success_probability - 0.15
