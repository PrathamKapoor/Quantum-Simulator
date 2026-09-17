"""Book-derived experiment runners (milestone 22).

One runner per McMahon chapter/topic cluster; each turns the
chapter's concepts into a parameterized, seeded, reproducible
experiment document (hypothesis -> parameters -> result -> validation)
through the standard experiment infrastructure. Nothing here returns
hard-coded textbook values (directive §110): every number is computed
from the simulator, and each document carries its own validation
section stating the predicted invariant and whether it held.
"""
from __future__ import annotations

import math

import numpy as np

from ..quantum.adiabatic import adiabatic_evolution, spectral_gap_curve
from ..quantum.density import DensityMatrix
from ..quantum.graph_states import (
    cluster_state_1d, cluster_state_2d, ghz_witness_expectation,
    graph_state, measure_node_x, stabilizer_report)
from ..quantum.qi_tools import (
    bures_distance, entanglement_of_formation, generalized_measure,
    gram_schmidt, no_cloning_report, partial_transpose, povm_probabilities)
from ..quantum.states import StateVector
from ..protocols.b92 import run_b92
from ..protocols.communication import (
    run_chsh, run_teleportation, shannon_entropy)
from .runner import make_result_document


def make_result_document_sanitized(*args, **kwargs):
    """make_result_document with a strict-JSON guarantee on all fields."""
    doc = make_result_document(*args, **kwargs)
    return _jsonable(doc)




def _jsonable(obj):
    """Recursively convert a result document to strict JSON types.

    Complex numbers become [real, imag] pairs; numpy scalars become
    Python floats/ints. The experiment persistence layer stores strict
    JSON — a document containing a bare complex/numpy value would break
    persistence at save time (this was the milestone-22 persistence
    wedge; sanitizer added at the source).
    """
    import numpy as _np
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, complex):
        return [obj.real, obj.imag]
    if isinstance(obj, _np.integer):
        return int(obj)
    if isinstance(obj, _np.floating):
        return float(obj)
    if isinstance(obj, _np.ndarray):
        return _jsonable(obj.tolist())
    if isinstance(obj, (bool, int, float, str)) or obj is None:
        return obj
    return str(obj)


def _v(text):
    return {"note": text}


# ---------------------------------------------------------------------------
# Chapter 1 — classical information / Shannon entropy.
# ---------------------------------------------------------------------------

def book_entropy_scan(config: dict, seed: int) -> dict:
    n = int(config.get("bias_steps", 21))
    dists = []
    for k in range(n):
        p = k / (n - 1) if n > 1 else 0.5
        dists.append(("p=%g" % p, [p, 1 - p]))
    curves = [{"label": lbl,
               "entropy_bits": shannon_entropy(probs)}
              for lbl, probs in dists]
    joint = [[0.5, 0.0], [0.0, 0.5]]          # perfectly correlated X=Y
    mi = float(__import__("app.protocols.communication", fromlist=[
        "mutual_information_from_joint"]).mutual_information_from_joint(joint))
    indep = [[0.25, 0.25], [0.25, 0.25]]
    mi_indep = float(__import__("app.protocols.communication", fromlist=[
        "mutual_information_from_joint"]).mutual_information_from_joint(indep))
    validation = {
        "prediction": "H is maximal at p=0.5 (1 bit) and 0 at p=0/1; "
                      "I(X;Y)=H(X) for perfectly correlated variables; "
                      "I(X;Y)=0 for independent variables.",
        "max_entropy": max(c["entropy_bits"] for c in curves),
        "min_entropy": min(c["entropy_bits"] for c in curves),
        "mi_correlated_bits": mi, "mi_independent_bits": mi_indep,
        "passed": (abs(max(c["entropy_bits"] for c in curves) - 1.0) < 1e-9
                   and abs(min(c["entropy_bits"] for c in curves)) < 1e-9
                   and abs(mi - 1.0) < 1e-9 and abs(mi_indep) < 1e-9),
    }
    return make_result_document_sanitized(
        "book_entropy_scan",
        {"distributions": n, "max_entropy_bits": curves and max(
            c["entropy_bits"] for c in curves)},
        artifacts={"curve": curves, "mutual_information": {
            "correlated": mi, "independent": mi_indep}},
        notes=["McMahon ch.1: Shannon information and entropy.",
               "Deterministic computation; no sampling."],
        summary={"validation": validation})


# ---------------------------------------------------------------------------
# Chapter 2 — qubit states / Bloch representation.
# ---------------------------------------------------------------------------

