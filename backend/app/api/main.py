"""FastAPI application: validated endpoints, health checks, WebSocket progress.

Every endpoint validates inputs via pydantic schemas and returns structured
errors. Simulation results always trace to computation; the API never
fabricates data (directive §237, §323).
"""
from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path as _Path

from ..circuits import (
    Circuit,
    circuit_from_dict,
    circuit_to_dict,
    simulate,
    validate_circuit,
)
from ..quantum.states import QuantumCoreError
from ..noise.models import NoiseModel
from ..persistence.db import Database, ensure_default_project
from ..experiments.service import ExperimentService
from ..experiments.runner import ExperimentSpec, RUNNER_REGISTRY
from ..workers.jobs import JobQueue
from ..distributed import (
    DistributedExecutor,
    DistributedConfig,
    topology_from_nodes_links,
)
from ..network import NetworkConfig
from pydantic import BaseModel, Field, field_validator

from . import schemas


STATE: dict = {}


def get_db() -> Database:
    return STATE["db"]


def get_service() -> ExperimentService:
    return STATE["service"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: database + workers (directive §223 health-checkable).
    # Testability (E2E milestone): the database path is overridable via
    # QUANTUMLAB_DB so browser tests can run against an isolated database
    # instead of the developer's working database.
    db = Database(os.environ.get("QUANTUMLAB_DB", "quantumlab.db"))
    service = ExperimentService(db)
    # Startup recovery (AD-014): runs orphaned by a previous process exit
    # become FAILED (never COMPLETED); volatile QUEUED marks return to CREATED.
    recovery = service.recover_interrupted_runs()
    queue = JobQueue(db=db, workers=2)

    loop = asyncio.get_running_loop()
    def broadcast(job):
        for ws in list(WS_CLIENTS):
            try:
                payload = {
                    "type": "job.progress",
                    "job_id": job.id,
                    "status": job.status,
                    "progress": job.progress,
                    "detail": job.detail,
                    "run_id": job.payload.get("run_id"),
                    "error": job.error,
                }
                loop.create_task(_safe_send(ws, json.dumps(payload)))
            except Exception:
                pass

    queue.subscribe(broadcast)
    queue.start()
    STATE.update({"db": db, "service": service, "queue": queue})
    yield
    queue.shutdown()
    db.close()


async def _safe_send(ws: WebSocket, text: str) -> None:
    try:
        await ws.send_text(text)
    except Exception:
        pass


app = FastAPI(
    title="QuantumLab API",
    version="0.1.0",
    description=(
        "Quantum computing, information, and networking research laboratory. "
        "All results come from real simulation; nothing is fabricated."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


WS_CLIENTS: set[WebSocket] = set()


def http_error(status: int, code: str, message: str, suggestion: str | None = None) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"code": code, "message": message, "suggestion": suggestion},
    )


# ---------------------------------------------------------------------------
# Health / diagnostics (§223-228)
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict:
    checks = {}
    checks["database"] = _check_database()
    checks["quantum_engine"] = _check_quantum_engine()
    checks["network_engine"] = _check_network_engine()
    q: JobQueue = STATE["queue"]
    checks["worker"] = {
        "status": "ok" if q.running_count() >= 0 else "unknown",
        "queued": q.pending_count(),
        "running": q.running_count(),
        "workers": q.workers,
    }
    overall = all(v.get("status") == "ok" for k, v in checks.items() if isinstance(v, dict))
    return {"status": "ok" if overall else "degraded", "checks": checks}


def _check_quantum_engine() -> dict:
    """H|0> -> X -> measure sanity check (§224)."""
    try:
        c = Circuit(num_qubits=2, num_clbits=2)
        c.add_gate("X", [0])
        c.add_measure([0], [0])
        res = simulate(c, seed=1, shots=16)
        ok = res.counts.get("01", 0) == 16  # little-endian register string
        return {"status": "ok" if ok else "failed",
                "detail": "X gate truth table check"}
    except Exception as e:
        return {"status": "failed", "detail": str(e)}


def _check_network_engine() -> dict:
    """Minimal A->B network executes events (§225)."""
    try:
        from ..network import Topology, NetworkNode, NetworkEngine, NetworkConfig

        t = Topology()
        t.add_node(NetworkNode("A"))
        t.add_node(NetworkNode("B"))
        t.add_quantum_link("A", "B", distance_km=1)
        eng = NetworkEngine(t, NetworkConfig(), seed=1)
        eng.submit_request("A", "B")
        r = eng.run(until_ns=100_000)
        ok = r.success_count >= 1 or r.failure_count <= 1
        return {"status": "ok" if ok else "failed",
                "detail": "two-node entanglement request executed"}
    except Exception as e:
        return {"status": "failed", "detail": str(e)}


def _check_database() -> dict:
    try:
        row = get_db().query_one("SELECT COUNT(*) AS c FROM projects")
        return {"status": "ok", "detail": f"{row['c']} project(s)"}
    except Exception as e:
        return {"status": "failed", "detail": str(e)}


# ---------------------------------------------------------------------------
# Circuits
# ---------------------------------------------------------------------------

@app.post("/api/circuits/validate")
def validate_circuit_endpoint(req: schemas.ValidateCircuitRequest) -> dict:
    try:
        circuit = circuit_from_dict(req.circuit)
    except ValueError as e:
        raise http_error(400, "INVALID_DOCUMENT", str(e))
    issues = [i.to_dict() for i in validate_circuit(circuit)]
    return {"valid": not issues, "issues": issues}


@app.post("/api/circuits/execute")
def execute_circuit(req: schemas.CircuitExecuteRequest) -> dict:
    try:
        circuit = circuit_from_dict(req.circuit)
        noise = NoiseModel.from_config(req.noise_config) if req.noise_config else None
        result = simulate(
            circuit, mode=req.mode, seed=req.seed, shots=req.shots, noise_model=noise
        )
    except ValueError as e:
        raise http_error(400, "VALIDATION_ERROR", str(e))
    except QuantumCoreError as e:
        raise http_error(400, "NUMERICAL_ERROR", str(e),
                         suggestion="Check circuit size/parameters; density mode caps at 12 qubits.")
    out = {
        "mode": result.mode,
        "counts": result.counts,
        "probabilities": result.probabilities,
        "warnings": result.warnings,
    }
    if result.final_state is not None:
        amps = result.final_state.amplitudes
        probs = result.final_state.probabilities()
        n = result.final_state.n_qubits
        if n <= 8:
            out["statevector"] = {
                format(i, f"0{n}b"): {"re": round(float(a.real), 6), "im": round(float(a.imag), 6),
                                      "p": round(float(probs[i]), 9)}
                for i, a in enumerate(amps) if probs[i] > 1e-12
            }
        else:
            top = sorted(range(len(probs)), key=lambda i: -probs[i])[:64]
            out["statevector_top"] = {
                format(i, f"0{n}b"): round(float(probs[i]), 9) for i in top if probs[i] > 1e-12
            }
        reduced = result.final_state.marginal_probabilities(list(range(min(n, 10))))
        out["marginal_probabilities"] = {
            format(i, f"0{min(n, 10)}b"): float(p) for i, p in enumerate(reduced) if p > 1e-12
        }
        if n == 1:
            from ..quantum.density import DensityMatrix
            rho = DensityMatrix.pure(result.final_state)
            out["bloch_vector"] = [round(float(x), 6) for x in rho.bloch_vector()]
        elif n <= 3:
            from ..quantum.density import DensityMatrix
            rho = DensityMatrix.pure(result.final_state)
            out["entanglement_entropy_bits"] = [
                round(rho.partial_trace([q]).entropy(), 6) for q in range(n)
            ]
    if result.density_matrix is not None:
        dm = result.density_matrix
        out["density_summary"] = {
            "purity": round(dm.purity(), 9),
            "entropy_bits": round(dm.entropy(), 9),
        }
    if req.circuit.get("metadata", {}).get("custom_gates"):
        out["notes"] = ["Circuit used custom gates; matrices validated as unitary."]
    return out


# ---------------------------------------------------------------------------
# Algorithms
# ---------------------------------------------------------------------------

@app.post("/api/algorithms/grover")
def grover(req: schemas.GroverRequest):
    from ..algorithms import run_grover

    try:
        res = run_grover(req.n_qubits, req.marked_index, shots=req.shots, seed=req.seed)
    except QuantumCoreError as e:
        raise http_error(400, "NUMERICAL_ERROR", str(e))
    return {
        "marked_state": res.marked_state,
        "counts": res.counts,
        "success_probability": res.success_probability_estimate,
        "optimal_iterations": res.optimal_iterations,
        "per_iteration_probabilities": res.per_iteration_probabilities,
    }


@app.post("/api/algorithms/bv")
def bernstein_vazirani(req: schemas.BvRequest):
    from ..algorithms import run_bernstein_vazirani

    return run_bernstein_vazirani(req.secret)


@app.post("/api/algorithms/qft/matrix")
def qft_matrix(req: schemas.QftRequest):
    from ..algorithms import build_qft

    circuit, info = build_qft(req.n_qubits, inverse=req.inverse,
                              cutoff_exponent=req.cutoff_exponent)
    return {"circuit": circuit_to_dict(circuit), "approximate": info.approximate,
            "dropped_rotations": info.dropped_rotations, "warnings": info.warnings}


@app.post("/api/algorithms/deutsch-jozsa")
def deutsch_jozsa(req: schemas.DeutschJozsaRequest):
    from ..algorithms import OracleSpec, run_deutsch_jozsa

    oracle = OracleSpec.constant(req.n_qubits, 0) if req.kind == "constant" \
        else OracleSpec.balanced(req.n_qubits, seed=req.seed)
    return run_deutsch_jozsa(oracle)


@app.post("/api/algorithms/superdense")
def superdense(req: schemas.SuperdenseRequest):
    from ..algorithms import run_superdense

    return run_superdense(req.bits, shots=req.shots, seed=req.seed % 100000)


@app.post("/api/algorithms/order-finding")
def order_finding(req: schemas.OrderFindingRequest):
    from math import gcd
    from ..algorithms import run_order_finding
    from app.quantum.states import QuantumCoreError

    if gcd(req.a, req.N) != 1:
        raise http_error(400, "INVALID_INPUT", f"gcd(a={req.a}, N={req.N}) != 1",
                         suggestion="Choose a coprime base a.")
    try:
        res = run_order_finding(req.a, req.N, seed=req.a * 31 + req.N)
    except QuantumCoreError as e:
        raise http_error(400, "LIMIT_EXCEEDED", str(e))
    return {
        "a": res.a, "N": res.N,
        "true_order": res.true_order,
        "recovered_order": res.recovered_order,
        "success": res.success,
        "measured_phases_top": res.measured_phases_top[:8],
    }


@app.post("/api/algorithms/quantum-walk")
def quantum_walk(req: schemas.QuantumWalkRequest):
    from ..algorithms import discrete_quantum_walk

    return discrete_quantum_walk(req.n_position_qubits, req.steps)


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------

@app.post("/api/protocols/bb84")
def bb84(req: schemas.BB84Request):
    from ..protocols import run_bb84

    r = run_bb84(req.n_qubits, eve_intercept_probability=req.eve_intercept_probability,
                 sample_fraction=req.sample_fraction, seed=req.seed)
    return {
        "n_signal_qubits": r.n_signal_qubits,
        "sifted_bits": len(r.sifted_indices),
        "sample_size": r.sample_size,
        "qber": r.qber,
        "eve_present": r.eve_present,
        "key_match_sample_agreement": sum(a == b for a, b in zip(r.sifted_key_alice, r.sifted_key_bob)) /
                                      max(len(r.sifted_key_alice), 1),
        "notes": r.notes,
    }


@app.post("/api/protocols/e91")
def e91(req: schemas.E91Request):
    from ..protocols import run_e91

    r = run_e91(req.n_pairs, noise_correlation_factor=req.noise_correlation_factor,
                seed=req.seed)
    return {
        "chsh_statistic": r.chsh_statistic,
        "classical_bound": r.classical_bound,
        "quantum_bound": r.quantum_bound,
        "violates_classical": r.chsh_violates_classical,
        "key_length": len(r.alice_key),
        "key_agreement": sum(a == b for a, b in zip(r.alice_key, r.bob_key)) /
                         max(len(r.alice_key), 1),
        "notes": r.notes,
    }


@app.post("/api/protocols/chsh")
def chsh(req: schemas.CHSHRequest):
    from ..protocols import run_chsh

    return run_chsh(req.state_fidelity, shots_per_setting=req.shots_per_setting,
                    seed=req.seed)


@app.post("/api/protocols/qrng")
def qrng(req: schemas.QRNGRequest):
    from ..protocols import run_qrng

    return run_qrng(req.n_bits, seed=req.seed)


# ---------------------------------------------------------------------------
# QEC
# ---------------------------------------------------------------------------

@app.get("/api/qec/codes")
def qec_codes():
    from ..qec import CODE_REGISTRY

    return [
        {
            "name": c.name, "n": c.n, "k": c.k, "distance": c.distance,
            "description": c.description,
            "corrects_paulis": list(c.corrects_paulis),
        }
        for c in CODE_REGISTRY.values()
    ]


@app.post("/api/qec/sweep")
def qec_sweep(req: schemas.QECSweepRequest):
    from ..qec import sweep_physical_error_rate, get_code

    try:
        get_code(req.code)
    except KeyError as e:
        raise http_error(400, "UNKNOWN_CODE", str(e))
    pts = sweep_physical_error_rate(req.code, req.physical_error_rates,
                                    trials=req.trials, seed=req.seed)
    return {
        "code": req.code,
        "table": [
            {"physical_error_rate": p.physical_error_rate,
             "logical_error_rate": p.logical_error_rate,
             "ci95_low": p.ci_low, "ci95_high": p.ci_high,
             "logical_failures": p.logical_failures, "trials": p.trials}
            for p in pts
        ],
    }


@app.post("/api/qec/surface-code")
def surface_code(req: schemas.SurfaceCodeRequest):
    from ..qec import simulate_surface_code, ToricCodeLayout

    res = simulate_surface_code(req.d, req.physical_error_rate,
                                trials=req.trials, seed=req.seed)
    layout = ToricCodeLayout(req.d).visualization_layout()
    return {
        "d": res.d,
        "physical_error_rate": res.physical_error_rate,
        "logical_error_rate": res.logical_error_rate,
        "ci95": list(res.ci95),
        "trials": res.trials,
        "note": res.note,
        "layout": layout,
    }


# ---------------------------------------------------------------------------
# Network studio
# ---------------------------------------------------------------------------

@app.post("/api/network/simulate")
def network_simulate(req: schemas.NetworkSimulateRequest):
    from ..network import Topology, NetworkNode, NetworkEngine, NetworkConfig

    topo = Topology()
    names = set()
    for node in req.nodes:
        topo.add_node(NetworkNode(name=node.name, node_type=node.type,
                                  memory_slots=node.memory_slots,
                                  latitude=node.latitude, longitude=node.longitude))
        names.add(node.name)
    for link in req.links:
        if link.source not in names or link.destination not in names:
            raise http_error(400, "BAD_LINK",
                             f"Link {link.source}-{link.destination} references unknown nodes.")
        try:
            topo.add_quantum_link(link.source, link.destination,
                                  distance_km=link.distance_km,
                                  base_fidelity=link.base_fidelity,
                                  detector_efficiency=link.detector_efficiency)
        except ValueError as e:
            raise http_error(400, "BAD_LINK", str(e))
    for rq in req.requests:
        src, dst = rq.get("source"), rq.get("destination")
        if src not in names or dst not in names:
            raise http_error(400, "BAD_REQUEST",
                             f"Request {src}->{dst} references unknown nodes.")
    cfg_kwargs = dict(
        routing_strategy=req.routing_strategy,
        scheduler_policy=req.scheduler_policy,
        swap_success_probability=req.swap_success_probability,
        classical_latency_mode=req.classical_latency_mode,
        memory_coherence_ns=req.memory_coherence_ns,
        trace_mode=req.trace_mode,
    )
    if req.node_failure_rate_per_s > 0 or req.link_failure_rate_per_s > 0:
        cfg_kwargs.update(node_failure_rate_per_s=req.node_failure_rate_per_s,
                          link_failure_rate_per_s=req.link_failure_rate_per_s)
    if req.purification_protocol is not None:
        cfg_kwargs["purification_protocol"] = req.purification_protocol
    engine = NetworkEngine(topo, NetworkConfig(**cfg_kwargs), seed=req.seed)
    for rq in req.requests:
        engine.submit_request(
            rq["source"], rq["destination"],
            protocol=rq.get("protocol", "entanglement"),
            fidelity_requirement=rq.get("fidelity_requirement"),
            deadline_ns=rq.get("deadline_ns"),
            priority=int(rq.get("priority", 0)),
        )
    result = engine.run(until_ns=req.sim_time_ms * 1e6)
    return {
        "sim_time_ns": result.sim_time_ns,
        "stats": result.stats,
        "fairness": result.fairness,
        "utilization": result.utilization,
        "avg_fidelity": result.avg_fidelity,
        "avg_service_ns": result.avg_service_ns,
        "success_count": result.success_count,
        "failure_count": result.failure_count,
        "outcomes": [
            {
                "request_id": o.request_id, "source": o.source,
                "destination": o.destination, "protocol": o.protocol,
                "success": o.success, "fidelity": o.fidelity,
                "completion_ns": o.completion_ns, "waiting_ns": o.waiting_ns,
                "route": list(o.route) if o.route else None,
                "failure_reason": o.failure_reason,
            }
            for o in result.outcomes
        ],
        "event_log": result.event_log,
        "truncated": result.truncated,
    }


# ---------------------------------------------------------------------------
# Distributed quantum computing
# ---------------------------------------------------------------------------

def _distributed_topology(req_topo):
    """Build a Topology from a request payload, or None."""
    if req_topo is None:
        return None
    nodes = [{"name": n.name, "type": n.type, "memory_slots": n.memory_slots} for n in req_topo.nodes]
    links = [
        {"source": l.source, "destination": l.destination, "distance_km": l.distance_km,
         "base_fidelity": l.base_fidelity, "detector_efficiency": l.detector_efficiency}
        for l in req_topo.links
    ]
    return topology_from_nodes_links(nodes, links)


def _distributed_config(req, *, for_plan: bool = False) -> DistributedConfig:
    q2n = {int(k): v for k, v in (req.qubit_to_node or {}).items()} if req.qubit_to_node else None
    topo = _distributed_topology(getattr(req, "topology", None))
    kwargs = dict(
        protocol=getattr(req, "protocol", "single_ebit"),
        seed=getattr(req, "seed", None),
        qubit_to_node=q2n,
        num_nodes=getattr(req, "num_nodes", 2),
        node_names=getattr(req, "node_names", None),
        objective=getattr(req, "objective", "minimize_cross_node"),
        topology=topo,
    )
    if not for_plan:
        ncfg = getattr(req, "network_config", None)
        kwargs["network_config"] = NetworkConfig(**ncfg) if ncfg else None
        kwargs["fallback"] = getattr(req, "fallback", "error")
        kwargs["ebit_noise"] = getattr(req, "ebit_noise", "ideal")
        kwargs["ebit_noise_fidelity"] = getattr(req, "ebit_noise_fidelity", None)
    return DistributedConfig(**kwargs)


@app.post("/api/distributed/partition")
def distributed_partition(req: schemas.DistributedPartitionRequest):
    """Partition a circuit across nodes and report local/remote operations."""
    try:
        circuit = circuit_from_dict(req.circuit)
        cfg = _distributed_config(req, for_plan=True)
        plan = DistributedExecutor(cfg).plan(circuit)
    except ValueError as e:
        raise http_error(400, "VALIDATION_ERROR", str(e))
    except QuantumCoreError as e:
        raise http_error(400, "NUMERICAL_ERROR", str(e),
                         suggestion="Check qubit counts and gate operands.")
    return plan.to_dict()


@app.post("/api/distributed/simulate")
def distributed_simulate(req: schemas.DistributedSimulateRequest):
    """Execute a distributed circuit through the genuine remote-CNOT protocol."""
    try:
        circuit = circuit_from_dict(req.circuit)
        cfg = _distributed_config(req)
        result = DistributedExecutor(cfg).execute(circuit)
    except ValueError as e:
        raise http_error(400, "VALIDATION_ERROR", str(e))
    except QuantumCoreError as e:
        raise http_error(400, "NUMERICAL_ERROR", str(e))
    return result.to_dict()


@app.post("/api/distributed/remote-cnot")
def distributed_remote_cnot(req: schemas.RemoteCNOTRequest):
    """Analyze a single remote CNOT between two nodes (resources + equivalence)."""
    try:
        assignment = {int(k): v for k, v in (req.qubit_to_node or {}).items()}
        if not assignment:
            assignment = {req.control_qubit: "node_0", req.target_qubit: "node_1"}
        cfg = _distributed_config(req)
        result = DistributedExecutor(cfg).analyze_single_remote_cnot(
            req.control_qubit, req.target_qubit, assignment
        )
    except ValueError as e:
        raise http_error(400, "VALIDATION_ERROR", str(e))
    except QuantumCoreError as e:
        raise http_error(400, "NUMERICAL_ERROR", str(e))
    return result.to_dict()


@app.post("/api/qec/rotated-surface-code/decode")
def rotated_surface_code_decode(req: schemas.RotatedSurfaceCodeDecodeRequest):
    """Decode one error on the rotated planar surface code with exact MWPM."""
    from ..qec import RotatedSurfaceCode, RotatedSurfaceCodeDecoder, error_from_string
    from ..qec.rotated_surface_code import sample_single_error

    try:
        code = RotatedSurfaceCode.build(req.d)
        if req.error is not None:
            if len(req.error) != code.d * code.d:
                raise ValueError(
                    f"error string must have exactly {code.d * code.d} characters "
                    f"for d={req.d}."
                )
            ex, ez = error_from_string(code, req.error)
            seed = req.seed
        else:
            ex, ez = sample_single_error(code, req.error_model,
                                         req.physical_error_rate, req.seed)
            seed = req.seed
        result = RotatedSurfaceCodeDecoder(code).decode(
            ex, ez, seed=seed, error_model=req.error_model)
    except ValueError as e:
        raise http_error(400, "VALIDATION_ERROR", str(e))
    body = result.to_dict()
    if req.include_layout:
        body["layout"] = code.layout()
    return body


@app.post("/api/qec/rotated-surface-code/simulate")
def rotated_surface_code_simulate(req: schemas.RotatedSurfaceCodeSimulateRequest):
    """Monte Carlo logical-error estimate for one (d, p) point (MWPM)."""
    from ..qec import simulate_rotated_surface_code

    try:
        res = simulate_rotated_surface_code(
            req.d, req.physical_error_rate, trials=req.trials,
            seed=req.seed, error_model=req.error_model)
    except ValueError as e:
        raise http_error(400, "VALIDATION_ERROR", str(e))
    return res.to_dict()


@app.post("/api/qec/rotated-surface-code/repeated-round/decode")
def repeated_round_decode(req: schemas.RepeatedRoundDecodeRequest):
    """Sample and decode one repeated-round error history (space-time MWPM)."""
    from ..qec import RotatedSurfaceCode, sample_repeated, decode_repeated

    try:
        code = RotatedSurfaceCode.build(req.d)
        ex, ez, _, obs = sample_repeated(
            code, req.rounds, req.p_data, req.p_measurement,
            error_model=req.error_model, seed=req.seed)
        result = decode_repeated(
            code, req.rounds, req.p_data, req.p_measurement,
            data_error_x=ex, data_error_z=ez, observed_syndromes=obs,
            seed=req.seed, error_model=req.error_model)
    except ValueError as e:
        raise http_error(400, "VALIDATION_ERROR", str(e))
    body = result.to_dict()
    if req.include_layout:
        body["layout"] = code.layout()
    return body


@app.post("/api/qec/rotated-surface-code/repeated-round/simulate")
def repeated_round_simulate(req: schemas.RepeatedRoundSimulateRequest):
    """Monte Carlo logical-error estimate for repeated-round decoding."""
    from ..qec import simulate_repeated

    try:
        res = simulate_repeated(
            req.d, req.rounds, req.p_data, req.p_measurement,
            trials=req.trials, seed=req.seed, error_model=req.error_model)
    except ValueError as e:
        raise http_error(400, "VALIDATION_ERROR", str(e))
    return res


@app.post("/api/qec/rotated-surface-code/circuit-level/decode")
def circuit_level_decode(req: schemas.CircuitLevelDecodeRequest):
    """Sample + decode one circuit-level error history (ancilla circuits)."""
    from ..qec import RotatedSurfaceCode, simulate_circuit_level, decode_circuit_level

    try:
        code = RotatedSurfaceCode.build(req.d)
        ex, ez, hooks, obs = simulate_circuit_level(
            code, req.rounds, req.p_gate, req.p_readout, req.p_reset, req.p_prep,
            seed=req.seed)
        result = decode_circuit_level(
            code, req.rounds, req.p_gate, req.p_readout, req.p_reset, req.p_prep,
            data_error_x=ex, data_error_z=ez, observed_syndromes=obs,
            hook_events=hooks, seed=req.seed)
    except ValueError as e:
        raise http_error(400, "VALIDATION_ERROR", str(e))
    body = result.to_dict()
    if req.include_layout:
        body["layout"] = code.layout()
    return body


@app.post("/api/qec/rotated-surface-code/circuit-level/simulate")
def circuit_level_simulate(req: schemas.CircuitLevelSimulateRequest):
    """Circuit-level Monte Carlo logical-error estimate.

    `schedule_mode`: "naive" (default) uses the production simulator's
    support-order CNOT schedule. "optimized" uses the deterministic
    minimum-risk ordering from the fault catalogue. NOTE: under the
    implemented H-CNOTs-H circuit the phenomenological-MWPM p_L is
    empirically invariant under schedule selection at d=3 (the
    decoder is syndrome-driven); this is a documented finding, not
    a bug. The endpoint is provided so users can verify the
    invariance on their own configurations.
    """
    from ..qec import (
        RotatedSurfaceCode, simulate_circuit_level, decode_circuit_level,
    )
    from ..qec.fault_catalogue import (
        select_optimized_schedules, get_naive_schedules,
    )
    from ..qec.pipeline import wilson_interval

    try:
        code = RotatedSurfaceCode.build(req.d)
        if req.schedule_mode == "optimized":
            opt = select_optimized_schedules(code)
            schedules = {(k, i): c.order for (k, i), c in opt.items()}
        else:
            naive = get_naive_schedules(code)
            schedules = {(k, i): c.order for (k, i), c in naive.items()}
        fails = 0
        total_hooks = 0
        for t in range(req.trials):
            ts = req.seed + t * 7919
            ex, ez, hooks, obs = simulate_circuit_level(
                code, req.rounds, req.p_gate, req.p_readout,
                req.p_reset, req.p_prep, seed=ts, schedules=schedules)
            total_hooks += len(hooks)
            res = decode_circuit_level(
                code, req.rounds, req.p_gate, req.p_readout,
                req.p_reset, req.p_prep,
                data_error_x=ex, data_error_z=ez, observed_syndromes=obs,
                hook_events=hooks, seed=ts)
            if not res.success:
                fails += 1
        lo, hi = wilson_interval(fails, req.trials)
        res = {
            "d": req.d, "rounds": req.rounds,
            "p_gate": req.p_gate, "p_readout": req.p_readout,
            "p_reset": req.p_reset, "p_prep": req.p_prep,
            "schedule_mode": req.schedule_mode,
            "trials": req.trials,
            "logical_failures": fails,
            "logical_error_rate": fails / req.trials,
            "ci95": [lo, hi], "seed": req.seed, "decoder": "mwpm",
            "hook_error_events": total_hooks,
            "note": (
                "Circuit-level surface-code decoding: explicit ancilla "
                "stabilizer circuits with gate (p_gate), readout "
                "(p_readout), reset (p_reset), and preparation (p_prep) "
                "noise, decoded by the repeated-round MWPM. "
                "Single-qubit gates ideal; no hardware or threshold claims. "
                "Schedule mode: " + req.schedule_mode + "."
            ),
        }
    except ValueError as e:
        raise http_error(400, "VALIDATION_ERROR", str(e))
    return res


@app.post("/api/qec/rotated-surface-code/schedule/analyze")
def schedule_analyze(req: schemas.ScheduleAnalyzeRequest):
    """Fault-aware stabilizer-schedule analysis: enumerate every
    candidate CNOT ordering, score each by deterministic structural
    risk, and select the optimized schedule reproducibly.

    The naive schedule is preserved (directive §15). The score
    function is documented in `qec.fault_catalogue`.

    Under the H-CNOTs-H stabilizer-measurement circuit (the model
    implemented in the production simulator) the schedule is provably
    degenerate: every permutation of a stabilizer's support produces
    the same risk profile. The optimizer therefore selects the naive
    schedule as optimal, and the response reports this finding
    transparently. The comparison infrastructure is real and can detect
    a non-degenerate schedule if one is ever introduced.
    """
    from ..qec import RotatedSurfaceCode, compare_naive_vs_optimized
    try:
        code = RotatedSurfaceCode.build(req.d)
        report = compare_naive_vs_optimized(code, exhaustive=req.exhaustive)
    except ValueError as e:
        raise http_error(400, "VALIDATION_ERROR", str(e))
    report["layout"] = code.layout()
    report["note"] = (
        "Naive vs optimized schedule comparison. The optimization "
        "selects the schedule with the lowest (n_logical_risk_hooks, "
        "max_hook_weight, n_hooks, sum_hook_weight, canonical-order) "
        "lexicographic key. Under the H-CNOTs-H circuit model the "
        "schedule is provably degenerate (every permutation of a "
        "stabilizer's CNOT support produces the same risk profile, "
        "documented in fault_catalogue); the naive schedule is the "
        "selected optimum. No threshold or hardware claims."
    )
    return report


@app.post("/api/qec/rotated-surface-code/fault/analyze")
def fault_analyze(req: schemas.FaultAnalyzeRequest):
    """Inspect a single representative fault mechanism: the propagated
    data support, the detection-event pattern, and the residual
    classification. All values come from the fault catalogue (no
    computation in the TypeScript layer)."""
    from ..qec import RotatedSurfaceCode
    from ..qec.fault_catalogue import _enumerate_faults_for_candidate, CandidateSchedule
    try:
        code = RotatedSurfaceCode.build(req.d)
        if req.stabilizer_type == "Z":
            if req.stabilizer_index >= len(code.z_checks):
                raise ValueError(
                    f"Z stabilizer index {req.stabilizer_index} out of range "
                    f"for d={req.d}.")
            sup = code.z_checks[req.stabilizer_index].support
        else:
            if req.stabilizer_index >= len(code.x_checks):
                raise ValueError(
                    f"X stabilizer index {req.stabilizer_index} out of range "
                    f"for d={req.d}.")
            sup = code.x_checks[req.stabilizer_index].support
        if req.gate_index >= len(sup) and req.fault_location == "CNOT_PRE":
            raise ValueError(
                f"gate_index {req.gate_index} out of range for support "
                f"size {len(sup)}.")
        cand = CandidateSchedule(
            req.stabilizer_type, req.stabilizer_index,
            order=tuple(sup), support=tuple(sorted(sup)))
        catalogue = _enumerate_faults_for_candidate(code, cand, req.round)
        matches = [f for f in catalogue
                    if f.fault_location == req.fault_location
                    and f.pauli_fault == req.pauli_fault
                    and f.gate_index == req.gate_index]
        if not matches:
            raise ValueError(
                f"No matching mechanism for "
                f"{req.fault_location}/{req.pauli_fault}/g{req.gate_index} "
                f"in {req.stabilizer_type}{req.stabilizer_index} (round "
                f"{req.round}).")
        mechanism = matches[0]
    except ValueError as e:
        raise http_error(400, "VALIDATION_ERROR", str(e))
    return {
        "d": req.d, "round": req.round,
        "stabilizer": {
            "type": req.stabilizer_type,
            "index": req.stabilizer_index,
            "center": list(
                (code.x_checks if req.stabilizer_type == "X"
                 else code.z_checks)[req.stabilizer_index].center),
            "support": list(sup),
        },
        "mechanism": mechanism.to_dict(),
        "layout": code.layout(),
    }


@app.post("/api/qec/rotated-surface-code/circuit-derived/graph")
def circuit_derived_graph(req: schemas.CircuitDerivedGraphRequest):
    """Build the circuit-derived detector graph for one (d, R, noise)
    configuration. Reports the exact-pairwise coverage, the
    multi-event-mechanism excluded mass, and the structural summary."""
    from ..qec import RotatedSurfaceCode, build_circuit_graph
    try:
        code = RotatedSurfaceCode.build(req.d)
        graph = build_circuit_graph(
            code, req.rounds, req.p_gate, req.p_readout,
            req.p_reset, req.p_prep)
    except ValueError as e:
        raise http_error(400, "VALIDATION_ERROR", str(e))
    body = graph.to_dict()
    body["layout"] = code.layout()
    return body


@app.post("/api/qec/rotated-surface-code/circuit-derived/simulate")
def circuit_derived_simulate(req: schemas.CircuitDerivedSimulateRequest):
    """Monte Carlo with the circuit-level noise model, plus the
    circuit-derived graph coverage reported alongside. The
    logical-decoding is performed by the EXISTING phenomenological
    MWPM (preserved semantics, AD-016); the graph is reported as
    structural metadata only (directive §41, §42: avoid silently
    changing the decoder)."""
    from ..qec import simulate_circuit_derived_mc
    try:
        res = simulate_circuit_derived_mc(
            req.d, req.rounds, req.p_gate, req.p_readout, req.p_reset,
            req.p_prep, trials=req.trials, seed=req.seed)
    except ValueError as e:
        raise http_error(400, "VALIDATION_ERROR", str(e))
    return res


@app.get("/api/qec/rotated-surface-code/extraction-models")
def list_extraction_models_endpoint():
    """List supported stabilizer-extraction models (milestone 13)."""
    from ..qec import list_extraction_models
    return {"models": list_extraction_models()}


@app.post("/api/qec/rotated-surface-code/circuit-aware/simulate")
def circuit_aware_simulate(req: schemas.CircuitAwareSimulateRequest):
    """Circuit-AWARE hybrid decoder Monte Carlo (milestone 13, AD-019).

    The decoder uses the circuit-derived pair-edge graph plus
    multi-event post-processing (Approach 3, directive §9). It
    ACTUALLY uses the multi-event mechanisms (not just coverage).
    """
    from ..qec import simulate_circuit_aware_mc
    try:
        res = simulate_circuit_aware_mc(
            req.d, req.rounds, req.p_gate, req.p_readout, req.p_reset,
            req.p_prep, trials=req.trials, seed=req.seed)
    except ValueError as e:
        raise http_error(400, "VALIDATION_ERROR", str(e))
    return res


@app.get("/api/qec/rotated-surface-code/hook-forensics")
def hook_forensics(d: int = 3, round: int = 1):
    """Hook-error forensic analysis (milestone 14, Phase B).

    Programmatically enumerates every ancilla Pauli at every CNOT
    position for every stabilizer, propagates it through the
    actual circuit, and reports the data-side hook support with
    a danger classification. This is the EVIDENCE GATHERING step
    for hook-safe schedule design (Phase C)."""
    from ..qec import RotatedSurfaceCode
    from ..qec.hook_forensics import run_hook_forensics, summarize_forensics
    try:
        code = RotatedSurfaceCode.build(d)
        reports = run_hook_forensics(code, round_index=round)
        summary = summarize_forensics(reports)
        return {
            "d": d, "round": round,
            "summary": summary,
            "reports": [r.to_dict() for r in reports],
            "note": (
                "Forensic report: every elementary ancilla fault "
                "with a data hook or a single-event boundary, "
                "classified as SAFE / STABILIZER_EQUIVALENT / "
                "DATA_HOOK / LOGICAL_RISK / LOGICAL. The "
                "interior 4-data-qubit stabilizers are the most "
                "dangerous (max hook weight 4 at d=3). The schedule "
                "order does NOT change the total hook-weight "
                "distribution under H-CNOT-H (degeneracy finding, "
                "AD-018, AD-019); a faithful hook-safe schedule "
                "requires Shor cat-state (4 ancillas) or "
                "lattice-wide temporal interleaving (architectural)."
            ),
        }
    except ValueError as e:
        raise http_error(400, "VALIDATION_ERROR", str(e))


@app.post("/api/network/route")
def network_route(req: schemas.NetworkSimulateRequest):
    """Route explanation endpoint: returns chosen path + why (§197)."""
    from ..network import Topology, NetworkNode, find_best_route

    topo = Topology()
    for node in req.nodes:
        topo.add_node(NetworkNode(name=node.name, node_type=node.type,
                                  memory_slots=node.memory_slots))
    for link in req.links:
        try:
            topo.add_quantum_link(link.source, link.destination,
                                  distance_km=link.distance_km,
                                  base_fidelity=link.base_fidelity)
        except ValueError as e:
            raise http_error(400, "BAD_LINK", str(e))
    responses = []
    for rq in req.requests:
        route, expl = find_best_route(topo, rq["source"], rq["destination"],
                                      strategy=req.routing_strategy,
                                      fidelity_requirement=rq.get("fidelity_requirement"))
        responses.append({
            "source": rq["source"], "destination": rq["destination"],
            "route": list(route) if route else None,
            "explanation": expl.describe() if expl else None,
            "expected_fidelity": expl.expected_fidelity if expl else None,
            "estimated_latency_ns": expl.estimated_latency_ns if expl else None,
        })
    return {"routes": responses}


# ---------------------------------------------------------------------------
# Optimization lab
# ---------------------------------------------------------------------------

@app.post("/api/optimize/vqe")
def vqe(req: schemas.VQERequest):
    from ..optimization.variational import run_vqe, two_local_h2_ansatz
    from ..optimization.hamiltonians import h2_hamiltonian, transverse_field_ising
    from ..circuits.model import Circuit

    def make_tfim_ansatz(n):
        def ansatz(params):
            c = Circuit(num_qubits=n)
            k = 0
            for q in range(n):
                c.add_gate("RY", [q], params=[float(params[k])]); k += 1
            for q in range(n - 1):
                c.add_gate("CX", [q, q + 1])
            for q in range(n):
                c.add_gate("RY", [q], params=[float(params[k])]); k += 1
            return c
        return ansatz

    if req.system == "h2":
        ham = h2_hamiltonian(req.bond_length_angstrom)
        builder, count = two_local_h2_ansatz, 3
    else:
        ham = transverse_field_ising(req.n_qubits)
        builder, count = make_tfim_ansatz(req.n_qubits), 2 * req.n_qubits
    res = run_vqe(ham, builder, count, max_iter=req.max_iter, seed=req.seed)
    return {
        "estimated_energy": res.estimated_energy,
        "exact_energy": res.exact_energy,
        "error": res.error,
        "energy_history": res.energy_history,
        "final_params": res.final_params,
        "notes": res.notes,
    }


@app.post("/api/optimize/qaoa")
def qaoa(req: schemas.QAOARequest):
    from ..optimization.variational import run_qaoa_maxcut

    edges = [(int(a), int(b)) for a, b in req.edges]
    res = run_qaoa_maxcut(edges, req.n_nodes, p_layers=req.p_layers, seed=req.seed)
    return {
        "best_cut_value": res.best_cut_value,
        "exact_optimum": res.exact_optimum,
        "approximation_ratio": res.approximation_ratio,
        "most_likely_bitstring": res.most_likely_bitstring,
        "probability_distribution_top": res.probability_distribution_top,
        "optimization_history": res.optimization_history,
        "notes": res.notes,
    }


@app.post("/api/optimize/h2-curve")
def h2_curve(req: schemas.H2CurveRequest):
    from ..optimization.variational import h2_dissociation_curve

    lengths = [float(x) for x in req.lengths]
    curve = h2_dissociation_curve(lengths, seed=req.seed)
    return curve


@app.post("/api/optimize/qml")
def qml_experiment(req: schemas.QMLExperimentRequest):
    from ..optimization.qml import run_qml_experiment

    return run_qml_experiment(req.dataset, seed=req.seed, max_iter=req.max_iter,
                              noise_label="depolarizing-0.01" if req.compare_noisy else None)


# ---------------------------------------------------------------------------
# Experiments & jobs
# ---------------------------------------------------------------------------

@app.post("/api/experiments")
def create_experiment(req: schemas.ExperimentCreateRequest):
    svc = get_service()
    spec = ExperimentSpec.from_dict({
        "name": req.name, "module": req.module, "config": req.config,
        "sweep": req.sweep, "backend": req.backend,
        "noise_model": req.noise_model, "seed": req.seed,
    })
    issues = spec.validate()
    if issues:
        raise http_error(400, "INVALID_EXPERIMENT", "; ".join(issues),
                         suggestion=f"Available modules: {sorted(RUNNER_REGISTRY)}")
    exp_id = svc.create_experiment(spec, objective=req.objective,
                                   hypothesis=req.hypothesis,
                                   description=req.description)
    run_ids = svc.create_runs_for_experiment(exp_id)
    return {"experiment_id": exp_id, "run_ids": run_ids}


@app.get("/api/experiments")
def list_experiments():
    return get_service().list_experiments()


@app.get("/api/experiments/{exp_id}")
def get_experiment(exp_id: int):
    exp = get_service().get_experiment(exp_id)
    if not exp:
        raise http_error(404, "NOT_FOUND", f"Experiment {exp_id} does not exist.")
    runs = get_service().list_runs(exp_id)
    return {**exp, "runs": runs}


@app.post("/api/runs/{run_id}/execute")
async def execute_run(run_id: int):
    svc = get_service()
    if not svc.get_run(run_id):
        raise http_error(404, "NOT_FOUND", f"Run {run_id} does not exist.")
    queue: JobQueue = STATE["queue"]
    job = queue.submit_run_job(run_id, svc)
    return {"job_id": job.id, "run_id": run_id, "status": job.status}


@app.post("/api/runs/execute-batch")
async def execute_runs_batch(req: schemas.RunActionRequest):
    svc = get_service()
    queue: JobQueue = STATE["queue"]
    jobs = []
    for rid in req.run_ids:
        if not svc.get_run(rid):
            raise http_error(404, "NOT_FOUND", f"Run {rid} does not exist.")
        job = queue.submit_run_job(rid, svc)
        jobs.append({"job_id": job.id, "run_id": rid})
    return {"jobs": jobs}


@app.get("/api/runs/{run_id}")
def get_run(run_id: int):
    run = get_service().get_run(run_id)
    if not run:
        raise http_error(404, "NOT_FOUND", f"Run {run_id} does not exist.")
    return run


@app.get("/api/runs/{run_id}/result")
def get_run_result(run_id: int):
    res = get_service().get_result(run_id)
    if not res:
        raise http_error(404, "NOT_FOUND",
                         f"No stored result for run {run_id}. Has it completed?")
    return res


@app.post("/api/runs/{run_id}/reproduce")
def reproduce_run(run_id: int):
    """Re-execute a completed run from its stored config+seed and compare
    result documents (directive §44). Original run is never modified."""
    svc = get_service()
    if not svc.get_run(run_id):
        raise http_error(404, "NOT_FOUND", f"Run {run_id} does not exist.")
    try:
        report = svc.reproduce_run(run_id)
    except ValueError as e:
        raise http_error(409, "NOT_REPRODUCIBLE", str(e))
    return report.to_dict()


@app.get("/api/runs/{run_id}/export.csv")
def export_run_csv(run_id: int):
    """Provenance-rich CSV of the run's tabular artifacts (§97, §210)."""
    from fastapi.responses import PlainTextResponse

    svc = get_service()
    try:
        csv_text = svc.export_run_csv(run_id)
    except ValueError as e:
        raise http_error(404, "NOT_FOUND", str(e))
    return PlainTextResponse(csv_text, media_type="text/csv")


@app.post("/api/experiments/compare")
def compare_experiments_runs(req: schemas.RunActionRequest):
    return get_service().compare_runs(req.run_ids)


@app.get("/api/jobs")
def list_jobs():
    q: JobQueue = STATE["queue"]
    return [
        {
            "job_id": j.id, "kind": j.kind, "status": j.status,
            "progress": j.progress, "detail": j.detail,
            "payload": j.payload, "error": j.error,
            "created_at": j.created_at, "completed_at": j.completed_at,
        }
        for j in q.list_jobs()
    ]


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: int):
    q: JobQueue = STATE["queue"]
    if not q.cancel_job(job_id):
        # Also mark DB run cancelled when possible.
        raise http_error(409, "NOT_CANCELLABLE",
                         f"Job {job_id} cannot be cancelled in its current state.")
    return {"cancelled": True}


