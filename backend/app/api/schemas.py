"""Pydantic schemas: explicit request/response models (directive §284-286)."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class ErrorDetail(BaseModel):
    code: str
    message: str
    field: Optional[str] = None
    suggestion: Optional[str] = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


# ---------------- circuits ----------------

class CircuitExecuteRequest(BaseModel):
    circuit: dict = Field(..., description="quantumlab.circuit v1 document")
    shots: int | None = Field(default=None, ge=0, le=10_000_000)
    mode: Literal["statevector", "density_matrix"] = "statevector"
    seed: int | None = None
    noise_config: dict | None = None

    @field_validator("circuit")
    @classmethod
    def _check_schema(cls, v: dict) -> dict:
        if not isinstance(v, dict) or v.get("schema") != "quantumlab.circuit":
            raise ValueError('circuit document must declare schema "quantumlab.circuit"')
        return v


class ValidateCircuitRequest(BaseModel):
    circuit: dict


# ---------------- algorithms ----------------

class GroverRequest(BaseModel):
    n_qubits: int = Field(default=4, ge=1, le=10)
    marked_index: int = Field(default=0, ge=0)
    shots: int = Field(default=1024, ge=1, le=1_000_000)
    seed: int = 17

    @field_validator("marked_index")
    @classmethod
    def _range(cls, v, info):
        n = info.data.get("n_qubits", 4)
        if v >= (1 << n):
            raise ValueError(f"marked_index must be < 2^{n}")
        return v


class BvRequest(BaseModel):
    secret: str = Field(..., pattern=r"^[01]{1,12}$")


class QftRequest(BaseModel):
    n_qubits: int = Field(default=3, ge=1, le=8)
    inverse: bool = False
    cutoff_exponent: int | None = Field(default=None, ge=1)


class DeutschJozsaRequest(BaseModel):
    kind: Literal["constant", "balanced"] = "balanced"
    n_qubits: int = Field(default=3, ge=1, le=6)
    seed: int = 0


class SuperdenseRequest(BaseModel):
    bits: str = Field(..., pattern=r"^[01]{2}$")
    shots: int = Field(default=256, ge=1)
    seed: int = 0


class OrderFindingRequest(BaseModel):
    a: int = Field(default=7, ge=2)
    N: int = Field(default=15, ge=3, le=32)

    @field_validator("N")
    @classmethod
    def _odd(cls, v):
        if v % 2 == 0:
            raise ValueError("N must be odd for order finding demo")
        return v


class QuantumWalkRequest(BaseModel):
    n_position_qubits: int = Field(default=4, ge=2, le=8)
    steps: int = Field(default=5, ge=1, le=64)


# ---------------- protocols ----------------

class BB84Request(BaseModel):
    n_qubits: int = Field(default=256, ge=8, le=100_000)
    eve_intercept_probability: float = Field(default=0.0, ge=0, le=1)
    sample_fraction: float = Field(default=0.5, gt=0, le=1)
    seed: int = 0


class E91Request(BaseModel):
    n_pairs: int = Field(default=2000, ge=100, le=200_000)
    noise_correlation_factor: float = Field(default=1.0, ge=0, le=1)
    seed: int = 0


class CHSHRequest(BaseModel):
    state_fidelity: float = Field(default=1.0, ge=0.25, le=1)
    shots_per_setting: int = Field(default=2000, ge=100, le=500_000)
    seed: int = 0


class QRNGRequest(BaseModel):
    n_bits: int = Field(default=1024, ge=16, le=10_000_000)
    seed: int = 0


# ---------------- QEC ----------------

class QECSweepRequest(BaseModel):
    code: str
    physical_error_rates: list[float] = Field(default_factory=lambda: [0.001, 0.005, 0.01, 0.05])
    trials: int = Field(default=2000, ge=100, le=1_000_000)
    seed: int = 42

    @field_validator("physical_error_rates")
    @classmethod
    def _rates(cls, v):
        if not v or any(not (0 <= p <= 1) for p in v):
            raise ValueError("Rates must be non-empty with values within [0,1].")
        if len(v) > 24:
            raise ValueError("At most 24 sweep points per request.")
        return [float(p) for p in v]


class SurfaceCodeRequest(BaseModel):
    d: int = Field(default=3, ge=2, le=6)
    physical_error_rate: float = Field(default=0.01, ge=0, le=1)
    trials: int = Field(default=3000, ge=100, le=1_000_000)
    seed: int = 5


# ---------------- network ----------------

class NetworkNodeIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    type: Literal["end", "repeater", "router", "satellite", "measurement_station"] = "repeater"
    memory_slots: int = Field(default=4, ge=0, le=256)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class NetworkLinkIn(BaseModel):
    source: str
    destination: str
    distance_km: float = Field(default=10, ge=0, le=20_000_000)
    base_fidelity: float = Field(default=0.99, ge=0.25, le=1)
    detector_efficiency: float = Field(default=1.0, gt=0, le=1)


class NetworkSimulateRequest(BaseModel):
    nodes: list[NetworkNodeIn] = Field(min_length=1, max_length=64)
    links: list[NetworkLinkIn] = Field(max_length=256)
    requests: list[dict] = Field(default_factory=list, max_length=64)
    routing_strategy: Literal[
        "shortest_path", "min_loss", "max_fidelity",
        "min_expected_time", "resource_aware",
    ] = "min_expected_time"
    scheduler_policy: Literal["fifo", "priority", "deadline"] = "fifo"
    swap_success_probability: float = Field(default=1.0, ge=0, le=1)
    classical_latency_mode: Literal["realistic", "idealized"] = "realistic"
    node_failure_rate_per_s: float = Field(default=0.0, ge=0, le=1e6)
    link_failure_rate_per_s: float = Field(default=0.0, ge=0, le=1e6)
    memory_coherence_ns: float = Field(default=1_000_000.0, gt=0)
    sim_time_ms: float = Field(default=500, gt=0, le=60_000)
    trace_mode: Literal["full", "summary", "sampled"] = "summary"
    seed: int = 7
    purification_protocol: Literal["BBPSSW", "DEJMPS"] | None = None


# ---------------- optimization ----------------

class VQERequest(BaseModel):
    system: Literal["h2", "tfim"] = "h2"
    bond_length_angstrom: float = Field(default=0.735, ge=0.2, le=2.05)
    n_qubits: int = Field(default=3, ge=2, le=6)
    max_iter: int = Field(default=150, ge=10, le=1000)
    seed: int = 0


class QAOARequest(BaseModel):
    edges: list[tuple[int, int]] = Field(min_length=1, max_length=40)
    n_nodes: int = Field(default=4, ge=2, le=12)
    p_layers: int = Field(default=2, ge=1, le=5)
    seed: int = 0

    @field_validator("edges")
    @classmethod
    def _nodes_in_range(cls, v, info):
        n = info.data.get("n_nodes", 4)
        for a, b in v:
            if not (0 <= a < n and 0 <= b < n) or a == b:
                raise ValueError(f"Edge ({a},{b}) invalid for {n} nodes.")
        return v


class H2CurveRequest(BaseModel):
    lengths: list[float] = Field(
        default_factory=lambda: [0.35, 0.5, 0.65, 0.735, 0.9, 1.1],
        min_length=2, max_length=12,
    )
    seed: int = 0


class QMLExperimentRequest(BaseModel):
    dataset: Literal["blobs", "circles", "iris"] = "blobs"
    max_iter: int = Field(default=80, ge=20, le=600)
    compare_noisy: bool = True
    seed: int = 0


# ---------------- experiments ----------------

class ExperimentCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    module: str
    config: dict = Field(default_factory=dict)
    sweep: list[dict] = Field(default_factory=list, max_length=6)
    backend: str = "statevector"
    noise_model: str | None = None
    seed: int = 0
    objective: str = ""
    hypothesis: str = ""
    description: str = ""


class RunActionRequest(BaseModel):
    run_ids: list[int] = Field(min_length=1, max_length=64)


# ---------------- distributed quantum computing ----------------

class DistributedTopologyIn(BaseModel):
    nodes: list[NetworkNodeIn] = Field(min_length=1, max_length=64)
    links: list[NetworkLinkIn] = Field(max_length=256)


class DistributedPartitionRequest(BaseModel):
    circuit: dict = Field(..., description="quantumlab.circuit v1 document")
    qubit_to_node: dict[int, str] | None = None
    num_nodes: int = Field(default=2, ge=2, le=16)
    node_names: list[str] | None = None
    objective: str = "minimize_cross_node"

    @field_validator("circuit")
    @classmethod
    def _check_schema(cls, v: dict) -> dict:
        if not isinstance(v, dict) or v.get("schema") != "quantumlab.circuit":
            raise ValueError('circuit document must declare schema "quantumlab.circuit"')
        return v


class DistributedSimulateRequest(BaseModel):
    circuit: dict = Field(..., description="quantumlab.circuit v1 document")
    protocol: Literal["single_ebit", "double_teleport"] = "single_ebit"
    seed: int | None = None
    qubit_to_node: dict[int, str] | None = None
    num_nodes: int = Field(default=2, ge=2, le=16)
    node_names: list[str] | None = None
    objective: str = "minimize_cross_node"
    topology: DistributedTopologyIn | None = None
    network_config: dict | None = None
    fallback: Literal["error", "centralized"] = "error"
    ebit_noise: Literal["ideal", "network_fidelity", "fixed"] = "ideal"
    ebit_noise_fidelity: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("circuit")
    @classmethod
    def _check_schema(cls, v: dict) -> dict:
        if not isinstance(v, dict) or v.get("schema") != "quantumlab.circuit":
            raise ValueError('circuit document must declare schema "quantumlab.circuit"')
        return v


class RemoteCNOTRequest(BaseModel):
    control_qubit: int = Field(ge=0, le=63)
    target_qubit: int = Field(ge=0, le=63)
    qubit_to_node: dict[int, str] | None = None
    protocol: Literal["single_ebit", "double_teleport"] = "single_ebit"
    seed: int | None = None
    topology: DistributedTopologyIn | None = None
    network_config: dict | None = None
    ebit_noise: Literal["ideal", "network_fidelity", "fixed"] = "ideal"
    ebit_noise_fidelity: float | None = Field(default=None, ge=0.0, le=1.0)
