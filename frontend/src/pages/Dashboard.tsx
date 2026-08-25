import { useEffect, useState } from "react";
import { get, post } from "../lib/api";
import { LineChart } from "../lib/charts";

export default function Dashboard() {
  const [health, setHealth] = useState<any>(null);
  const [demoResult, setDemoResult] = useState<any>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const loadHealth = async () => {
    try { setHealth(await get("/api/health")); } catch { setHealth(null); }
  };
  useEffect(() => { loadHealth(); }, []);

  const runDemo = async (name: string, fn: () => Promise<any>) => {
    setBusy(name);
    setDemoResult(null);
    try {
      const r = await fn();
      setDemoResult({ name, data: r });
    } catch (e: any) {
      setDemoResult({ name, error: e.message });
    } finally {
      setBusy(null);
    }
  };

  const demos: [string, string, () => Promise<any>][] = [
    ["Teleportation-style Bell flow", "Bell pair + measurement statistics",
     async () => {
       const c = {
         schema: "quantumlab.circuit", version: 1, name: "bell", num_qubits: 2,
         num_clbits: 2, metadata: {},
         operations: [
           { kind: "gate", gate: "H", params: [], qubits: [0], clbits: [], condition: null },
           { kind: "gate", gate: "CX", params: [], qubits: [0, 1], clbits: [], condition: null },
           { kind: "measure", qubits: [0, 1], clbits: [0, 1], condition: null },
         ],
       };
       return post("/api/circuits/execute", { circuit: c, shots: 2000, seed: 7 });
     }],
    ["Grover search (4 qubits)", "marked state |1001⟩",
     () => post("/api/algorithms/grover", { n_qubits: 4, marked_index: 9, shots: 2048 })],
    ["BB84 without Eve", "QBER should be ≈ 0",
     () => post("/api/protocols/bb84", { n_qubits: 512, seed: 5 })],
    ["Repeater chain A–R–B", "entanglement swapping over the network engine",
     async () => post("/api/network/simulate", {
       nodes: [
         { name: "Alice", type: "end", memory_slots: 8 },
         { name: "R", type: "repeater", memory_slots: 8 },
         { name: "Bob", type: "end", memory_slots: 8 },
       ],
       links: [
         { source: "Alice", destination: "R", distance_km: 25 },
         { source: "R", destination: "Bob", distance_km: 25 },
       ],
       requests: [{ source: "Alice", destination: "Bob" }],
       sim_time_ms: 200, seed: 11,
     })],
  ];

  return (
    <div>
      <h1 className="page-title">QuantumLab</h1>
      <p className="page-sub">
        An integrated quantum computing, information, and networking research laboratory.
        Every number in this application comes from real simulation — nothing is fabricated.
      </p>

      <div className="metric-cards">
        <MetricCard label="Backend" value={health?.status === "ok" ? "Healthy" : health ? "Degraded" : "…"} />
        <MetricCard label="Quantum engine" value={health?.checks?.quantum_engine?.status ?? "…"} />
        <MetricCard label="Network engine" value={health?.checks?.network_engine?.status ?? "…"} />
        <MetricCard label="Worker queue" value={String(health?.checks?.worker?.workers ?? "…")} />
        <button className="btn secondary small" style={{ alignSelf: "center" }} onClick={loadHealth}>
          Re-check
        </button>
      </div>

      <div className="grid2">
        <div className="panel">
          <h3>Flagship demos</h3>
          <table className="data-table">
            <tbody>
              {demos.map(([name, desc]) => (
                <tr key={name}>
                  <td>
                    <b>{name}</b>
                    <div style={{ color: "var(--text-dim)", fontSize: 12 }}>{desc}</div>
                  </td>
                  <td style={{ width: 110 }}>
                    <button className="btn small" disabled={busy !== null}
                            onClick={() => runDemo(name, demos.find((d) => d[0] === name)![2])}>
                      {busy === name ? "Running…" : "Run"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="panel">
          <h3>Latest demo output</h3>
          {!demoResult && <p style={{ color: "var(--text-dim)", fontSize: 13 }}>Run a demo to see live simulation output here.</p>}
          {demoResult?.error && <div className="error-box">{demoResult.error}</div>}
          {demoResult?.data && (
            <pre className="event-log">{JSON.stringify(demoResult.data, null, 2).slice(0, 2400)}</pre>
          )}
        </div>
      </div>

      {demoResult?.name?.startsWith("Repeater") && demoResult.data?.event_log && (
        <div className="panel">
          <h3>Network event timeline</h3>
          <div className="event-log">{demoResult.data.event_log.join("\n")}</div>
        </div>
      )}

      {demoResult?.name?.startsWith("Grover") && demoResult.data?.per_iteration_probabilities && (
        <div className="panel">
          <LineChart
            title="Success probability per Grover iteration"
            xLabel="iteration"
            yLabel="P(marked)"
            series={[{
              name: "P(marked)",
              points: demoResult.data.per_iteration_probabilities.map((p: number, i: number) => ({ x: i + 1, y: p })),
            }]}
          />
        </div>
      )}

      <div className="panel">
        <h3>Research loop</h3>
        <p style={{ fontSize: 13 }}>
          Formulate a question → configure an experiment → simulate with a fixed seed →
          collect statistically meaningful results → compare configurations → save and reproduce.
          The <b>Experiments</b> page supports this workflow end-to-end; every result is stored
          with its configuration, backend, noise model, seed, and code version.
        </p>
      </div>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  const ok = value === "ok" || value === "Healthy";
  const cls = value === "…" ? "" : ok ? "ok" : "warn";
  return (
    <div className="metric-card">
      <div className={"badge " + cls}>{value}</div>
      <div className="label" style={{ marginTop: 6 }}>{label}</div>
    </div>
  );
}
