"""Network topology: nodes, quantum/classical links, graph algorithms.

Units (directive §155): distances in kilometers, latencies in nanoseconds,
loss probabilities dimensionless. Physical distance and routing cost are kept
distinct (§156): cost functions may combine distance/loss/fidelity/latency
with explicit weights exposed to the user (§76-77).

Fidelity semantics (§157): link-level `base_fidelity` is an ESTIMATE of the
Werner-parameter-like quality of generated pairs; end-to-end entanglement
fidelity after swaps follows the documented model in entanglement.py. We never
label anything "fidelity" without saying which definition applies.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import math

NODE_TYPES = ("end", "repeater", "router", "satellite", "measurement_station")


@dataclass
class NetworkNode:
    name: str
    node_type: str = "end"
    # Quantum memory
    memory_slots: int = 4
    # Geographic coordinates for the digital-twin view (degrees; optional)
    latitude: float | None = None
    longitude: float | None = None
    # Failure modeling
    failed: bool = False
    reliability: float = 1.0  # per-simulation survival probability (informational)

    def __post_init__(self):
        if self.node_type not in NODE_TYPES:
            raise ValueError(f"Node type {self.node_type!r} invalid; use {NODE_TYPES}.")
        if self.memory_slots < 0:
            raise ValueError("memory_slots must be >= 0.")
        if self.latitude is not None and not (-90 <= self.latitude <= 90):
            raise ValueError("latitude out of range [-90, 90].")
        if self.longitude is not None and not (-180 <= self.longitude <= 180):
            raise ValueError("longitude out of range [-180, 180].")

    @property
    def is_repeater(self) -> bool:
        return self.node_type in ("repeater", "router")


@dataclass
class QuantumLink:
    source: str
    destination: str
    distance_km: float
    attenuation_db_per_km: float = 0.2   # standard fiber ~0.2 dB/km at 1550 nm
    base_fidelity: float = 0.99           # quality estimate of a fresh pair
    attempt_rate_per_ms: float = 1000.0   # attempts per simulated millisecond
    detector_efficiency: float = 1.0      # combined detection probability model
    available: bool = True
    capacity: int = 10                    # concurrent pending attempts

    def __post_init__(self):
        if self.distance_km < 0:
            raise ValueError(f"Link distance must be >= 0 km, got {self.distance_km}.")
        if not (0 <= self.base_fidelity <= 1):
            raise ValueError("base_fidelity must be within [0,1].")
        if not (0 < self.detector_efficiency <= 1):
            raise ValueError("detector_efficiency must be within (0,1].")
        if self.attempt_rate_per_ms <= 0:
            raise ValueError("attempt_rate_per_ms must be positive.")

    def transmission_loss_probability(self) -> float:
        """Photon survival probability over fiber: eta = 10^(-alpha*d/10).

        Documented model (directive §154): standard fiber attenuation with
        alpha dB/km; d=0 gives lossless channel (limiting case validated in
        tests). Detector efficiency multiplies the survival probability.
        """
        eta_fiber = 10 ** (-self.attenuation_db_per_km * self.distance_km / 10)
        return float(min(1.0, eta_fiber * self.detector_efficiency))

    def other_end(self, node: str) -> str:
        return self.destination if node == self.source else self.source


@dataclass
class ClassicalLink:
    source: str
    destination: str
    latency_ns: float = 5000.0     # ~1km fiber round-trip order of magnitude
    bandwidth_mbps: float = 1000.0
    reliability: float = 1.0

    def __post_init__(self):
        if self.latency_ns < 0:
            raise ValueError("Classical latency must be >= 0.")
        if not (0 <= self.reliability <= 1):
            raise ValueError("reliability must be within [0,1].")


@dataclass
class Topology:
    """Directed-allowed graph; quantum links are treated as bidirectional pairs."""

    nodes: dict[str, NetworkNode] = field(default_factory=dict)
    links: list[QuantumLink] = field(default_factory=list)
    classical_links: list[ClassicalLink] = field(default_factory=list)

    def add_node(self, node: NetworkNode) -> NetworkNode:
        if node.name in self.nodes:
            raise ValueError(f"Duplicate node {node.name!r}.")
        self.nodes[node.name] = node
        return node

    def add_quantum_link(
        self,
        source: str,
        destination: str,
        distance_km: float,
        **kwargs,
    ) -> QuantumLink:
        self._require_nodes(source, destination)
        if source == destination:
            raise ValueError("Self-loops are not supported.")
        if self.get_link(source, destination) is not None:
            raise ValueError(f"Quantum link {source}-{destination} already exists.")
        link = QuantumLink(source, destination, distance_km=distance_km, **kwargs)
        self.links.append(link)
        return link

    def add_classical_link(self, source: str, destination: str, **kwargs) -> ClassicalLink:
        self._require_nodes(source, destination)
        cl = ClassicalLink(source, destination, **kwargs)
        self.classical_links.append(cl)
        return cl

    def _require_nodes(self, *names: str) -> None:
        for n in names:
            if n not in self.nodes:
                raise ValueError(f"Unknown node {n!r}; add it to the topology first.")

    def get_link(self, a: str, b: str) -> QuantumLink | None:
        for l in self.links:
            if {l.source, l.destination} == {a, b}:
                return l
        return None

    def neighbors(self, node: str, *, require_available: bool = True) -> list[tuple[str, QuantumLink]]:
        out = []
        for l in self.links:
            if l.source == node or l.destination == node:
                if require_available and (not l.available or self.nodes[l.other_end(node)].failed):
                    continue
                out.append((l.other_end(node), l))
        return out

    def adjacency(self, *, require_available: bool = True) -> dict[str, list[tuple[str, QuantumLink]]]:
        adj = {}
        for name in self.nodes:
            if require_available and self.nodes[name].failed:
                continue
            adj[name] = self.neighbors(name, require_available=require_available)
        return adj

    def validate(self) -> list[str]:
        issues = []
        names = set(self.nodes)
        for l in self.links + self.classical_links:
            if l.source not in names or l.destination not in names:
                issues.append(f"Link {l.source}-{l.destination} references unknown nodes.")
        return issues

    def copy(self) -> "Topology":
        """Deep-enough copy: fresh node/link objects, same parameter values."""
        new = Topology()
        for name, n in self.nodes.items():
            new.add_node(
                NetworkNode(
                    name=name,
                    node_type=n.node_type,
                    memory_slots=n.memory_slots,
                    latitude=n.latitude,
                    longitude=n.longitude,
                    failed=n.failed,
                    reliability=n.reliability,
                )
            )
        for l in self.links:
            new.add_quantum_link(
                l.source, l.destination, distance_km=l.distance_km,
                attenuation_db_per_km=l.attenuation_db_per_km,
                base_fidelity=l.base_fidelity,
                attempt_rate_per_ms=l.attempt_rate_per_ms,
                detector_efficiency=l.detector_efficiency,
                capacity=l.capacity,
            )
            new.links[-1].available = l.available
        for cl in self.classical_links:
            new.add_classical_link(cl.source, cl.destination,
                                   latency_ns=cl.latency_ns,
                                   bandwidth_mbps=cl.bandwidth_mbps,
                                   reliability=cl.reliability)
        return new


# ---------------------------------------------------------------------------
# Routing strategies (directive §75-77, §197)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RouteExplanation:
    """Why a route was selected — makes routing inspectable (directive §197)."""

    route: tuple[str, ...]
    strategy: str
    score: float
    expected_fidelity: float
    estimated_latency_ns: float
    total_distance_km: float
    details: dict

    def describe(self) -> str:
        return (
            f"Route {' -> '.join(self.route)} via {self.strategy}: "
            f"score={self.score:.4f}, expected fidelity≈{self.expected_fidelity:.3f}, "
            f"latency≈{self.estimated_latency_ns / 1e6:.3f} ms"
        )


ROUTING_STRATEGIES = (
    "shortest_path",
    "min_loss",
    "max_fidelity",
    "min_expected_time",
    "resource_aware",
)


def expected_end_to_end_fidelity(topology: Topology, route: tuple[str, ...]) -> float:
    """Documented swap-fidelity model for Werner-style links.

    For each link i with base fidelity F_i, the depolarizing parameter is
    q_i = (4*F_i - 1)/3 (Werner state parameter). Under ideal entanglement
    swapping across m links, the resulting Werner parameter multiplies:
    Q = prod_i q_i, giving F_e2e = (3Q + 1)/4 (documented approximation — see
    SCIENTIFIC_MODELS.md §entanglement swapping).
    """
    q_product = 1.0
    for a, b in zip(route, route[1:]):
        link = topology.get_link(a, b)
        if link is None:
            return 0.0
        fi = link.base_fidelity
        qi = (4 * fi - 1) / 3
        if qi <= 0:
            return 0.5  # maximally mixed limit
        q_product *= max(qi, 0.0)
    return (3 * q_product + 1) / 4


def route_cost(
    topology: Topology,
    route: tuple[str, ...],
    strategy: str,
    weights: dict[str, float] | None = None,
) -> tuple[float, dict]:
    """Compute routing cost; LOWER is better for min-strategies.

    Strategies:
      shortest_path     — total km
      min_loss          — sum of -log10(survival) (dB-like additive loss)
      max_fidelity      — negative expected e2e fidelity
      min_expected_time — latency dominated by per-link attempts/propagation
      resource_aware    — weighted combination using explicit weights
    """
    w = weights or {}
    total_km = 0.0
    loss_sum = 0.0
    latency = 0.0
    free_memory_penalty = 0.0
    for a, b in zip(route, route[1:]):
        link = topology.get_link(a, b)
        if link is None or not link.available:
            return math.inf, {}
        eta = link.transmission_loss_probability()
        total_km += link.distance_km
        loss_sum += -math.log10(max(eta, 1e-12)) * 10  # dB
        # Expected attempts per successful pair ~ 1/eta (geometric), plus
        # propagation delay c.f.o. light in fiber (~5 us/km one way).
        attempts = 1.0 / max(eta, 1e-9)
        propagation_ns = link.distance_km * 5000.0
        latency += attempts * (propagation_ns * 2) / max(link.attempt_rate_per_ms / 1000.0, 1e-9) \
            + propagation_ns
        for node_name in (a, b):
            node = topology.nodes[node_name]
            free_memory_penalty += max(0, node.memory_slots * 0.25)  # more slots => cheaper
    fid = expected_end_to_end_fidelity(topology, route)
    if strategy == "shortest_path":
        return total_km, {"total_km": total_km}
    if strategy == "min_loss":
        return loss_sum, {"loss_dB": loss_sum}
    if strategy == "max_fidelity":
        return -fid, {"expected_fidelity": fid}
    if strategy == "min_expected_time":
        return latency, {"latency_ns": latency}
    if strategy == "resource_aware":
        wf = float(w.get("fidelity_weight", 1.0))
        wl = float(w.get("loss_weight", 1.0))
        wt = float(w.get("latency_weight", 1.0))
        wm = float(w.get("resource_weight", 0.5))
        cost = (
            wf * (1 - fid)
            + wl * (loss_sum / 100.0)
            + wt * (latency / 1e6)
            - wm * (free_memory_penalty / max(len(route), 1))
        )
        return cost, {
            "expected_fidelity": fid, "loss_dB": loss_sum,
            "latency_ns": latency, "memory_score": free_memory_penalty,
        }
    raise ValueError(f"Unknown routing strategy {strategy!r}.")


def find_best_route(
    topology: Topology,
    source: str,
    destination: str,
    *,
    strategy: str = "min_expected_time",
    weights: dict[str, float] | None = None,
    fidelity_requirement: float | None = None,
) -> tuple[tuple[str, ...] | None, RouteExplanation | None]:
    """Dijkstra over the cost function of the chosen strategy.

    Routes failing a fidelity requirement are excluded from selection even if
    shortest/cheapest (directive §196); when no route qualifies, returns
    (None, explanation-of-best-effort) so callers can explain why.
    """
    if source not in topology.nodes or destination not in topology.nodes:
        raise ValueError("Source and destination must exist in the topology.")
    if source == destination:
        raise ValueError("Source equals destination.")
    import heapq as hq

    adj = topology.adjacency(require_available=True)
    best: dict[str, tuple[float, tuple[str, ...]]] = {source: (0.0, (source,))}
    heap: list[tuple[float, int, str, tuple[str, ...]]] = [(0.0, 0, source, (source,))]
    counter = 1
    while heap:
        cost, _, node, path = hq.heappop(heap)
        if cost > best.get(node, (math.inf, ()))[0]:
            continue
        if node == destination:
            break
        for nb, link in sorted(adj.get(node, [])):
            if nb in path:
                continue
            new_path = path + (nb,)
            full_cost, _seg = route_cost(topology, new_path, strategy, weights)
            if math.isinf(full_cost):
                continue
            if nb not in best or full_cost < best[nb][0]:
                best[nb] = (full_cost, new_path)
                hq.heappush(heap, (full_cost, counter, nb, new_path))
                counter += 1
    route = best.get(destination, (None, None))[1]
    if route is None:
        return None, None
    fid = expected_end_to_end_fidelity(topology, route)
    score, details = route_cost(topology, route, strategy, weights)
    explanation = RouteExplanation(
        route=route,
        strategy=strategy,
        score=score,
        expected_fidelity=fid,
        estimated_latency_ns=float(details.get("latency_ns", 0.0)),
        total_distance_km=float(details.get("total_km", 0.0)),
        details=details,
    )
    if fidelity_requirement is not None and fid < fidelity_requirement:
        return None, explanation
    return route, explanation
