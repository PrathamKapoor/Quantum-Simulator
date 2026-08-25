"""Circuit execution engines.

Modes (directive §162):
  - "statevector": exact pure-state evolution. With a noise model, per-shot
    quantum-trajectory (Monte Carlo wavefunction) sampling is used: after each
    noisy gate one Kraus operator K_i is sampled with probability ||K_i ψ||².
    Across many shots this reproduces the channel ensemble exactly.
  - "density_matrix": exact channel application Σ K ρ K†; measurement outcomes
    are sampled stochastically from the diagonal.

Mid-circuit measurement stores results in the classical register and later
operations may be conditioned on them (§28-29). Reset deterministically
projects target qubits to |0⟩.

Determinism: all randomness flows from a single seeded Generator; identical
(circuit, seed) pairs reproduce identical counts bit-for-bit (directive §147).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..quantum.states import StateVector, QuantumCoreError
from ..quantum.density import DensityMatrix
from ..quantum.apply import apply_gate_statevector
from ..quantum import measurement as meas
from ..quantum.channels import KrausChannel
from ..quantum.measurement import apply_readout_error
from .model import Circuit
from .validate import assert_valid, ValidationIssue
from ..noise.models import NoiseModel


@dataclass
class SimulationResult:
    """Outcome of one execution request.

    For `shots == None` (pure statevector mode): final_state is set.
    For shots >= 1: counts/probabilities are set; final_state holds the last
    shot's post-measurement state when trajectory semantics require it.
    """

    mode: str
    num_shots: int | None
    seed: int | None
    final_state: StateVector | None = None
    density_matrix: DensityMatrix | None = None
    counts: dict[str, int] = field(default_factory=dict)
    probabilities: dict[str, float] = field(default_factory=dict)
    classical_registers: list[list[int]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def most_likely_outcome(self) -> str | None:
        if not self.counts:
            return None
        return max(self.counts.items(), key=lambda kv: kv[1])[0]


class StatevectorEngine:
    """Exact statevector executor with optional stochastic noise trajectories."""

    name = "statevector"

    def run(
        self,
        circuit: Circuit,
        *,
        seed: int | None = None,
        noise_model: NoiseModel | None = None,
        initial_state: StateVector | None = None,
        shots: int | None = None,
    ) -> SimulationResult:
        issues = _check(circuit)
        if issues:
            raise ValueError("Circuit failed validation; see issues.")
        n = circuit.num_qubits
        if initial_state is not None:
            if initial_state.n_qubits != n:
                raise QuantumCoreError(
                    f"Initial state has {initial_state.n_qubits} qubits; circuit has {n}."
                )
            base = initial_state
        else:
            base = StateVector.zero(n)

        noise = noise_model or NoiseModel.ideal()
        fast_path_ok = (
            shots is not None
            and not circuit.has_mid_circuit_measurement()
            and not circuit.has_conditions()
            and not any(op.kind == "reset" for op in circuit.operations)
            and noise.is_noiseless
            and initial_state is None
        )
        # Fast path: evolve once, sample the final distribution multinomially.
        # Scientifically equivalent because unitary evolution commutes with the
        # final computational-basis measurement distribution.
        if fast_path_ok:
            state = self._evolve_unitary_only(base, circuit)
            rng = _rng(seed)
            counts = self._sample_final_measurements(state, circuit, rng, int(shots))
            return SimulationResult(
                mode=self.name,
                num_shots=shots,
                seed=seed,
                final_state=state,
                counts=_ordered_counts(counts),
                probabilities={k: v / shots for k, v in _ordered_counts(counts).items()},
            )

        total_shots = shots if shots is not None else 0
        counts: dict[str, int] = {}
        registers: list[list[int]] = []
        last_state: StateVector | None = base
        if total_shots == 0:
            # Pure evolution mode (shots=None).
            #
            # Semantics (documented): operations are applied in order; terminal
            # measurements (nothing but barriers after them) are recorded into
            # the classical register WITHOUT collapsing, so the returned
            # final_state remains the full pre-measurement state — this is what
            # state inspection wants. Circuits that USE measurement results
            # (any gate/reset after the first measure, or any condition) run as
            # a single collapsed trajectory instead.
            rng = _rng(seed)
            register = [0] * circuit.num_clbits
            collapse_needed = _uses_mid_circuit_results(circuit)
            last_state, register = self._run_single_shot(
                base, circuit, rng, noise, register,
                apply_readout=False, collapse=collapse_needed,
            )
            if circuit.num_clbits:
                registers.append(register)
            return SimulationResult(
                mode=self.name,
                num_shots=None,
                seed=seed,
                final_state=last_state,
                classical_registers=registers,
            )
        for shot in range(total_shots):
            rng = _rng(None if seed is None else seed + shot)
            state = base
            register = [0] * circuit.num_clbits
            state, register = self._run_single_shot(state, circuit, rng, noise, register)
            last_state = state
            key = "".join(str(b) for b in reversed(register)) if register else ""
            if not register:
                # No classical bits recorded: nothing to aggregate.
                continue
            counts[key] = counts.get(key, 0) + 1
            registers.append(register)
        return SimulationResult(
            mode=self.name,
            num_shots=total_shots,
            seed=seed,
            final_state=last_state,
            counts=_ordered_counts(counts),
            probabilities={k: v / total_shots for k, v in _ordered_counts(counts).items()},
            classical_registers=registers,
        )

    @staticmethod
    def _sample_final_measurements(
        state: StateVector, circuit: Circuit, rng: np.random.Generator, shots: int
    ) -> dict[str, int]:
        """Sample all terminal measurements exactly via one multinomial draw.

        Each measurement op maps its qubits to clbits; the full-register
        classical outcome per shot is drawn independently according to the
        exact final-state distribution restricted through those mappings.
        """
        idx = np.arange(state.dimension)
        key_int = np.zeros(state.dimension, dtype=np.int64)
        any_measure = False
        for op in circuit.operations:
            if op.kind != "measure":
                continue
            any_measure = True
            for k, qubit in enumerate(op.qubits):
                key_int |= ((idx >> qubit) & 1) << op.clbits[k]
        if not any_measure:
            return {}
        probs = np.abs(state.amplitudes) ** 2
        unique_keys, inverse = np.unique(key_int, return_inverse=True)
        agg = np.zeros(len(unique_keys))
        np.add.at(agg, inverse, probs)
        agg /= agg.sum()
        draws = rng.multinomial(shots, agg)
        m = max(circuit.num_clbits, 1)
        return {
            format(int(unique_keys[j]), f"0{m}b"): int(draws[j])
            for j in range(len(unique_keys))
            if draws[j] > 0
        }

    def _evolve_unitary_only(self, state: StateVector, circuit: Circuit) -> StateVector:
        amps = state.amplitudes
        for op in circuit.operations:
            if op.kind == "gate":
                spec = resolve_gate(circuit, op.gate, list(op.params))
                amps = apply_gate_statevector(amps, circuit.num_qubits, list(op.qubits), spec.matrix)
            elif op.kind in ("measure", "reset", "barrier"):
                continue
        return StateVector(amps, circuit.num_qubits)

    def _run_single_shot(
        self,
        state: StateVector,
        circuit: Circuit,
        rng: np.random.Generator,
        noise: NoiseModel,
        register: list[int],
        *,
        apply_readout: bool = True,
        collapse: bool = True,
    ) -> tuple[StateVector, list[int]]:
        for op in circuit.operations:
            if op.condition is not None:
                if register[op.condition.clbit] != op.condition.value:
                    continue
            if op.kind == "gate":
                spec = resolve_gate(circuit, op.gate, list(op.params))
                amps = apply_gate_statevector(state.amplitudes, circuit.num_qubits, list(op.qubits), spec.matrix)
                state = StateVector(amps, circuit.num_qubits)
                channel = noise.error_for(spec.name, len(op.qubits))
                if channel is not None and not channel.is_unitary_channel():
                    state = self._apply_channel_trajectory(state, channel, list(op.qubits), rng)
            elif op.kind == "measure":
                outcome_bits = []
                for q_idx, qubit in enumerate(op.qubits):
                    p1 = float(state.marginal_probabilities([qubit])[1])
                    bit = int(rng.random() < p1)
                    if collapse:
                        state = meas.project_statevector(state, [qubit], bit)
                    outcome_bits.append(bit)
                if apply_readout and not noise.readout_error == _NO_READOUT:
                    outcome_bits = apply_readout_error(
                        outcome_bits,
                        noise.readout_error.p_read1_given_0,
                        noise.readout_error.p_read0_given_1,
                        rng,
                    )
                for cbit, bit in zip(op.clbits, outcome_bits):
                    register[cbit] = bit
            elif op.kind == "reset":
                for qubit in op.qubits:
                    # Deterministic reset-to-zero via measure + conditional X.
                    # Ends in |0> regardless of prior population.
                    p1 = float(state.marginal_probabilities([qubit])[1])
                    bit = int(rng.random() < p1)
                    state = meas.project_statevector(state, [qubit], bit)
                    if bit == 1:
                        x = resolve_gate(circuit, "X", [])
                        state = StateVector(
                            apply_gate_statevector(state.amplitudes, circuit.num_qubits, [qubit], x.matrix),
                            circuit.num_qubits,
                        )
            elif op.kind == "barrier":
                continue
        return state, register

    def _apply_channel_trajectory(
        self, state: StateVector, channel: KrausChannel, qubits: list[int], rng: np.random.Generator
    ) -> StateVector:
        """Sample one Kraus operator (quantum trajectory method).

        P(K_i) = ||K_i ψ||²; resulting state K_i ψ / ||K_i ψ||. This ensemble
        equals exact channel action averaged over shots — documented method.
        """
        weights = []
        candidates = []
        from ..quantum.apply import embed_operator

        for k in channel.kraus_operators:
            full_k = (
                k
                if len(qubits) == state.n_qubits and qubits == list(range(state.n_qubits))
                else embed_operator(k, state.n_qubits, qubits)
            )
            out = full_k @ state.amplitudes
            w = float(np.real(np.vdot(out, out)))
            if w > 1e-18:
                candidates.append((out, full_k))
                weights.append(w)
        if not candidates:
            return state
        total = sum(weights)
        probs = np.array(weights) / total
        choice = int(rng.choice(len(candidates), p=probs))
        out, _full = candidates[choice]
        norm = np.linalg.norm(out)
        return StateVector(out / norm, state.n_qubits)


class DensityMatrixEngine:
    """Exact open-system executor: channels applied as CPTP maps."""

    name = "density_matrix"
    MAX_QUBITS = 12  # ρ has 4^n entries; hard safety ceiling documented in LIMITATIONS.md

    def run(
        self,
        circuit: Circuit,
        *,
        seed: int | None = None,
        noise_model: NoiseModel | None = None,
        shots: int | None = None,
    ) -> SimulationResult:
        if circuit.num_qubits > self.MAX_QUBITS:
            raise QuantumCoreError(
                f"Density-matrix mode supports at most {self.MAX_QUBITS} qubits "
                f"(requested {circuit.num_qubits}); ρ would need "
                f"{(1 << (2 * min(circuit.num_qubits, 30)))} complex entries."
            )
        issues = _check(circuit)
        if issues:
            raise ValueError("Circuit failed validation; see issues.")
        rho = DensityMatrix.pure(StateVector.zero(circuit.num_qubits))
        noise = noise_model or NoiseModel.ideal()
        rng = _rng(seed)
        register = [0] * circuit.num_clbits
        for op in circuit.operations:
            if op.condition is not None and register[op.condition.clbit] != op.condition.value:
                continue
            if op.kind == "gate":
                spec = resolve_gate(circuit, op.gate, list(op.params))
                rho = rho.apply_unitary(spec.matrix, list(op.qubits))
                channel = noise.error_for(spec.name, len(op.qubits))
                if channel is not None:
                    rho = channel.apply_to_qubits(rho, list(op.qubits))
            elif op.kind == "measure":
                for cbit, qubit in zip(op.clbits, op.qubits):
                    p1 = float(rho.partial_trace([qubit]).probabilities()[1])
                    bit = int(rng.random() < p1)
                    rho = self._project_density(rho, qubit, bit)
                    register[cbit] = bit
            elif op.kind == "reset":
                for qubit in op.qubits:
                    # Measure-then-flip: ends deterministically at |0>.
                    p1 = float(rho.partial_trace([qubit]).probabilities()[1])
                    bit = int(rng.random() < p1)
                    rho = self._project_density(rho, qubit, bit)
                    if bit == 1:
                        from ..quantum.apply import apply_gate_density
                        x = build_gate("X", [])
                        rho = DensityMatrix(
                            apply_gate_density(rho.matrix, circuit.num_qubits, [qubit], x.matrix),
                            circuit.num_qubits,
                        )
        result = SimulationResult(
            mode=self.name,
            num_shots=None,
            seed=seed,
            density_matrix=rho,
            warnings=[],
        )
        if shots:
            diag = np.clip(rho.probabilities(), 0.0, None)
            diag /= diag.sum()
            draws = rng.multinomial(int(shots), diag)
            counts = {
                format(i, f"0{circuit.num_qubits}b"): int(draws[i])
                for i in range(len(draws))
                if draws[i] > 0
            }
            result.counts = _ordered_counts(counts)
            result.probabilities = {k: v / shots for k, v in result.counts.items()}
        return result

    @staticmethod
    def _project_density(rho: DensityMatrix, qubit: int, outcome: int) -> DensityMatrix:
        from ..quantum.apply import embed_operator

        proj = np.zeros((2, 2), dtype=np.complex128)
        proj[outcome, outcome] = 1.0
        full_p = embed_operator(proj, rho.n_qubits, [qubit])
        out = full_p @ rho.matrix @ full_p.conj().T
        tr = float(np.real(np.trace(out)))
        if tr <= 1e-15:
            raise QuantumCoreError(
                f"Measurement outcome {outcome} on qubit {qubit} has ~zero probability."
            )
        return DensityMatrix(out / tr, rho.n_qubits)


def simulate(
    circuit: Circuit,
    mode: str = "statevector",
    *,
    seed: int | None = None,
    noise_model: NoiseModel | None = None,
    shots: int | None = None,
    initial_state: StateVector | None = None,
) -> SimulationResult:
    """Dispatch to an engine by mode with explicit unsupported-mode errors (§163)."""
    if shots is not None:
        if not isinstance(shots, (int, np.integer)) or isinstance(shots, bool):
            raise QuantumCoreError(
                f"shots must be an integer, got {shots!r} of type {type(shots).__name__}."
            )
        if shots < 0:
            raise QuantumCoreError(
                f"shots must be >= 0 (0 means evolve only), got {shots}."
            )
        if shots > MAX_SHOTS_PER_REQUEST:
            raise QuantumCoreError(
                f"shots={shots} exceeds the per-request safety limit "
                f"{MAX_SHOTS_PER_REQUEST}; split the work into batches."
            )
    if mode == "statevector":
        engine: StatevectorEngine | DensityMatrixEngine = StatevectorEngine()
        kwargs = {}
        if initial_state is not None:
            kwargs["initial_state"] = initial_state
        return engine.run(circuit, seed=seed, noise_model=noise_model, shots=shots, **kwargs)
    if mode == "density_matrix":
        if initial_state is not None:
            raise QuantumCoreError(
                "Custom initial states are currently supported only in statevector mode; "
                "use statevector mode or encode preparation gates into the circuit."
            )
        return DensityMatrixEngine().run(circuit, seed=seed, noise_model=noise_model, shots=shots)
    raise QuantumCoreError(
        f"Unknown simulation mode {mode!r}. Available modes: 'statevector', 'density_matrix'."
    )


# ---------------------------------------------------------------------------


def _rng(seed: int | None) -> np.random.Generator:
    return np.random.default_rng(seed)


def resolve_gate(circuit: Circuit, gate_name: str, params: list[float]):
    """Resolve a gate name to a validated GateSpec.

    Custom gates declared in ``circuit.metadata["custom_gates"]`` take priority
    and pass through full unitarity validation; arbitrary user code is never
    executed (directive §209).
    """
    from .model import Circuit as _C
    from ..quantum.operators import build_gate, custom_gate

    custom = (circuit.metadata.get("custom_gates") or {}).get(gate_name)
    if custom is not None:
        matrix = np.asarray(custom["matrix"], dtype=np.complex128)
        if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
            raise QuantumCoreError(
                f"Custom gate {gate_name!r} must be a square matrix."
            )
        return custom_gate(gate_name, matrix)
    return build_gate(gate_name, params)


_NO_READOUT = NoiseModel.ideal().readout_error


def _uses_mid_circuit_results(circuit: Circuit) -> bool:
    """True when measurement outcomes influence later quantum operations."""
    seen_measure = False
    for op in circuit.operations:
        if op.kind == "measure":
            seen_measure = True
        elif op.kind in ("gate", "reset") and (seen_measure or op.condition is not None):
            return True
    return False

# Safety ceiling for a single request; batched jobs aggregate beyond this
# through the experiment engine instead (directive §114).
MAX_SHOTS_PER_REQUEST = 10_000_000


def _ordered_counts(counts: dict[str, int]) -> dict[str, int]:
    return dict(sorted(counts.items()))


def _check(circuit: Circuit) -> list[ValidationIssue]:
    try:
        assert_valid(circuit)
    except ValueError as e:
        raise ValueError(str(e)) from e
    return []
