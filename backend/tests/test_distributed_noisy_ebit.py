"""Noisy-ebit (Werner) injection tests: network fidelity -> quantum state.

Levels covered (directive §75):
  1. Werner trajectory sampling statistics.
  2. Remote-CNOT protocol expansion with sampled Pauli errors.
  3. NetworkBridge grant fidelity reaching the protocol (direct, multi-hop,
     memory decay).
  4. DistributedExecutor end-to-end (F=1 regression, analytic references,
     basis/superposition/entangled inputs, reproducibility, config errors).

Independent reference (§22-§23): teleportation through a Werner-errored ebit
is ideal teleportation composed with the corresponding Pauli on the carried
qubit. Hence for the single-ebit protocol the effective logical channel is
    rho_out = sum_P p_P * CNOT (P_c x I) rho_in (P_c x I)^dagger CNOT^dagger,
p_P = (F, (1-F)/3, (1-F)/3, (1-F)/3); for double teleportation the two ebit
errors compose on both sides of the CNOT:
    rho_out = sum_{P1,P2} p1 p2 (P2 x I) CNOT (P1 x I) rho_in ... .
These references are derived, not produced by the code under test.
"""
import numpy as np
import pytest

from app.circuits.model import Circuit
from app.distributed import (
    DistributedConfig,
    DistributedExecutor,
    expand_remote_cnot,
    sample_ebit_pauli_error,
    topology_from_nodes_links,
)
from app.network import NetworkConfig
from app.quantum.density import DensityMatrix, trace_distance

I2 = np.eye(2, dtype=complex)
PX = np.array([[0, 1], [1, 0]], dtype=complex)
PY = np.array([[0, -1j], [1j, 0]], dtype=complex)
PZ = np.diag([1, -1]).astype(complex)
CNOT2 = np.array([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]], dtype=complex)
H1 = np.array([[1, 1], [1, -1]], dtype=complex) / np.sqrt(2)

PAULIS = {"I": I2, "X": PX, "Y": PY, "Z": PZ}


def werner_pauli_weights(f: float) -> list[tuple[float, str]]:
    return [(f, "I"), ((1 - f) / 3.0, "X"), ((1 - f) / 3.0, "Z"), ((1 - f) / 3.0, "Y")]


def remote_cnot_circuit() -> Circuit:
    c = Circuit(num_qubits=2)
    c.add_gate("H", [0])  # control in superposition; target |0>
    c.add_gate("CX", [0, 1])  # remote across node_0/node_1
    return c


def run_noisy(circuit, seed, protocol="single_ebit", f=0.7, **kw):
    cfg = DistributedConfig(
        seed=seed, protocol=protocol,
        qubit_to_node={q: f"node_{q}" for q in range(circuit.num_qubits)},
        ebit_noise="fixed", ebit_noise_fidelity=f, **kw,
    )
    return DistributedExecutor(cfg).execute(circuit)


def reduced_matrix(result) -> np.ndarray:
    m = result.output_state["reduced_density_matrix"]
    return np.array([[complex(a, b) for a, b in row] for row in m])


def average_reduced_state(f, protocol, seeds, circuit=None):
    circuit = circuit or remote_cnot_circuit()
    acc = np.zeros((4, 4), dtype=complex)
    for s in seeds:
        r = run_noisy(circuit, s, protocol=protocol, f=f, include_reduced_state=True)
        assert r.status == "success", r.errors
        acc += reduced_matrix(r)
    return acc / len(seeds)


def analytic_reference(rho_in, f, protocol):
    """Derived Pauli-channel reference (see module docstring)."""
    weights = werner_pauli_weights(f)
    out = np.zeros_like(rho_in)

    def pauli_step(rho, name):
        P = np.kron(PAULIS[name], I2)
        return P @ rho @ P.conj().T

    if protocol == "single_ebit":
        for p, name in weights:
            mid = pauli_step(rho_in, name)
            out += p * CNOT2 @ mid @ CNOT2.conj().T
        return out
    if protocol == "double_teleport":
        for p1, n1 in weights:
            mid = CNOT2 @ pauli_step(rho_in, n1) @ CNOT2.conj().T
            for p2, n2 in weights:
                out += p1 * p2 * pauli_step(mid, n2)
        return out
    raise ValueError(protocol)


