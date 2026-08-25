"""Quantum network discrete-event simulation engine (flagship module).

Separation of concerns (directive §193):
  - THIS engine executes events and mutates state ("what happens physically")
  - requests express intent; the scheduler orders them
  - routing selects paths and explains why (§197)
  - entanglement models define attempt/swap statistics (documented formulas)

Chain-completion model:
Each request tracks which ROUTE SEGMENTS its established pairs cover. A fresh
link pair covers one segment; an idealized swap merges two adjacent coverages.
The request completes when one pair covers the whole source->destination span.
Pairs are shared resources: on request failure, intact short pairs remain in
memory where later requests may reuse them (documented behavior).

All stochastic output flows from one seeded RNG (deterministic reruns, §327).
Trace modes keep long simulations memory-bounded (§205).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .events import EventQueue, SimulationClock, EventTrace
from .resources import ResourceManager, EntangledPairHalf
from .scheduler import RequestScheduler, EntangleRequest, FairnessReport
from .topology import Topology, find_best_route
from .entanglement import (
    generation_success_probability,
    attempt_duration_ns,
    swap_fidelity,
    swap_classical_latency_ns,
)


@dataclass
class NetworkConfig:
    """Simulation configuration — every limit explicit (directive §114)."""

    routing_strategy: str = "min_expected_time"
    routing_weights: dict = field(default_factory=dict)
    scheduler_policy: str = "fifo"
    memory_coherence_ns: float = 1_000_000.0   # 1 ms default coherence
    swap_success_probability: float = 1.0      # ideal BSM by default
    classical_latency_mode: str = "realistic"  # or "idealized" (zero latency)
    node_failure_rate_per_s: float = 0.0       # chaos testing knobs (§80)
    link_failure_rate_per_s: float = 0.0
    mean_recovery_time_ns: float = 50_000_000.0
    trace_mode: str = "summary"
    max_events: int = 200_000
    max_sim_time_ns: float = 10_000_000_000.0  # logical-time ceiling (10 s)
    max_retries_per_request: int = 128
    max_chaos_events: int = 10_000             # safety bound on injected failures
    purification_protocol: str | None = None   # "BBPSSW" | "DEJMPS" | None

    def __post_init__(self):
        if not (0 <= self.swap_success_probability <= 1):
            raise ValueError("swap_success_probability must be within [0,1].")
        if self.classical_latency_mode not in ("realistic", "idealized"):
            raise ValueError("classical_latency_mode must be realistic|idealized.")
        if self.memory_coherence_ns <= 0:
            raise ValueError("memory_coherence_ns must be > 0.")
        if self.trace_mode not in ("full", "summary", "sampled"):
            raise ValueError("trace_mode must be full|summary|sampled.")
        if self.max_events < 1 or self.max_sim_time_ns <= 0:
            raise ValueError("Simulation limits must be positive.")
        if self.max_retries_per_request < 1:
            raise ValueError("max_retries_per_request must be >= 1.")
        if self.purification_protocol is not None and \
                self.purification_protocol not in ("BBPSSW", "DEJMPS"):
            raise ValueError(
                "purification_protocol must be 'BBPSSW', 'DEJMPS', or None."
            )


@dataclass
class RequestOutcome:
    request_id: int
    source: str
    destination: str
    protocol: str
    success: bool
    completion_ns: float | None
    waiting_ns: float
    service_ns: float | None
    fidelity: float | None
    route: tuple[str, ...] | None
    attempts_used: int
    failure_reason: str | None = None


@dataclass
class NetworkStats:
    events_processed: int = 0
    link_attempts: int = 0
    links_generated: int = 0
    swaps_performed: int = 0
    swaps_failed: int = 0
    memory_expirations: int = 0
    teleportations_completed: int = 0
    purification_rounds_attempted: int = 0
    purification_rounds_succeeded: int = 0
    pairs_consumed_by_purification: int = 0

    def to_dict(self) -> dict:
        return {
            "events_processed": self.events_processed,
            "link_attempts": self.link_attempts,
            "links_generated": self.links_generated,
            "swaps_performed": self.swaps_performed,
            "swaps_failed": self.swaps_failed,
            "memory_expirations": self.memory_expirations,
            "teleportations_completed": self.teleportations_completed,
            "purification_rounds_attempted": self.purification_rounds_attempted,
            "purification_rounds_succeeded": self.purification_rounds_succeeded,
            "pairs_consumed_by_purification": self.pairs_consumed_by_purification,
        }


@dataclass
class NetworkResult:
    sim_time_ns: float
    outcomes: list[RequestOutcome]
    stats: dict
    fairness: dict
    utilization: dict
    event_log: list[str]
    truncated: bool
    avg_service_ns: float | None = None
    avg_fidelity: float | None = None
    success_count: int = 0
    failure_count: int = 0
    engine_errors: list[str] = field(default_factory=list)


class _ActiveRequest:
    def __init__(self, request: EntangleRequest, started_ns: float):
        self.request = request
        self.started_ns = started_ns
        self.route: tuple[str, ...] | None = None
        self.expected_fidelity: float | None = None
        self.retry_count = 0
        self.attempts = 0
        # pair_id -> (seg_start_idx, seg_end_idx) inclusive span over the route
        self.coverage: dict[int, tuple[int, int]] = {}
        # segments with an in-flight attempt chain (prevents duplicate chains)
        self.pending_segments: set[int] = set()


class NetworkEngine:
    """Discrete-event quantum network simulator."""

    def __init__(self, topology: Topology, config: NetworkConfig | None = None, seed: int = 7):
        issues = topology.validate()
        if issues:
            raise ValueError("Topology invalid: " + "; ".join(issues))
        self.topology = topology
        self.config = config or NetworkConfig()
        self._rng_seed = seed
        self.clock = SimulationClock()
        self.queue = EventQueue()
        self.trace = EventTrace(mode=self.config.trace_mode, max_events=self.config.max_events)
        self.scheduler = RequestScheduler(self.config.scheduler_policy)
        self.resources = ResourceManager(topology)
        for mem in self.resources.memories.values():
            mem.coherence_ns = self.config.memory_coherence_ns
        self.stats = NetworkStats()
        self.outcomes: list[RequestOutcome] = []
        self.engine_errors: list[str] = []
        self._active: dict[int, _ActiveRequest] = {}
        self._route_cache: dict[tuple, tuple] = {}

    @property
    def rng(self):
        rng = getattr(self, "_rng", None)
        if rng is None:
            import numpy as np

            rng = np.random.default_rng(self._rng_seed)
            self._rng = rng
        return rng

    # ---------------- public API ----------------

    def submit_request(
        self,
        source: str,
        destination: str,
        *,
        protocol: str = "entanglement",
        fidelity_requirement: float | None = None,
        deadline_ns: float | None = None,
        priority: int = 0,
    ) -> EntangleRequest:
        """Queue a request BEFORE calling run(); requests are submitted at t=0."""
        if source not in self.topology.nodes or destination not in self.topology.nodes:
            raise ValueError(f"Unknown endpoint {source!r}/{destination!r}.")
        if source == destination:
            raise ValueError("Request source and destination must differ.")
        return self.scheduler.submit(
            source,
            destination,
            now_ns=self.clock.now_ns,
            protocol=protocol,
            priority=priority,
            deadline_ns=deadline_ns,
            fidelity_requirement=fidelity_requirement,
        )

    def run(self, *, until_ns: float | None = None, max_events: int | None = None) -> NetworkResult:
        horizon = min(until_ns if until_ns is not None else math.inf,
                      self.config.max_sim_time_ns)
        limit = max_events or self.config.max_events
        self._schedule_chaos(horizon)
        processed = 0
        while processed < limit:
            # Launch pending requests whenever the engine is idle enough.
            while self.scheduler.has_pending():
                req = self.scheduler.pop_next()
                self._start_request(req)
                if req.protocol == "entanglement" or True:
                    break  # launch one per loop pass; events interleave below
            self._fail_expired_requests()
            ev = self.queue.pop()
            if ev is None or ev.time_ns > horizon:
                break
            try:
                self.clock.advance_to(ev.time_ns)
                self._handle_event(ev)
            except Exception as exc:
                # Engine-level guard: a bad event must not corrupt the whole
                # run, but failures are NEVER silent (§289) — they are recorded
                # and surfaced in the result.
                self.engine_errors.append(
                    f"t={ev.time_ns:.0f}ns {ev.type}: {type(exc).__name__}: {exc}"
                )
                processed += 1
                continue
            self.trace.record(ev)  # single recording point (directive §85, §205)
            self.stats.events_processed += 1
            processed += 1
        return self._collect(truncated=processed >= limit)

    # ---------------- request lifecycle ----------------

    def _start_request(self, req: EntangleRequest) -> None:
        active = _ActiveRequest(request=req, started_ns=self.clock.now_ns)
        self._active[req.request_id] = active
        self._attempt_route(req)

    def _route_cache_key(self, req: EntangleRequest):
        failed_nodes = tuple(sorted(n for n, nd in self.topology.nodes.items() if nd.failed))
        down_links = tuple(sorted((l.source, l.destination) for l in self.topology.links if not l.available))
        weights = tuple(sorted((k, round(float(v), 6)) for k, v in (self.config.routing_weights or {}).items()))
        return (req.source, req.destination, self.config.routing_strategy, weights,
                failed_nodes, down_links)

    def _attempt_route(self, req: EntangleRequest) -> None:
        active = self._active[req.request_id]
        key = self._route_cache_key(req)
        cached = self._route_cache.get(key)
        if cached is None:
            cached = find_best_route(
                self.topology, req.source, req.destination,
                strategy=self.config.routing_strategy,
                weights=self.config.routing_weights,
                fidelity_requirement=req.fidelity_requirement,
            )
            self._route_cache[key] = cached
        route, explanation = cached
        if route is None:
            reason = "no_available_route"
            if explanation is not None and req.fidelity_requirement is not None \
                    and explanation.expected_fidelity < req.fidelity_requirement:
                reason = "fidelity_requirement_unreachable"
            self._fail_request(req.request_id, reason)
            return
        active.route = route
        active.expected_fidelity = explanation.expected_fidelity
        ev = self.queue.push(
            self.clock.now_ns, "route_selected", source=req.source,
            destination=req.destination, request_id=req.request_id,
            route="->".join(route),
        )
        self._schedule_segment_attempts(req.request_id)

    def _schedule_segment_attempts(self, request_id: int) -> None:
        """Kick off link attempts for every uncovered segment.

        A segment has at most ONE in-flight attempt chain: `pending_segments`
        prevents duplicate parallel chains (a real defect found by tracing).
        """
        active = self._active.get(request_id)
        if active is None or active.route is None:
            return
        covered = self._covered_segments(active)
        launched = False
        for i in range(len(active.route) - 1):
            if i in covered or i in active.pending_segments:
                continue
            a, b = active.route[i], active.route[i + 1]
            link = self.topology.get_link(a, b)
            if link is None or not link.available:
                self._fail_request(request_id, "segment_link_down")
                return
            delay = max(attempt_duration_ns(link.distance_km), 1.0)
            active.pending_segments.add(i)
            self.queue.push(
                self.clock.now_ns + delay, "link_attempt_started",
                source=a, destination=b, request_id=request_id, segment=i,
            )
            launched = True
        if not launched and len(covered) == len(active.route) - 1:
            self._complete_request(request_id)

    def _covered_segments(self, active: _ActiveRequest) -> set[int]:
        covered: set[int] = set()
        live_pair_ids = set()
        for mem in self.resources.memories.values():
            for h in mem.all_halves():
                live_pair_ids.add(h.pair_id)
        for pid, (s, e) in active.coverage.items():
            if pid in live_pair_ids:
                covered.update(range(s, e))
        return covered

    # ---------------- events ----------------

    def _handle_event(self, ev) -> None:
        t = ev.type
        if t == "link_attempt_started":
            self._handle_link_attempt(ev)
        elif t == "memory_expired":
            self._expire_pair(ev.payload.get("pair_id"))
        elif t == "node_failed":
            node = self.topology.nodes.get(ev.source)
            if node and not node.failed:
                node.failed = True
                self._invalidate_routes()
        elif t == "node_recovered":
            node = self.topology.nodes.get(ev.source)
            if node:
                node.failed = False
                self._invalidate_routes()
        elif t == "link_failed":
            link = self.topology.get_link(ev.source, ev.destination)
            if link and link.available:
                link.available = False
                self._invalidate_routes()
        elif t == "link_recovered":
            link = self.topology.get_link(ev.source, ev.destination)
            if link:
                link.available = True
                self._invalidate_routes()
        elif t in ("route_selected", "request_created", "request_completed",
                   "request_failed", "entanglement_generated", "entanglement_failed",
                   "swap_performed", "teleportation_completed"):
            pass  # informational milestones
        else:
            raise RuntimeError(f"No handler for event type {t!r}.")

    def _handle_link_attempt(self, ev) -> None:
        request_id = ev.payload["request_id"]
        segment = ev.payload["segment"]
        active = self._active.get(request_id)
        if active is None or active.route is None:
            return
        active.pending_segments.discard(segment)
        req = active.request
        if req.deadline_ns is not None and self.clock.now_ns > req.deadline_ns:
            self._fail_request(request_id, "deadline_exceeded")
            return
        mem_a_cap0 = self.resources.memories[ev.source].capacity == 0
        mem_b_cap0 = self.resources.memories[ev.destination].capacity == 0
        if mem_a_cap0 or mem_b_cap0:
            # Zero-capacity memory can never hold a pair: fail honestly now.
            self._fail_request(request_id, "no_memory_capacity")
            return
        a, b = ev.source, ev.destination
        link = self.topology.get_link(a, b)
        if link is None or not link.available or self.topology.nodes[a].failed \
                or self.topology.nodes[b].failed:
            self._retry(request_id, segment, "link_unavailable")
            return
        mem_a, mem_b = self.resources.memories[a], self.resources.memories[b]
        if mem_a.free == 0 or mem_b.free == 0:
            self._retry(request_id, segment, "memory_full")
            return
        self.stats.link_attempts += 1
        active.attempts += 1
        eta = generation_success_probability(
            link.distance_km, link.attenuation_db_per_km, link.detector_efficiency
        )
        if self.rng.random() >= eta:
            fail_ev = self.queue.push(
                self.clock.now_ns, "entanglement_failed", source=a, destination=b,
                reason="photon_loss",
            )
            delay = max(attempt_duration_ns(link.distance_km), 1.0)
            active.pending_segments.add(segment)
            self.queue.push(
                self.clock.now_ns + delay, "link_attempt_started",
                source=a, destination=b, request_id=request_id, segment=segment,
            )
            return

        self.stats.links_generated += 1
        pid = self.resources.pairs.create_pair_id(a, b)
        ha = EntangledPairHalf(pid, b, self.clock.now_ns, link.base_fidelity, slot=-1)
        hb = EntangledPairHalf(pid, a, self.clock.now_ns, link.base_fidelity, slot=-1)
        ok_a, ok_b = mem_a.store(ha), mem_b.store(hb)
        if not (ok_a and ok_b):
            mem_a.release(ha.slot)
            mem_b.release(hb.slot)
            self.resources.pairs.consume_pair(pid)
            self._retry(request_id, segment, "memory_full")
            return
        active.coverage[pid] = (segment, segment + 1)
        gen_ev = self.queue.push(
            self.clock.now_ns, "entanglement_generated", source=a, destination=b,
            pair_id=pid, fidelity=link.base_fidelity,
        )
        self.queue.push(
            self.clock.now_ns + self.config.memory_coherence_ns, "memory_expired",
            source=a, destination=b, pair_id=pid,
        )
        if self.config.purification_protocol is not None:
            self._try_purification(request_id)
        self._try_swaps(request_id)
        self._schedule_segment_attempts(request_id)

    def _try_purification(self, request_id: int) -> None:
        """Optional post-generation purification (directive §21).

        When TWO live pairs cover the SAME route segment, consume both and run
        one round of the configured protocol; success replaces them with a
        single higher-fidelity pair covering that segment. Failure consumes
        both pairs and leaves the segment uncovered (honest accounting).
        """
        from .purification import purify_once
        from ..quantum.states import QuantumCoreError

        active = self._active.get(request_id)
        if active is None or active.route is None:
            return
        by_segment: dict[int, list[int]] = {}
        live = self._live_halves_by_pair(active)
        for pid, (s, e) in list(active.coverage.items()):
            if s == e - 1 and pid in live:
                by_segment.setdefault(s, []).append(pid)
        for seg, pids in by_segment.items():
            if len(pids) < 2:
                continue
            pid_a, pid_b = pids[0], pids[1]
            involved = [
                (name, h) for name, m in self.resources.memories.items()
                for h in m.all_halves() if h.pair_id in (pid_a, pid_b)
            ]
            fa = next(h for n, h in involved if h.pair_id == pid_a)                 .current_fidelity(self.clock.now_ns, self.config.memory_coherence_ns)
            fb = next(h for n, h in involved if h.pair_id == pid_b)                 .current_fidelity(self.clock.now_ns, self.config.memory_coherence_ns)
            # Protocols require identical inputs; asymmetric fidelities are
            # skipped honestly rather than silently approximated.
            if abs(fa - fb) > 1e-6 or fa < 0.5:
                continue
            self.stats.purification_rounds_attempted += 1
            try:
                outcome = purify_once(
                    self.config.purification_protocol, float((fa + fb) / 2),
                    rng=self.rng,
                )
            except QuantumCoreError as exc:
                self.engine_errors.append(f"purification: {exc}")
                return
            for name, h in involved:
                self.resources.memories[name].release(h.slot)
            self.resources.pairs.consume_pair(pid_a)
            self.resources.pairs.consume_pair(pid_b)
            active.coverage.pop(pid_a, None)
            active.coverage.pop(pid_b, None)
            if outcome.success:
                self.stats.purification_rounds_succeeded += 1
                end_a = next(n for n, h in involved if h.pair_id == pid_a)
                end_b = next(n for n, h in involved if h.pair_id == pid_b)
                new_pid = self.resources.pairs.create_pair_id(end_a, end_b)
                ha = EntangledPairHalf(new_pid, end_b, self.clock.now_ns,
                                       outcome.output_fidelity, slot=-1)
                hb = EntangledPairHalf(new_pid, end_a, self.clock.now_ns,
                                       outcome.output_fidelity, slot=-1)
                self.resources.memories[end_a].store(ha)
                self.resources.memories[end_b].store(hb)
                active.coverage[new_pid] = (seg, seg + 1)
            else:
                # both pairs consumed; the segment is uncovered again — honest
                # accounting, no silent replacement.
                pass
            self.stats.pairs_consumed_by_purification += 2
            return  # one purification round per generation event

    def _try_swaps(self, request_id: int) -> None:
        active = self._active.get(request_id)
        if active is None or active.route is None:
            return
        changed = True
        while changed:
            changed = False
            live = self._live_halves_by_pair(active)
            for pid_a, (s_a, e_a) in list(active.coverage.items()):
                for pid_b, (s_b, e_b) in list(active.coverage.items()):
                    if e_a != s_b or s_a >= e_a or s_b >= e_b:
                        continue
                    if pid_a not in live or pid_b not in live:
                        continue
                    middle_idx = s_b  # repeater index between segments
                    repeater = active.route[middle_idx]
                    ha_left = live[pid_a].get(repeater)
                    ha_right = live[pid_b].get(repeater)
                    if ha_left is None or ha_right is None:
                        continue
                    self._perform_swap(active, repeater, middle_idx, pid_a, pid_b)
                    changed = True
                    live = self._live_halves_by_pair(active)

    def _live_halves_by_pair(self, active: _ActiveRequest) -> dict[int, dict[str, EntangledPairHalf]]:
        out: dict[int, dict[str, EntangledPairHalf]] = {}
        for name, mem in self.resources.memories.items():
            for h in mem.all_halves():
                out.setdefault(h.pair_id, {})[name] = h
        return out

    def _perform_swap(
        self, active: _ActiveRequest, repeater: str, middle_idx: int,
        pid_left: int, pid_right: int,
    ) -> None:
        # Gather all four halves.
        halves_by_pair = self._live_halves_by_pair(active)
        left_map = halves_by_pair.get(pid_left, {})
        right_map = halves_by_pair.get(pid_right, {})
        involved = [
            (name, h)
            for name, m in self.resources.memories.items()
            for h in m.all_halves()
            if h.pair_id in (pid_left, pid_right)
        ]
        # Endpoints of the merged span.
        left_far = next(n for n, h in involved if h.pair_id == pid_left and n != repeater)
        right_far = next(n for n, h in involved if h.pair_id == pid_right and n != repeater)
        f_left = next(h for n, h in involved if h.pair_id == pid_left and n != repeater) \
            .current_fidelity(self.clock.now_ns, self.config.memory_coherence_ns)
        f_right = next(h for n, h in involved if h.pair_id == pid_right and n != repeater) \
            .current_fidelity(self.clock.now_ns, self.config.memory_coherence_ns)
        # Consume old pairs.
        for name, h in involved:
            self.resources.memories[name].release(h.slot)
        self.resources.pairs.consume_pair(pid_left)
        self.resources.pairs.consume_pair(pid_right)
        del left_map, right_map

        if self.rng.random() >= self.config.swap_success_probability:
            self.stats.swaps_failed += 1
            active.coverage.pop(pid_left, None)
            active.coverage.pop(pid_right, None)
            fail_ev = self.queue.push(
                self.clock.now_ns, "swap_performed", source=repeater,
                result="failed",
            )
            return

        self.stats.swaps_performed += 1
        new_fid = swap_fidelity(f_left, f_right)
        pid = self.resources.pairs.create_pair_id(left_far, right_far)
        ha = EntangledPairHalf(pid, right_far, self.clock.now_ns, new_fid, slot=-1)
        hb = EntangledPairHalf(pid, left_far, self.clock.now_ns, new_fid, slot=-1)
        self.resources.memories[left_far].store(ha)
        self.resources.memories[right_far].store(hb)
        s = active.coverage.pop(pid_left)
        e = active.coverage.pop(pid_right)
        active.coverage[pid] = (min(s[0], e[0]), max(s[1], e[1]))
        lat = 0.0 if self.config.classical_latency_mode == "idealized" else \
            swap_classical_latency_ns(10.0)
        ev = self.queue.push(
            self.clock.now_ns + lat, "swap_performed", source=repeater,
            pair_id=pid, fidelity=round(new_fid, 6),
        )

    # ---------------- completion / failure ----------------

    def _complete_request(self, request_id: int) -> None:
        active = self._active.pop(request_id, None)
        if active is None:
            return
        req = active.request
        fid = self._end_to_end_fidelity(active.route)
        if fid < 0.25:
            self._fail_request(request_id, "degraded_pair")
            return
        service_ns = self.clock.now_ns - active.started_ns
        waiting_ns = active.started_ns - req.submitted_ns
        if req.protocol == "teleport":
            if self.config.classical_latency_mode != "idealized":
                clink = self._classical_route_latency(req.source, req.destination)
                self.clock.advance_to(self.clock.now_ns + clink)
            self.stats.teleportations_completed += 1
            ev = self.queue.push(
                self.clock.now_ns, "teleportation_completed", source=req.source,
                destination=req.destination, fidelity=round(fid, 6),
                request_id=request_id,
            )
        else:
            ev = self.queue.push(
                self.clock.now_ns, "request_completed", source=req.source,
                destination=req.destination, fidelity=round(fid, 6),
                request_id=request_id,
            )
        self.outcomes.append(RequestOutcome(
            request_id=request_id, source=req.source, destination=req.destination,
            protocol=req.protocol, success=True, completion_ns=self.clock.now_ns,
            waiting_ns=waiting_ns, service_ns=service_ns, fidelity=fid,
            route=active.route, attempts_used=active.attempts,
        ))

    def _classical_route_latency(self, a: str, b: str) -> float:
        for cl in self.topology.classical_links:
            if {cl.source, cl.destination} == {a, b}:
                return cl.latency_ns
        return 50_000.0  # documented default assumption

    def _end_to_end_fidelity(self, route) -> float:
        from .topology import expected_end_to_end_fidelity

        return expected_end_to_end_fidelity(self.topology, tuple(route))

    def _fail_request(self, request_id: int, reason: str) -> None:
        active = self._active.pop(request_id, None)
        if active is None:
            return
        req = active.request
        ev = self.queue.push(
            self.clock.now_ns, "request_failed", source=req.source,
            destination=req.destination, request_id=request_id, reason=reason,
        )
        self.outcomes.append(RequestOutcome(
            request_id=request_id, source=req.source, destination=req.destination,
            protocol=req.protocol, success=False, completion_ns=self.clock.now_ns,
            waiting_ns=self.clock.now_ns - req.submitted_ns, service_ns=None,
            fidelity=None, route=active.route, attempts_used=active.attempts,
            failure_reason=reason,
        ))

    def _retry(self, request_id: int, segment: int, reason: str) -> None:
        active = self._active.get(request_id)
        if active is None or active.route is None:
            return
        req = active.request
        if req.deadline_ns is not None and self.clock.now_ns > req.deadline_ns:
            self._fail_request(request_id, "deadline_exceeded")
            return
        active.retry_count += 1
        if active.retry_count > self.config.max_retries_per_request:
            self._fail_request(request_id, reason)
            return
        a, b = active.route[segment], active.route[segment + 1]
        backoff_ns = 1000.0 * active.retry_count
        delay = backoff_ns + max(attempt_duration_ns(
            self.topology.get_link(a, b).distance_km), 1.0)
        active.pending_segments.add(segment)
        self.queue.push(
            self.clock.now_ns + delay, "link_attempt_started",
            source=a, destination=b, request_id=request_id, segment=segment,
        )

    # ---------------- failures & chaos ----------------

    def _expire_pair(self, pair_id) -> None:
        if pair_id is None:
            return
        removed = False
        for mem in self.resources.memories.values():
            for h in list(mem.all_halves()):
                if h.pair_id == pair_id:
                    mem.release(h.slot)
                    removed = True
        self.resources.pairs.consume_pair(pair_id)
        if removed:
            self.stats.memory_expirations += 1

    def _invalidate_routes(self) -> None:
        self._route_cache.clear()

    def _schedule_chaos(self, horizon_ns: float) -> None:
        cfg = self.config
        if horizon_ns is math.inf:
            horizon_ns = cfg.max_sim_time_ns
        budget = cfg.max_chaos_events
        if cfg.node_failure_rate_per_s > 0 and self.topology.nodes:
            expected = cfg.node_failure_rate_per_s * (horizon_ns / 1e9)
            names = sorted(self.topology.nodes)
            n_failures = min(int(self.rng.poisson(expected)), max(budget, 0))
            for _ in range(n_failures):
                name = names[int(self.rng.integers(len(names)))]
                t_fail = float(self.rng.uniform(0, min(horizon_ns, cfg.max_sim_time_ns)))
                self.queue.push(t_fail, "node_failed", source=name)
                self.queue.push(
                    min(t_fail + cfg.mean_recovery_time_ns, horizon_ns),
                    "node_recovered", source=name,
                )
                budget -= 2
                if budget <= 0:
                    return
        if cfg.link_failure_rate_per_s > 0 and self.topology.links:
            expected = cfg.link_failure_rate_per_s * (horizon_ns / 1e9)
            n_failures = min(int(self.rng.poisson(expected)), max(budget // 2, 0))
            for _ in range(n_failures):
                idx = int(self.rng.integers(len(self.topology.links)))
                link = self.topology.links[idx]
                t_fail = float(self.rng.uniform(0, min(horizon_ns, cfg.max_sim_time_ns)))
                self.queue.push(t_fail, "link_failed", source=link.source,
                                destination=link.destination)
                self.queue.push(
                    min(t_fail + cfg.mean_recovery_time_ns, horizon_ns),
                    "link_recovered", source=link.source, destination=link.destination,
                )

    def _fail_expired_requests(self) -> None:
        now = self.clock.now_ns
        for r in self.scheduler.drop_expired(now):
            self._fail_request(r.request_id, "deadline_exceeded")

    # ---------------- collection ----------------

    def _collect(self, *, truncated: bool) -> NetworkResult:
        successful = [o for o in self.outcomes if o.success]
        failed = [o for o in self.outcomes if not o.success]
        total_time_s = max(self.clock.now_ns / 1e9, 1e-9)
        throughput_by_source: dict[str, float] = {}
        for o in successful:
            throughput_by_source[o.source] = round(
                throughput_by_source.get(o.source, 0.0) + 1.0 / total_time_s, 6
            )
        jain = FairnessReport(throughput_by_source).jain_index()
        services = [o.service_ns for o in successful if o.service_ns is not None]
        fids = [o.fidelity for o in successful if o.fidelity is not None]
        return NetworkResult(
            sim_time_ns=self.clock.now_ns,
            outcomes=list(self.outcomes),
            stats=self.stats.to_dict(),
            fairness={
                "jain_index": round(jain, 6),
                "throughput_per_s_by_source": throughput_by_source,
            },
            utilization=self.resources.utilization_report(),
            event_log=self.trace.render(),
            truncated=truncated or self.trace.dropped > 0,
            avg_service_ns=sum(services) / len(services) if services else None,
            avg_fidelity=sum(fids) / len(fids) if fids else None,
            success_count=len(successful),
            failure_count=len(failed),
            engine_errors=list(self.engine_errors),
        )
