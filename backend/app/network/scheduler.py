"""Request scheduler for competing network requests (directive §78).

Policies:
  fifo      — first-come first-served
  priority  — higher priority value first (ties FIFO)
  deadline  — earliest deadline first (requests without deadline treated last)

The scheduler does NOT touch topology internals; it orders pending requests,
and the engine decides feasibility (routing + resources) — separation per §193.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(order=True)
class EntangleRequest:
    submitted_ns: float
    priority: int = field(compare=False, default=0)
    deadline_ns: float | None = field(compare=False, default=None)
    request_id: int = field(compare=False, default=0)
    source: str = field(compare=False, default="")
    destination: str = field(compare=False, default="")
    protocol: str = field(compare=False, default="entanglement")
    fidelity_requirement: float | None = field(compare=False, default=None)


class RequestScheduler:
    """Holds pending requests; pop order depends on policy."""

    POLICIES = ("fifo", "priority", "deadline")

    def __init__(self, policy: str = "fifo"):
        if policy not in self.POLICIES:
            raise ValueError(f"Unknown scheduler policy {policy!r}; use {self.POLICIES}.")
        self.policy = policy
        self._pending: list[EntangleRequest] = []
        self._next_id = 1

    def submit(
        self,
        source: str,
        destination: str,
        *,
        now_ns: float,
        protocol: str = "entanglement",
        priority: int = 0,
        deadline_ns: float | None = None,
        fidelity_requirement: float | None = None,
    ) -> EntangleRequest:
        req = EntangleRequest(
            submitted_ns=now_ns,
            priority=priority,
            deadline_ns=deadline_ns,
            request_id=self._next_id,
            source=source,
            destination=destination,
            protocol=protocol,
            fidelity_requirement=fidelity_requirement,
        )
        self._next_id += 1
        self._pending.append(req)
        return req

    def has_pending(self) -> bool:
        return bool(self._pending)

    def pending_count(self) -> int:
        return len(self._pending)

    def pop_next(self) -> EntangleRequest | None:
        if not self._pending:
            return None
        if self.policy == "fifo":
            # list append order == submission order
            return self._pending.pop(0)
        if self.policy == "priority":
            best_idx = max(range(len(self._pending)), key=lambda i: (self._pending[i].priority, -i))
            return self._pending.pop(best_idx)
        # deadline
        def key(i):
            r = self._pending[i]
            d = r.deadline_ns if r.deadline_ns is not None else float("inf")
            return (d, -r.request_id)

        best_idx = min(range(len(self._pending)), key=key)
        return self._pending.pop(best_idx)

    def drop_expired(self, now_ns: float) -> list[EntangleRequest]:
        expired = [r for r in self._pending if r.deadline_ns is not None and r.deadline_ns < now_ns]
        for r in expired:
            self._pending.remove(r)
        return expired

    def waiting_times_ns(self, now_ns: float) -> dict[int, float]:
        return {r.request_id: now_ns - r.submitted_ns for r in self._pending}


@dataclass
class FairnessReport:
    """Jain fairness index over per-source successful deliveries (§255)."""

    throughput_by_source: dict[str, float]

    def jain_index(self) -> float:
        vals = list(self.throughput_by_source.values())
        n = len(vals)
        if n == 0:
            return 1.0
        s = sum(vals)
        ss = sum(v * v for v in vals)
        return (s * s) / (n * ss) if ss > 0 else 1.0
