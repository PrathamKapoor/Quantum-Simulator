"""Explicit, configurable noise models (directive §38-40, §261).

A NoiseModel is plain validated data: which error channel applies to which
gate, and what readout confusion to apply at measurement time. It never lives
inside circuit code. Gate errors are applied through the quantum channel
framework — fidelity is never hand-adjusted after simulation (§259).

Supported channel types:
    bit_flip(p), phase_flip(p), bit_phase_flip(p), depolarizing(p),
    amplitude_damping(gamma), phase_damping(gamma),
    thermal_relaxation(t1_ns, t2_ns, duration_ns)

Readout error uses asymmetric rates P(read 1|actual 0), P(read 0|actual 1).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..quantum.channels import (
    KrausChannel,
    bit_flip_channel,
    phase_flip_channel,
    bit_phase_flip_channel,
    depolarizing_channel,
    amplitude_damping_channel,
    phase_damping_channel,
    thermal_relaxation_channel,
)
from ..quantum.states import QuantumCoreError


@dataclass(frozen=True)
class ReadoutError:
    """Asymmetric classical readout confusion (directive §260)."""

    p_read1_given_0: float = 0.0
    p_read0_given_1: float = 0.0

    def __post_init__(self):
        for name, v in (("p_read1_given_0", self.p_read1_given_0), ("p_read0_given_1", self.p_read0_given_1)):
            if not (0.0 <= v <= 1.0):
                raise QuantumCoreError(f"Readout {name} must be within [0, 1], got {v}.")


def _build_channel(spec: dict) -> KrausChannel:
    """Construct a channel from a structured spec dict (no code evaluation)."""
    if not isinstance(spec, dict) or "type" not in spec:
        raise QuantumCoreError(f"Noise channel spec must be an object with 'type', got {spec!r}.")
    t = str(spec["type"]).lower()
    if t == "bit_flip":
        return bit_flip_channel(float(spec["probability"]))
    if t == "phase_flip":
        return phase_flip_channel(float(spec["probability"]))
    if t == "bit_phase_flip":
        return bit_phase_flip_channel(float(spec["probability"]))
    if t == "depolarizing":
        return depolarizing_channel(float(spec["probability"]))
    if t == "amplitude_damping":
        return amplitude_damping_channel(float(spec["gamma"]))
    if t == "phase_damping":
        return phase_damping_channel(float(spec["gamma"]))
    if t == "thermal_relaxation":
        return thermal_relaxation_channel(
            float(spec["t1_ns"]), float(spec["t2_ns"]), float(spec.get("duration_ns", 0.0))
        )
    raise QuantumCoreError(
        f"Unknown noise channel type {spec['type']!r}. Supported: bit_flip, phase_flip, "
        "bit_phase_flip, depolarizing, amplitude_damping, phase_damping, thermal_relaxation."
    )


@dataclass
class NoiseModel:
    """Data-driven noise specification.

    gate_errors maps a canonical gate name to a channel applied after each use
    of that gate. `default_gate_error` applies to any gate without a specific
    entry (used e.g. for hardware-inspired single-qubit vs CX error split).
    """

    label: str = "custom"
    gate_errors: dict[str, KrausChannel] = field(default_factory=dict)
    default_gate_error: KrausChannel | None = None
    two_qubit_default_error: KrausChannel | None = None
    readout_error: ReadoutError = field(default_factory=ReadoutError)

    def error_for(self, gate_name: str, n_qubits: int) -> KrausChannel | None:
        name = gate_name.upper()
        if name in self.gate_errors:
            return self.gate_errors[name]
        if n_qubits >= 2 and self.two_qubit_default_error is not None:
            return self.two_qubit_default_error
        return self.default_gate_error

    @property
    def is_noiseless(self) -> bool:
        return (
            not self.gate_errors
            and self.default_gate_error is None
            and self.two_qubit_default_error is None
            and self.readout_error.p_read1_given_0 == 0.0
            and self.readout_error.p_read0_given_1 == 0.0
        )

    # ---------- constructors ----------

    @classmethod
    def ideal(cls) -> "NoiseModel":
        return cls(label="ideal")

    @classmethod
    def from_config(cls, config: dict, *, label: str = "custom") -> "NoiseModel":
        """Build from validated JSON-style config (directive §39)."""
        if not isinstance(config, dict):
            raise QuantumCoreError("Noise config must be a JSON object.")
        model = cls(label=label)
        for gate_name, spec in (config.get("gate_errors") or {}).items():
            model.gate_errors[gate_name.upper()] = _build_channel(spec)
        if "default_gate_error" in config:
            model.default_gate_error = _build_channel(config["default_gate_error"])
        if "two_qubit_default_error" in config:
            model.two_qubit_default_error = _build_channel(config["two_qubit_default_error"])
        ro = config.get("readout_error")
        if ro:
            model.readout_error = ReadoutError(
                p_read1_given_0=float(ro.get("p_read1_given_0", 0.0)),
                p_read0_given_1=float(ro.get("p_read0_given_1", 0.0)),
            )
        return model

    def describe(self) -> dict:
        return {
            "label": self.label,
            "noiseless": self.is_noiseless,
            "gates_with_errors": sorted(self.gate_errors),
            "has_default_single_qubit_error": self.default_gate_error is not None,
            "has_default_two_qubit_error": self.two_qubit_default_error is not None,
            "readout": {
                "p_read1_given_0": self.readout_error.p_read1_given_0,
                "p_read0_given_1": self.readout_error.p_read0_given_1,
            },
        }


# Named presets (documented simulation configurations, NOT real devices — §325)


def preset_depolarizing_1q(p: float = 0.001) -> NoiseModel:
    return NoiseModel(
        label=f"depolarizing-{p}",
        default_gate_error=depolarizing_channel(p),
        two_qubit_default_error=depolarizing_channel(min(10 * p, 1.0)),
    )


def preset_thermal(t1_ns: float = 50_000.0, t2_ns: float = 70_000.0, gate_ns: float = 100.0) -> NoiseModel:
    ch = thermal_relaxation_channel(t1_ns, t2_ns, gate_ns)
    cx_ch = thermal_relaxation_channel(t1_ns, t2_ns, 4 * gate_ns)
    return NoiseModel(
        label=f"thermal-t1={t1_ns:.0f}ns-t2={t2_ns:.0f}ns",
        default_gate_error=ch,
        two_qubit_default_error=cx_ch,
        readout_error=ReadoutError(p_read1_given_0=0.01, p_read0_given_1=0.01),
    )
