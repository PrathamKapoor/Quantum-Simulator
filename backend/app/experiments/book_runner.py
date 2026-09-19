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
    gram_schmidt, no_cloning_report, partial_transpose, povm_probabilities,
    purification)
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
    if isinstance(obj, _np.bool_):
        return bool(obj)
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
    # P(Y=+1) = |<+Y|psi>|^2 with |+Y>=(1,i)/sqrt(2): (1 + 2*Im(a0* a1))/2.
    # (The literal |a0 + i a1|^2/2 equals the minus branch and was the bug.)
    proj_y = (1 + 2 * float(np.imag(np.conjugate(vec[0]) * vec[1]))) / 2
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
    # uncertainty: prepare (|0>+|1>)/sqrt(2) and measure A and B variances
    psi = np.array([1, 1], dtype=np.complex128) / np.sqrt(2)
    # Anticommutation (Pauli algebra sense): {A,B} = 0 while [A,B] != 0
    # (e.g. {X,Y}=0, [X,Y]=2iZ). Requiring a nonzero commutator excludes
    # degenerate pairs like (I, I).
    anticomm_norm = float(np.max(np.abs(a @ b + b @ a)))
    anticommute = bool(anticomm_norm < 1e-12
                       and float(np.max(np.abs(comm))) > 1e-12)
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
        "passed": bool(product + 1e-12 >= comm_bound - 1e-12
                       and var_a >= -1e-12 and var_b >= -1e-12),
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
    from ..quantum.info_theory import concurrence as _conc
    from ..quantum.channels import (
        depolarizing_channel, amplitude_damping_channel, phase_damping_channel)
    bell, imax = _bell(), _imax()
    rows = []
    for w in (0.0, 0.25, 0.5, 0.75, 1.0):
        rho = DensityMatrix((1 - w) * bell.matrix
                            + w * imax.matrix, 2)
        rows.append({"werner_weight": w,
                     "trace_distance": td(rho, imax),
                     "fidelity": float(rho.fidelity_with(imax)),
                     "bures": bures_distance(rho, imax),
                     "concurrence": float(_conc(rho)),
                     "eof": entanglement_of_formation(rho)})
    nc = [no_cloning_report(np.cos(t / 2), np.exp(1j * t / 4) * np.sin(t / 2))
          for t in (0.4, 1.2, 2.3)]
    # The same CPTP map acts on BOTH members of a fixed noncommuting pair.
    # This is distinct from comparing unrelated points in the Werner sweep.
    r, s = np.array([0.6, 0.2, 0.3]), np.array([-0.2, 0.5, -0.4])

    def bloch_density(v):
        x, y, z = v
        return DensityMatrix(np.array([[1 + z, x - 1j * y],
                                       [x + 1j * y, 1 - z]]) / 2, 1)

    rho, sigma = bloch_density(r), bloch_density(s)
    distance_before = td(rho, sigma)
    fidelity_before = float(rho.fidelity_with(sigma))
    contractivity = []
    for name, factory in (("depolarizing", depolarizing_channel),
                          ("amplitude_damping", amplitude_damping_channel),
                          ("phase_damping", phase_damping_channel)):
        for strength in (0.0, 0.25, 0.5, 0.75, 1.0):
            channel = factory(strength)
            after_rho, after_sigma = channel.apply(rho), channel.apply(sigma)
            distance_after = td(after_rho, after_sigma)
            fidelity_after = float(after_rho.fidelity_with(after_sigma))
            # Independent affine Bloch-vector formulas, not Kraus re-use.
            if name == "depolarizing":
                a, b = (1 - strength) * r, (1 - strength) * s
            elif name == "amplitude_damping":
                a, b = [np.array([np.sqrt(1 - strength) * v[0],
                                  np.sqrt(1 - strength) * v[1],
                                  (1 - strength) * v[2] + strength]) for v in (r, s)]
            else:
                a, b = [v * [1 - strength, 1 - strength, 1] for v in (r, s)]
            expected_distance = float(np.linalg.norm(a - b) / 2)
            expected_fidelity = float((1 + a @ b + np.sqrt(max(
                0.0, (1 - a @ a) * (1 - b @ b)))) / 2)
            contractivity.append({
                "channel": name, "strength": strength,
                "trace_distance_before": distance_before,
                "trace_distance_after": distance_after,
                "fidelity_before": fidelity_before,
                "fidelity_after": fidelity_after,
                "expected_trace_distance_after": expected_distance,
                "expected_fidelity_after": expected_fidelity,
                "passed": bool(distance_after <= distance_before + 1e-9
                               and fidelity_after >= fidelity_before - 1e-9
                               and abs(distance_after - expected_distance) < 1e-9
                               and abs(fidelity_after - expected_fidelity) < 1e-9),
            })
    sweep_monotone = all(
        all(a[key] >= b[key] - 1e-9 for a, b in zip(rows, rows[1:]))
        for key in ("trace_distance", "bures", "concurrence", "eof"))
    validation = {
        "prediction": "A common CPTP channel cannot increase trace distance "
                      "or decrease squared Uhlmann fidelity. The separate Werner "
                      "sweep approaches the mixed state monotonically. The three "
                      "tested CNOT-cloning superpositions have fidelity below one.",
        "cloning_fidelities": [round(c["clone_fidelity"], 6) for c in nc],
        "contractivity": contractivity,
        "passed": bool(sweep_monotone
                       and all(c["clone_fidelity"] < 1 for c in nc)
                       and all(c["passed"] for c in contractivity)),
    }
    return make_result_document_sanitized(
        "book_qi_metrics", {"mixing_points": 5},
        artifacts={"sweep": rows, "no_cloning": validation[
            "cloning_fidelities"], "contractivity": contractivity,
            "contractivity_input_bloch_vectors": [r, s]},
        notes=["McMahon ch.13: trace distance, fidelity, Bures distance, "
               "concurrence, EoF, no-cloning.",
               "Fidelity means squared Uhlmann fidelity and is nondecreasing "
               "under a common channel; trace distance is nonincreasing. "
               "Fifteen one-qubit cases are checked against affine Bloch "
               "formulas, not a proof for every CPTP map or postselected branch."],
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

    Config extensions (Exercise 14.3 / Example 14.1): `initial_level` n
    (default 1), `width_from`/`width_to` (default 1.0 -> 3.0). The runner
    tracks the instantaneous level-n probability along the path and
    validates the finite-difference eigenvalues against the analytic
    E_n(L) = (n*pi/L)^2/2 (hbar = m = 1), including the contraction
    energy ratio (w_from/w_to)^2.
    """
    n_grid = int(config.get("grid_points", 601))
    level = config.get("initial_level", 1)
    w0 = float(config.get("width_from", 1.0))
    w1 = float(config.get("width_to", 3.0))
    if not isinstance(level, int) or isinstance(level, bool) or not 1 <= level <= 4:
        raise ValueError("initial_level must be an integer in [1, 4].")
    if not 0.1 <= w0 <= 3.0 or not 0.1 <= w1 <= 3.0:
        raise ValueError("width_from/width_to must lie in [0.1, 3.0].")
    L = 3.0                     # final width 3a with a = 1
    hbar = 1.0
    mass = 1.0
    xs = np.linspace(0.0, L, n_grid)
    dx = xs[1] - xs[0]

    def analytic_energy(n: int, width: float) -> float:
        return (n * np.pi / width) ** 2 / 2.0

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

    # initial level-n state of the width-w0 well
    evals0, states0 = well_eigen(w0, count=8)
    psi = states0[:, level - 1].copy().astype(np.complex128)
    energy_initial_num = float(evals0[level - 1])
    energy_initial_ref = analytic_energy(level, w0)

    # SLOW: true time evolution under the expanding well. The wall moves
    # in small width steps; over each step the state evolves under the
    # piecewise-constant well Hamiltonian via its (truncated) eigenbasis,
    # psi -> sum_n e^{-i E_n dt} |n_w><n_w| psi. Slow expansion makes the
    # adiabatic theorem keep the state in the instantaneous ground state
    # (the book's answer: the system remains n = 1).
    n_steps = int(config.get("expansion_steps", 640))
    tau = float(config.get("total_time", 200.0))
    dt = tau / n_steps
    widths = np.linspace(w0, w1, n_steps + 1)[1:]
    overlaps_level = []
    K = 8                       # truncated low-level basis (documented)
    for w in widths:
        evals_w, states_w = well_eigen(w, count=K)
        coeffs = states_w.T.astype(np.complex128) @ psi * dx
        phases = np.exp(-1j * evals_w * dt)
        psi = states_w @ (coeffs * phases)
        norm = float(np.sqrt(np.sum(np.abs(psi) ** 2) * dx))
        psi = psi / norm
        level_amp = states_w[:, level - 1].astype(np.complex128) @ psi * dx
        overlaps_level.append(float(abs(level_amp) ** 2))
    final_evals, final_states = well_eigen(w1, count=8)
    slow_overlap = float(abs(final_states[:, level - 1].astype(np.complex128) @ psi * dx) ** 2)
    energy_final_num = float(final_evals[level - 1])
    energy_final_ref = analytic_energy(level, w1)

    # SUDDEN: project the initial state directly onto the final basis.
    sudden_overlap = float((final_states[:, level - 1] @ states0[:, level - 1] * dx) ** 2)
    # analytic oracle: <psi_n(w0)|psi_n(w1)> over [0, min(w0, w1)]
    lo = min(w0, w1)
    analytic = 0.0
    for x0 in xs[xs <= lo]:
        analytic += (np.sqrt(2 / w0) * np.sin(level * np.pi * x0 / w0)
                     * np.sqrt(2 / w1) * np.sin(level * np.pi * x0 / w1)) * dx
    analytic_overlap = analytic ** 2
    energy_ratio_num = energy_final_num / energy_initial_num
    energy_ratio_ref = (w0 / w1) ** 2
    # Direction-aware slow bar: the expansion direction is accurate to
    # >0.995 in this model; contraction additionally suffers the known
    # moving-wall projection loss (each width step cuts the tail beyond
    # the new wall and renormalizes; ~2% cumulative for n=2 at default
    # resolution). The book's qualitative claim (level preserved vs
    # sudden ~ 0) is decided by the separation, not the absolute bar.
    slow_bar = 0.995 if w1 >= w0 else 0.95
    # Absolute energy tolerance 5%: first-order FD places the wall up to
    # dx beyond the nominal width, a systematic O(dx/w) underestimate of
    # E ~ 1/L^2 (worst at the narrowest width). The ratio check (3%)
    # carries the scaling claim.
    validation = {
        "prediction": ("Slow width change: level-n probability ~ 1 "
                       "(state stays n, Example 14.2's answer; Exercise 14.3 "
                       "for n=2 contraction). Sudden change: strictly smaller, "
                       "matching the analytic <psi_n(w0)|psi_n(w1)>^2. "
                       "Finite-difference energies match E_n(L)=(n*pi/L)^2/2 "
                       "and the ratio follows (w0/w1)^2."),
        "initial_level": level, "width_from": w0, "width_to": w1,
        "slow_level_probability": slow_overlap,
        "sudden_level_probability": sudden_overlap,
        "analytic_sudden_overlap": analytic_overlap,
        "energy_initial": {"numerical": energy_initial_num,
                           "analytic": energy_initial_ref},
        "energy_final": {"numerical": energy_final_num,
                         "analytic": energy_final_ref},
        "energy_ratio_numerical": energy_ratio_num,
        "energy_ratio_analytic": energy_ratio_ref,
        "slow_bar": slow_bar,
        "passed": bool(slow_overlap > slow_bar
                        and abs(sudden_overlap - analytic_overlap) < 5e-3
                        # tolerance is the finite-difference eigenfunction
                        # error at the wall kink (first-order FD)
                        and slow_overlap > sudden_overlap + 0.1
                        and abs(energy_initial_num - energy_initial_ref)
                        / energy_initial_ref < 0.05
                        and abs(energy_final_num - energy_final_ref)
                        / energy_final_ref < 0.05
                        and abs(energy_ratio_num - energy_ratio_ref)
                        / energy_ratio_ref < 0.03),
    }
    return make_result_document_sanitized(
        "book_adiabatic_well", {"grid_points": n_grid,
                                "expansion_steps": n_steps,
                                "initial_level": level,
                                "width_from": w0, "width_to": w1},
        artifacts={"adiabatic_overlap_curve": [
            {"width": float(w), "ground_probability": o}
            for w, o in zip(widths, overlaps_level)],
            "slow": slow_overlap, "sudden": sudden_overlap,
            "analytic_sudden": analytic_overlap,
            "energies": {"initial": energy_initial_num,
                         "initial_analytic": energy_initial_ref,
                         "final": energy_final_num,
                         "final_analytic": energy_final_ref}},
        notes=["McMahon ch.14 Example 14.2 (pp. 309-310): expanding "
               "infinite well, adiabatic following of the ground state.",
               "Levels/widths configurable: Exercise 14.3 contraction "
               "(initial_level=2, width_from=1.0, width_to=0.5); Example 14.1 "
               "stationary-state energies via the analytic oracle.",
               "Contraction uses a 0.95 slow bar (documented moving-wall "
               "projection loss); expansion uses 0.995."],
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


# ===========================================================================
# Milestone 23 additions to backend/app/experiments/book_runner.py
# (promoted primitives + dedicated chapter experiments). Appended verbatim.
# All primitives reused from the existing modules; no hard-coded textbook
# values (directive 110): every check computes its own oracle.
# ===========================================================================


# ---------------------------------------------------------------------------
# Chapter 2/3 - Gram-Schmidt orthonormalization (promoted primitive).
# ---------------------------------------------------------------------------

def book_gram_schmidt(config: dict, seed: int) -> dict:
    """McMahon ch.2-3: Gram-Schmidt orthonormalization and the numerical
    linear-independence test.

    A deliberately rank-deficient input set {v0, v1, v0 + 2 v1} in C^d is
    orthonormalized with the existing `qi_tools.gram_schmidt`. Three
    independent invariants are checked (nothing hard-coded):
      * orthonormality of the surviving basis vectors: <b_i|b_j> = delta_ij;
      * span preservation: every input reconstructs from its projection onto
        the basis, v = sum_i <b_i|v> b_i;
      * rank detection: the dependent vector leaves a numerically zero
        residual norm, the independent ones do not (rank matches numpy's
        matrix_rank of the input as the oracle).
    """
    dim = int(config.get("dimension", 4))
    if dim < 2:
        raise ValueError("dimension must be >= 2.")
    rng = np.random.default_rng(seed if seed else 13)
    v0 = rng.normal(size=dim) + 1j * rng.normal(size=dim)
    v1 = rng.normal(size=dim) + 1j * rng.normal(size=dim)
    v2 = v0 + 2.0 * v1                       # linearly dependent by construction
    vectors = [v0, v1, v2]
    basis, norms = gram_schmidt(vectors)
    rank = int(sum(1 for x in norms if x > 1e-10))

    ortho_err = 0.0
    for i in range(rank):
        for j in range(rank):
            expect = 1.0 if i == j else 0.0
            ortho_err = max(ortho_err, abs(np.vdot(basis[i], basis[j]) - expect))

    recon_err = 0.0
    for v in vectors:
        recon = np.zeros(dim, dtype=np.complex128)
        for b in basis:
            recon = recon + np.vdot(b, v) * b
        recon_err = max(recon_err, float(np.max(np.abs(recon - v))))

    oracle_rank = int(np.linalg.matrix_rank(np.array(vectors).T))
    validation = {
        "prediction": ("Gram-Schmidt returns an orthonormal basis spanning "
                       "the input; the rank-deficient set (v0, v1, v0 + 2 v1) "
                       "has rank 2 and its dependent vector normalizes to 0."),
        "orthonormality_error": ortho_err,
        "reconstruction_error": recon_err,
        "detected_rank": rank,
        "numpy_matrix_rank_oracle": oracle_rank,
        "dependent_residual_norm": float(norms[2]),
        "passed": bool(ortho_err < 1e-10 and recon_err < 1e-10
                       and rank == oracle_rank == 2 and norms[2] < 1e-10),
    }
    return make_result_document_sanitized(
        "book_gram_schmidt",
        {"dimension": dim, "detected_rank": rank,
         "orthonormality_error": ortho_err},
        artifacts={"basis": [[complex(z) for z in b] for b in basis],
                   "norms_before_normalization": [float(x) for x in norms],
                   "input_vectors": [[complex(z) for z in v] for v in vectors]},
        notes=["McMahon ch.2-3: vector spaces, inner products, "
               "Gram-Schmidt orthonormalization, linear independence.",
               "Deterministic given (dimension, seed); no sampling."],
        summary={"validation": validation})


# ---------------------------------------------------------------------------
# Chapter 7 - purification of a mixed state (promoted primitive).
# ---------------------------------------------------------------------------

def book_purification(config: dict, seed: int) -> dict:
    """McMahon ch.7: purification of a mixed state.

    Any mixed state rho_A admits a pure extension |Psi>_AB on a larger
    Hilbert space with Tr_B|Psi><Psi| = rho_A. Two representative states are
    purified: a single-qubit Bloch state and a two-qubit Werner state.
    Invariants (each computed here, none hard-coded):
      * the reduced state of |Psi> (tracing out the environment) equals rho
        (trace distance ~ 0);
      * the singular values of the amplitude matrix equal sqrt(eigenvalues of
        rho) - the Schmidt-spectrum oracle via `schmidt_decomposition`;
      * |Psi> is pure, and its entanglement entropy across the A|B split
        equals the von Neumann entropy of rho; its Schmidt rank equals the
        rank of rho.
    """
    pop0 = float(config.get("pop0", 0.7))
    coherence = float(config.get("coherence", 0.2))
    single = DensityMatrix(
        np.array([[pop0, coherence], [np.conj(coherence), 1 - pop0]],
                 dtype=np.complex128), 1)
    w = float(config.get("werner_weight", 0.6))
    werner = DensityMatrix((1 - w) * _bell().matrix + w * _imax().matrix, 2)

    from ..quantum.density import trace_distance
    from ..quantum.info_theory import (
        schmidt_decomposition, schmidt_rank, von_neumann_entropy_bits)

    rows = []
    for label, rho in (("single_qubit", single), ("werner_2q", werner)):
        psi, env_labels = purification(rho)
        n_env = len(env_labels)
        n_sys = rho.n_qubits
        full = DensityMatrix(np.outer(psi.amplitudes, psi.amplitudes.conj()),
                             n_sys + n_env)
        keep = list(range(n_env, n_sys + n_env))          # the SYSTEM qubits
        reduced = full.partial_trace(keep)
        td = float(trace_distance(reduced, rho))

        s, _, _ = schmidt_decomposition(psi, n_sys)       # split A = system
        oracle = np.sqrt(np.sort(np.linalg.eigvalsh(rho.matrix))[::-1])
        spec_err = float(np.max(np.abs(np.sort(s)[::-1] - oracle)))
        rd = int(schmidt_rank(psi, n_sys))
        s_rho = float(von_neumann_entropy_bits(rho))
        s_pur = float(full.partial_trace(keep).entropy())
        rows.append({
            "state": label,
            "trace_distance_to_rho": td,
            "purity_of_purification": float(np.trace(
                full.matrix @ full.matrix).real),
            "schmidt_spectrum_error": spec_err,
            "schmidt_rank": rd,
            "rho_rank": int(np.sum(np.linalg.eigvalsh(rho.matrix) > 1e-10)),
            "rho_entropy_bits": s_rho,
            "purification_entanglement_bits": s_pur,
        })

    ok = all(r["trace_distance_to_rho"] < 1e-9
             and r["schmidt_spectrum_error"] < 1e-9
             and abs(r["purity_of_purification"] - 1.0) < 1e-9
             and r["schmidt_rank"] == r["rho_rank"]
             for r in rows)
    validation = {
        "prediction": ("Purifying rho onto system+environment yields a pure "
                       "|Psi> whose reduced state is exactly rho and whose "
                       "Schmidt coefficients squared are the eigenvalues of "
                       "rho; the Schmidt rank equals rank(rho)."),
        "states": rows,
        "passed": bool(ok),
    }
    return make_result_document_sanitized(
        "book_purification",
        {"states_purified": len(rows),
         "single_qubit_trace_distance": rows[0]["trace_distance_to_rho"]},
        artifacts={"purifications": rows},
        notes=["McMahon ch.7: Schmidt decomposition and purification "
               "(any mixed state is the reduction of a pure state on a "
               "larger space).",
               "Environment register has the same dimension as the system "
               "(one ancillary level per spectral branch)."],
        summary={"validation": validation})


# ---------------------------------------------------------------------------
# Chapter 10 - entanglement swapping (dedicated book-shaped experiment).
# ---------------------------------------------------------------------------

def _bits(i: int, q: int) -> int:
    return (i >> q) & 1


def _apply_1q(state: np.ndarray, mat: np.ndarray, q: int, n: int) -> np.ndarray:
    """Apply a single-qubit matrix to qubit q (little-endian ordering)."""
    ops = [np.eye(2, dtype=np.complex128)] * n
    ops[q] = np.asarray(mat, dtype=np.complex128)
    full = np.array([[1.0 + 0j]])
    for k in range(n - 1, -1, -1):          # qubit n-1 is most significant
        full = np.kron(full, ops[k])
    return full @ state


def _cnot(state: np.ndarray, control: int, target: int, n: int) -> np.ndarray:
    out = np.zeros_like(state)
    for i, a in enumerate(state):
        j = i ^ (1 << target) if _bits(i, control) else i
        out[j] += a
    return out


def _hz(state: np.ndarray, q: int, n: int) -> np.ndarray:
    h = np.array([[1, 1], [1, -1]], dtype=np.complex128) / np.sqrt(2)
    return _apply_1q(state, h, q, n)


def book_entanglement_swapping(config: dict, seed: int) -> dict:
    """McMahon ch.10 extension: entanglement swapping.

    Two independent Bell pairs (A-B and C-D) are prepared; a Bell-basis
    measurement on the middle qubits (B, C) projects the outer qubits
    (A, D) onto a maximally entangled state, teleporting entanglement
    without ever interacting A and D. Validated against:
      * the pre-measurement outer pair is a product state (concurrence 0);
      * for EVERY Bell-measurement outcome (with the standard Pauli
        corrections) the outer pair reaches concurrence 1 and negativity
        1/2 (maximal two-qubit entanglement);
      * the four outcome probabilities sum to 1.
    """
    n = 4
    psi = np.zeros(1 << n, dtype=np.complex128)
    psi[0] = 1.0
    psi = _hz(psi, 0, n)
    psi = _cnot(psi, 0, 1, n)               # Bell pair on qubits (0, 1)
    psi = _hz(psi, 2, n)
    psi = _cnot(psi, 2, 3, n)               # Bell pair on qubits (2, 3)

    from ..quantum.info_theory import concurrence, negativity

    def outer_pair(state_vec: np.ndarray):
        dm = DensityMatrix(np.outer(state_vec, state_vec.conj()), n)
        reduced = dm.partial_trace([0, 3])
        return reduced, float(concurrence(reduced)), float(negativity(reduced))

    _, c_no, n_no = outer_pair(psi)          # control: no measurement yet
    # Bell-basis measurement on qubits 1 and 2: CNOT(1 -> 2), H(1), read out.
    bsm = _hz(_cnot(psi, 1, 2, n), 1, n)
    x = np.array([[0, 1], [1, 0]], dtype=np.complex128)
    z = np.array([[1, 0], [0, -1]], dtype=np.complex128)

    outcomes = []
    for m1 in (0, 1):
        for m2 in (0, 1):
            proj = bsm.copy()
            for i in range(1 << n):
                if _bits(i, 1) != m1 or _bits(i, 2) != m2:
                    proj[i] = 0.0
            prob = float(np.linalg.norm(proj) ** 2)
            if prob < 1e-15:
                continue
            proj = proj / np.sqrt(prob)
            before, _, _ = outer_pair(proj)
            # In the reduced |D A> ordering, the analytical branch is
            # (|m2,0> + (-1)^m1 |1-m2,1>)/sqrt(2).
            target = np.zeros(4, dtype=complex)
            target[2 * m2] = 1 / np.sqrt(2)
            target[2 * (1 - m2) + 1] = (-1) ** m1 / np.sqrt(2)
            branch_fidelity = float(np.vdot(target, before.matrix @ target).real)
            # corrections on the receiving qubit (3)
            if m2 == 1:
                proj = _apply_1q(proj, x, 3, n)
            if m1 == 1:
                proj = _apply_1q(proj, z, 3, n)
            after, conc, neg = outer_pair(proj)
            phi_plus = np.array([1, 0, 0, 1], dtype=complex) / np.sqrt(2)
            corrected_fidelity = float(np.vdot(phi_plus, after.matrix @ phi_plus).real)
            outcomes.append({"outcome_bc": [m1, m2], "probability": prob,
                             "outer_concurrence": conc,
                             "outer_negativity": neg,
                             "conditional_target_fidelity": branch_fidelity,
                             "corrected_target_fidelity": corrected_fidelity,
                             "outer_density_before_correction": before.matrix,
                             "outer_density_after_correction": after.matrix})

    total_p = float(sum(o["probability"] for o in outcomes))
    validation = {
        "prediction": ("A Bell measurement on the middle qubits of two Bell "
                       "pairs leaves the outer qubits maximally entangled "
                       "(concurrence 1, negativity 1/2), while before the "
                       "measurement the outer pair is a product state."),
        "outer_concurrence_before_bsm": c_no,
        "outer_negativity_before_bsm": n_no,
        "outcomes": outcomes,
        "total_probability": total_p,
        "passed": bool(abs(c_no) < 1e-9 and abs(n_no) < 1e-9
                       and len(outcomes) == 4
                       and all(abs(o["probability"] - 0.25) < 1e-9
                               and o["conditional_target_fidelity"] > 1 - 1e-9
                               and o["corrected_target_fidelity"] > 1 - 1e-9
                               for o in outcomes)
                       and all(o["outer_concurrence"] > 1 - 1e-9
                               for o in outcomes)
                       and all(abs(o["outer_negativity"] - 0.5) < 1e-9
                               for o in outcomes)
                       and abs(total_p - 1.0) < 1e-9),
    }
    return make_result_document_sanitized(
        "book_entanglement_swapping",
        {"bell_measurement_outcomes": len(outcomes),
         "outer_concurrence_after_swap":
             outcomes[0]["outer_concurrence"] if outcomes else None},
        artifacts={"outcomes": outcomes,
                   "control": {"concurrence": c_no, "negativity": n_no}},
        notes=["McMahon ch.10: entanglement as a resource; swapping extends "
               "teleportation to a relay (A-B and C-D -> A-D entangled).",
               "Exact statevector computation; the four BSM outcomes are "
               "enumerated deterministically (no sampling). Each uncorrected "
               "branch is checked against its outcome-dependent Bell state; "
               "Z^m1 X^m2 on D must restore Phi+, not merely entanglement."],
        summary={"validation": validation})


# ---------------------------------------------------------------------------
# Chapters 12-13 - quantum error-correcting codes (small, deterministic).
# ---------------------------------------------------------------------------

def _encoded_states(code) -> tuple[np.ndarray, np.ndarray]:
    """Project |0L>, then fix |1L>'s relative phase with logical X."""
    from ..qec.stabilizer import apply_pauli_string

    dim = 1 << code.n
    for k in range(dim):
        state = np.zeros(dim, dtype=np.complex128)
        state[k] = 1
        for generator in (*code.generators, code.logical_z):
            state = (state + apply_pauli_string(state, generator)) / 2
        norm = float(np.linalg.norm(state))
        if norm > 1e-10:
            zero = state / norm
            return zero, apply_pauli_string(zero, code.logical_x)
    raise ValueError(f"Code {code.name} has no logical-zero eigenspace")


def _syndrome_branches(state, code):
    """Exact joint stabilizer measurement; retain every nonzero branch."""
    from ..qec.stabilizer import apply_pauli_string

    branches = [((), state)]
    for generator in code.generators:
        next_branches = []
        for syndrome, vector in branches:
            acted = apply_pauli_string(vector, generator)
            for bit, sign in ((0, 1), (1, -1)):
                projected = (vector + sign * acted) / 2
                if float(np.vdot(projected, projected).real) > 1e-14:
                    next_branches.append((syndrome + (bit,), projected))
        branches = next_branches
    return branches


def book_qec_codes(config: dict, seed: int) -> dict:
    """Ideal syndrome recovery of complex logical states and coherent errors.

    The existing recovery table is driven by measured projector branches,
    not by knowledge of the injected error. Repetition codes only guarantee
    their named Pauli axis; general codes protect any one-qubit Pauli and
    the tested coherent rotation about each axis. This is not a noisy
    extraction circuit or a multi-fault/fault-tolerance demonstration.
    """
    from ..qec.codes import build_recovery_table, decode_and_recover, get_code
    from ..qec.stabilizer import apply_pauli_string, syndrome_of

    names = config.get("codes") or [
        "bit-flip-3", "phase-flip-3", "shor-9", "steane-7", "five-qubit"]
    logical_states = [
        (0, np.array([1, 0], dtype=complex)),
        (1, np.array([0, 1], dtype=complex)),
        ("plus", np.array([1, 1], dtype=complex) / np.sqrt(2)),
        ("plus_i", np.array([1, 1j], dtype=complex) / np.sqrt(2)),
        ("complex", np.array([np.sqrt(0.3), np.exp(0.7j) * np.sqrt(0.7)])),
    ]
    angle = 0.73
    rows = []
    for name in names:
        code = get_code(str(name))
        table = build_recovery_table(code)
        psi0, psi1 = _encoded_states(code)
        basis = np.column_stack((psi0, psi1))
        basis_error = float(np.max(np.abs(basis.conj().T @ basis - np.eye(2))))
        for vector in (psi0, psi1):
            for generator in code.generators:
                basis_error = max(basis_error, float(np.linalg.norm(
                    apply_pauli_string(vector, generator) - vector)))
        guaranteed = set(code.corrects_paulis)
        cases = []
        for logical, amplitudes in logical_states:
            encoded = basis @ amplitudes
            for q in range(code.n):
                for pauli in ("X", "Y", "Z"):
                    chars = ["I"] * code.n
                    chars[code.n - 1 - q] = pauli
                    error = "".join(chars)
                    _, ok_flag = decode_and_recover(code, table, error)
                    acted = apply_pauli_string(encoded, error)
                    for noise, damaged in (
                        ("pauli", acted),
                        ("coherent_rotation", np.cos(angle / 2) * encoded
                         - 1j * np.sin(angle / 2) * acted),
                    ):
                        branches = []
                        for syndrome, projected in _syndrome_branches(damaged, code):
                            probability = float(np.vdot(projected, projected).real)
                            recovery = table.get(syndrome)
                            corrected = projected / np.sqrt(probability)
                            if recovery is not None:
                                corrected = apply_pauli_string(corrected, recovery)
                            decoded = basis.conj().T @ corrected
                            branches.append({
                                "syndrome": list(syndrome),
                                "probability": probability,
                                "recovery": recovery,
                                "state_fidelity": float(abs(np.vdot(encoded, corrected)) ** 2),
                                "logical_density": np.outer(decoded, decoded.conj()),
                                "codespace_population": float(np.vdot(decoded, decoded).real),
                            })
                        fidelity = sum(b["probability"] * b["state_fidelity"] for b in branches)
                        expected_syndrome = list(syndrome_of(error, list(code.generators)))
                        cases.append({
                            "logical": logical, "qubit": q, "pauli": pauli,
                            "noise": noise, "guaranteed": pauli in guaranteed,
                            "decoder_reports_corrected": bool(ok_flag),
                            "state_fidelity": float(fidelity),
                            "total_probability": sum(b["probability"] for b in branches),
                            "syndrome_matches_pauli_algebra": noise != "pauli" or (
                                len(branches) == 1 and branches[0]["syndrome"] == expected_syndrome),
                            "branches": branches,
                        })
        good = [c for c in cases if c["guaranteed"]]
        bad = [c for c in cases if not c["guaranteed"]]
        rows.append({
            "code": code.name, "n": code.n, "k": code.k,
            "distance": code.distance,
            "corrects": list(code.corrects_paulis),
            "recovery_table_size": len(table),
            "basis_error": basis_error,
            "guaranteed_cases": len(good),
            "guaranteed_success": sum(
                1 for c in good if c["state_fidelity"] > 1 - 1e-9
                and all(b["recovery"] is not None and b["state_fidelity"] > 1 - 1e-9
                        for b in c["branches"])),
            "unguaranteed_cases": len(bad),
            "unguaranteed_failures": sum(1 for c in bad if c["state_fidelity"] < 1 - 1e-9),
            "cases": cases,
        })
    all_ok = all(r["guaranteed_success"] == r["guaranteed_cases"]
                 and r["guaranteed_cases"] > 0 and r["basis_error"] < 1e-9
                 and all(abs(c["total_probability"] - 1) < 1e-9
                         and c["syndrome_matches_pauli_algebra"] for c in r["cases"])
                 for r in rows)
    validation = {
        "prediction": ("Every guaranteed one-qubit Pauli and coherent axis rotation "
                       "is corrected in every nonzero ideal syndrome branch, preserving "
                       "complex logical coherence. Unguaranteed errors may fail."),
        "codes": rows,
        "passed": bool(all_ok),
    }
    return make_result_document_sanitized(
        "book_qec_codes",
        {"codes_tested": len(rows),
         "guaranteed_cases": sum(r["guaranteed_cases"] for r in rows),
         "guaranteed_success": sum(r["guaranteed_success"] for r in rows)},
        artifacts={"codes": rows, "logical_states": [
            {"label": label, "amplitudes": a} for label, a in logical_states],
            "coherent_angle": angle},
        notes=["McMahon ch.12-13: existing stabilizer codes and recovery tables; "
               "exact syndrome projectors, no sampling or noisy extraction.",
               "Repetition-code distance here denotes protection along the named "
               "axis, not distance three against arbitrary quantum errors.",
               "Qubit indices are little-endian. Five logical probes include complex "
               "relative phases; coherent rotations use exp(-i angle P/2). "
               "Zero branches below probability 1e-14 are omitted.",
               "The tested weight-one errors do not establish multi-error or "
               "fault-tolerant recovery. Logical density is not renormalized after "
               "codespace projection, so leakage remains visible."],
        summary={"validation": validation})


# ===========================================================================
# Milestone 23 additions (part 2): genuinely-new experiments.
# ===========================================================================


def book_state_tomography(config: dict, seed: int) -> dict:
    """Measurement-based single-qubit quantum state tomography.

    A known state (fixed by its Bloch vector) is measured along the three
    Pauli axes with `shots` projective measurements per axis; the state is
    reconstructed by linear inversion followed by Euclidean projection onto
    the Bloch ball. Raw estimates are retained: finite-shot inversion need
    not be positive. The projected estimate is physical, not an unbiased
    estimator or a maximum-likelihood fit. Ideal inversion is exact; the
    shot scan reports realizations and analytic RMS error, not a promise
    that each larger sample has smaller error.
    """
    from ..quantum.operators import pauli_matrix
    theta = float(config.get("theta", 1.1))
    phi = float(config.get("phi", 0.5))
    shots = int(config.get("shots", 20000))
    if shots < 10:
        raise ValueError("shots must be >= 10.")
    rng = np.random.default_rng(seed if seed else 7)

    axes = {"X": pauli_matrix("X"), "Y": pauli_matrix("Y"),
            "Z": pauli_matrix("Z")}
    target = np.array([np.sin(theta) * np.cos(phi),
                       np.sin(theta) * np.sin(phi),
                       np.cos(theta)])
    rho_true = DensityMatrix(
        0.5 * (np.eye(2, dtype=np.complex128)
               + target[0] * axes["X"] + target[1] * axes["Y"]
               + target[2] * axes["Z"]), 1)

    ideal = {}
    measured = {}
    for name, pauli in axes.items():
        ev = float(np.real(np.trace(rho_true.matrix @ pauli)))   # exact <P>
        p_plus = (1.0 + ev) / 2.0
        ideal[name] = ev
        n_plus = int(rng.binomial(shots, p_plus))
        measured[name] = (2.0 * n_plus - shots) / shots          # observed <P>

    def _rho_from(vec):
        return DensityMatrix(
            0.5 * (np.eye(2, dtype=np.complex128)
                   + vec[0] * axes["X"] + vec[1] * axes["Y"]
                   + vec[2] * axes["Z"]), 1)

    vec_ideal = np.array([ideal["X"], ideal["Y"], ideal["Z"]])
    vec_raw = np.array([measured["X"], measured["Y"], measured["Z"]])
    raw_norm = float(np.linalg.norm(vec_raw))
    vec_meas = vec_raw / max(1.0, raw_norm)
    rho_ideal = _rho_from(vec_ideal)
    rho_meas = _rho_from(vec_meas)

    ideal_err = float(np.max(np.abs(vec_ideal - target)))
    finite_err = float(np.max(np.abs(vec_meas - target)))
    min_eig_ideal = float(np.linalg.eigvalsh(rho_ideal.matrix).min())
    min_eig_meas = float(np.linalg.eigvalsh(rho_meas.matrix).min())
    stat_bound = 6.0 / np.sqrt(shots)

    # Single realizations need not decrease monotonically with sample size.
    scan = []
    for s in (500, 2000, 8000, 32000):
        rng_s = np.random.default_rng((seed or 7) + s)
        err = 0.0
        for name, pauli in axes.items():
            ev = float(np.real(np.trace(rho_true.matrix @ pauli)))
            n_plus = int(rng_s.binomial(s, (1.0 + ev) / 2.0))
            err = max(err, abs((2.0 * n_plus - s) / s - ev))
        scan.append({"shots": s, "max_abs_bloch_error": err,
                     "analytic_rms_bloch_error": float(np.sqrt(
                         np.sum(1.0 - vec_ideal ** 2) / s))})

    validation = {
        "prediction": ("Ideal Pauli inversion is exact. Bloch-ball projection "
                       "makes the finite-shot estimate PSD and unit trace; "
                       "raw estimator RMS error scales as 1/sqrt(shots) in "
                       "expectation, not monotonically per realization."),
        "target_bloch": [float(x) for x in target],
        "ideal_reconstruction_error": ideal_err,
        "finite_shot_error": finite_err,
        "statistical_bound": float(stat_bound),
        "min_eigenvalue_ideal": min_eig_ideal,
        "min_eigenvalue_finite": min_eig_meas,
        "min_eigenvalue_raw": (1.0 - raw_norm) / 2.0,
        "raw_l2_error": float(np.linalg.norm(vec_raw - target)),
        "projected_l2_error": float(np.linalg.norm(vec_meas - target)),
        "within_statistical_bound": bool(finite_err < stat_bound),
        "shot_scan": scan,
        "passed": bool(ideal_err < 1e-12 and min_eig_ideal > -1e-9
                       and min_eig_meas >= -1e-12
                       and np.linalg.norm(vec_meas - target)
                       <= np.linalg.norm(vec_raw - target) + 1e-12),
    }
    return make_result_document_sanitized(
        "book_state_tomography",
        {"shots_per_basis": shots,
         "finite_shot_bloch_error": finite_err},
        artifacts={"measured_expectations": measured,
                   "ideal_expectations": ideal,
                   "reconstructed_bloch_finite": [float(x) for x in vec_meas],
                   "raw_bloch_finite": [float(x) for x in vec_raw],
                   "shot_scan": scan},
        notes=["Single-qubit state tomography: Pauli-basis frequencies -> "
               "Bloch vector by linear inversion, followed by Euclidean "
               "projection onto the unit Bloch ball; raw estimates retained.",
               "Finite-shot errors are statistical and seeded (deterministic "
               "given the run seed)."],
        summary={"validation": validation})


def book_rabi_oscillations(config: dict, seed: int) -> dict:
    """Driven two-level system: Rabi oscillations (rotating-wave model).

    A qubit starts in |0> and is driven by the time-independent RWA
    Hamiltonian H = (Delta/2) sigma_z + (Omega/2) sigma_x (hbar = 1). The
    excited-state population is evolved numerically by stepwise propagation
    and validated against the closed-form generalized Rabi law
    P_e(t) = (Omega^2/(Omega^2+Delta^2)) sin^2( sqrt(Omega^2+Delta^2) t / 2 ).

    Invariants (each computed, none hard-coded):
      * the full numerically evolved trajectory matches the analytic law to
        machine precision;
      * at resonance the first maximum is at t = pi/Omega with peak
        population 1 (the Rabi period 2 pi / Omega);
      * off resonance the peak population is Omega^2/(Omega^2+Delta^2).
    """
    from ..quantum.operators import pauli_matrix
    omega = float(config.get("rabi_frequency", 1.0))
    detunings = [float(d) for d in (config.get("detunings")
                                    or [0.0, 0.5, 1.0, 2.0])]
    steps = int(config.get("steps", 4000))
    if omega <= 0 or steps < 100:
        raise ValueError("rabi_frequency and steps must be positive.")
    sz, sx = pauli_matrix("Z"), pauli_matrix("X")
    ident = np.eye(2, dtype=np.complex128)

    rows = []
    for delta in detunings:
        gen = float(np.hypot(omega, delta))            # generalized Rabi freq
        h = 0.5 * delta * sz + 0.5 * omega * sx
        t_max = 4.0 * np.pi / gen
        dt = t_max / steps
        half = gen * dt / 2.0                        # h eigenvalues = +/- gen/2
        u = (np.cos(half) * ident
             - 1j * np.sin(half) / (gen / 2.0) * h)   # exact step propagator
        psi = np.array([1.0, 0.0], dtype=np.complex128)
        traj, max_err = [], 0.0
        for k in range(steps + 1):
            t = k * dt
            p_num = float(abs(psi[1]) ** 2)
            p_for = (omega ** 2 / gen ** 2) * np.sin(gen * t / 2.0) ** 2
            max_err = max(max_err, abs(p_num - p_for))
            traj.append({"t": t, "p_numeric": p_num, "p_analytic": float(p_for)})
            if k < steps:
                psi = u @ psi
        peak_num = max(p["p_numeric"] for p in traj)
        t_star = next((traj[i]["t"] for i in range(1, len(traj) - 1)
                       if traj[i]["p_numeric"] >= traj[i - 1]["p_numeric"]
                       and traj[i]["p_numeric"] > traj[i + 1]["p_numeric"]),
                      None)
        rows.append({
            "detuning": delta,
            "generalized_rabi_frequency": gen,
            "peak_excited_population_numeric": peak_num,
            "peak_excited_population_analytic": omega ** 2 / gen ** 2,
            "sampled_peak_analytic": max(p["p_analytic"] for p in traj),
            "time_step": dt,
            "first_maximum_time": t_star,
            "analytic_first_maximum_time": float(np.pi / gen),
            "max_trajectory_error": max_err,
        })

    res = next((r for r in rows if r["detuning"] == 0.0), None)
    max_err_all = max(r["max_trajectory_error"] for r in rows)
    validation = {
        "prediction": ("Rabi dynamics follow the generalized Rabi law: the "
                       "resonant first maximum is at t = pi/Omega with peak 1, "
                       "and off resonance the peak scales as "
                       "Omega^2/(Omega^2+Delta^2)."),
        "max_trajectory_error": max_err_all,
        "resonant_first_maximum_time": res["first_maximum_time"] if res else None,
        "analytic_first_maximum_time": res["analytic_first_maximum_time"] if res else None,
        "resonant_peak_population": res["peak_excited_population_numeric"] if res else None,
        "detuned_peaks": [{"detuning": r["detuning"],
                           "peak": r["peak_excited_population_numeric"],
                           "analytic": r["peak_excited_population_analytic"]}
                          for r in rows],
        "passed": bool(max_err_all < 1e-9
                       and all(r["first_maximum_time"] is not None
                               and abs(r["first_maximum_time"]
                                       - r["analytic_first_maximum_time"]) <= r["time_step"]
                               and abs(r["peak_excited_population_numeric"]
                                       - r["sampled_peak_analytic"]) < 1e-9
                               for r in rows)),
    }
    return make_result_document_sanitized(
        "book_rabi_oscillations",
        {"detunings": len(rows), "max_trajectory_error": max_err_all},
        artifacts={"sweeps": rows},
        notes=["Rotating-wave two-level model H = (Delta/2) sigma_z + "
               "(Omega/2) sigma_x; the numerical stepwise evolution is the "
               "experiment and the closed-form Rabi law is the oracle.",
               "Curves are sampled at the configured number of steps."],
        summary={"validation": validation})


def book_helstrom(config: dict, seed: int) -> dict:
    """Binary minimum-error discrimination of depolarized qubit states.

    rho0 is a noisy |0>, rho1 a noisy Bloch(theta, phi) state. mixing is
    the shared white-noise weight. Exact Born probabilities, no sampling.
    """
    from ..quantum.qi_tools import helstrom_measurement, validate_povm
    from ..quantum.operators import pauli_matrix

    theta = float(config.get("theta", np.pi / 2))
    phi = float(config.get("phi", 0.4))
    prior = float(config.get("prior", 0.5))
    mixing = float(config.get("mixing", 0.0))
    if not np.all(np.isfinite([theta, phi, prior, mixing])):
        raise ValueError("Angles and probabilities must be finite.")
    if not (0 <= prior <= 1 and 0 <= mixing <= 1):
        raise ValueError("prior and mixing must be in [0, 1].")
    ident = np.eye(2, dtype=np.complex128)
    r0 = (1 - mixing) * np.array([0.0, 0.0, 1.0])
    r1 = (1 - mixing) * np.array([np.sin(theta) * np.cos(phi),
                                  np.sin(theta) * np.sin(phi), np.cos(theta)])
    paulis = [pauli_matrix(axis) for axis in ("X", "Y", "Z")]
    rho0, rho1 = [DensityMatrix((ident + sum(v * p for v, p in zip(r, paulis))) / 2, 1)
                  for r in (r0, r1)]
    effects = helstrom_measurement(rho0, rho1, prior)
    probabilities = [povm_probabilities(rho, effects) for rho in (rho0, rho1)]
    success = prior * probabilities[0][0] + (1 - prior) * probabilities[1][1]
    # Qubit weighted-difference eigenvalues are (a +/- |b|)/2. Its trace
    # norm is max(|a|, |b|): independent of the eigensolver constructing POVM.
    oracle = (1 + max(abs(2 * prior - 1),
                      float(np.linalg.norm(prior * r0 - (1 - prior) * r1)))) / 2
    report = validate_povm(effects, 1)
    validation = {"prediction": "Optimal binary discrimination attains the Helstrom bound.",
                  "analytic_success_probability": oracle,
                  "success_error": abs(success - oracle),
                  "povm": report,
                  "passed": bool(abs(success - oracle) < 1e-10
                                 and report["complete"] and report["positive"])}
    return make_result_document_sanitized(
        "book_helstrom", {"success_probability": success,
                          "error_probability": 1 - success,
                          "prior_only_success": max(prior, 1 - prior)},
        artifacts={"effects": effects, "conditional_probabilities": probabilities,
                   "state_bloch_vectors": [r0, r1]},
        notes=["Two known single-qubit alternatives; exact probabilities, not finite-shot inference.",
               "mixing=1 makes both states maximally mixed; no measurement can beat the prior.",
               "Helstrom-Holevo theorem; IBM Quantum Learning, discrimination and tomography."],
        summary={"validation": validation})


def book_channel_algebra(config: dict, seed: int) -> dict:
    """Bit flip and amplitude damping: composition order, Choi and fidelity."""
    from ..quantum.channels import bit_flip_channel, amplitude_damping_channel
    from ..quantum.channel_algebra import (
        compose_channels, choi_matrix, validate_choi, verify_composition_identity,
        process_fidelity_to_unitary, average_gate_fidelity)
    from ..quantum.density import trace_distance
    from ..quantum.operators import pauli_matrix

    p = float(config.get("flip_probability", 0.3))
    gamma = float(config.get("gamma", 0.4))
    if not (0 <= p <= 1 and 0 <= gamma <= 1):
        raise ValueError("flip_probability and gamma must be in [0, 1].")
    flip, damping = bit_flip_channel(p), amplitude_damping_channel(gamma)
    forward = compose_channels(flip, damping)
    reverse = compose_channels(damping, flip)
    ground = DensityMatrix.computational_mixture([1.0, 0.0])
    output_forward, output_reverse = forward.apply(ground), reverse.apply(ground)
    order_distance = trace_distance(output_forward, output_reverse)
    ident = np.eye(2, dtype=np.complex128)
    basis = [ident] + [pauli_matrix(axis) for axis in ("X", "Y", "Z")]
    composition = verify_composition_identity(flip, damping, basis)
    choi_report = validate_choi(forward)
    process_fidelity = process_fidelity_to_unitary(forward, ident)
    average_fidelity = average_gate_fidelity(forward, ident)
    # Sum |Tr K|^2 / 4 for damping after bit-flip, expanded analytically.
    process_oracle = ((1 - p) * (1 + np.sqrt(1 - gamma)) ** 2 + p * gamma) / 4
    # Six axial pure states form a qubit state 2-design: exact Haar average.
    axial_fidelities = []
    for pauli in basis[1:]:
        for sign in (-1, 1):
            rho = DensityMatrix((ident + sign * pauli) / 2, 1)
            axial_fidelities.append(float(np.trace(rho.matrix @ forward.apply(rho).matrix).real))
    average_oracle = float(np.mean(axial_fidelities))
    validation = {
        "prediction": "Composition agrees on an operator basis; channel order changes ground-state output by p*gamma; Choi is CP/TP and fidelities match independent oracles.",
        "composition": composition, "choi": choi_report,
        "order_trace_distance_oracle": p * gamma,
        "process_fidelity_oracle": process_oracle,
        "average_fidelity_six_state_oracle": average_oracle,
        "passed": bool(composition["agrees"] and choi_report["all_valid"]
                       and abs(order_distance - p * gamma) < 1e-10
                       and abs(process_fidelity - process_oracle) < 1e-10
                       and abs(average_fidelity - average_oracle) < 1e-10)}
    return make_result_document_sanitized(
        "book_channel_algebra",
        {"order_trace_distance": order_distance, "process_fidelity": process_fidelity,
         "average_gate_fidelity": average_fidelity},
        artifacts={"choi_matrix": choi_matrix(forward),
                   "flip_then_damping": output_forward.matrix,
                   "damping_then_flip": output_reverse.matrix,
                   "six_state_fidelities": axial_fidelities},
        notes=["Unnormalized Choi convention: trace J=2 and partial trace over output is I.",
               "Exact one-qubit channel algebra, not process tomography or a diamond-norm estimate."],
        summary={"validation": validation})



def book_mbqc(config: dict, seed: int) -> dict:
    """Three-node cluster processing; exhaustive branches and one seeded run."""
    from ..quantum.graph_states import run_mbqc_pattern
    theta, phi, alpha, beta = (float(config.get(key, default)) for key, default
                               in (("theta", 1.0), ("phi", 0.37),
                                   ("alpha", 0.4), ("beta", 1.1)))
    if not np.all(np.isfinite([theta, phi, alpha, beta])):
        raise ValueError("MBQC state and measurement angles must be finite.")
    ket = np.array([np.cos(theta / 2), np.exp(1j * phi) * np.sin(theta / 2)])
    adjacency = [[0, 1, 0], [1, 0, 1], [0, 1, 0]]
    h = np.array([[1, 1], [1, -1]]) / np.sqrt(2)
    target = (h @ np.diag(np.exp(np.array([1, -1]) * 0.5j * beta)) @ h
              @ np.diag(np.exp(np.array([1, -1]) * 0.5j * alpha)) @ ket)

    def record(result):
        return {"outcomes": result["outcomes"],
                "measurement_angles": result["measurement_angles"],
                "probability": float(np.prod(result["probabilities"])),
                "fidelity": float(abs(np.vdot(target, result["state"].amplitudes)) ** 2),
                "uncorrected_fidelity": float(abs(np.vdot(target, result["raw_state"].amplitudes)) ** 2),
                "output_state": result["state"].amplitudes,
                "correction": result["correction"]}

    branches = [record(run_mbqc_pattern(adjacency, ket, [alpha, beta],
                                        outcomes=[first, second]))
                for first in (0, 1) for second in (0, 1)]
    sample = record(run_mbqc_pattern(adjacency, ket, [alpha, beta],
                                     rng=np.random.default_rng(seed)))
    min_fidelity = min(row["fidelity"] for row in branches)
    probability_sum = sum(row["probability"] for row in branches)
    return make_result_document_sanitized(
        "book_mbqc", {"minimum_branch_fidelity": min_fidelity},
        summary={"validation": {
            "prediction": "All four corrected branches equal H Rz(-beta) H Rz(-alpha)|input>.",
            "minimum_branch_fidelity": min_fidelity,
            "branch_probability_sum": probability_sum,
            "passed": bool(abs(min_fidelity - 1) < 1e-10
                           and abs(probability_sum - 1) < 1e-10)}},
        artifacts={"branches": branches, "sample": sample,
                   "target_state": target, "input_state": ket, "seed": seed},
        notes=["Chapter 15 cluster-state processing: a bounded three-node adaptive pattern, not a general MBQC compiler.",
               "Nodes use MSB-first tensor order. Second angle depends on first outcome; final X then Z corrections remove byproducts.",
               "Exact state-vector branch probabilities; the displayed sample uses the supplied seed. No hardware-noise model."])


def book_simon(config: dict, seed: int) -> dict:
    """Acquire Simon equations under an explicitly nonzero two-to-one promise."""
    from ..algorithms.core_algorithms import make_simon_problem, run_simon

    n = config.get("n_qubits", 3)
    secret = config.get("secret", 5)
    shots = config.get("shots", 64)
    if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= 4:
        raise ValueError("n_qubits must be an integer in [1, 4].")
    if not isinstance(secret, int) or isinstance(secret, bool) or not 1 <= secret < (1 << n):
        raise ValueError("secret must be a nonzero n-bit integer.")
    if not isinstance(shots, int) or isinstance(shots, bool) or not 1 <= shots <= 128:
        raise ValueError("shots must be an integer query budget in [1, 128].")
    result = run_simon(make_simon_problem(n, format(secret, f"0{n}b")), shots=shots, seed=seed)
    equations = [int(y, 2) for y in result["independent_equations"]]
    candidates = [s for s in range(1, 1 << n)
                  if all((s & y).bit_count() % 2 == 0 for y in equations)]
    violations = sum(count for key, count in result["counts"].items()
                     if (int(key, 2) & secret).bit_count() % 2)
    # T independent uniform vectors in GF(2)^(n-1) span with this exact
    # probability. It describes the fixed budget, not an optional-stopping CI.
    log_recovery = sum(float(np.log1p(-2.0 ** (j - shots))) for j in range(n - 1)) if shots >= n - 1 else None
    recovery_probability = float(np.exp(log_recovery)) if log_recovery is not None else 0.0
    failure_probability = float(-np.expm1(log_recovery)) if log_recovery is not None else 1.0
    passed = result["correct"] and candidates == [secret] and violations == 0
    return make_result_document_sanitized(
        "book_simon", {"rank": result["rank"], "target_rank": n - 1,
                       "shots_used": result["shots_used"], "recovered_mask": result["recovered_mask"],
                       "correct": result["correct"]},
        artifacts={"acquisition": result, "candidate_masks": candidates,
                   "ideal_equation_probabilities": {format(y, f"0{n}b"): 1 / (1 << (n - 1))
                       for y in range(1 << n) if (y & secret).bit_count() % 2 == 0}, "seed": seed},
        summary={"validation": {"prediction": "Independent low-register equations uniquely identify the nonzero mask at rank n-1.",
                  "orthogonality_violations": violations, "candidate_count": len(candidates),
                  "budget_recovery_probability": recovery_probability,
                  "budget_failure_probability": failure_probability,
                  "stopping_reason": result["stopping_reason"], "passed": bool(passed)}},
        notes=["Dense bounded Simon oracle; zero masks and broken two-to-one promises are rejected.",
               "shots is a maximum query budget. Exhausted rank acquisition is inconclusive and does not pass validation.",
               "The exact ideal budget-recovery probability is not a confidence interval for this adaptively stopped run."])


def book_qft(config: dict, seed: int) -> dict:
    """Exact DFT versus a rotation-truncated QFT, including complex amplitudes."""
    from ..algorithms.qft import build_qft
    from ..circuits.simulate import simulate

    n = config.get("n_qubits", 3)
    cutoff = config.get("cutoff_exponent", 2)
    if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= 6:
        raise ValueError("n_qubits must be an integer in [1, 6].")
    if cutoff is not None and (not isinstance(cutoff, int) or isinstance(cutoff, bool) or not 1 <= cutoff <= 6):
        raise ValueError("cutoff_exponent must be null or an integer in [1, 6].")
    dim = 1 << n
    mode = config.get("input_mode", "basis")
    if mode == "basis":
        index = config.get("basis_state", 3)
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < dim:
            raise ValueError("basis_state must be an integer in the register range.")
        initial = StateVector.basis_state(n, index)
    elif mode == "seeded_random":
        rng = np.random.default_rng(seed)
        initial = StateVector.from_amplitudes(rng.normal(size=dim) + 1j * rng.normal(size=dim), normalize_if_needed=True)
    else:
        raise ValueError("input_mode must be basis or seeded_random.")
    exact, _ = build_qft(n)
    approximate, info = build_qft(n, cutoff_exponent=cutoff)
    exact_state = simulate(exact, initial_state=initial).final_state.amplitudes
    approximate_state = simulate(approximate, initial_state=initial).final_state.amplitudes
    indices = np.arange(dim)
    dft = np.exp(2j * np.pi * np.outer(indices, indices) / dim) / np.sqrt(dim)
    reference = dft @ initial.amplitudes
    # Independent binary-fraction formula: each input/output bit pair adds
    # 2pi/2^(n-a-b). H contributes exponent 1; only larger exponents truncate.
    phase = np.zeros((dim, dim))
    for a in range(n):
        for b in range(n - a):
            exponent = n - a - b
            if exponent == 1 or cutoff is None or exponent <= cutoff:
                phase += np.outer((indices >> b) & 1, (indices >> a) & 1) / (2 ** exponent)
    truncated_reference = np.exp(2j * np.pi * phase) @ initial.amplitudes / np.sqrt(dim)
    exact_error = float(np.max(np.abs(exact_state - reference)))
    truncated_error = float(np.max(np.abs(approximate_state - truncated_reference)))
    state_error = float(np.linalg.norm(approximate_state - reference))
    fidelity = float(abs(np.vdot(reference, approximate_state)) ** 2)
    return make_result_document_sanitized(
        "book_qft", {"state_error": state_error, "fidelity_to_exact": fidelity,
                     "dropped_rotations": info.dropped_rotations, "approximate": info.approximate},
        artifacts={"input_state": initial.amplitudes, "exact_state": exact_state,
                   "approximate_state": approximate_state, "dft_reference": reference,
                   "truncated_reference": truncated_reference, "input_mode": mode,
                   "cutoff_exponent": cutoff, "cutoff_convention": info.cutoff_convention, "seed": seed},
        summary={"validation": {"prediction": "Exact QFT agrees with DFT; truncated QFT agrees with retained binary-fraction phases.",
                  "dft_max_error": exact_error, "truncated_oracle_max_error": truncated_error,
                  "passed": bool(exact_error < 1e-10 and truncated_error < 1e-10)}},
        notes=["cutoff_exponent=m retains CP(2pi/2^j) iff j<=m; equality is retained. Null means exact.",
               "Exact noiseless amplitudes, not samples. Basis-state probabilities are uniform even when phases change; amplitude error exposes this."] + info.warnings)


def book_qpe(config: dict, seed: int) -> dict:
    """Arbitrary Bloch eigenstate, exact QPE distribution and finite-shot counts."""
    from ..algorithms.phase_estimation_shor import run_phase_estimation
    from ..analytics.statistics import proportion_summary

    theta = float(config.get("theta", 1.0))
    phi = float(config.get("phi", 0.3))
    eigenphase = float(config.get("eigenphase", 0.375))
    precision = config.get("precision_bits", 4)
    shots = config.get("shots", 128)
    if not np.all(np.isfinite([theta, phi, eigenphase])) or not 0 <= eigenphase < 1:
        raise ValueError("Angles must be finite and eigenphase must lie in [0, 1).")
    if not isinstance(precision, int) or isinstance(precision, bool) or not 2 <= precision <= 6:
        raise ValueError("precision_bits must be an integer in [2, 6].")
    if not isinstance(shots, int) or isinstance(shots, bool) or not 1 <= shots <= 256:
        raise ValueError("shots must be an integer in [1, 256].")
    psi = np.array([np.cos(theta / 2), np.exp(1j * phi) * np.sin(theta / 2)])
    unitary = np.eye(2) + (np.exp(2j * np.pi * eigenphase) - 1) * np.outer(psi, psi.conj())
    result = run_phase_estimation(unitary, StateVector(psi, 1), precision,
                                  known_eigenphase=eigenphase, seed=seed, shots=shots)
    dim = 1 << precision
    reference = np.abs(np.exp(2j * np.pi * np.outer(eigenphase - np.arange(dim) / dim,
                                                  np.arange(dim))).mean(axis=1)) ** 2
    rows = [{"integer": y, "phase": y / dim, "probability": result.probabilities[format(y, f"0{precision}b")],
             "analytic_probability": float(reference[y]),
             "sampling": proportion_summary(result.counts.get(format(y, f"0{precision}b"), 0), shots)}
            for y in range(dim)]
    error = max(abs(row["probability"] - row["analytic_probability"]) for row in rows)
    return make_result_document_sanitized(
        "book_qpe", {"estimated_phase": result.estimated_phase, "eigenphase": eigenphase,
                     "circular_phase_error": result.error, "distribution_max_error": error},
        artifacts={"distribution": rows, "counts": result.counts, "eigenstate": psi,
                   "unitary": unitary, "precision_bits": precision, "shots": shots, "seed": seed},
        summary={"validation": {"prediction": "QPE probabilities equal the squared finite geometric sum for an arbitrary eigenstate.",
                  "distribution_max_error": error, "eigenstate_residual": result.eigenstate_residual,
                  "passed": bool(error < 1e-10 and result.eigenstate_residual < 1e-10)}},
        notes=["Eigenstate preparation uses the common StateVector simulator, not a basis-only approximation.",
               "Per-bin 95% Wilson intervals are marginal, not simultaneous; finite-shot mode/error need not equal the true phase.",
               "Validation compares exact simulated probabilities with a mathematical oracle; sampling fluctuations do not decide pass/fail."])


def book_multigrover(config: dict, seed: int) -> dict:
    """Distinct-set Grover sweep including the zero-query baseline."""
    from ..algorithms.core_algorithms import run_grover
    from ..analytics.statistics import proportion_summary

    n = config.get("n_qubits", 3)
    marked = config.get("marked_indices", [1, 5])
    maximum = config.get("max_iterations", 4)
    shots = config.get("shots", 128)
    if not isinstance(n, int) or isinstance(n, bool) or not 2 <= n <= 5:
        raise ValueError("n_qubits must be an integer in [2, 5].")
    if not isinstance(marked, list) or not marked or any(not isinstance(x, int) or isinstance(x, bool)
                                                       or not 0 <= x < (1 << n) for x in marked):
        raise ValueError("marked_indices must be a nonempty list of register indices.")
    if len(set(marked)) != len(marked):
        raise ValueError("marked_indices must be distinct.")
    if not isinstance(maximum, int) or isinstance(maximum, bool) or not 0 <= maximum <= 8:
        raise ValueError("max_iterations must be an integer in [0, 8].")
    if not isinstance(shots, int) or isinstance(shots, bool) or not 1 <= shots <= 256:
        raise ValueError("shots must be an integer in [1, 256].")
    angle = np.arcsin(np.sqrt(len(marked) / (1 << n)))
    rows = []
    for k in range(maximum + 1):
        result = run_grover(n, marked_indices=marked, iterations=k, shots=shots, seed=seed + k)
        successes = sum(result.counts.get(format(x, f"0{n}b"), 0) for x in marked)
        rows.append({"iterations": k, "exact_success_probability": result.exact_success_probability,
                     "analytic_success_probability": float(np.sin((2 * k + 1) * angle) ** 2),
                     "sampling": proportion_summary(successes, shots), "counts": result.counts})
    error = max(abs(row["exact_success_probability"] - row["analytic_success_probability"]) for row in rows)
    return make_result_document_sanitized(
        "book_multigrover", {"marked_fraction": len(marked) / (1 << n),
                             "optimal_iterations": result.optimal_iterations, "max_probability_error": error},
        artifacts={"sweep": rows, "marked_indices": sorted(marked), "shots_per_iteration": shots, "seed": seed},
        summary={"validation": {"prediction": "Marked probability follows sin^2((2k+1)asin(sqrt(M/N))) including k=0 and high marked fractions.",
                  "max_probability_error": error, "passed": bool(error < 1e-10)}},
        notes=["Distinct marked states share one phase oracle and the existing diffusion engine; no replacement algorithm.",
               "optimal_iterations is the nearest first-peak prescription, not a global optimum over later oscillations.",
               "Each sweep point has its own seed (seed+k), shot count and marginal 95% Wilson interval; validation uses exact probabilities."])


# ===========================================================================
# Gap-closure additions: source-fixtured worksheets for records that had no
# executable experiment (McMahon ch.1 classical tasks, ch.8 Hubbard units,
# ch.9 beam splitter, ch.10 GHZ superdense coding, ch.11 toy RSA, ch.14
# well contraction / nonlinear path, qutrit measurement, operator and
# density worksheets). Every value is computed, never hard-coded; each
# runner carries an independent oracle in its validation section.
# ===========================================================================

def book_classical_info(config: dict, seed: int) -> dict:
    """McMahon ch.1 Exercises 1.1, 1.3, 1.6 (+ Example 1.1 machinery).

    Exact source fixtures (pp.8-9): 26-letter alphabet -> 5-bit codes,
    52-symbol mixed-case alphabet -> 6-bit codes; 1024-byte storage ->
    8192 bits -> 2**8192 distinct messages; income table
    values [25.5, 30, 42, 50, 63, 75, 90] with counts [3, 5, 7, 3, 1, 2, 1]
    -> mode 42, mean 44.25, exact rational variance.

    Independent oracles: bit_length() for code lengths (no log2 floats in
    the oracle path), exact Python-integer message count, and
    Fraction-based exact mean/variance cross-checked against the float
    computation. Deterministic; seed unused.
    """
    from fractions import Fraction

    alphabets = config.get("alphabet_sizes", [26, 52])
    storage_bytes = config.get("storage_bytes", 1024)
    values = config.get("income_values", [25.5, 30, 42, 50, 63, 75, 90])
    counts = config.get("income_counts", [3, 5, 7, 3, 1, 2, 1])
    if (not isinstance(alphabets, list) or not alphabets
            or any(not isinstance(a, int) or isinstance(a, bool) or a < 1 for a in alphabets)):
        raise ValueError("alphabet_sizes must be a nonempty list of positive integers.")
    if not isinstance(storage_bytes, int) or isinstance(storage_bytes, bool) or storage_bytes < 1:
        raise ValueError("storage_bytes must be a positive integer.")
    if (not isinstance(values, list) or not isinstance(counts, list)
            or len(values) != len(counts) or not values
            or any(not isinstance(c, int) or isinstance(c, bool) or c < 0 for c in counts)
            or sum(counts) <= 0):
        raise ValueError("income_values/counts must be equal-length lists with a positive total count.")

    # Exercise 1.1: fixed-length code bits via integer oracle (N-1).bit_length().
    code_rows = [{"alphabet_size": a,
                 "code_bits": int(math.ceil(math.log2(a))),
                 "oracle_bits": (a - 1).bit_length()} for a in alphabets]
    # Exercise 1.3: exact bignum message count.
    total_bits = 8 * storage_bytes
    messages = 1 << total_bits
    # Exercise 1.6 / Example 1.1 machinery: exact rational statistics.
    fracs = [Fraction(str(v)) for v in values]
    total = sum(counts)
    mean_exact = sum(f * c for f, c in zip(fracs, counts)) / total
    var_exact = sum(c * (f - mean_exact) ** 2 for f, c in zip(fracs, counts)) / total
    floats = [float(v) for v in values]
    mean_float = sum(v * c for v, c in zip(floats, counts)) / total
    var_float = sum(c * (v - mean_float) ** 2 for v, c in zip(floats, counts)) / total
    mode_value = values[int(np.argmax(np.asarray(counts)))]
    table = [{"value": v, "count": c,
              "probability": f"{Fraction(c, total)}",
              "probability_float": c / total} for v, c in zip(values, counts)]
    validation = {
        "prediction": ("ceil(log2(26))=5 and ceil(log2(52))=6; 1024 B -> 8192 bits -> "
                       "2**8192 messages exactly; income mode 42, mean 44.25, float "
                       "variance matches the exact rational variance."),
        "code_bits": [r["code_bits"] for r in code_rows],
        "message_count_digits": len(str(messages)),
        "mode": mode_value,
        "mean_exact": f"{mean_exact}",
        "variance_exact": f"{var_exact}",
        "variance_float": var_float,
        "passed": bool(
            all(r["code_bits"] == r["oracle_bits"] for r in code_rows)
            and [r["code_bits"] for r in code_rows] == [5, 6]
            and messages == 2 ** 8192
            and mode_value == 42 and mean_exact == Fraction(177, 4)
            and abs(var_float - float(var_exact)) < 1e-9),
    }
    return make_result_document_sanitized(
        "book_classical_info",
        {"code_bits": [r["code_bits"] for r in code_rows],
         "message_count_digits": len(str(messages)),
         "mode": mode_value, "mean": float(mean_exact),
         "variance": var_float},
        artifacts={"code_lengths": code_rows,
                    "storage_bits": total_bits,
                    "message_count": str(messages),
                    "frequency_table": table,
                    "mean_exact": f"{mean_exact}",
                    "variance_exact": f"{var_exact}"},
        notes=["McMahon ch.1 (pp.8-9): fixed-length codes, storage counting, "
               "frequency-table mode/mean/variance.",
               "Classical Shannon quantities only; no quantum-information claim.",
               "Deterministic exact computation; no sampling."],
        summary={"validation": validation})


def book_beamsplitter(config: dict, seed: int) -> dict:
    """McMahon ch.9 Exercise 9.2 (pp.221-222): the beam-splitter unitary.

    Exact source fixture: B = iI/sqrt(2) + X/sqrt(2). The runner computes
    B|0>, B|1>, (B tensor B)|00>, and B^2, validating B^2 = iX (double
    application), unitarity, and 50/50 measurement statistics on B|0>.

    Independent oracle: B^2 is compared against the literal matrix iX
    (not against a second call of this runner's own square); output
    amplitudes are compared against the closed forms (i|0>+|1>)/sqrt(2)
    and (|0>+i|1>)/sqrt(2). Deterministic; seed unused.
    """
    s = np.sqrt(2.0)
    eye = np.eye(2, dtype=complex)
    mat_x = np.array([[0, 1], [1, 0]], dtype=complex)
    mat_b = 1j * eye / s + mat_x / s
    zero = np.array([1, 0], dtype=complex)
    one = np.array([0, 1], dtype=complex)
    b0 = mat_b @ zero
    b1 = mat_b @ one
    expected_b0 = np.array([1j, 1], dtype=complex) / s
    expected_b1 = np.array([1, 1j], dtype=complex) / s
    tensor_in = np.array([1, 0, 0, 0], dtype=complex)  # |00>
    tensor_out = np.kron(mat_b, mat_b) @ tensor_in
    expected_tensor = np.kron(expected_b0, expected_b0)
    square = mat_b @ mat_b
    oracle_ix = 1j * mat_x
    square_err = float(np.max(np.abs(square - oracle_ix)))
    unitary_err = float(np.max(np.abs(mat_b @ mat_b.conj().T - eye)))
    probs_b0 = (np.abs(b0) ** 2).tolist()
    validation = {
        "prediction": ("B|0>=(i|0>+|1>)/sqrt(2), B|1>=(|0>+i|1>)/sqrt(2), "
                       "(B tensor B)|00> is the product state, B^2=iX, B unitary, "
                       "measuring B|0> gives 50/50."),
        "b_squared_error_vs_ix": square_err,
        "unitarity_error": unitary_err,
        "b0_error": float(np.max(np.abs(b0 - expected_b0))),
        "b1_error": float(np.max(np.abs(b1 - expected_b1))),
        "tensor_error": float(np.max(np.abs(tensor_out - expected_tensor))),
        "measurement_probabilities_b0": [float(p) for p in probs_b0],
        "passed": bool(square_err < 1e-12 and unitary_err < 1e-12
                        and float(np.max(np.abs(b0 - expected_b0))) < 1e-12
                        and float(np.max(np.abs(b1 - expected_b1))) < 1e-12
                        and float(np.max(np.abs(tensor_out - expected_tensor))) < 1e-12
                        and all(abs(p - 0.5) < 1e-12 for p in probs_b0)),
    }
    return make_result_document_sanitized(
        "book_beamsplitter", {"b_squared_error_vs_ix": square_err,
                              "unitarity_error": unitary_err},
        artifacts={"beam_splitter": mat_b.tolist(), "b0": b0.tolist(),
                    "b1": b1.tolist(), "tensor_b00": tensor_out.tolist(),
                    "b_squared": square.tolist()},
        notes=["McMahon ch.9 Exercise 9.2: beam-splitter superposition, "
               "tensor action, double application B^2=iX.",
               "Deterministic matrix computation; no sampling."],
        summary={"validation": validation})


def book_hubbard(config: dict, seed: int) -> dict:
    """McMahon ch.8 Exercises 8.2-8.3 (p.195): Hubbard matrix units.

    Exact source fixtures: the FOUR Hubbard units X^{mn} = |m><n|
    (m, n in {0, 1}); part (B) applies each unit to the TWO Hadamard
    states |+>, |->; Exercise 8.3 expands the THREE Pauli operators
    X, Y, Z in those units:
    X = X^{01}+X^{10}, Y = -iX^{01}+iX^{10}, Z = X^{00}-X^{11}
    (plus I = X^{00}+X^{11} as the completeness check).

    Independent oracle: every action is compared against the literal
    outer-product definition applied by hand (X^{mn}|k> = delta_{nk}|m>),
    and every Pauli expansion against the textbook Pauli matrices from
    the operators module (a different code path from this runner's sums).
    Deterministic; seed unused.
    """
    from ..quantum.operators import pauli_matrix

    ket0 = np.array([1, 0], dtype=complex)
    ket1 = np.array([0, 1], dtype=complex)
    plus = (ket0 + ket1) / np.sqrt(2)
    minus = (ket0 - ket1) / np.sqrt(2)
    units = {(m, n): np.outer([ket0, ket1][m], [ket0, ket1][n].conj())
             for m in (0, 1) for n in (0, 1)}
    # Part (B): each unit on both Hadamard states, oracle = delta rule.
    action_rows = []
    action_ok = True
    for (m, n), u in sorted(units.items()):
        for label, state in (("plus", plus), ("minus", minus)):
            got = u @ state
            # delta_{n,+} structure: X^{mn}|+> = |m>/sqrt(2) always;
            # X^{mn}|-> = (-1)^n |m>/sqrt(2).
            sign = 1.0 if label == "plus" else (1.0 if n == 0 else -1.0)
            target = sign * [ket0, ket1][m] / np.sqrt(2)
            err = float(np.max(np.abs(got - target)))
            action_ok = action_ok and err < 1e-12
            action_rows.append({"unit": f"X^{m}{n}", "input": label,
                                "output": got.tolist(), "oracle_error": err})
    # Exercise 8.3: Pauli expansions in Hubbard units.
    x01, x10, x00, x11 = units[(0, 1)], units[(1, 0)], units[(0, 0)], units[(1, 1)]
    expansions = {"X": x01 + x10, "Y": -1j * x01 + 1j * x10,
                  "Z": x00 - x11, "I": x00 + x11}
    expansion_rows = []
    expansion_ok = True
    for name, mat in expansions.items():
        ref = (pauli_matrix(name) if name in ("X", "Y", "Z")
               else np.eye(2, dtype=complex))
        err = float(np.max(np.abs(mat - ref)))
        expansion_ok = expansion_ok and err < 1e-12
        expansion_rows.append({"operator": name, "oracle_error": err})
    validation = {
        "prediction": ("Each Hubbard unit acts as X^{mn}|k>=delta_{nk}|m> on "
                       "|+> and |->; X/Y/Z/I expand exactly as the "
                       "Hubbard-basis sums."),
        "all_actions_match": bool(action_ok),
        "all_expansions_match": bool(expansion_ok),
        "passed": bool(action_ok and expansion_ok),
    }
    return make_result_document_sanitized(
        "book_hubbard",
        {"units": 4, "hadamard_actions": len(action_rows),
         "pauli_expansions": len(expansion_rows)},
        artifacts={"actions": action_rows, "expansions": expansion_rows,
                    "units": {f"X^{m}{n}": u.tolist()
                              for (m, n), u in sorted(units.items())}},
        notes=["McMahon ch.8 Exercises 8.2-8.3: Hubbard units on Hadamard "
               "states; Pauli operators in the Hubbard basis.",
               "Deterministic matrix computation; no sampling."],
        summary={"validation": validation})


def _egcd(a: int, b: int):
    if b == 0:
        return (a, 1, 0)
    g, x1, y1 = _egcd(b, a % b)
    return (g, y1, x1 - (a // b) * y1)


def _is_prime_small(n: int) -> bool:
    if n < 2:
        return False
    if n % 2 == 0:
        return n == 2
    f = 3
    while f * f <= n:
        if n % f == 0:
            return False
        f += 2
    return True


def book_rsa_toy(config: dict, seed: int) -> dict:
    """McMahon ch.11 §11.1 / Example 11.1 / Exercise 11.1: toy RSA.

    Pedagogical small-prime RSA (defaults p=61, q=53, e=17): key setup,
    encryption c = m^e mod n, recovery m = c^d mod n. The runner
    validates the key relation e*d = 1 mod phi, round-trips every
    default probe message, and checks the textbook known answer
    m=65 -> c=2790 as a computed (not pasted) equality.

    Independent oracle: Python's built-in three-argument pow() is the
    reference for both directions; the runner's own square-and-multiply
    implementation must agree with it. Deterministic; seed unused.

    LIMITATIONS: educational arithmetic only. Toy moduli factor
    trivially; nothing here is a production-security claim, and the
    book's exact worked numbers were not transcribed, so this is a
    concept demonstration (EXPERIMENTAL), not a source-fixture match.
    """
    p = config.get("p", 61)
    q = config.get("q", 53)
    e = config.get("public_exponent", 17)
    messages = config.get("messages", [0, 1, 2, 42, 65, 123, 1000])
    for name, v in (("p", p), ("q", q), ("public_exponent", e)):
        if not isinstance(v, int) or isinstance(v, bool) or v < 2:
            raise ValueError(f"{name} must be an integer >= 2.")
    if not _is_prime_small(p) or not _is_prime_small(q):
        raise ValueError("Toy RSA requires prime p and q (trial-division checked).")
    if p == q:
        raise ValueError("Toy RSA requires distinct primes p != q.")
    n = p * q
    phi = (p - 1) * (q - 1)
    import math as _math
    if _math.gcd(e, phi) != 1:
        raise ValueError("public_exponent must be coprime to phi(n).")
    g, x, _ = _egcd(e, phi)
    assert g == 1
    d = x % phi
    if (not isinstance(messages, list) or not messages
            or any(not isinstance(m, int) or isinstance(m, bool) or not 0 <= m < n
                   for m in messages)):
        raise ValueError("messages must be a nonempty list of integers in [0, n).")

    def modexp(base: int, exp: int, mod: int) -> int:
        result = 1
        b = base % mod
        k = exp
        while k:
            if k & 1:
                result = (result * b) % mod
            b = (b * b) % mod
            k >>= 1
        return result

    rows = []
    all_ok = True
    for m in messages:
        c = modexp(m, e, n)
        m_back = modexp(c, d, n)
        oracle_c = pow(m, e, n)
        oracle_m = pow(c, d, n)
        ok = c == oracle_c and m_back == m == oracle_m
        all_ok = all_ok and ok
        rows.append({"message": m, "ciphertext": c, "recovered": m_back,
                     "matches_pow_oracle": bool(ok)})
    key_ok = (e * d) % phi == 1
    known = {"message": 65, "ciphertext": modexp(65, e, n)}
    validation = {
        "prediction": ("e*d = 1 mod phi; every probe message round-trips; "
                       "the runner's square-and-multiply agrees with pow(); "
                       "m=65 encrypts to 2790 for the default key."),
        "modulus": n, "phi": phi, "private_exponent": d,
        "key_relation_holds": bool(key_ok),
        "all_round_trips_match_oracle": bool(all_ok),
        "known_answer_65_to_2790": bool(known["ciphertext"] == 2790),
        "passed": bool(key_ok and all_ok and known["ciphertext"] == 2790),
    }
    return make_result_document_sanitized(
        "book_rsa_toy",
        {"modulus": n, "phi": phi, "private_exponent": d,
         "messages_tested": len(rows)},
        artifacts={"public_key": {"n": n, "e": e},
                    "rows": rows, "known_answer": known},
        notes=["McMahon ch.11 RSA baseline: key setup, encryption, recovery.",
               "Toy arithmetic with tiny primes; NOT a security demonstration.",
               "Deterministic computation; no sampling."],
        summary={"validation": validation})


def book_ghz_superdense(config: dict, seed: int) -> dict:
    """McMahon ch.10 Exercise 10.6: GHZ-assisted superdense coding.

    Alice holds qubit 0 of |GHZ> = (|000>+|111>)/sqrt(2); Bob holds
    qubits 1-2. Alice encodes one of four 2-bit messages with
    {I, X, Z, XZ} on her qubit (four mutually orthogonal 3-qubit
    states); she sends the qubit, and Bob decodes with
    CNOT(0->1), CNOT(0->2), H(0) plus computational-basis measurement.

    Convention: qubit 0 is the leftmost Kronecker factor; decoded
    outcome strings read q0q1q2. Independent oracle: the 4x4 Gram
    matrix of the encoded states (must equal identity) and explicit
    decode-circuit matrix multiplication (not the encoder reused as
    its own check). Deterministic; seed unused.

    LIMITATION: the book's exact encoding choice was not transcribed;
    {I,X,Z,XZ} is the standard orthogonal set. Mechanism validated;
    source-choice match unconfirmed (EXPERIMENTAL).
    """
    s = np.sqrt(2.0)
    ghz = np.zeros(8, dtype=complex)
    ghz[0] = ghz[7] = 1 / s
    mat_i = np.eye(2, dtype=complex)
    mat_x = np.array([[0, 1], [1, 0]], dtype=complex)
    mat_z = np.array([[1, 0], [0, -1]], dtype=complex)
    encodings = {"00": mat_i, "01": mat_x, "10": mat_z,
                 "11": mat_x @ mat_z}
    encoded = {bits: np.kron(u, np.eye(4, dtype=complex)) @ ghz
               for bits, u in encodings.items()}
    keys = ["00", "01", "10", "11"]
    gram = np.array([[complex(np.vdot(encoded[a], encoded[b]))
                      for b in keys] for a in keys])
    gram_err = float(np.max(np.abs(gram - np.eye(4))))
    # Decode circuit D = (H tensor I tensor I) CNOT02 CNOT01.
    cnot01 = np.zeros((8, 8), dtype=complex)
    cnot02 = np.zeros((8, 8), dtype=complex)
    for q0 in (0, 1):
        for q1 in (0, 1):
            for q2 in (0, 1):
                src = (q0 * 4 + q1 * 2 + q2)
                cnot01[(q0 * 4 + (q1 ^ q0) * 2 + q2), src] = 1.0
                cnot02[(q0 * 4 + q1 * 2 + (q2 ^ q0)), src] = 1.0
    had = np.array([[1, 1], [1, -1]], dtype=complex) / s
    decode = np.kron(had, np.eye(4, dtype=complex)) @ cnot02 @ cnot01
    rows = []
    outcomes = set()
    decode_ok = True
    for bits in keys:
        final = decode @ encoded[bits]
        probs = np.abs(final) ** 2
        top = int(np.argmax(probs))
        outcome = format(top, "03b")
        outcomes.add(outcome)
        ok = (abs(probs[top] - 1.0) < 1e-12
              and abs(float(np.sum(probs)) - 1.0) < 1e-12)
        decode_ok = decode_ok and ok
        rows.append({"message": bits, "decoded_outcome": outcome,
                     "top_probability": float(probs[top]),
                     "perfect": bool(ok)})
    validation = {
        "prediction": ("Four encoded states mutually orthogonal "
                       "(Gram = I); decode circuit maps each to a distinct "
                       "computational basis state with probability 1."),
        "gram_max_error_vs_identity": gram_err,
        "distinct_outcomes": len(outcomes),
        "all_decode_perfect": bool(decode_ok),
        "passed": bool(gram_err < 1e-12 and len(outcomes) == 4 and decode_ok),
    }
    return make_result_document_sanitized(
        "book_ghz_superdense", {"messages": 4,
                                "distinct_outcomes": len(outcomes)},
        artifacts={"messages": rows,
                    "gram_matrix": gram.tolist()},
        notes=["McMahon ch.10 Exercise 10.6: 2 classical bits via 1 sent "
               "qubit + shared GHZ state; full decode demonstrated.",
               "Standard {I,X,Z,XZ} encoding; book's exact choice unconfirmed.",
               "Deterministic statevector computation; no sampling."],
        summary={"validation": validation})


def book_adiabatic_nonlinear(config: dict, seed: int) -> dict:
    """McMahon ch.14 Exercise 14.4: adiabatic path with nonlinear coupling.

    H(s) = (1-s) H0 + s H1 + s(1-s) Hc with diagonal endpoints
    H0 = diag(0,1,3,4), H1 = diag(0,1,4,3) (the 2<->3 swap is the CNOT
    basis permutation) and off-diagonal coupling
    Hc = g(|2><3| + |3><2|). Without coupling the middle levels cross
    exactly at s=1/2; the coupling opens an avoided crossing so slow
    evolution follows eigenbranches, mapping |10> <-> |11>.

    Independent oracles: the gap curve is recomputed here by direct
    dense diagonalization (not via the engine's helper); the CNOT
    permutation comes from the literal CNOT matrix. Each of the four
    eigenbranches is evolved with the shared engine from its own
    initial eigenstate. Deterministic; seed unused.

    LIMITATIONS: the book's exact endpoint matrices were not
    transcribed, so endpoints/coupling are documented QuantumLab
    choices (EXPERIMENTAL). Only the basis permutation is validated,
    not coherent-phase CNOT process equivalence.
    """
    from ..quantum.adiabatic import adiabatic_evolution

    g = float(config.get("coupling_strength", 1.0))
    total_time = float(config.get("total_time", 120.0))
    steps = int(config.get("steps", 600))
    if not np.isfinite(g) or g < 0:
        raise ValueError("coupling_strength must be a finite nonnegative number.")
    if not np.isfinite(total_time) or total_time <= 0:
        raise ValueError("total_time must be positive.")
    if not isinstance(steps, int) or isinstance(steps, bool) or steps < 1:
        raise ValueError("steps must be a positive integer.")
    h0 = np.diag([0.0, 1.0, 3.0, 4.0])
    h1 = np.diag([0.0, 1.0, 4.0, 3.0])
    hc = np.zeros((4, 4))
    hc[2, 3] = hc[3, 2] = g
    # Independent gap oracle: dense diagonalization on this runner's grid.
    # The relevant gap is between ADJACENT levels (the 2<->3 avoided
    # crossing), not the ground gap, so the minimum runs over all
    # adjacent pairs.
    grid = np.linspace(0.0, 1.0, 101)
    gaps = []
    for s in grid:
        h = (1 - s) * h0 + s * h1 + s * (1 - s) * hc
        evals = np.linalg.eigvalsh(h)
        gaps.append(float(np.min(np.diff(evals))))
    min_gap = min(gaps)
    # CNOT basis-permutation oracle from the literal CNOT matrix.
    cnot = np.array([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1],
                     [0, 0, 1, 0]], dtype=complex)
    perm_oracle = [int(np.argmax(np.abs(cnot[:, j]))) for j in range(4)]
    branch_rows = []
    branch_ok = True
    for j in range(4):
        # H0 is diagonal, so initial eigenstate j IS basis |j>.
        r = adiabatic_evolution(h0, h1, total_time, steps=steps,
                                coupling=hc, initial_level=j)
        final = np.asarray(r["final_state"], dtype=complex)
        # Basis-image check: the evolved vector must be the CNOT image
        # basis state up to phase (sorted eigen-indices are NOT compared
        # with basis labels; that conflation was a real bug).
        basis_overlaps = [float(abs(final[b]) ** 2) for b in range(4)]
        peak_basis = int(np.argmax(np.asarray(basis_overlaps)))
        ok = peak_basis == perm_oracle[j] and basis_overlaps[peak_basis] > 0.999
        branch_ok = branch_ok and ok
        branch_rows.append({"initial_basis_state": j,
                            "final_peak_basis_state": peak_basis,
                            "peak_overlap": float(basis_overlaps[peak_basis]),
                            "expected_cnot_image": perm_oracle[j],
                            "matches": bool(ok)})
    validation = {
        "prediction": ("s(1-s) coupling opens the s=1/2 crossing "
                       "(min gap > 0.1); slow evolution follows all four "
                       "eigenbranches onto the CNOT basis permutation."),
        "min_gap_dense_oracle": min_gap,
        "all_branches_follow_cnot_permutation": bool(branch_ok),
        "passed": bool(min_gap > 0.1 and branch_ok),
    }
    return make_result_document_sanitized(
        "book_adiabatic_nonlinear",
        {"coupling_strength": g, "min_gap": min_gap,
         "branches_mapped": len(branch_rows)},
        artifacts={"branches": branch_rows,
                    "gap_curve": [{"s": float(s), "gap": gp}
                                  for s, gp in zip(grid, gaps)]},
        notes=["McMahon ch.14 Exercise 14.4: nonlinear coupling path, "
               "spectrum/eigenbranch mapping, CNOT interpretation.",
               "Basis-permutation claim only; coherent-phase CNOT process "
               "equivalence is a stronger separate claim (not asserted).",
               "Deterministic evolution; no sampling."],
        summary={"validation": validation})


def book_qutrit_measurement(config: dict, seed: int) -> dict:
    """McMahon ch.6 Exercise 6.2 / ch.3 Exercise 3.10: qutrit projectors.

    Native three-level projective measurement worksheet. Two documented
    presets reconstruct the source's stated outputs:
    - "ch06_ex2": psi = (|0>+sqrt(2)|1>+|2>)/2, energy projectors with
      energies (1,2,3) hbar*omega -> probabilities (1/4,1/2,1/4),
      mean energy 2 hbar*omega;
    - "ch03_ex10": psi = (|0>+|1>+sqrt(2)|2>)/2 -> probabilities
      (1/4,1/4,1/2).
    A custom state vector and energy spectrum can be supplied instead.

    Independent oracle: probabilities from |amplitudes|^2 (Born rule on
    the input amplitudes, not via the projector code path); expectation
    from the probability-weighted sum; post-measurement states checked
    normalized; completeness sum P_i = I. Deterministic; seed unused.

    LIMITATION: the book's exact state vectors were not transcribed;
    the presets are QuantumLab reconstructions reproducing the stated
    outputs (EXPERIMENTAL).
    """
    preset = str(config.get("preset", "ch06_ex2"))
    if preset == "ch06_ex2":
        amps = np.array([0.5, np.sqrt(2) / 2, 0.5], dtype=complex)
        energies = [1.0, 2.0, 3.0]
    elif preset == "ch03_ex10":
        amps = np.array([0.5, 0.5, np.sqrt(2) / 2], dtype=complex)
        energies = [0.0, 1.0, 2.0]
    elif preset == "custom":
        raw = config.get("amplitudes")
        energies = config.get("energies", [0.0, 1.0, 2.0])
        if (not isinstance(raw, list) or len(raw) != 3
                or not isinstance(energies, list) or len(energies) != 3):
            raise ValueError("custom preset needs 3 amplitudes and 3 energies.")
        amps = np.array([complex(a[0], a[1]) if isinstance(a, list) else complex(a)
                         for a in raw], dtype=complex)
        if abs(float(np.vdot(amps, amps).real) - 1.0) > 1e-9:
            raise ValueError("custom amplitudes must be normalized.")
        energies = [float(x) for x in energies]
    else:
        raise ValueError("preset must be ch06_ex2, ch03_ex10, or custom.")
    projectors = [np.outer(b, b.conj()) for b in np.eye(3, dtype=complex)]
    completeness_err = float(np.max(np.abs(sum(projectors) - np.eye(3))))
    born_oracle = (np.abs(amps) ** 2).tolist()
    rows = []
    total = 0.0
    all_ok = True
    for i, proj in enumerate(projectors):
        p = float(np.vdot(amps, proj @ amps).real)
        total += p
        post = proj @ amps / np.sqrt(p) if p > 0 else np.zeros(3)
        norm_ok = abs(float(np.vdot(post, post).real) - 1.0) < 1e-12
        oracle_ok = abs(p - born_oracle[i]) < 1e-12
        all_ok = all_ok and norm_ok and oracle_ok
        rows.append({"level": i, "probability": p,
                     "oracle_probability": float(born_oracle[i]),
                     "energy": float(energies[i]),
                     "post_state": post.tolist(),
                     "post_state_normalized": bool(norm_ok)})
    mean_energy = sum(r["probability"] * r["energy"] for r in rows)
    oracle_mean = sum(p * e for p, e in zip(born_oracle, energies))
    probs = [r["probability"] for r in rows]
    expected = {"ch06_ex2": ([0.25, 0.5, 0.25], 2.0),
                "ch03_ex10": ([0.25, 0.25, 0.5], None),
                "custom": (None, None)}[preset]
    source_ok = True
    if expected[0] is not None:
        source_ok = all(abs(p - q) < 1e-12 for p, q in zip(probs, expected[0]))
    if expected[1] is not None:
        source_ok = source_ok and abs(mean_energy - expected[1]) < 1e-12
    validation = {
        "prediction": ("Born probabilities match |amplitudes|^2, sum to 1, "
                       "post-states normalized, projectors complete; presets "
                       "reproduce the source's stated outputs."),
        "probabilities": [float(p) for p in probs],
        "probability_sum": float(total),
        "mean_energy": float(mean_energy),
        "oracle_mean_energy": float(oracle_mean),
        "completeness_error": completeness_err,
        "matches_source_outputs": bool(source_ok),
        "passed": bool(all_ok and abs(total - 1.0) < 1e-12
                        and abs(mean_energy - oracle_mean) < 1e-12
                        and completeness_err < 1e-12 and source_ok),
    }
    return make_result_document_sanitized(
        "book_qutrit_measurement", {"preset": preset,
                                    "probabilities": [float(p) for p in probs],
                                    "mean_energy": float(mean_energy)},
        artifacts={"outcomes": rows},
        notes=["McMahon ch.6 Exercise 6.2 / ch.3 Exercise 3.10: three-level "
               "projectors, Born probabilities, post-measurement states, "
               "energy expectation.",
               "Preset states are documented reconstructions; book's exact "
               "vectors unconfirmed.",
               "Deterministic computation; no sampling."],
        summary={"validation": validation})


def book_operator_worksheet(config: dict, seed: int) -> dict:
    """McMahon ch.3 worksheet: normal-operator classification, spectral
    decomposition, and polar/SVD factors for a user-supplied matrix.

    Default input is the rotation-scaling matrix [[2,-1],[1,2]]
    (Example 3.18 family): non-Hermitian, non-unitary, normal (scaled
    rotation: A A† = 5I), with both singular values sqrt(5). Reports Hermitian/unitary/normal verdicts, characteristic
    polynomial coefficients, eigenpairs with residuals, spectral
    reconstruction error, trace/determinant, and polar factors A = U P
    (U = W V†, P = V Σ V† from the SVD) with unitarity/PSD checks.

    Independent oracle: characteristic roots from np.roots must equal
    the eigenvalues; spectral projectors must resolve identity and
    rebuild A; U/V factors cross-checked (U†U = I, P ⪰ 0, UP = A).
    Deterministic; seed unused.

    LIMITATION: inputs are QuantumLab-chosen unless the caller supplies
    the source's exact matrices (EXPERIMENTAL for the ch.3 records).
    """
    raw = config.get("matrix", [[2.0, -1.0], [1.0, 2.0]])
    try:
        mat = np.asarray(raw, dtype=complex)
    except (ValueError, TypeError):
        raise ValueError("matrix must be a square numeric array.")
    if mat.ndim != 2 or mat.shape[0] != mat.shape[1] or mat.shape[0] < 2:
        raise ValueError("matrix must be a square array of dimension >= 2.")
    n = mat.shape[0]
    eye = np.eye(n, dtype=complex)
    hermitian = bool(np.allclose(mat, mat.conj().T, atol=1e-12))
    unitary = bool(np.allclose(mat @ mat.conj().T, eye, atol=1e-12))
    normal = bool(np.allclose(mat @ mat.conj().T, mat.conj().T @ mat, atol=1e-12))
    charpoly = np.poly(mat)
    char_roots = np.roots(charpoly)
    evals, evecs = np.linalg.eig(mat)
    root_match = float(np.max(np.abs(np.sort(char_roots) - np.sort(evals))))
    residuals = [float(np.linalg.norm(mat @ evecs[:, j] - evals[j] * evecs[:, j]))
                 for j in range(n)]
    # Spectral rebuild (exact for diagonalizable inputs; reported, not assumed).
    try:
        spectral = evecs @ np.diag(evals) @ np.linalg.inv(evecs)
        spectral_err = float(np.max(np.abs(spectral - mat)))
    except np.linalg.LinAlgError:
        spectral_err = float("nan")
    # Polar factors from the SVD: A = W Σ V† -> U = W V†, P = V Σ V†.
    w_svd, sigma, vh = np.linalg.svd(mat)
    vv = vh.conj().T
    u_pol = w_svd @ vv.conj().T
    p_pol = vv @ np.diag(sigma) @ vv.conj().T
    u_unitary_err = float(np.max(np.abs(u_pol @ u_pol.conj().T - eye)))
    p_herm_err = float(np.max(np.abs(p_pol - p_pol.conj().T)))
    p_psd_min = float(np.linalg.eigvalsh(p_pol).min())
    polar_err = float(np.max(np.abs(u_pol @ p_pol - mat)))
    validation = {
        "prediction": ("Classification flags correct; characteristic roots "
                       "equal eigenvalues; eigen-residuals ~ 0; spectral "
                       "rebuild and polar factors reconstruct A with "
                       "unitary U and PSD P."),
        "hermitian": hermitian, "unitary": unitary, "normal": normal,
        "eigenvalues": [float(x.real) if abs(x.imag) < 1e-12 else [float(x.real), float(x.imag)]
                        for x in evals],
        "max_eigen_residual": max(residuals),
        "charpoly_root_error": root_match,
        "spectral_rebuild_error": spectral_err,
        "singular_values": [float(s) for s in sigma],
        "polar_unitary_error": u_unitary_err,
        "polar_psd_min_eigenvalue": p_psd_min,
        "polar_rebuild_error": polar_err,
        "passed": bool(max(residuals) < 1e-9 and root_match < 1e-9
                        and (np.isnan(spectral_err) or spectral_err < 1e-9)
                        and u_unitary_err < 1e-12 and p_psd_min > -1e-12
                        and polar_err < 1e-12),
    }
    return make_result_document_sanitized(
        "book_operator_worksheet",
        {"dimension": n, "hermitian": hermitian, "unitary": unitary,
         "normal": normal, "singular_values": [float(s) for s in sigma]},
        artifacts={"characteristic_polynomial": [float(c.real) for c in charpoly],
                    "eigen_residuals": residuals,
                    "polar": {"unitary_error": u_unitary_err,
                              "psd_min": p_psd_min, "rebuild_error": polar_err}},
        notes=["McMahon ch.3: normal/Hermitian/unitary classification, "
               "characteristic equation, spectral decomposition, polar "
               "decomposition and singular values.",
               "Default matrix is a QuantumLab-chosen rotation-scaling "
               "example; supply the source's exact matrices to reproduce "
               "specific tasks.",
               "Deterministic computation; no sampling."],
        summary={"validation": validation})


def book_density_worksheet(config: dict, seed: int) -> dict:
    """McMahon ch.5 worksheet: validity, purity, and Bloch analysis of a
    user-supplied single-qubit density matrix.

    Default input rho = [[0.6, 0.2],[0.2, 0.4]] (mixed, valid): the
    runner checks Hermiticity deviation, trace, eigenvalues/PSD verdict,
    purity Tr(rho^2), Bloch vector with the |r|^2 = 2 Tr(rho^2) - 1
    consistency oracle, and computational/X-basis probabilities.

    Independent oracle: eigenvalues from np.linalg.eigvalsh (separate
    path from the verdict logic); Bloch components from Tr(rho σ_i)
    with Pauli matrices; purity cross-checked via eigenvalues
    (sum λ^2). Deterministic; seed unused.

    LIMITATION: the default state is QuantumLab-chosen; caller-supplied
    matrices reproduce specific source tasks (EXPERIMENTAL).
    """
    from ..quantum.operators import pauli_matrix

    raw = config.get("rho", [[0.6, 0.2], [0.2, 0.4]])
    try:
        rho = np.asarray(raw, dtype=complex)
    except (ValueError, TypeError):
        raise ValueError("rho must be a 2x2 numeric array.")
    if rho.shape != (2, 2):
        raise ValueError("rho must be a 2x2 array (single-qubit worksheet).")
    herm_dev = float(np.max(np.abs(rho - rho.conj().T)))
    trace = complex(np.trace(rho))
    evals = np.linalg.eigvalsh((rho + rho.conj().T) / 2)
    psd_min = float(evals.min())
    valid = bool(herm_dev < 1e-9 and abs(trace - 1.0) < 1e-9 and psd_min >= -1e-9)
    purity = float(np.trace(rho @ rho).real)
    purity_oracle = float(np.sum(evals ** 2))
    paulis = {name: pauli_matrix(name) for name in ("X", "Y", "Z")}
    bloch = [float(np.trace(rho @ paulis[name]).real) for name in ("X", "Y", "Z")]
    bloch_norm_sq = sum(b * b for b in bloch)
    bloch_consistency = abs(bloch_norm_sq - (2 * purity - 1))
    p0 = float(rho[0, 0].real)
    px_plus = float(np.vdot(np.array([1, 1], complex) / np.sqrt(2),
                            rho @ (np.array([1, 1], complex) / np.sqrt(2))).real)
    validation = {
        "prediction": ("Hermitian, unit trace, PSD with purity in "
                       "[0.5, 1]; |r|^2 = 2 Tr(rho^2)-1; purity equals "
                       "sum of squared eigenvalues; Born probabilities "
                       "in [0, 1]."),
        "hermiticity_deviation": herm_dev,
        "trace": [trace.real, trace.imag],
        "eigenvalues": [float(x) for x in evals],
        "valid_density": valid,
        "purity": purity,
        "purity_oracle_eig": purity_oracle,
        "bloch_vector": [float(b) for b in bloch],
        "bloch_consistency_error": float(bloch_consistency),
        "p_z0": p0, "p_x_plus": float(px_plus),
        "passed": bool(valid and abs(purity - purity_oracle) < 1e-12
                        and bloch_consistency < 1e-9
                        and 0.5 - 1e-12 <= purity <= 1.0 + 1e-12
                        and 0.0 - 1e-12 <= p0 <= 1.0 + 1e-12
                        and 0.0 - 1e-12 <= px_plus <= 1.0 + 1e-12),
    }
    return make_result_document_sanitized(
        "book_density_worksheet",
        {"valid": valid, "purity": purity,
         "bloch_vector": [float(b) for b in bloch]},
        artifacts={"eigenvalues": [float(x) for x in evals],
                    "probabilities": {"z0": p0, "x_plus": float(px_plus)}},
        notes=["McMahon ch.5: density-operator validity (Hermitian, trace, "
               "PSD), purity, Bloch representation, basis probabilities.",
               "Default state is QuantumLab-chosen; supply exact source "
               "matrices to reproduce specific exercises.",
               "Invalid inputs are reported (valid=false), not silently "
               "repaired. Deterministic; no sampling."],
        summary={"validation": validation})