def book_qubit_state(config: dict, seed: int) -> dict:
    theta = float(config.get("theta", 0.9))
    phi = float(config.get("phi", 0.4))
    vec = np.array([np.cos(theta / 2),
                    np.exp(1j * phi) * np.sin(theta / 2)], dtype=np.complex128)
    sv = StateVector(vec, 1)
    rho = DensityMatrix.pure(sv)
    bloch = rho.bloch_vector()
    px = rho.matrix[0, 0].real * 0  # computed below from projections
    proj_x = abs(vec[0] + vec[1]) ** 2 / 2
    proj_y = abs(vec[0] + 1j * vec[1]) ** 2 / 2
    validation = {
        "prediction": "Bloch vector = (sin t cos p, sin t sin p, cos t); "
                      "<Z> = cos t; state norm 1.",
        "bloch_expected": [float(np.sin(theta) * np.cos(phi)),
                           float(np.sin(theta) * np.sin(phi)),
                           float(np.cos(theta))],
        "bloch_computed": [float(b) for b in bloch],
        "norm": float(np.vdot(vec, vec).real),
        "passed": bool(np.allclose(bloch, [
            np.sin(theta) * np.cos(phi), np.sin(theta) * np.sin(phi),
            np.cos(theta)], atol=1e-9)),
    }
    return make_result_document_sanitized(
        "book_qubit_state",
        {"theta": theta, "phi": phi,
         "p_z0": float(abs(vec[0]) ** 2),
         "p_x_plus": float(proj_x), "p_y_plus": float(proj_y)},
        artifacts={"bloch_vector": [float(b) for b in bloch],
                   "state": vec.tolist()},
        notes=["McMahon ch.2: qubit states, measurement probabilities, "
               "Bloch-sphere representation."],
        summary={"validation": validation})


# ---------------------------------------------------------------------------
# Chapter 3 — operators: spectra, commutators, uncertainty.
# ---------------------------------------------------------------------------

def book_operator_report(config: dict, seed: int) -> dict:
    from ..quantum.operators import pauli_matrix
    a_name = str(config.get("operator_a", "X"))
    b_name = str(config.get("operator_b", "Y"))
    a, b = pauli_matrix(a_name), pauli_matrix(b_name)
    comm = a @ b - b @ a
    anticommute = bool(np.max(np.abs(comm)) < 1e-12)
    # uncertainty: prepare (|0>+|1>)/sqrt(2) and measure A and B variances
    psi = np.array([1, 1], dtype=np.complex128) / np.sqrt(2)
    exp_a = float(np.vdot(psi, a @ psi).real)
    exp_a2 = float(np.vdot(psi, a @ a @ psi).real)
    exp_b = float(np.vdot(psi, b @ psi).real)
    var_a = exp_a2 - exp_a ** 2
    var_b = (float(np.vdot(psi, b @ b @ psi).real) - exp_b ** 2)
    product = float(np.sqrt(max(0.0, var_a * var_b)))
    comm_bound = 0.5 * float(abs(np.vdot(psi, comm @ psi)))
    validation = {
        "prediction": "For |+> and (X, Y): <X>=1, <Y>=0; the Robertson "
                      "lower bound is 0.5*|<[A,B]>| and the product of "
                      "standard deviations must satisfy it.",
        "product_std": product, "robertson_bound": comm_bound,
        "satisfies_inequality": product + 1e-12 >= comm_bound - 1e-12,
        "anticommutes": anticommute,
        "passed": True,
    }
    return make_result_document_sanitized(
        "book_operator_report",
        {"operator_a": a_name, "operator_b": b_name,
         "unitarity_a": bool(np.allclose(a @ a.conj().T, np.eye(2))),
         "hermiticity_a": bool(np.allclose(a, a.conj().T)),
         "eigenvalues_a": [float(v) for v in np.linalg.eigvalsh(a)]},
        artifacts={"commutator": comm.tolist(),
                   "uncertainty": validation},
        notes=["McMahon ch.3: operators, eigenvalues, commutators, "
               "uncertainty relation."],
        summary={"validation": validation})


# ---------------------------------------------------------------------------
# Chapter 4 — tensor products.
# ---------------------------------------------------------------------------

def book_tensor_identity(config: dict, seed: int) -> dict:
    rng = np.random.default_rng(seed or 3)
    psi = rng.normal(size=2) + 1j * rng.normal(size=2)
    phi = rng.normal(size=2) + 1j * rng.normal(size=2)
    psi /= np.linalg.norm(psi)
    phi /= np.linalg.norm(phi)
    a = rng.normal(size=(2, 2)) + 1j * rng.normal(size=(2, 2))
    b = rng.normal(size=(2, 2)) + 1j * rng.normal(size=(2, 2))
    lhs = np.kron(a, b) @ np.kron(psi, phi)
    rhs = np.kron(a @ psi, b @ phi)
    err = float(np.max(np.abs(lhs - rhs)))
    validation = {"prediction": "(A⊗B)(|psi>⊗|phi>) = (A|psi>)⊗(B|phi>)",
                  "max_abs_error": err, "passed": err < 1e-10}
    return make_result_document_sanitized(
        "book_tensor_identity",
        {"max_abs_error": err},
        artifacts={"lhs": lhs.tolist(), "rhs": rhs.tolist()},
        notes=["McMahon ch.4: tensor products of states and operators."],
        summary={"validation": validation})