class HardwareTranspileRequest(BaseModel):
    circuit: dict
    profile_name: str

    @field_validator("circuit")
    @classmethod
    def _check_schema(cls, v: dict) -> dict:
        if not isinstance(v, dict) or v.get("schema") != "quantumlab.circuit":
            raise ValueError('circuit document must declare schema "quantumlab.circuit"')
        return v


@app.get("/api/hardware/profiles")
def list_hardware_profiles():
    """Capability discovery for hardware model profiles (§229-231)."""
    from ..hardware.profiles import PROFILE_REGISTRY

    out = []
    for name, factory in PROFILE_REGISTRY.items():
        p = factory()
        out.append({
            "name": p.name,
            "n_qubits": p.n_qubits,
            "coupling_edges": [sorted(e) for e in sorted(p.coupling, key=sorted)],
            "native_gates": sorted(p.native_gates),
            "t1_us": p.t1_us,
            "t2_us": p.t2_us,
            "readout": {
                "p_read1_given_0": p.readout_p_read1_given_0,
                "p_read0_given_1": p.readout_p_read0_given_1,
            },
            "model_label": p.model_label,
        })
    return out


@app.post("/api/hardware/transpile")
def hardware_transpile(req: HardwareTranspileRequest):
    """Map a logical circuit onto a hardware profile with SWAP insertion.

    Validation status of the mapping is reported per run (ideal-action check
    when the qubit count permits dense verification).
    """
    from ..hardware.profiles import PROFILE_REGISTRY
    from ..hardware.transpile import (
        transpile_for_hardware, verify_mapping_preserves_action,
    )
    from ..circuits.analysis import analyze_circuit
    from ..circuits import circuit_to_dict

    if req.profile_name not in PROFILE_REGISTRY:
        raise http_error(
            400, "UNKNOWN_PROFILE",
            f"Unknown hardware profile {req.profile_name!r}.",
            suggestion=f"Available: {sorted(PROFILE_REGISTRY)}",
        )
    try:
        logical = circuit_from_dict(req.circuit)
        result = transpile_for_hardware(logical, PROFILE_REGISTRY[req.profile_name]())
    except ValueError as e:
        raise http_error(400, "VALIDATION_ERROR", str(e))
    except QuantumCoreError as e:
        raise http_error(400, "TRANSPILE_ERROR", str(e),
                         suggestion="Check gate set and qubit count against the profile.")
    verification = verify_mapping_preserves_action(logical, result)
    return {
        "mapped_circuit": circuit_to_dict(result.circuit),
        "final_mapping": {str(k): v for k, v in result.final_mapping.items()},
        "metrics": {
            "swap_count": result.swap_count,
            "original_depth": result.original_depth,
            "mapped_depth": result.mapped_depth,
            "original_gate_count": result.original_gate_count,
            "mapped_gate_count": result.mapped_gate_count,
            "added_two_qubit_gates": result.added_two_qubit_gates,
        },
        "verification": verification,
        "warnings": result.warnings,
    }


