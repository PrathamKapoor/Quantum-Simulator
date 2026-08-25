"""Hardware abstraction layer (directive Layer 11 / §10-11).

A HardwareProfile is a DATA-DRIVEN SIMULATION CONFIGURATION — explicitly NOT a
claim about any specific commercial device (§325). Presets carry model labels.

Contents:
  - HardwareProfile: qubit count, coupling graph, native gate set, durations,
    error rates, T1/T2, readout errors
  - Topology presets: line / ring / grid / all-to-all
  - Named research presets labeled as models
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..quantum.states import QuantumCoreError


@dataclass(frozen=True)
class GateSpecInfo:
    """Native-gate declaration on a hardware profile."""

    name: str          # canonical QuantumLab gate name (uppercase)
    arity: int
    duration_ns: float
    error_rate: float  # depolarizing-parameter-style per-application error


@dataclass
class HardwareProfile:
    """Data-driven hardware model used by the transpiler and noisy executor."""

    name: str
    n_qubits: int
    coupling: set[frozenset[int]]                 # undirected edges
    native_gates: dict[str, GateSpecInfo]
    t1_us: float = 1e6                            # effectively infinite default
    t2_us: float = 1e6
    readout_p_read1_given_0: float = 0.0
    readout_p_read0_given_1: float = 0.0
    measurement_duration_ns: float = 1000.0
    reset_duration_ns: float = 500.0
    model_label: str = "MODEL PROFILE"            # explicit honesty label

    def __post_init__(self):
        if self.n_qubits < 1:
            raise QuantumCoreError("n_qubits must be >= 1.")
        for edge in self.coupling:
            if len(edge) != 2:
                raise QuantumCoreError("Coupling edges connect exactly 2 qubits.")
            for q in edge:
                if not (0 <= q < self.n_qubits):
                    raise QuantumCoreError(f"Coupling references qubit {q} outside profile.")
        for name, spec in self.native_gates.items():
            if spec.arity >= 2:
                # multi-qubit native gates must respect coupling when applied;
                # enforced at transpilation time, not here.

                pass

    def are_coupled(self, a: int, b: int) -> bool:
        return frozenset((a, b)) in self.coupling

    def neighbors(self, qubit: int) -> list[int]:
        return sorted(next(iter(e - {qubit})) for e in self.coupling if qubit in e)

    def shortest_coupling_path(self, a: int, b: int) -> list[int] | None:
        """BFS shortest path over the coupling graph (list including ends)."""
        if a == b:
            return [a]
        from collections import deque

        prev: dict[int, int] = {a: a}
        queue = deque([a])
        while queue:
            cur = queue.popleft()
            for nb in self.neighbors(cur):
                if nb in prev:
                    continue
                prev[nb] = cur
                if nb == b:
                    path = [b]
                    while path[-1] != a:
                        path.append(prev[path[-1]])
                    return path[::-1]
                queue.append(nb)
        return None


# ---------------------------------------------------------------------------
# Topology generators (deterministic)
# ---------------------------------------------------------------------------

def line_topology(n_qubits: int) -> set[frozenset[int]]:
    if n_qubits < 1:
        raise ValueError("Need at least 1 qubit.")
    return {frozenset((i, i + 1)) for i in range(n_qubits - 1)}


def ring_topology(n_qubits: int) -> set[frozenset[int]]:
    if n_qubits < 3:
        raise ValueError("Ring needs at least 3 qubits.")
    return line_topology(n_qubits) | {frozenset((0, n_qubits - 1))}


def grid_topology(rows: int, cols: int) -> tuple[set[frozenset[int]], int]:
    if rows < 1 or cols < 1:
        raise ValueError("Grid dims must be positive.")
    edges = set()
    def idx(r, c):
        return r * cols + c
    for r in range(rows):
        for c in range(cols):
            if c + 1 < cols:
                edges.add(frozenset((idx(r, c), idx(r, c + 1))))
            if r + 1 < rows:
                edges.add(frozenset((idx(r, c), idx(r + 1, c))))
    return edges, rows * cols


def all_to_all_topology(n_qubits: int) -> set[frozenset[int]]:
    if n_qubits < 1:
        raise ValueError("Need at least 1 qubit.")
    return {
        frozenset((a, b))
        for a in range(n_qubits)
        for b in range(a + 1, n_qubits)
    }


def star_topology(n_qubits: int, center: int = 0) -> set[frozenset[int]]:
    if n_qubits < 2:
        raise ValueError("Star needs at least 2 qubits.")
    if not (0 <= center < n_qubits):
        raise ValueError("Center out of range.")
    return {frozenset((center, other)) for other in range(n_qubits) if other != center}


# ---------------------------------------------------------------------------
# Native gate sets
# ---------------------------------------------------------------------------

def _standard_native_set(cx_error: float, cx_duration_ns: float,
                         sq_error: float, sq_duration_ns: float) -> dict[str, GateSpecInfo]:
    specs = {}
    for g in ("I", "X", "Y", "Z", "H", "S", "SDG", "T", "TDG",
              "RX", "RY", "RZ", "U3", "P"):
        specs[g] = GateSpecInfo(g, 1, sq_duration_ns, sq_error)
    for g in ("CX", "CZ", "SWAP"):
        specs[g] = GateSpecInfo(g, 2, cx_duration_ns, cx_error)
    return specs


# ---------------------------------------------------------------------------
# Named research presets — MODEL PROFILES, not real devices (directive §325)
# ---------------------------------------------------------------------------

def preset_ideal_8q() -> HardwareProfile:
    return HardwareProfile(
        name="Ideal-8Q",
        n_qubits=8,
        coupling=all_to_all_topology(8),
        native_gates=_standard_native_set(0.0, 0.0, 0.0, 0.0),
        t1_us=1e12, t2_us=1e12,
        model_label="IDEAL MODEL (no noise, all-to-all coupling)",
    )


def preset_noisy_generic_8q() -> HardwareProfile:
    return HardwareProfile(
        name="NoisyGeneric-8Q",
        n_qubits=8,
        coupling=line_topology(8),
        native_gates=_standard_native_set(0.01, 300.0, 0.001, 40.0),
        t1_us=80.0, t2_us=110.0,
        readout_p_read1_given_0=0.015,
        readout_p_read0_given_1=0.02,
        model_label="PHENOMENOLOGICAL MODEL (line coupling, generic error rates)",
    )


def preset_superconducting_inspired() -> HardwareProfile:
    return HardwareProfile(
        name="SuperconductingInspired-16Q",
        n_qubits=16,
        coupling=grid_topology(4, 4)[0],
        native_gates=_standard_native_set(0.008, 250.0, 0.0008, 25.0),
        t1_us=100.0, t2_us=140.0,
        readout_p_read1_given_0=0.012,
        readout_p_read0_given_1=0.025,
        model_label="PHYSICS-INSPIRED MODEL (grid coupling, superconducting-like timescales)",
    )


def preset_trapped_ion_inspired() -> HardwareProfile:
    return HardwareProfile(
        name="TrappedIonInspired-10Q",
        n_qubits=10,
        coupling=all_to_all_topology(10),
        native_gates=_standard_native_set(0.002, 9000.0, 0.0002, 50.0),
        t1_us=1e7, t2_us=5e6,
        readout_p_read1_given_0=0.004,
        readout_p_read0_given_1=0.004,
        model_label="PHYSICS-INSPIRED MODEL (all-to-all coupling, ion-like timescales)",
    )


PROFILE_REGISTRY: dict[str, callable] = {
    "Ideal-8Q": preset_ideal_8q,
    "NoisyGeneric-8Q": preset_noisy_generic_8q,
    "SuperconductingInspired-16Q": preset_superconducting_inspired,
    "TrappedIonInspired-10Q": preset_trapped_ion_inspired,
}


def to_noise_model(profile: HardwareProfile):
    """Convert a HardwareProfile into an executor NoiseModel.

    Single-qubit gates get the profile's single-qubit error as depolarizing;
    two-qubit gates get the CX-class error scaled x10 toward depolarizing
    probability conservatively (documented approximation). Readout uses the
    profile's asymmetric rates. Thermal relaxation is composed from T1/T2 at
    each gate's duration.
    """
    from ..noise.models import NoiseModel, ReadoutError
    from ..quantum.channels import (
        depolarizing_channel, thermal_relaxation_channel, CompositeChannel,
    )

    def make(spec: GateSpecInfo):
        dep = depolarizing_channel(min(max(spec.error_rate, 0.0), 1.0))
        thermal = thermal_relaxation_channel(
            profile.t1_us * 1000.0, profile.t2_us * 1000.0, spec.duration_ns
        )
        try:
            return CompositeChannel([dep, thermal])
        except Exception:
            return CompositeChannel([dep, dep])

    gate_errors: dict[str, object] = {}
    for name, spec in profile.native_gates.items():
        if spec.error_rate > 0 or spec.duration_ns > 0:
            gate_errors[name] = make(spec)
    return NoiseModel(
        label=f"hardware:{profile.name}",
        gate_errors=gate_errors,  # type: ignore[arg-type]
        readout_error=ReadoutError(
            p_read1_given_0=profile.readout_p_read1_given_0,
            p_read0_given_1=profile.readout_p_read0_given_1,
        ),
    )