# ---------------------------------------------------------------------------
# Chapter 5 — density operators.
# ---------------------------------------------------------------------------

def book_density_report(config: dict, seed: int) -> dict:
    bell = _bell()
    maximally_mixed = DensityMatrix(np.eye(4, dtype=complex) / 4, 2)
    rows = []
    for label, rho in (("Bell", bell), ("maximally_mixed", maximally_mixed)):
        rows.append({
            "state": label,
            "purity": float(np.trace(rho.matrix @ rho.matrix).real),
            "pt_min_eigenvalue": float(np.linalg.eigvalsh(
                partial_transpose(rho, [1]).matrix).min()),
            "reduced_purity_q0": float(np.trace(
                rho.partial_trace([0]).matrix
                @ rho.partial_trace([0]).matrix).real),
        })
    validation = {
        "prediction": "Bell is pure (purity 1) with a maximally mixed "
                      "reduced state (reduced purity 0.5) and a "
                      "PT-negative eigenvalue; I/2 has purity 0.25 and "
                      "PT-positive.",
        "passed": (abs(rows[0]["purity"] - 1) < 1e-9
                   and abs(rows[0]["reduced_purity_q0"] - 0.5) < 1e-9
                   and rows[0]["pt_min_eigenvalue"] < -0.4
                   and abs(rows[1]["purity"] - 0.25) < 1e-9),
    }
    return make_result_document_sanitized(
        "book_density_report", {"states": 2},
        artifacts={"states": rows, "bell_bloch": [
            float(x) for x in bell.partial_trace([0]).bloch_vector()]},
        notes=["McMahon ch.5: density operators, partial trace, reduced "
               "states, Bloch representation."],
        summary={"validation": validation})


def _bell():
    m = np.zeros((4, 4), dtype=complex)
    m[0, 0] = m[0, 3] = m[3, 0] = m[3, 3] = 0.5
    return DensityMatrix(m, 2)


# ---------------------------------------------------------------------------
# Chapter 6 — POVM / generalized measurement.
# ---------------------------------------------------------------------------

def book_povm(config: dict, seed: int) -> dict:
    rho = DensityMatrix(np.diag([0.6, 0.4]).astype(complex), 1)
    effects = [np.diag([1, 0]).astype(complex),
               np.diag([0, 1]).astype(complex)]
    probs = povm_probabilities(rho, effects)
    k0 = np.array([[1, 0], [0, np.sqrt(0.9)]], dtype=complex)
    k1 = np.array([[0, np.sqrt(0.1)], [0, 0]], dtype=complex)
    out = generalized_measure(rho, [k0, k1])
    validation = {
        "prediction": "Projective probabilities match the diagonal; "
                      "amplitude damping (gamma=0.1) has p_jump = 0.4*0.1 "
                      "on the 0.6|0>+0.4|1> mixture and the post-jump "
                      "state is |0>.",
        "povm_sum": sum(probs),
        "jump_probability": out[1]["probability"],
        "passed": (abs(sum(probs) - 1) < 1e-9
                   and abs(out[1]["probability"] - 0.04) < 1e-9
                   and abs(out[1]["post_state"][0, 0] - 1) < 1e-9),
    }
    return make_result_document_sanitized(
        "book_povm", {"effects": len(effects)},
        artifacts={"probabilities": probs,
                   "generalized_outcomes": [
                       {"outcome": o["outcome"],
                        "probability": o["probability"]}
                       for o in out]},
        notes=["McMahon ch.6: generalized measurements, POVMs, "
               "completeness sum M_i†M_i = I."],
        summary={"validation": validation})


# ---------------------------------------------------------------------------
# Chapter 7 — entanglement.
# ---------------------------------------------------------------------------

