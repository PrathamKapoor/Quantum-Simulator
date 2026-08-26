"""Network integration bridge for the distributed subsystem (§NETWORK INTEGRATION).

This module does NOT reimplement a network simulator. It drives the existing
``NetworkEngine`` to obtain, for a requested pair of nodes, a real shared
entangled pair: its fidelity, the modelled service latency, and the number of
generation attempts. Those figures are then reported as the entanglement
resources consumed by a remote-CNOT.

When no topology is supplied the bridge returns an *ideal* grant (fidelity 1,
zero modelled latency, zero attempts) and labels the model explicitly so the
result is never mistaken for a physical-network simulation.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..network import Topology, NetworkNode, NetworkEngine, NetworkConfig
from .model import EbitGrant


def topology_from_nodes_links(
    nodes: list[dict], links: list[dict]
) -> Topology:
    """Build a :class:`Topology` from plain node/link dicts (reuses network API)."""
    topo = Topology()
    names: set[str] = set()
    for n in nodes:
        topo.add_node(NetworkNode(
            name=n["name"],
            node_type=n.get("type", "repeater"),
            memory_slots=int(n.get("memory_slots", 4)),
        ))
        names.add(n["name"])
    for lk in links:
        if lk["source"] not in names or lk["destination"] not in names:
            raise ValueError(
                f"Link {lk['source']}-{lk['destination']} references unknown nodes."
            )
        topo.add_quantum_link(
            lk["source"], lk["destination"],
            distance_km=float(lk.get("distance_km", 10)),
            base_fidelity=float(lk.get("base_fidelity", 0.99)),
            detector_efficiency=float(lk.get("detector_efficiency", 1.0)),
        )
    return topo


@dataclass
class NetworkBridge:
    """Request entanglement resources from the existing network engine."""

    topology: Topology | None = None
    config: NetworkConfig | None = None
    seed: int = 7
    # Cache one grant per ordered node pair so repeated remote CNOTs between the
    # same nodes reuse a single engine run (deterministic, reproducible).
    _cache: dict[tuple[str, str], EbitGrant] = field(default_factory=dict)

    def request_ebit(self, node_a: str, node_b: str, *, protocol: str = "single_ebit") -> EbitGrant:
        key = (node_a, node_b)
        if key in self._cache:
            return self._cache[key]
        if self.topology is None:
            grant = EbitGrant(
                node_a=node_a, node_b=node_b, success=True,
                fidelity=1.0, latency_ns=0.0, attempts=0,
                model="ideal (no topology supplied)",
            )
            self._cache[key] = grant
            return grant
        if node_a not in self.topology.nodes or node_b not in self.topology.nodes:
            grant = EbitGrant(
                node_a=node_a, node_b=node_b, success=False,
                model="network", failure_reason=f"Unknown node in pair {node_a}/{node_b}.",
            )
            self._cache[key] = grant
            return grant
        if node_a == node_b:
            grant = EbitGrant(
                node_a=node_a, node_b=node_b, success=False,
                model="network", failure_reason="Cannot share entanglement within one node.",
            )
            self._cache[key] = grant
            return grant
        engine = NetworkEngine(self.topology, self.config or NetworkConfig(), seed=self.seed)
        try:
            engine.submit_request(node_a, node_b, protocol="entanglement")
        except ValueError as e:
            grant = EbitGrant(
                node_a=node_a, node_b=node_b, success=False,
                model="network", failure_reason=str(e),
            )
            self._cache[key] = grant
            return grant
        result = engine.run()
        if not result.outcomes:
            grant = EbitGrant(
                node_a=node_a, node_b=node_b, success=False,
                model="network", failure_reason="Network engine returned no outcome.",
            )
            self._cache[key] = grant
            return grant
        outcome = result.outcomes[0]
        if not outcome.success:
            grant = EbitGrant(
                node_a=node_a, node_b=node_b, success=False,
                model="network", fidelity=outcome.fidelity,
                latency_ns=outcome.completion_ns,
                attempts=outcome.attempts_used,
                route=list(outcome.route) if outcome.route else None,
                failure_reason=outcome.failure_reason or "Entanglement generation failed.",
            )
            self._cache[key] = grant
            return grant
        grant = EbitGrant(
            node_a=node_a, node_b=node_b, success=True,
            fidelity=outcome.fidelity, latency_ns=outcome.completion_ns,
            attempts=outcome.attempts_used,
            route=list(outcome.route) if outcome.route else None,
            model="network",
        )
        self._cache[key] = grant
        return grant

    def classical_latency_ns(self, node_a: str, node_b: str) -> float | None:
        """Modelled classical latency between two nodes, if the topology supports it.

        Sums the per-hop classical latency (from the network model) along the
        best route. Returns None when no route exists or no topology is set.
        """
        if self.topology is None:
            return None
        from ..network.topology import find_best_route
        from ..network.entanglement import swap_classical_latency_ns

        route, _ = find_best_route(self.topology, node_a, node_b)
        if not route:
            return None
        total = 0.0
        for a, b in zip(route[:-1], route[1:]):
            link = self.topology.get_link(a, b)
            if link is None:
                return None
            total += swap_classical_latency_ns(link.distance_km)
        return total