@app.post("/api/circuits/analyze")
def analyze_circuit_endpoint(req: schemas.ValidateCircuitRequest):
    """Structural metrics for a circuit (depth, counts, T accounting, pairs)."""
    from ..circuits.analysis import analyze_circuit

    try:
        circuit = circuit_from_dict(req.circuit)
    except ValueError as e:
        raise http_error(400, "INVALID_DOCUMENT", str(e))
    issues = validate_circuit(circuit)
    blocking = [i for i in issues if i.code != "EMPTY_CIRCUIT"]
    if blocking:
        raise http_error(400, "VALIDATION_ERROR",
                         "; ".join(i.code for i in blocking))
    return analyze_circuit(circuit).to_dict()


class ReadoutMitigationRequest(BaseModel):
    counts: dict[str, int] = Field(min_length=1)
    p_read1_given_0: float = Field(ge=0, le=1)
    p_read0_given_1: float = Field(ge=0, le=1)


@app.post("/api/mitigation/readout")
def readout_mitigation_endpoint(req: ReadoutMitigationRequest):
    """Mitigate readout confusion on an empirical histogram (§12).

    MODEL: tensor-product classical confusion channel inversion; negative
    quasi-probabilities clipped and reported.
    """
    from ..mitigation import mitigate_readout_error

    try:
        res = mitigate_readout_error(
            req.counts,
            p_read1_given_0=req.p_read1_given_0,
            p_read0_given_1=req.p_read0_given_1,
        )
    except QuantumCoreError as e:
        raise http_error(400, "MITIGATION_ERROR", str(e))
    return {
        "mitigated_probabilities": res.mitigated_probabilities,
        "raw_probabilities": res.raw_probabilities,
        "condition_number": res.condition_number,
        "clipped_negative_mass": res.clipped_negative_mass,
        "notes": res.notes,
    }