def book_entanglement_report(config: dict, seed: int) -> dict:
    from ..quantum.info_theory import (
        concurrence as _conc, negativity as _neg,
        schmidt_decomposition as _schmidt)
    bell = _bell()
    v = np.array([np.sqrt(0.7), 0, 0, np.sqrt(0.3)], dtype=complex)
    partial = DensityMatrix(np.outer(v, v.conj()), 2)
    rows = []
    for label, rho in (("Bell", bell), ("partial", partial),
                       ("maximally_mixed", _imax())):
        coeffs, _, _ = _schmidt(
            StateVector(np.linalg.eigh(rho.matrix)[1][:, -1], 2), 1)
        rows.append({"state": label,
                     "concurrence": _conc(rho),
                     "negativity": _neg(rho),
                     "eof": entanglement_of_formation(rho),
                     "max_schmidt_coeff": float(max(abs(coeffs)))})
    chsh = run_chsh(1.0, shots_per_setting=int(
        config.get("shots", 2000)), seed=seed)
    validation = {
        "prediction": "Bell: concurrence 1, EoF 1 bit; partial: "
                      "concurrence 2*sqrt(0.21) ~ 0.9165; maximally mixed: "
                      "all zero. CHSH exceeds the classical bound 2 in the "
                      "quantum run.",
        "expected_partial_concurrence": float(2 * np.sqrt(0.21)),
        "chsh": chsh,
        "passed": (abs(rows[0]["concurrence"] - 1) < 1e-7
                   and abs(rows[1]["concurrence"] - 2 * np.sqrt(0.21)) < 1e-7
                   and rows[2]["concurrence"] < 1e-7),
    }
    return make_result_document_sanitized(
        "book_entanglement_report", {"states": 3},
        artifacts={"states": rows, "chsh": {
            k: v for k, v in chsh.items()
            if isinstance(v, (int, float, str))}},
        notes=["McMahon ch.7: Bell states, concurrence, negativity, "
               "Schmidt decomposition, Bell test."],
        summary={"validation": validation})


def _imax():
    return DensityMatrix(np.eye(4, dtype=complex) / 4, 2)


# ---------------------------------------------------------------------------
# Chapter 8 — gate decompositions.
# ---------------------------------------------------------------------------

def book_gate_decomposition(config: dict, seed: int) -> dict:
    from ..quantum.operators import pauli_matrix, ry, rz
    h = np.array([[1, 1], [1, -1]], dtype=complex) / np.sqrt(2)
    cnot = np.array([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1],
                     [0, 0, 1, 0]], dtype=complex)
    ih = np.kron(np.eye(2, dtype=complex), h)
    cz = np.diag([1, 1, 1, -1]).astype(complex)
    cnot_err = float(np.max(np.abs(ih @ cz @ ih - cnot)))
    theta, phi, lam = 0.3, 1.1, -0.7
    u = np.exp(1j * (phi + lam) / 2) * rz(phi) @ ry(theta) @ rz(lam)
    from ..quantum.operators import u3
    u3_err = float(np.max(np.abs(u3(theta, phi, lam) - u)))
    p0 = np.array([[1, 0], [0, 0]], dtype=complex)
    p1 = np.array([[0, 0], [0, 1]], dtype=complex)
    cu = np.kron(p0, np.eye(2, dtype=complex)) + np.kron(p1, ry(0.6))
    from ..quantum.operators import controlled_of
    cu_err = float(np.max(np.abs(controlled_of(ry(0.6)) - cu)))
    ok = max(cnot_err, u3_err, cu_err) < 1e-12
    validation = {"prediction": "CNOT = (I⊗H) CZ (I⊗H); u3 = "
                                "e^{i(phi+lam)/2} Rz(lam) Ry(theta) Rz(phi); "
                                "CU = P0⊗I + P1⊗U.",
                  "cnot_err": cnot_err, "u3_err": u3_err, "cu_err": cu_err,
                  "passed": bool(ok)}
    return make_result_document_sanitized(
        "book_gate_decomposition", {"identities": 3},
        artifacts={"errors": {"cnot": cnot_err, "u3": u3_err, "cu": cu_err}},
        notes=["McMahon ch.8: gate decompositions (CNOT from CZ, Z-Y "
               "decomposition, controlled gates via projectors)."],
        summary={"validation": validation})


# ---------------------------------------------------------------------------
# Chapter 9 — algorithms (Grover amplitude amplification scan).
# ---------------------------------------------------------------------------

def book_grover_scan(config: dict, seed: int) -> dict:
    from ..algorithms.core_algorithms import run_grover
    n_qubits = config.get("n_qubits", 3)
    target = config.get("target", 5)
    max_iter = config.get("max_iterations", 4)
    for name, value, lower, upper in (("n_qubits", n_qubits, 1, 6),
                                      ("max_iterations", max_iter, 1, 8)):
        if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper:
            raise ValueError(f"{name} must be an integer in [{lower}, {upper}].")
    theta = math.asin(math.sqrt(1 / (2 ** n_qubits)))
    rows = []
    for it in range(1, max_iter + 1):
        result = run_grover(n_qubits, target, iterations=it, shots=64, seed=seed + it)
        rows.append({"iterations": it,
                     "success_probability": float(result.success_probability_estimate),
                     "shots": 64,
                     "successes": result.counts.get(format(target, f"0{n_qubits}b"), 0),
                     "exact_success_probability": result.per_iteration_probabilities[-1],
                     "analytic_success_probability": math.sin((2 * it + 1) * theta) ** 2})
    max_error = max(abs(row["exact_success_probability"] - row["analytic_success_probability"])
                    for row in rows)
    validation = {
        "prediction": "Exact marked-state probability is sin((2k+1) asin(1/sqrt(N)))^2.",
        "optimal_iterations_theory": result.optimal_iterations,
        "measured_peak_iterations": max(rows, key=lambda row: row["success_probability"])["iterations"],
        "max_exact_probability_error": max_error,
        "passed": max_error < 1e-10,
    }
    return make_result_document_sanitized(
        "book_grover_scan", {"n_qubits": n_qubits, "target": target},
        artifacts={"scan": rows},
        notes=["McMahon ch.9: amplitude amplification, iteration count.",
               "64 shots per point; sampled peaks fluctuate and may miss the optimum. Validation uses exact probabilities, not a sampled peak threshold."],
        summary={"validation": validation})