# ---------------------------------------------------------------------------
# Level 1: trajectory sampling
# ---------------------------------------------------------------------------

class TestSampling:
    def test_sample_statistics_match_werner_mixture(self):
        rng = np.random.default_rng(123)
        f = 0.7
        draws = [sample_ebit_pauli_error(f, rng) for _ in range(30000)]
        for expected_p, name in werner_pauli_weights(f):
            freq = draws.count(name) / len(draws)
            # sigma = sqrt(p(1-p)/N) ~ 0.0026; 6 sigma bound.
            assert abs(freq - expected_p) < 6 * (expected_p * (1 - expected_p) / 30000) ** 0.5 + 1e-9, name

    def test_F1_returns_ideal_without_drawing(self):
        class CountingRng:
            def __init__(self):
                self.draws = 0

            def random(self):
                self.draws += 1
                return 0.999

        rng = CountingRng()
        assert sample_ebit_pauli_error(1.0, rng) == "I"
        assert rng.draws == 0

    def test_invalid_fidelity_rejected(self):
        with pytest.raises(ValueError):
            sample_ebit_pauli_error(1.5, np.random.default_rng(0))
        with pytest.raises(ValueError):
            sample_ebit_pauli_error(-0.1, np.random.default_rng(0))


# ---------------------------------------------------------------------------
# Level 2: protocol expansion
# ---------------------------------------------------------------------------

class TestExpansion:
    _UNSET = object()

    @staticmethod
    def _expand(protocol, fidelity, rng=_UNSET):
        ancillas = iter(range(10, 100))
        clbits = iter(range(5, 50))
        return expand_remote_cnot(
            0, 1, "node_0", "node_1", protocol,
            lambda: next(ancillas), lambda: next(clbits),
            ebit_noise_fidelity=fidelity,
            ebit_noise_rng=np.random.default_rng(0) if rng is TestExpansion._UNSET else rng,
        )

    def test_ideal_and_F1_expansions_are_identical(self):
        for protocol in ("single_ebit", "double_teleport"):
            ideal = self._expand(protocol, None)
            f1 = self._expand(protocol, 1.0)
            assert [o.to_dict() for o in ideal.operations] == [o.to_dict() for o in f1.operations]
            assert f1.ebit_noise == []

    def test_noise_inserts_one_unconditioned_pauli_per_ebit(self):
        exp = self._expand("single_ebit", 0.5, np.random.default_rng(7))
        gates = [(o.gate, o.condition) for o in exp.operations]
        # Only UNCONDITIONED X/Y/Z gates count as noise: the protocol's
        # classical corrections are also X/Z but clbit-conditioned (AD-004).
        noise_ops = [g for g in gates if g[1] is None and g[0] in ("X", "Y", "Z")]
        assert len(exp.ebit_noise) == 1
        assert len(noise_ops) == 1
        assert noise_ops[0][1] is None  # unconditioned, correction logic untouched
        # The error sits after ebit prep (H, CX) and before the Bell measurement.
        first_two = gates[:2]
        assert [g[0] for g in first_two] == ["H", "CX"]
        assert noise_ops[0] == gates[2]

    def test_double_teleport_draws_two_components(self):
        exp = self._expand("double_teleport", 0.5, np.random.default_rng(3))
        assert len(exp.ebit_noise) == 2

    def test_noise_without_rng_rejected(self):
        with pytest.raises(ValueError):
            self._expand("single_ebit", 0.5, rng=None)


# ---------------------------------------------------------------------------
# Level 4: executor
# ---------------------------------------------------------------------------

