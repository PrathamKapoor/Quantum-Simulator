"""Extended validation for idle-time execution (directive §149).

Long Monte Carlo runs that verify statistical trends across many seeds.
Run explicitly; excluded from the fast suite via the `extended` marker.

    python -m pytest backend/tests/test_extended_validation.py -m extended
"""
import numpy as np
import pytest

pytestmark = pytest.mark.extended

from app.qec import sweep_physical_error_rate
from app.protocols import run_bb84, run_chsh
from app.network import (
    Topology, NetworkNode, NetworkEngine, NetworkConfig,
)


def test_qec_shor9_trend_many_seeds():
    points = sweep_physical_error_rate(
        "shor-9", [0.001, 0.003, 0.01, 0.03], trials=20000, seed=101)
    rates = [p.logical_error_rate for p in points]
    assert all(rates[i] <= rates[i + 1] + 0.005 for i in range(len(rates) - 1)), rates
    # Shor-9 at p=0.001 must be far below physical rate.
    assert rates[0] < 10 * 1e-4


def test_bb84_eve_fraction_linearity():
    fracs = [0.0, 0.25, 0.5, 0.75, 1.0]
    qbers = []
    for f in fracs:
        qs = [run_bb84(4096, eve_intercept_probability=f, seed=s).qber for s in range(6)]
        qbers.append(float(np.mean(qs)))
    assert qbers[0] < 0.005
    assert qbers[-1] > 0.2
    assert all(qbers[i] < qbers[i + 1] + 0.01 for i in range(len(qbers) - 1))


def test_chsh_s_linear_in_fidelity():
    fs = np.linspace(0.55, 0.95, 5)
    ss = []
    for f in fs:
        vals = [abs(run_chsh(float(f), shots_per_setting=20000, seed=s)["chsh_S"])
                for s in range(3)]
        ss.append(float(np.mean(vals)))
    expected = 2 * np.sqrt(2) * (2 * fs - 1)
    assert all(abs(ss[i] - expected[i]) < 0.05 for i in range(len(fs))), list(zip(ss, expected))


def test_repeater_chain_success_over_time_budget():
    """Success probability grows with the simulated attempt budget."""
    t = Topology()
    for n, ty in [("A", "end"), ("R1", "repeater"), ("R2", "repeater"), ("B", "end")]:
        t.add_node(NetworkNode(n, ty, memory_slots=8))
    for a, b, d in (("A", "R1", 20), ("R1", "R2", 20), ("R2", "B", 20)):
        t.add_quantum_link(a, b, distance_km=d)
    results = []
    for horizon_ms in (50, 200):
        successes = 0
        trials = 24
        for i in range(trials):
            eng = NetworkEngine(t.copy(), NetworkConfig(), seed=500 + i)
            eng.submit_request("A", "B")
            r = eng.run(until_ns=horizon_ms * 1e6)
            successes += r.success_count
        results.append(successes / trials)
    assert results[1] >= results[0], results