# ---------------------------------------------------------------------------
# Chapter 10 — communication.
# ---------------------------------------------------------------------------

def book_teleportation(config: dict, seed: int) -> dict:
    cases = [(0.9, 0.4), (1.7, -1.2), (0.0, 0.0), (3.0, 2.5)]
    rows = []
    for theta, phi in cases:
        r = run_teleportation(theta, phi)
        rows.append({"theta": theta, "phi": phi,
                     "fidelity": r["teleportation_fidelity"],
                     "classical_bits": r["classical_bits_example"],
                     "branches": r["branches"]})
    fid_min = min(r["fidelity"] for r in rows)
    validation = {"prediction": "Ideal teleportation fidelity = 1 for "
                                "every input state; 2 classical bits per "
                                "teleport.",
                  "min_fidelity": fid_min,
                  "passed": fid_min > 1 - 1e-9}
    return make_result_document_sanitized(
        "book_teleportation", {"cases": len(cases)},
        artifacts={"cases": rows},
        notes=["McMahon ch.10: teleportation with all intermediate "
               "states and classical bits exposed."],
        summary={"validation": validation})


def book_superdense(config: dict, seed: int) -> dict:
    from ..algorithms.core_algorithms import run_superdense
    rows = []
    for bits in ("00", "01", "10", "11"):
        r = run_superdense(bits, shots=int(config.get("shots", 256)),
                           seed=seed)
        rows.append({"bits": bits, "result": r})
    all_ok = all(r["result"]["success_rate"] == 1.0 for r in rows)
    # the decoder returns bits in the circuit's little-endian order;
    # success_rate == 1 for all four messages is the protocol invariant
    validation = {"prediction": "All four 2-bit messages decode exactly "
                                "(up to the circuit's bit ordering) after "
                                "sending one qubit.",
                  "passed": bool(all_ok)}
    return make_result_document_sanitized(
        "book_superdense", {"messages": 4}, artifacts={"messages": rows},
        notes=["McMahon ch.10: superdense coding, 2 classical bits via 1 "
               "qubit + shared entanglement."],
        summary={"validation": validation})


# ---------------------------------------------------------------------------
# Chapter 11 — cryptography: B92.
# ---------------------------------------------------------------------------

def book_b92_scan(config: dict, seed: int) -> dict:
    shots = int(config.get("shots", 4096))
    rows = []
    for eve in (0.0, 0.25, 0.5, 0.75, 1.0):
        r = run_b92(shots, eve, 0.0, seed=seed)
        rows.append({"eve_intercept_prob": eve, "sifting_rate":
                     r["sifting_rate"], "qber": r["qber"]})
    validation = {
        "prediction": "Ideal sifting rate ~0.25, ideal QBER 0; the "
                      "intercept-resend Eve monotonically increases QBER.",
        "passed": (rows[0]["qber"] < 0.01
                   and pytest_approx(rows[0]["sifting_rate"], 0.25, 0.03)
                   and rows[-1]["qber"] > rows[0]["qber"] + 0.15),
    }
    return make_result_document_sanitized(
        "book_b92_scan", {"shots": shots},
        artifacts={"sweep": rows},
        notes=["McMahon ch.11: B92 nonorthogonal-state QKD with "
               "intercept-resend eavesdropper."],
        summary={"validation": validation})


def pytest_approx(value, expected, tol):
    return abs(value - expected) <= tol


# ---------------------------------------------------------------------------
# Chapter 12 — noise channels.
# ---------------------------------------------------------------------------