class TestExecutorF1Regression:
    def test_F1_matches_ideal_exactly(self):
        circuit = remote_cnot_circuit()
        ideal = run_noisy(circuit, 42, f=1.0)
        cfg = DistributedConfig(
            seed=42, qubit_to_node={0: "node_0", 1: "node_1"})
        reference = DistributedExecutor(cfg).execute(circuit)
        assert reference.status == ideal.status == "success"
        assert ideal.output_state["probabilities"] == reference.output_state["probabilities"]
        assert ideal.equivalence["fidelity"] == 1.0 and ideal.equivalence["passed"]
        assert ideal.remote_operations[0].ebit_fidelity_applied == 1.0
        assert ideal.remote_operations[0].ebit_noise == []

    def test_legacy_default_stays_ideal(self):
        circuit = remote_cnot_circuit()
        cfg = DistributedConfig(seed=42, qubit_to_node={0: "node_0", 1: "node_1"})
        r = DistributedExecutor(cfg).execute(circuit)
        rop = r.remote_operations[0]
        assert rop.ebit_noise is None
        assert rop.ebit_fidelity_applied is None
        assert r.reproducibility["ebit_noise"] == "ideal"
        assert all("Werner" not in note for note in r.notes)


class TestExecutorNoisyBehaviour:
    def test_basis_input_probabilities_follow_werner_mixture(self):
        """Input |10>: ideal CNOT -> |11>. Werner error on the control maps
        I,Z -> |11> (F + (1-F)/3) and X,Y -> |00> (2(1-F)/3)."""
        f = 0.7
        circuit = Circuit(num_qubits=2)
        circuit.add_gate("X", [0])
        circuit.add_gate("CX", [0, 1])
        p11 = f + (1 - f) / 3.0
        p00 = 2 * (1 - f) / 3.0
        seeds = range(1000, 1200)
        acc = {"11": 0.0, "00": 0.0}
        for s in seeds:
            r = run_noisy(circuit, s, f=f)
            assert r.status == "success", r.errors
            probs = r.output_state["probabilities"]
            assert set(probs) <= {"00", "11"}, probs  # pure component, no mixture
            for k in acc:
                acc[k] += probs.get(k, 0.0)
        n = len(seeds)
        assert abs(acc["11"] / n - p11) < 0.05
        assert abs(acc["00"] / n - p00) < 0.05

    @pytest.mark.parametrize("protocol", ["single_ebit", "double_teleport"])
    @pytest.mark.parametrize("f", [0.6, 0.85])
    def test_superposition_matches_analytic_reference(self, protocol, f):
        seeds = range(2000, 2300)
        avg = average_reduced_state(f, protocol, seeds)
        h = np.kron(H1, I2)
        psi = h @ np.array([1, 0, 0, 0], dtype=complex)
        rho_in = np.outer(psi, psi.conj())
        ref = analytic_reference(rho_in, f, protocol)
        d = DensityMatrix(avg, 2)
        r = DensityMatrix(ref, 2)
        assert d.fidelity_with(r) > 0.98
        assert trace_distance(d, r) < 0.06

    def test_multiple_remote_ops_degrade_and_record_noise(self):
        """GHZ chain H(0), CX(0,1), CX(0,2) across three nodes: two remote
        CNOTs, each with its own sampled Werner component."""
        circuit = Circuit(num_qubits=3)
        circuit.add_gate("H", [0])
        circuit.add_gate("CX", [0, 1])
        circuit.add_gate("CX", [0, 2])
        cfg = DistributedConfig(
            seed=99, qubit_to_node={0: "node_0", 1: "node_1", 2: "node_2"},
            ebit_noise="fixed", ebit_noise_fidelity=0.6,
        )
        r = DistributedExecutor(cfg).execute(circuit)
        assert r.status == "success", r.errors
        assert len(r.remote_operations) == 2
        for rop in r.remote_operations:
            assert rop.executed
            assert rop.ebit_fidelity_applied == 0.6
            assert len(rop.ebit_noise) == 1
            assert rop.ebit_noise[0] in ("I", "X", "Y", "Z")
        assert r.equivalence["fidelity"] < 0.95
        assert "ebit_noise" in r.reproducibility

    def test_noisy_reproducibility_same_seed(self):
        circuit = remote_cnot_circuit()
        a = run_noisy(circuit, 77, f=0.5)
        b = run_noisy(circuit, 77, f=0.5)
        assert a.output_state["probabilities"] == b.output_state["probabilities"]
        assert a.remote_operations[0].ebit_noise == b.remote_operations[0].ebit_noise

    def test_different_seed_changes_realization(self):
        # Deterministic given fixed seeds: this pair realizes different
        # components for a two-ebit double-teleport run at F=0.5.
        circuit = remote_cnot_circuit()
        a = run_noisy(circuit, 1, protocol="double_teleport", f=0.5)
        b = run_noisy(circuit, 2, protocol="double_teleport", f=0.5)
        assert a.remote_operations[0].ebit_noise != b.remote_operations[0].ebit_noise

    def test_noisy_result_degrades_below_ideal(self):
        """Statistical trend (not per-sample monotonicity): the average
        equivalence fidelity drops as the ebit fidelity drops."""
        circuit = remote_cnot_circuit()
        seeds = range(3000, 3100)
        for f in (1.0, 0.9, 0.7):
            vals = [run_noisy(circuit, s, f=f).equivalence["fidelity"] for s in seeds]
            assert np.mean(vals) < 1.0 + 1e-12
            if f == 1.0:
                assert np.mean(vals) > 0.999999
            elif f == 0.9:
                assert 0.85 < np.mean(vals) < 0.999
            else:
                assert np.mean(vals) < 0.9

    def test_network_fidelity_mode_consumes_grant_fidelity(self):
        topology = topology_from_nodes_links(
            nodes=[{"name": "node_0"}, {"name": "node_1"}],
            links=[{"source": "node_0", "destination": "node_1",
                    "distance_km": 0, "base_fidelity": 0.8}],
        )
        circuit = remote_cnot_circuit()
        cfg = DistributedConfig(
            seed=5, qubit_to_node={0: "node_0", 1: "node_1"},
            topology=topology, ebit_noise="network_fidelity",
        )
        r = DistributedExecutor(cfg).execute(circuit)
        assert r.status == "success", r.errors
        rop = r.remote_operations[0]
        grant = r.entanglement_operations[0]
        assert grant.success and grant.fidelity == pytest.approx(0.8)
        assert rop.ebit_fidelity == pytest.approx(0.8)
        assert rop.ebit_fidelity_applied == pytest.approx(0.8)
        assert len(rop.ebit_noise) == 1
        assert r.reproducibility["ebit_noise"] == "network_fidelity"
        # A single trajectory may realize the ideal component (probability F),
        # so aggregate over seeds: applied fidelity must actually degrade the
        # state for at least one realization, and on average overall.
        import dataclasses

        fids = []
        saw_noise = False
        for s in range(5, 25):
            rs = DistributedExecutor(dataclasses.replace(cfg, seed=s)).execute(circuit)
            assert rs.status == "success"
            fids.append(rs.equivalence["fidelity"])
            if rs.remote_operations[0].ebit_noise != ["I"]:
                saw_noise = True
        assert saw_noise
        assert np.mean(fids) < 1.0  # noise actually reached the state

    def test_network_fidelity_without_topology_is_ideal(self):
        circuit = remote_cnot_circuit()
        cfg = DistributedConfig(
            seed=5, qubit_to_node={0: "node_0", 1: "node_1"},
            ebit_noise="network_fidelity",
        )
        r = DistributedExecutor(cfg).execute(circuit)
        assert r.status == "success"
        # Ideal grant (F=1) degenerates to the ideal path, explicitly recorded.
        assert r.remote_operations[0].ebit_fidelity_applied == 1.0
        assert r.remote_operations[0].ebit_noise == []

    def test_bad_resource_executes_missing_resource_fails(self):
        """A low-fidelity grant is a legitimate resource; a missing link is
        not. The two must behave differently (directive §55)."""
        bad_topo = topology_from_nodes_links(
            nodes=[{"name": "node_0"}, {"name": "node_1"}],
            links=[{"source": "node_0", "destination": "node_1",
                    "distance_km": 0, "base_fidelity": 0.6}],
        )
        circuit = remote_cnot_circuit()
        cfg = DistributedConfig(
            seed=3, qubit_to_node={0: "node_0", 1: "node_1"},
            topology=bad_topo, ebit_noise="network_fidelity",
        )
        r = DistributedExecutor(cfg).execute(circuit)
        assert r.status == "success"
        assert r.remote_operations[0].ebit_fidelity_applied == pytest.approx(0.6)

        disconnected = topology_from_nodes_links(
            nodes=[{"name": "node_0"}, {"name": "node_1"}], links=[],
        )
        cfg = DistributedConfig(
            seed=3, qubit_to_node={0: "node_0", 1: "node_1"},
            topology=disconnected, ebit_noise="network_fidelity",
        )
        r = DistributedExecutor(cfg).execute(circuit)
        assert r.status == "failed"
        assert any("entanglement" in e.lower() for e in r.errors)