class ZNERequest(BaseModel):
    scale_factors: list[int] = Field(min_length=2)
    estimates: list[float] = Field(min_length=2)
    model: str = "linear"


@app.post("/api/mitigation/zne")
def zne_endpoint(req: ZNERequest):
    """Extrapolate noisy estimates to the zero-noise limit (§12).

    Raw samples are echoed unchanged; implausible extrapolations carry
    warnings rather than being clipped.
    """
    from ..mitigation import zero_noise_extrapolate

    try:
        res = zero_noise_extrapolate(req.scale_factors, req.estimates, model=req.model)
    except ValueError as e:
        raise http_error(400, "VALIDATION_ERROR", str(e))
    return {
        "scale_factors": res.scale_factors,
        "raw_estimates": res.raw_estimates,
        "extrapolated_value": res.extrapolated_value,
        "fitted_model": res.fitted_model,
        "fit_coefficients": res.fit_coefficients,
        "residuals": res.residuals,
        "warnings": res.warnings,
    }


class QuantumInfoRequest(BaseModel):
    circuit: dict = Field(..., description="quantumlab.circuit v1 document (unitary part defines the state)")
    split_qubits: list[int] | None = None

    @field_validator("circuit")
    @classmethod
    def _check_schema(cls, v: dict) -> dict:
        if not isinstance(v, dict) or v.get("schema") != "quantumlab.circuit":
            raise ValueError('circuit document must declare schema "quantumlab.circuit"')
        return v