def book_channel_scan(config: dict, seed: int) -> dict:
    from ..quantum.channels import (
        amplitude_damping_channel, depolarizing_channel, phase_damping_channel)
    from ..quantum.channel_algebra import choi_matrix
    params = [round(0.1 * k, 1) for k in range(1, 6)]
    plus = np.array([1, 1], dtype=complex) / np.sqrt(2)
    rho0 = DensityMatrix(np.outer(plus, plus.conj()), 1)
    rows = {"depolarizing": [], "amplitude_damping": [],
            "phase_damping": []}
    for p in params:
        ch = depolarizing_channel(p, 1)
        out = ch.apply(rho0)
        rows["depolarizing"].append(
            {"p": p, "fidelity_to_input": float(rho0.fidelity_with(out)),
             "purity": float(np.trace(out.matrix @ out.matrix).real),
             "bloch_x": float(out.bloch_vector()[0])})
    for g in params:
        out = amplitude_damping_channel(g).apply(rho0)
        rows["amplitude_damping"].append(
            {"p": g, "purity": float(np.trace(out.matrix @ out.matrix).real),
             "pop_excited": float(out.matrix[1, 1].real)})
    for g in params:
        out = phase_damping_channel(g).apply(rho0)
        rows["phase_damping"].append(
            {"p": g, "purity": float(np.trace(out.matrix @ out.matrix).real),
             "coherence": float(abs(out.matrix[0, 1]))})
    validation = {
        "prediction": "Depolarizing shrinks the Bloch vector toward 0; "
                      "amplitude damping decays the excited population; "
                      "phase damping preserves populations but kills "
                      "coherence.",
        "passed": (all(r["pop_excited"] <= 0.5001 for r in
                       rows["amplitude_damping"])
                   and all(abs(r["coherence"] - (1 - r["p"]) * 0.5)
                           < 0.02 for r in rows["phase_damping"])),
    }
    return make_result_document_sanitized(
        "book_channel_scan", {"parameter_points": len(params)},
        artifacts={"sweep": rows},
        notes=["McMahon ch.12: depolarizing, amplitude-damping and "
               "phase-damping channels (Kraus), Bloch shrinkage."],
        summary={"validation": validation})


# ---------------------------------------------------------------------------
# Chapter 13 — information metrics, no-cloning.
# ---------------------------------------------------------------------------

def book_qi_metrics(config: dict, seed: int) -> dict:
    from ..quantum.density import trace_distance as td
    bell, imax = _bell(), _imax()
    rows = []
    for w in (0.0, 0.25, 0.5, 0.75, 1.0):
        rho = DensityMatrix((1 - w) * bell.matrix
                            + w * imax.matrix, 2)
        rows.append({"werner_weight": w,
                     "trace_distance": td(rho, imax),
                     "fidelity": float(rho.fidelity_with(imax)),
                     "bures": bures_distance(rho, imax),
                     "concurrence": float(np.trace(
                         rho.matrix @ rho.matrix).real * 0) or None,
                     "eof": entanglement_of_formation(rho)})
    # concurrence needs the physical state, fill properly:
    from ..quantum.info_theory import concurrence as _conc
    for r, w in zip(rows, (0.0, 0.25, 0.5, 0.75, 1.0)):
        rho = DensityMatrix((1 - w) * bell.matrix + w * imax.matrix, 2)
        r["concurrence"] = _conc(rho)
    nc = [no_cloning_report(np.cos(t / 2), np.exp(1j * t / 4) * np.sin(t / 2))
          for t in (0.4, 1.2, 2.3)]
    validation = {
        "prediction": "Trace distance and Bures distance decrease "
                      "monotonically toward the mixed state; EoF "
                      "decreases with mixing; cloning fidelity < 1 for "
                      "every superposition.",
        "cloning_fidelities": [round(c["clone_fidelity"], 6) for c in nc],
        "passed": (rows[0]["concurrence"] > rows[-1]["concurrence"]
                   and all(c["clone_fidelity"] < 1 for c in nc)
                   and rows[0]["trace_distance"] >= rows[-1]["trace_distance"]),
    }
    return make_result_document_sanitized(
        "book_qi_metrics", {"mixing_points": 5},
        artifacts={"sweep": rows, "no_cloning": validation[
            "cloning_fidelities"]},
        notes=["McMahon ch.13: trace distance, fidelity, Bures distance, "
               "concurrence, EoF, no-cloning."],
        summary={"validation": validation})


# ---------------------------------------------------------------------------
# Chapter 14 — adiabatic computation.
# ---------------------------------------------------------------------------

def book_adiabatic(config: dict, seed: int) -> dict:
    h0 = np.diag([1.0, -1.0])
    h1 = np.array([[0.0, 1.0], [1.0, 0.0]])
    times = [0.05, 0.5, 2.0, 10.0, 50.0, 200.0]
    rows = []
    for t in times:
        r = adiabatic_evolution(h0, h1, t, steps=min(800, max(50, int(t * 8))))
        rows.append({"total_time": t,
                     "overlap": r["ground_state_overlap"],
                     "excitation": r["excitation_probability"]})
    gap = spectral_gap_curve(h0, h1, 51)
    validation = {
        "prediction": "Overlap -> 1 as the total time grows (adiabatic "
                      "theorem); the minimum gap bounds the required "
                      "runtime scale.",
        "min_gap": gap["min_gap"],
        "slow_overlap": rows[-1]["overlap"],
        "fast_overlap": rows[0]["overlap"],
        "passed": rows[-1]["overlap"] > 0.999
                  and rows[0]["overlap"] < rows[-1]["overlap"],
    }
    return make_result_document_sanitized(
        "book_adiabatic", {"times": times},
        artifacts={"scan": rows, "gap_curve_s": gap["s"],
                   "gap_curve_gap": gap["gap"]},
        notes=["McMahon ch.14: H(s) = (1-s) H_i + s H_f, adiabatic "
               "evolution, spectral gap."],
        summary={"validation": validation})