class TestExecutorConfigErrors:
    def test_unknown_noise_mode_fails(self):
        with pytest.raises(ValueError, match="ebit_noise"):
            DistributedConfig(
                seed=1, qubit_to_node={0: "node_0", 1: "node_1"}, ebit_noise="bogus",
            )

    def test_fixed_mode_requires_fidelity(self):
        circuit = remote_cnot_circuit()
        cfg = DistributedConfig(
            seed=1, qubit_to_node={0: "node_0", 1: "node_1"}, ebit_noise="fixed",
        )
        r = DistributedExecutor(cfg).execute(circuit)
        assert r.status == "failed"

    @pytest.mark.parametrize("bad", [1.5, -0.2])
    def test_fixed_mode_fidelity_range(self, bad):
        with pytest.raises(ValueError):
            DistributedConfig(
                seed=1, qubit_to_node={0: "node_0", 1: "node_1"},
                ebit_noise="fixed", ebit_noise_fidelity=bad,
            )

    def test_reduced_state_guard(self):
        circuit = Circuit(num_qubits=7)
        circuit.add_gate("H", [0])
        for q in range(1, 7):
            circuit.add_gate("CX", [0, q])
        cfg = DistributedConfig(
            seed=1,
            qubit_to_node={q: f"node_{min(q, 1)}" for q in range(7)},
            ebit_noise="fixed", ebit_noise_fidelity=0.9,
            include_reduced_state=True,
        )
        r = DistributedExecutor(cfg).execute(circuit)
        assert r.status == "failed"
        assert any("include_reduced_state" in e for e in r.errors)


