"""Network simulation event types and the discrete-event priority queue.

Simulation time is LOGICAL time in nanoseconds (directive §69): wall-clock
execution duration is unrelated to simulated durations. The event queue pops
the earliest-time event first (ties broken by insertion order for
determinism), applies it, and collects follow-up events (§68, §70).

Trace modes (directive §205):
  full    — keep every event (bounded by max_events)
  summary — keep only protocol-relevant milestones
  sampled — keep every k-th event plus all milestones
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from itertools import count

EVENT_TYPES = {
    "request_created",
    "request_completed",
    "request_failed",
    "link_attempt_started",
    "entanglement_generated",
    "entanglement_failed",
    "photon_transmitted",
    "photon_lost",
    "memory_stored",
    "memory_expired",
    "swap_performed",
    "purification_performed",
    "classical_message",
    "node_failed",
    "node_recovered",
    "link_failed",
    "link_recovered",
    "route_selected",
    "measurement_performed",
    "teleportation_completed",
}

MILESTONE_TYPES = {
    "request_created",
    "request_completed",
    "request_failed",
    "entanglement_generated",
    "memory_expired",
    "swap_performed",
    "node_failed",
    "link_failed",
    "teleportation_completed",
}


@dataclass(order=True)
class Event:
    """A network simulation event ordered by (time, sequence)."""

    time_ns: float
    seq: int = field(compare=True)
    type: str = field(compare=False)
    source: str | None = field(default=None, compare=False)
    destination: str | None = field(default=None, compare=False)
    payload: dict = field(default_factory=dict, compare=False)

    def describe(self) -> str:
        src = f" {self.source}" if self.source else ""
        dst = f" -> {self.destination}" if self.destination else ""
        extra = ""
        if self.payload:
            parts = []
            for k in ("pair_id", "fidelity", "reason", "route", "attempt"):
                if k in self.payload:
                    v = self.payload[k]
                    parts.append(f"{k}={v}")
            if parts:
                extra = " (" + ", ".join(parts) + ")"
        return f"t={self.time_ns:.1f}ns {self.type}{src}{dst}{extra}"


class EventQueue:
    """Deterministic priority queue keyed by (time_ns, seq)."""

    def __init__(self):
        self._heap: list[Event] = []
        self._counter = count()

    def push(self, time_ns: float, type_: str, *, source=None, destination=None, **payload) -> Event:
        if time_ns < 0:
            raise ValueError(f"Event time must be >= 0, got {time_ns}.")
        ev = Event(
            time_ns=float(time_ns),
            seq=next(self._counter),
            type=type_,
            source=source,
            destination=destination,
            payload=payload,
        )
        heapq.heappush(self._heap, ev)
        return ev

    def pop(self) -> Event | None:
        return heapq.heappop(self._heap) if self._heap else None

    def __len__(self) -> int:
        return len(self._heap)


class SimulationClock:
    """Logical clock; only advances when events are processed."""

    def __init__(self):
        self.now_ns: float = 0.0

    def advance_to(self, t_ns: float) -> None:
        if t_ns < self.now_ns - 1e-9:
            raise ValueError(
                f"Causality violation: event at {t_ns} ns precedes current time "
                f"{self.now_ns} ns."
            )
        self.now_ns = max(self.now_ns, t_ns)


class EventTrace:
    """Bounded trace storage with full/summary/sampled modes."""

    def __init__(self, mode: str = "summary", sample_rate: int = 10, max_events: int = 100_000):
        if mode not in ("full", "summary", "sampled"):
            raise ValueError(f"Unknown trace mode {mode!r}.")
        self.mode = mode
        self.sample_rate = max(1, int(sample_rate))
        self.max_events = max_events
        self.events: list[Event] = []
        self.dropped = 0

    def record(self, event: Event) -> None:
        keep = (
            self.mode == "full"
            or (self.mode == "summary" and event.type in MILESTONE_TYPES)
            or (self.mode == "sampled"
                and (event.seq % self.sample_rate == 0 or event.type in MILESTONE_TYPES))
        )
        if not keep:
            return
        if len(self.events) >= self.max_events:
            self.dropped += 1
            return
        self.events.append(event)

    def render(self, limit: int = 200) -> list[str]:
        return [e.describe() for e in self.events[:limit]]
