"""Bounded D7 research, not a validation suite or alternate decoder.
Run from the repository root: python backend/scripts/d7_study.py --phase all
The fitted circuit is a Pauli-error-frame model; see the exact instrument oracle.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import gc
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
import numpy as np
from app.qec import circuit_level as cl
from app.qec import correlation_decoder as cd
from app.qec import circuit_signatures as cs
from app.qec.circuit_extraction import EXTRACTION_BASELINE, EXTRACTION_FITTED, get_extraction_model
from app.qec.rotated_surface_code import RotatedSurfaceCode

MODES = (EXTRACTION_BASELINE, EXTRACTION_FITTED)
DISTANCES = (3, 5, 7)
ROUNDS = 3
REGIMES = {"gate_low": (0.001, 0.0, 0.0, 0.0),
           "combined_low": (0.001, 0.001, 0.001, 0.001),
           "combined_mid": (0.005, 0.005, 0.003, 0.003)}
SOURCES = ["backend/app/qec/" + f + ".py" for f in
           ("circuit_level", "circuit_extraction", "circuit_signatures",
            "correlation_decoder", "repeated_round", "rotated_surface_code", "matching")]


def hashes():
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCES}


def metadata(args):
    return {"started_utc": datetime.now(timezone.utc).isoformat(),
            "command": [sys.executable, *sys.argv], "python": sys.version,
            "platform": platform.platform(), "machine": platform.machine(),
            "packages": {p: importlib.metadata.version(p) for p in ("numpy", "scipy")},
            "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "source_sha256": hashes(), "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "rounds": ROUNDS, "trials": args.trials, "seed": args.seed,
            "trial_seed_rule": "cell_seed + trial_index * 7919",
            "scope": "Pauli-error-frame model only; no hardware or threshold inference"}


def save(path, result):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


def scaling():
    rows = []
    for mode in MODES:
        for d in DISTANCES:
            code = RotatedSurfaceCode.build(d)
            cs._CACHE.clear()
            gc.collect()
            start = time.perf_counter()
            db = cs.build_signature_db(code, ROUNDS, mode)
            untraced = time.perf_counter() - start
            counts = {"mid_signatures": len(db.mid), "final_signatures": len(db.final),
                      "mid_locations": db.n_locations_mid, "final_locations": db.n_locations_final,
                      "mid_null": db.n_null_locations_mid, "final_null": db.n_null_locations_final}
            del db
            cs._CACHE.clear()
            gc.collect()
            tracemalloc.start()
            start = time.perf_counter()
            db = cs.build_signature_db(code, ROUNDS, mode)
            traced = time.perf_counter() - start
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            row = {"d": d, "extraction_model": mode, **counts,
                   "cold_untraced_seconds": untraced, "cold_traced_seconds": traced,
                   "python_traced_current_bytes": current, "python_traced_peak_bytes": peak,
                   "allocation_scope": "tracemalloc only, not process RSS; imports/code construction excluded; lazy translation/event caches excluded",
                   "collect_subparities": False}
            rows.append(row)
            print(json.dumps(row), flush=True)
    return rows


def single_faults():
    rows = []
    for mode in MODES:
        for d in DISTANCES:
            code = RotatedSurfaceCode.build(d)
            db = cs.build_signature_db(code, ROUNDS, mode)
            faults = cs._elementary_faults(code, get_extraction_model(mode))
            clean = ((0,) * len(code.x_checks), (0,) * len(code.z_checks))
            for placement in (1, 2, 3):
                selected = faults if placement < ROUNDS else [f for f in faults if f[2] == "cnot"]
                counts = Counter()
                failures = []
                start = time.perf_counter()
                for fault in selected:
                    # Existing injection hook only injects round 1. At zero background,
                    # a clean prefix is exactly the same frame at later injection.
                    ex, ez, hooks, suffix, _mf, _ve = cl.simulate_circuit_level(
                        code, ROUNDS - placement + 1, 0., 0., 0., 0., seed=0,
                        extraction_model=mode, forced_faults=[fault])
                    obs = [clean] * (placement - 1) + suffix
                    hooks = [(t + placement - 1, k, ci) for t, k, ci in hooks]
                    phen = cl.decode_circuit_level(code, ROUNDS, 0., 0., 0., 0., data_error_x=ex,
                        data_error_z=ez, observed_syndromes=obs, hook_events=hooks, seed=0)
                    corr = cd.decode_correlation_aware(code, ROUNDS, 0., 0., 0., 0.,
                        data_error_x=ex, data_error_z=ez, observed_syndromes=obs, db=db, seed=0)
                    counts["enumerated"] += 1
                    counts["nontrivial"] += bool(ex or ez or phen.detection_events)
                    counts["control_failures"] += not phen.success
                    counts["correlation_failures"] += not corr.success
                    if not phen.success or not corr.success:
                        failures.append({"fault": fault, "control_outcome": phen.outcome,
                                         "correlation_outcome": corr.outcome})
                row = {"d": d, "extraction_model": mode, "injection_round": placement,
                       "coverage": "exhaustive enumerated elementary faults" if placement < ROUNDS else "exhaustive gate faults; final reset/prep/readout ideal",
                       **counts, "seconds": time.perf_counter() - start, "failures": failures,
                       "decoder_noise_weights": [0., 0., 0., 0.],
                       "note": "Includes reset Y/Z diagnostic injections not sampled by production reset channel; not probability-weighted"}
                rows.append(row)
                print(json.dumps({k: v for k, v in row.items() if k != "failures"}), flush=True)
    return rows


@contextmanager
def observe_decoders():
    """Instrument the existing paired-MC function; no copied simulation loop."""
    control_original = cl.decode_circuit_level
    corr_original = cd.decode_correlation_aware
    observations = {k: [] for k in ("control", "correlation", "two_fault")}
    seconds = {k: 0. for k in observations}
    def control(*args, **kwargs):
        start = time.perf_counter()
        result = control_original(*args, **kwargs)
        seconds["control"] += time.perf_counter() - start
        observations["control"].append(not result.success)
        return result
    def corr(*args, **kwargs):
        key = "two_fault" if kwargs.get("two_fault", False) else "correlation"
        start = time.perf_counter()
        result = corr_original(*args, **kwargs)
        seconds[key] += time.perf_counter() - start
        observations[key].append(not result.success)
        return result
    cl.decode_circuit_level, cd.decode_correlation_aware = control, corr
    try:
        yield observations, seconds
    finally:
        cl.decode_circuit_level, cd.decode_correlation_aware = control_original, corr_original


def paired_mc(trials, seed):
    rows = []
    for mode in MODES:
        for d in DISTANCES:
            code = RotatedSurfaceCode.build(d)
            cs.build_signature_db(code, ROUNDS, mode)
            for ri, (regime, noise) in enumerate(REGIMES.items()):
                cell_seed = seed + 100000 * d + 10000 * ri
                start = time.perf_counter()
                with observe_decoders() as (observations, seconds):
                    result = cd.simulate_decoder_comparison_mc(d, ROUNDS, *noise,
                        trials=trials, seed=cell_seed, extraction_model=mode)
                elapsed = time.perf_counter() - start
                assert all(len(v) == trials for v in observations.values())
                for label, key in (("phenomenological", "control"), ("correlation_aware", "correlation"),
                                   ("correlation_aware_two_fault", "two_fault")):
                    assert result[label]["logical_failures"] == sum(observations[key])
                discordant = {}
                for key in ("correlation", "two_fault"):
                    a, b = observations["control"], observations[key]
                    discordant[key] = {"control_only_fails": sum(x and not y for x, y in zip(a, b)),
                                       "candidate_only_fails": sum(y and not x for x, y in zip(a, b)),
                                       "both_fail": sum(x and y for x, y in zip(a, b)),
                                       "neither_fails": sum(not x and not y for x, y in zip(a, b))}
                result.update(regime=regime, measured_wall_seconds=elapsed,
                    instrumented_decoder_seconds=seconds, discordant_pairs=discordant,
                    decoder_overhead_ratio={k: seconds[k] / seconds["control"] for k in ("correlation", "two_fault")},
                    measurement_note="DB prebuilt; lazy event/translation initialization may occur in first trial. Original correlation_aware.decode_seconds combines single and two-fault calls; use instrumented split times.")
                rows.append(result)
                print(json.dumps(result), flush=True)
    return rows


def instrument_oracle():
    """Exact 4-data-qubit circuits, not the production error-frame propagation.

    Enumerate actual ancilla measurement branches and discard their record.
    Both possible pair parities have the same full stabilizer eigenvalue.
    """
    def h(state, q):
        out = state.copy()
        for i in range(len(state)):
            if not (i >> q) & 1:
                j = i | (1 << q)
                out[i] = (state[i] + state[j]) / np.sqrt(2)
                out[j] = (state[i] - state[j]) / np.sqrt(2)
        return out
    def cx(state, c, t):
        out = np.zeros_like(state)
        for i, value in enumerate(state):
            out[i ^ ((1 << t) if (i >> c) & 1 else 0)] += value
        return out
    rows = []
    for kind in ("Z", "X"):
        psi = np.zeros(16, dtype=complex)
        psi[0] = psi[5] = 1 / np.sqrt(2)
        if kind == "X":
            for q in range(4):
                psi = h(psi, q)
        for mode in MODES:
            n_anc = 1 if mode == EXTRACTION_BASELINE else 2
            state = np.zeros(16 * 2**n_anc, dtype=complex)
            state[:16] = psi
            groups = [list(range(4))] if n_anc == 1 else [[0, 1], [2, 3]]
            for p, members in enumerate(groups):
                anc = 4 + p
                if kind == "X":
                    state = h(state, anc)
                for q in members:
                    state = cx(state, q, anc) if kind == "Z" else cx(state, anc, q)
                if kind == "X":
                    state = h(state, anc)
            rho = np.zeros((16, 16), dtype=complex)
            outcomes = []
            for anc_bits in range(2**n_anc):
                branch = state[16 * anc_bits:16 * (anc_bits + 1)]
                probability = float(np.vdot(branch, branch).real)
                rho += np.outer(branch, branch.conj())
                outcomes.append({"ancilla_bits": format(anc_bits, f"0{n_anc}b"),
                                 "probability": probability, "xor": anc_bits.bit_count() % 2})
            row = {"kind": kind, "extraction_model": mode,
                   "input": "(|0000>+|0101>)/sqrt(2), H on all data for X",
                   "fidelity_to_input": float(np.vdot(psi, rho @ psi).real),
                   "purity": float(np.trace(rho @ rho).real), "outcomes": outcomes,
                   "trace": float(np.trace(rho).real)}
            assert abs(row["trace"] - 1) < 1e-12
            assert abs(row["fidelity_to_input"] - (1 if n_anc == 1 else .5)) < 1e-12
            rows.append(row)
    return {"scope": "One isolated noiseless weight-4 X or Z check using the source's ancilla/reset/H/CNOT/readout structure; exact state-vector branches. Not a full surface-code circuit.",
            "interpretation": "Same XOR parity distribution does not imply same postmeasurement instrument. Production fitted routine models pair_bits as Pauli-frame flips, not Born measurements of the data state.",
            "results": rows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("all", "scaling", "single", "mc", "oracle"), default="all")
    parser.add_argument("--trials", type=int, default=300)
    parser.add_argument("--seed", type=int, default=20260917)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/data/d7_study.json")
    args = parser.parse_args()
    result = {"metadata": metadata(args)}
    start = time.perf_counter()
    for name, fn in (("oracle", instrument_oracle), ("scaling", scaling),
                     ("single", single_faults), ("mc", lambda: paired_mc(args.trials, args.seed))):
        if args.phase in ("all", name):
            result[name] = fn()
            save(args.output, result)
    result["metadata"].update(completed_utc=datetime.now(timezone.utc).isoformat(),
        total_seconds=time.perf_counter() - start, sources_unchanged=hashes() == result["metadata"]["source_sha256"])
    save(args.output, result)
    print(f"Saved {args.output}; seconds={result['metadata']['total_seconds']:.3f}", flush=True)


if __name__ == "__main__":
    main()
