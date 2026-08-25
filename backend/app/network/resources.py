"""Quantum memory and entanglement resource management (directive §67, §189-190).

Memory slots hold entangled-pair halves with:
  - creation time, current age, fidelity decay over time
  - expiration at a configurable lifetime

Fidelity decay model (documented, §72): the pair is treated as a Werner state
whose depolarizing parameter decays exponentially with memory age,
  q(age) = q0 * exp(-age / T_memory),
giving F(age) = (3 q0 exp(-age/T) + 1) / 4. At age 0 this reproduces the link
base fidelity; as age >> T it converges to F = 1/2 (maximally mixed), the
physically correct limiting case. T = memory_coherence_ns.
"""
from __future__ import annotations

from dataclasses import dataclass, field


def werner_parameter(fidelity: float) -> float:
    """q = (4F - 1)/3 for a Werner state; valid for F >= 0.25."""
    if fidelity < 0.25 or fidelity > 1.0:
        raise ValueError(f"Fidelity {fidelity} outside Werner range [0.25, 1].")
    return (4 * fidelity - 1) / 3


def fidelity_from_werner(q: float) -> float:
    return (3 * q + 1) / 4


def aged_fidelity(base_fidelity: float, age_ns: float, coherence_ns: float) -> float:
    """Documented exponential-decay model; validated limiting cases in tests.

    Limit behavior: as age >> coherence the pair degrades to the maximally
    mixed two-qubit state with F = 1/4 under the Werner parameterization
    rho = q|Phi+><Phi+| + (1-q) I/4.
    """
    if coherence_ns <= 0:
        raise ValueError("memory_coherence_ns must be positive.")
    if age_ns < 0:
        raise ValueError("age must be non-negative.")
    q0 = werner_parameter(base_fidelity)
    q_t = q0 * float(np_exp(-age_ns / coherence_ns))
    return fidelity_from_werner(max(q_t, 0.0))


def np_exp(x: float) -> float:
    import math

    return math.exp(x)


@dataclass
class EntangledPairHalf:
    """One half of an entangled pair held by a node.

    pair_id groups the two halves. `remote_node` names the holder of the other
    half. Fidelity stored is the pair's CURRENT fidelity (decays with age).
    """

    pair_id: int
    remote_node: str
    created_ns: float
    base_fidelity: float
    slot: int

    def current_fidelity(self, now_ns: float, coherence_ns: float) -> float:
        return aged_fidelity(self.base_fidelity, now_ns - self.created_ns, coherence_ns)


@dataclass
class QuantumMemory:
    """Slot-based quantum memory attached to one node."""

    node_name: str
    capacity: int
    coherence_ns: float
    _slots: dict[int, EntangledPairHalf | None] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        if self.capacity < 0:
            raise ValueError("Memory capacity must be >= 0.")
        if self.coherence_ns <= 0:
            raise ValueError("coherence_ns must be > 0.")
        self._slots = {i: None for i in range(self.capacity)}

    @property
    def used(self) -> int:
        return sum(1 for v in self._slots.values() if v is not None)

    @property
    def free(self) -> int:
        return self.capacity - self.used

    def store(self, half: EntangledPairHalf) -> bool:
        """Store into the first free slot; returns False when full (no silent loss)."""
        for i, occupant in self._slots.items():
            if occupant is None:
                half.slot = i
                self._slots[i] = half
                return True
        return False

    def release(self, slot: int) -> EntangledPairHalf | None:
        half = self._slots.pop(slot, None)
        self._slots[slot] = None
        return half

    def peek(self, slot: int) -> EntangledPairHalf | None:
        return self._slots.get(slot)

    def all_halves(self) -> list[EntangledPairHalf]:
        return [h for h in self._slots.values() if h is not None]

    def expire_aged(self, now_ns: float) -> list[EntangledPairHalf]:
        expired = []
        for slot, half in list(self._slots.items()):
            if half is None:
                continue
            if now_ns - half.created_ns >= self.coherence_ns:
                expired.append(half)
                self._slots[slot] = None
        return expired


class PairRegistry:
    """Tracks complete entangled pairs across nodes (both halves)."""

    def __init__(self):
        self._next_id = 1
        self._open_pairs: dict[int, tuple[str, str]] = {}

    def create_pair_id(self, node_a: str, node_b: str) -> int:
        pid = self._next_id
        self._next_id += 1
        self._open_pairs[pid] = (node_a, node_b)
        return pid

    def consume_pair(self, pair_id: int) -> tuple[str, str] | None:
        return self._open_pairs.pop(pair_id, None)

    def drop_half(self, pair_id: int) -> None:
        self._open_pairs.pop(pair_id, None)

    @property
    def active_pairs(self) -> int:
        return len(self._open_pairs)


class ResourceManager:
    """Central resource accounting: memories, pairs, pending attempts."""

    def __init__(self, topology):
        from .topology import Topology

        if not isinstance(topology, Topology):
            raise TypeError("ResourceManager requires a Topology.")
        self.topology = topology
        self.memories: dict[str, QuantumMemory] = {
            name: QuantumMemory(name, node.memory_slots, coherence_ns=1_000_000.0)
            for name, node in topology.nodes.items()
        }
        # Per-node coherence override via node metadata is applied by engine.
        self.pairs = PairRegistry()
        self.pending_attempts: dict[str, int] = {name: 0 for name in topology.nodes}

    def try_allocate_for_attempt(self, node: str) -> bool:
        mem = self.memories[node]
        if mem.free == 0:
            return False
        if self.pending_attempts[node] + mem.used >= mem.capacity:
            return False
        self.pending_attempts[node] += 1
        return True

    def complete_attempt(self, node: str) -> None:
        self.pending_attempts[node] = max(0, self.pending_attempts[node] - 1)

    def utilization_report(self) -> dict:
        return {
            name: {
                "used": mem.used,
                "capacity": mem.capacity,
                "pending_attempts": self.pending_attempts[name],
                "active_pairs": len(mem.all_halves()),
            }
            for name, mem in self.memories.items()
        }