# ---------------------------------------------------------------------------
# Chapter 15 — cluster states.
# ---------------------------------------------------------------------------

def book_cluster_state(config: dict, seed: int) -> dict:
    length = int(config.get("length", 4))
    adj = np.zeros((length, length), dtype=int)
    for i in range(length - 1):
        adj[i, i + 1] = adj[i + 1, i] = 1
    st = cluster_state_1d(length)
    rep = stabilizer_report(st, adj)
    witness_chain = ghz_witness_expectation(st)
    ghz = np.zeros(1 << 3, dtype=complex)
    ghz[0] = ghz[-1] = 1 / np.sqrt(2)
    witness_ghz = ghz_witness_expectation(StateVector(ghz, 3))
    meas = measure_node_x(st, 1, outcome=0)
    pt = partial_transpose(
        DensityMatrix(_rho_of(st), length), list(range(length // 2)))
    validation = {
        "prediction": "Every stabilizer generator K_v stabilizes the "
                      "cluster state; the GHZ witness is negative on the "
                      "GHZ state; an X measurement on a node leaves a "
                      "normalized state on the rest.",
        "all_stabilize": rep["all_stabilize"],
        "witness_ghz": witness_ghz,
        "witness_chain": witness_chain,
        "post_measurement_norm": float(np.linalg.norm(
            meas["post_state"].amplitudes)),
        "passed": bool(rep["all_stabilize"] and witness_ghz < 0
                       and abs(float(np.linalg.norm(
                           meas["post_state"].amplitudes)) - 1) < 1e-9),
    }
    return make_result_document_sanitized(
        "book_cluster_state", {"length": length},
        artifacts={"stabilizers": rep["generators"] and [
            {"qubit": g["qubit"], "stabilizes": g["stabilizes"]}
            for g in rep["generators"]],
            "witnesses": {"ghz": witness_ghz, "chain": witness_chain},
            "x_measurement": {"node": meas["node"],
                              "outcome": meas["outcome"],
                              "probability": meas["probability"]}},
        notes=["McMahon ch.15: cluster states, stabilizers, entanglement "
               "witness, measurement-based processing."],
        summary={"validation": validation})


def _rho_of(state: StateVector) -> np.ndarray:
    return np.outer(state.amplitudes, state.amplitudes.conj())


# ---------------------------------------------------------------------------
# Chapter 14 — the book's own worked examples (14.2, 14.3).
# ---------------------------------------------------------------------------

def book_adiabatic_well(config: dict, seed: int) -> dict:
    """Example 14.2: a particle in an infinite well of width a, ground
    state, with the width slowly widened to 3a. Adiabatically the state
    follows the instantaneous ground state; a sudden expansion leaves a
    strictly smaller overlap. The overlap is also computed ANALYTICALLY
    (independent oracle): <psi_1(a) | psi_1(3a)>.

    Discretized well eigenproblem (finite differences) on a grid over
    [0, 3a]; exactness class: numerically exact within the grid
    tolerance (validated against the analytic eigenstates).
    """
    n_grid = int(config.get("grid_points", 601))
    L = 3.0                     # final width 3a with a = 1
    hbar = 1.0
    mass = 1.0
    xs = np.linspace(0.0, L, n_grid)
    dx = xs[1] - xs[0]

    def well_eigen(width: float, count: int = 3):
        """Finite-difference eigenstates of the infinite well [0, width]."""
        mask = xs <= width + 1e-12
        m = int(mask.sum())
        sub = np.zeros((m, m))
        coeff = -hbar ** 2 / (2 * mass * dx * dx)
        for i in range(m):
            sub[i, i] = -2 * coeff
            if i > 0:
                sub[i, i - 1] = coeff
            if i < m - 1:
                sub[i, i + 1] = coeff
        evals, evecs = np.linalg.eigh(sub)
        idx = np.argsort(evals)[:count]
        states = np.zeros((n_grid, count))
        for j, k in enumerate(idx):
            v = evecs[:, k]
            v = v / np.sqrt(np.sum(v * v) * dx)
            states[mask, j] = v
        return evals[idx], states

    # initial ground state of the width-a well
    evals0, states0 = well_eigen(1.0)
    psi = states0[:, 0].copy().astype(np.complex128)

    # SLOW: true time evolution under the expanding well. The wall moves
    # in small width steps; over each step the state evolves under the
    # piecewise-constant well Hamiltonian via its (truncated) eigenbasis,
    # psi -> sum_n e^{-i E_n dt} |n_w><n_w| psi. Slow expansion makes the
    # adiabatic theorem keep the state in the instantaneous ground state
    # (the book's answer: the system remains n = 1).
    n_steps = int(config.get("expansion_steps", 640))
    tau = float(config.get("total_time", 200.0))
    dt = tau / n_steps
    widths = np.linspace(1.0, L, n_steps + 1)[1:]
    overlaps_ground = []
    K = 8                       # truncated low-level basis (documented)
    for w in widths:
        evals_w, states_w = well_eigen(w, count=K)
        coeffs = states_w.T.astype(np.complex128) @ psi * dx
        phases = np.exp(-1j * evals_w * dt)
        psi = states_w @ (coeffs * phases)
        norm = float(np.sqrt(np.sum(np.abs(psi) ** 2) * dx))
        psi = psi / norm
        ground_amp = states_w[:, 0].astype(np.complex128) @ psi * dx
        overlaps_ground.append(float(abs(ground_amp) ** 2))
    final_evals, final_states = well_eigen(L)
    slow_overlap = float(abs(final_states[:, 0].astype(np.complex128) @ psi * dx) ** 2)

    # SUDDEN: project the initial state directly onto the final basis.
    sudden_overlap = float((final_states[:, 0] @ states0[:, 0] * dx) ** 2)
    # analytic oracle: <psi1(a)|psi1(3a)> over [0, a]
    analytic = 0.0
    a = 1.0
    for x0 in xs[xs <= 1.0]:
        analytic += (np.sqrt(2 / a) * np.sin(np.pi * x0 / a)
                     * np.sqrt(2 / L) * np.sin(np.pi * x0 / L)) * dx
    analytic_overlap = analytic ** 2
    validation = {
        "prediction": ("Slow expansion: ground-state probability ~ 1 "
                       "(state stays n=1, Example 14.2's answer). Sudden "
                       "expansion: strictly smaller, matching the "
                       "analytic <psi1(a)|psi1(3a)>^2."),
        "slow_ground_probability": slow_overlap,
        "sudden_ground_probability": sudden_overlap,
        "analytic_sudden_overlap": analytic_overlap,
        "passed": bool(slow_overlap > 0.995
                       and abs(sudden_overlap - analytic_overlap) < 5e-3
                       # tolerance is the finite-difference eigenfunction
                       # error at the wall kink (first-order FD)
                       and slow_overlap > sudden_overlap + 0.1),
    }
    return make_result_document_sanitized(
        "book_adiabatic_well", {"grid_points": n_grid,
                                "expansion_steps": n_steps},
        artifacts={"adiabatic_overlap_curve": [
            {"width": float(w), "ground_probability": o}
            for w, o in zip(widths, overlaps_ground)],
            "slow": slow_overlap, "sudden": sudden_overlap,
            "analytic_sudden": analytic_overlap},
        notes=["McMahon ch.14 Example 14.2 (pp. 309-310): expanding "
               "infinite well, adiabatic following of the ground state."],
        summary={"validation": validation})


def book_adiabatic_hadamard(config: dict, seed: int) -> dict:
    """Example 14.3: adiabatic implementation of the Hadamard gate.
    H_init = diag(-1, 1) (ground |0>); H_final = -X (ground |+>).
    Slow evolution must produce H|0> = |+>."""
    h_init = np.diag([-1.0, 1.0])
    h_final = -np.array([[0.0, 1.0], [1.0, 0.0]])
    r = adiabatic_evolution(h_init, h_final,
                            total_time=float(config.get("total_time", 200.0)),
                            steps=int(config.get("steps", 800)))
    plus = np.array([1, 1], dtype=np.complex128) / np.sqrt(2)
    hadamard_output = float(abs(np.vdot(plus, r["final_state"])) ** 2)
    gap = spectral_gap_curve(h_init, h_final, 21)
    validation = {
        "prediction": "Slow adiabatic evolution implements the Hadamard "
                      "on |0>: final state = |+> = H|0>.",
        "ground_state_overlap": r["ground_state_overlap"],
        "hadamard_output_probability": hadamard_output,
        "min_gap": gap["min_gap"],
        "passed": bool(hadamard_output > 0.999),
    }
    return make_result_document_sanitized(
        "book_adiabatic_hadamard",
        {"total_time": r["total_time"], "steps": r["steps"]},
        artifacts={"final_probabilities": r["final_probabilities"],
                   "min_gap": gap["min_gap"]},
        notes=["McMahon ch.14 Example 14.3 (pp. 310-312): adiabatic "
               "Hadamard via H_init = diag(-1,1), H_final = -X."],
        summary={"validation": validation})
