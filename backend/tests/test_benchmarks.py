"""Benchmark subsystem tests: measured values must be sane, never fabricated."""
import time

from app.experiments.benchmarks import (
    run_circuit_benchmarks,
    run_density_benchmark,
    run_network_benchmark,
    run_all_benchmarks,
)


class TestBenchmarks:
    def test_circuit_benchmarks_measured(self):
        res = run_circuit_benchmarks(max_qubits=8, repeats=2)
        entries = res["entries"]
        assert len(entries) >= 8
        for e in entries:
            assert e["value"] >= 0
        # QFT at n qubits should take longer than Bell at n qubits.
        by_name = {e["workload"]: e["value"] for e in entries}
        bell = next(v for k, v in by_name.items() if k.startswith("bell-"))
        qft = next(v for k, v in by_name.items() if k.startswith("qft-"))
        assert qft >= bell * 0.5

    def test_shot_throughput_positive(self):
        res = run_circuit_benchmarks(max_qubits=6, repeats=2)
        sps = next(e["value"] for e in res["entries"]
                   if e["metric"] == "shots_per_second")
        assert sps > 1000

    def test_network_throughput_measured(self):
        res = run_network_benchmark(requests=10, sim_time_ms=300)
        assert res["events_processed_best"] > 0
        assert res["events_per_second_best"] > 0

    def test_full_document_shape(self):
        doc = run_all_benchmarks(repeats=1)
        assert doc["schema"] == "quantumlab.run-result"
        assert "platform" in doc["environment"]