# ---------------------------------------------------------------------------
# Level 3: network-model interaction
# ---------------------------------------------------------------------------

def line(topology_nodes_links):
    return topology_from_nodes_links(*topology_nodes_links)


class TestNetworkModelInteraction:
    def _run(self, topology, seed, coherence_ns=None, protocol="single_ebit"):
        net_cfg = NetworkConfig(memory_coherence_ns=coherence_ns) if coherence_ns else None
        cfg = DistributedConfig(
            seed=seed, protocol=protocol,
            qubit_to_node={0: "A", 1: "B"},
            topology=topology, network_config=net_cfg,
            ebit_noise="network_fidelity",
        )
        r = DistributedExecutor(cfg).execute(remote_cnot_circuit())
        assert r.status == "success", (r.status, r.errors)
        return r

    def test_direct_link_fidelity_reaches_protocol(self):
        topo = topology_from_nodes_links(
            nodes=[{"name": "A"}, {"name": "B"}],
            links=[{"source": "A", "destination": "B",
                    "distance_km": 0, "base_fidelity": 0.95}],
        )
        r = self._run(topo, seed=11)
        grant = r.entanglement_operations[0]
        assert grant.success
        assert r.remote_operations[0].ebit_fidelity_applied == pytest.approx(grant.fidelity)
        assert grant.fidelity == pytest.approx(0.95)  # lossless single segment

    def test_multihop_swap_lowers_grant_fidelity(self):
        topo = topology_from_nodes_links(
            nodes=[{"name": "A"}, {"name": "R"}, {"name": "B"}],
            links=[
                {"source": "A", "destination": "R", "distance_km": 0, "base_fidelity": 0.95},
                {"source": "R", "destination": "B", "distance_km": 0, "base_fidelity": 0.95},
            ],
        )
        cfg = DistributedConfig(
            seed=11, qubit_to_node={0: "A", 1: "B"},
            topology=topo, ebit_noise="network_fidelity",
        )
        r = DistributedExecutor(cfg).execute(remote_cnot_circuit())
        assert r.status == "success", r.errors
        grant = r.entanglement_operations[0]
        assert grant.success
        # Werner-parameter multiplication: swap(0.95, 0.95) < 0.95.
        assert grant.fidelity < 0.95
        assert r.remote_operations[0].ebit_fidelity_applied == pytest.approx(grant.fidelity)
        # Aggregate over seeds: a single trajectory may realize the ideal
        # component (probability = grant fidelity), so require the average.
        import dataclasses

        fids = [r.equivalence["fidelity"]]
        for s in range(12, 32):
            rs = DistributedExecutor(
                dataclasses.replace(cfg, seed=s)).execute(remote_cnot_circuit())
            assert rs.status == "success", rs.errors
            fids.append(rs.equivalence["fidelity"])
        assert np.mean(fids) < 1.0

    def test_memory_decay_is_not_part_of_the_grant_model(self):
        """Documented engine boundary (LIMITATIONS): NetworkEngine reports the
        granted fidelity via the analytic link-base swap model
        (expected_end_to_end_fidelity); memory aging affects internal swap
        bookkeeping but NOT the reported grant fidelity for a request. The
        distributed protocol consumes exactly what the grant reports — this
        test pins that contract so a future engine change that adds decay to
        grants will surface here and flow through automatically.
        """
        nodes = [{"name": "A"}, {"name": "R"}, {"name": "B"}]
        links = [
            {"source": "A", "destination": "R", "distance_km": 1, "base_fidelity": 0.95},
            {"source": "R", "destination": "B", "distance_km": 0, "base_fidelity": 0.95},
        ]

        def grant_fid(coherence_ns):
            topo = topology_from_nodes_links(nodes=nodes, links=links)
            cfg = DistributedConfig(
                seed=23, qubit_to_node={0: "A", 1: "B"},
                topology=topo,
                network_config=NetworkConfig(memory_coherence_ns=coherence_ns),
                ebit_noise="network_fidelity",
            )
            r = DistributedExecutor(cfg).execute(remote_cnot_circuit())
            assert r.status == "success", r.errors
            grant = r.entanglement_operations[0]
            assert grant.success, grant.failure_reason
            assert r.remote_operations[0].ebit_fidelity_applied == pytest.approx(grant.fidelity)
            return grant.fidelity

        assert grant_fid(1_000_000_000.0) == grant_fid(20_000.0)

    def test_purification_config_consistency(self):
        """BBPSSW/DEJMPS purification is configured on the network engine, but
        the bridge's single-pair grant path cannot trigger a purification
        round (one in-flight chain per segment). The honest contract here:
        the config is accepted, the grant is a plain unpurified pair, and the
        noisy protocol consumes exactly its fidelity (documented limitation).
        """
        topo = topology_from_nodes_links(
            nodes=[{"name": "A"}, {"name": "B"}],
            links=[{"source": "A", "destination": "B",
                    "distance_km": 0, "base_fidelity": 0.7}],
        )
        cfg = DistributedConfig(
            seed=9, qubit_to_node={0: "A", 1: "B"}, topology=topo,
            network_config=NetworkConfig(purification_protocol="DEJMPS"),
            ebit_noise="network_fidelity",
        )
        r = DistributedExecutor(cfg).execute(remote_cnot_circuit())
        assert r.status == "success", r.errors
        grant = r.entanglement_operations[0]
        assert grant.success and grant.fidelity == pytest.approx(0.7)
        assert r.remote_operations[0].ebit_fidelity_applied == pytest.approx(0.7)
        # Resource accounting unchanged: one ebit for single_ebit.
        assert r.ebit_consumption == 1