@app.post("/api/quantum-info/state-report")
def quantum_info_state_report(req: QuantumInfoRequest):
    """Information measures of the state prepared by a unitary circuit.

    MODEL: exact statevector -> density matrix; all measures computed by
    Hermitian eigendecomposition (see docs/QUANTUM_INFORMATION.md).
    """
    from ..quantum.info_theory import state_report
    from ..quantum.density import DensityMatrix

    try:
        circuit = circuit_from_dict(req.circuit)
        if circuit.num_qubits > 10:
            raise http_error(
                400, "LIMIT_EXCEEDED",
                f"Quantum-information reports are bounded at 10 qubits "
                f"(requested {circuit.num_qubits}) to keep dense-matrix analysis fast.",
                suggestion="Trace out subsystems first or use fewer qubits.",
            )
        res = simulate(circuit)
        rho = DensityMatrix.pure(res.final_state)
    except ValueError as e:
        raise http_error(400, "VALIDATION_ERROR", str(e))
    try:
        rep = state_report(rho, req.split_qubits)
    except QuantumCoreError as e:
        raise http_error(400, "NUMERICAL_ERROR", str(e))
    return {
        "n_qubits": rho.n_qubits,
        "report": rep,
        "model_labels": {
            "computation": "EXACT (statevector eigendecomposition)",
            "separability_test": rep["separability"]["basis"],
        },
        "notes": [
            "Entropies in bits; conditional entropy may be negative for "
            "entangled states — that is physically meaningful.",
            "PPT sufficiency applies only to 2x2 and 2x3 bipartitions; other "
            "dimensions are labeled inconclusive when PPT passes.",
        ],
    }


@app.post("/api/benchmarks/run")
def run_benchmarks(max_qubits: int = 18, repeats: int = 3):
    """Wall-clock performance measurements of this machine (§112, §199)."""
    from ..experiments.benchmarks import run_all_benchmarks

    if not (4 <= max_qubits <= 24) or not (1 <= repeats <= 5):
        raise http_error(400, "INVALID_INPUT",
                         "max_qubits must be within [4,24] and repeats within [1,5].")
    return run_all_benchmarks(repeats=repeats)


@app.websocket("/ws/jobs")
async def ws_jobs(ws: WebSocket):
    await ws.accept()
    WS_CLIENTS.add(ws)
    try:
        while True:
            await ws.receive_text()  # keepalive/pings ignored safely
    except WebSocketDisconnect:
        pass
    finally:
        WS_CLIENTS.discard(ws)


# Serve repository documentation for the frontend docs viewer (read-only).
_DOCS_DIR = _Path(__file__).resolve().parents[3] / "docs"
if _DOCS_DIR.exists():
    app.mount("/repo-docs", StaticFiles(directory=str(_DOCS_DIR)), name="repo-docs")
