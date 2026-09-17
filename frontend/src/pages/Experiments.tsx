import { useEffect, useRef, useState } from "react";
import { get, post, API } from "../lib/api";
import { useInterval } from "../lib/charts";

const TEMPLATES: Record<string, any> = {
  "BB84 Eve comparison": {
    module: "bb84_study",
    config: { n_qubits: 512, eve_intercept_percent: [0, 25, 100] },
    objective: "How does QBER respond to intercept-resend fraction?",
    hypothesis: "QBER grows roughly linearly with the intercept probability, approaching 25%.",
  },
  "Repeater spacing study": {
    module: "network_study",
    config: {
      topology: {
        nodes: [
          { name: "Alice", type: "end", memory_slots: 8 },
          { name: "R", type: "repeater", memory_slots: 8 },
          { name: "Bob", type: "end", memory_slots: 8 },
        ],
        links: [
          { source: "Alice", destination: "R", distance_km: 25 },
          { source: "R", destination: "Bob", distance_km: 25 },
        ],
      },
      requests: [{ source: "Alice", destination: "Bob" }],
      sim_time_ms: 300,
    },
    sweep: [{ name: "sim_time_ms", values: [200, 500] }],
    objective: "Does more simulated time improve end-to-end entanglement delivery?",
    hypothesis: "Success probability increases with the attempt budget.",
  },
  "QEC logical error curve": {
    module: "qec_sweep",
    config: { code: "shor-9", physical_error_permille: [1, 2, 5, 10, 20, 50], trials_per_point: 1500 },
    objective: "Measure logical error suppression for Shor-9.",
    hypothesis: "Logical rate stays well below physical rate for small p.",
  },
  "Distributed GHZ study": {
    module: "distributed_circuit",
    config: {
      circuit: {
        schema: "quantumlab.circuit", version: 1, name: "ghz",
        num_qubits: 3, num_clbits: 0, metadata: {},
        operations: [
          { kind: "gate", gate: "H", params: [], qubits: [0], clbits: [], condition: null },
          { kind: "gate", gate: "CX", params: [], qubits: [0, 1], clbits: [], condition: null },
          { kind: "gate", gate: "CX", params: [], qubits: [1, 2], clbits: [], condition: null },
        ],
      },
      qubit_to_node: { 0: "node_0", 1: "node_1", 2: "node_1" },
      protocol: "single_ebit",
    },
    objective: "Does distributed GHZ preparation via remote CNOTs match the centralized reference?",
    hypothesis: "Equivalence fidelity reaches 1.0; ebit cost scales with cross-node edges.",
  },
  "Noisy distributed GHZ study": {
    module: "distributed_circuit",
    config: {
      circuit: {
        schema: "quantumlab.circuit", version: 1, name: "ghz-noisy",
        num_qubits: 3, num_clbits: 0, metadata: {},
        operations: [
          { kind: "gate", gate: "H", params: [], qubits: [0], clbits: [], condition: null },
          { kind: "gate", gate: "CX", params: [], qubits: [0, 1], clbits: [], condition: null },
          { kind: "gate", gate: "CX", params: [], qubits: [1, 2], clbits: [], condition: null },
        ],
      },
      qubit_to_node: { 0: "A", 1: "B", 2: "B" },
      protocol: "single_ebit",
      topology: {
        nodes: [
          { name: "A", type: "end", memory_slots: 4 },
          { name: "B", type: "end", memory_slots: 4 },
        ],
        links: [
          { source: "A", destination: "B", distance_km: 20, base_fidelity: 0.85 },
        ],
      },
      ebit_noise: "network_fidelity",
    },
    objective: "Does network-degraded entanglement fidelity propagate into the distributed computation?",
    hypothesis: "Equivalence fidelity tracks the granted ebit fidelity (Werner model); ebit cost is unchanged.",
  },
};

export default function Experiments() {
  const [experiments, setExperiments] = useState<any[]>([]);
  const [selected, setSelected] = useState<any>(null);
  const [resultDoc, setResultDoc] = useState<any>(null);
  const [jobs, setJobs] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [reproReport, setReproReport] = useState<any>(null);
  const [compareDoc, setCompareDoc] = useState<any>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const refresh = async () => {
    try {
      setExperiments(await get("/api/experiments"));
      setJobs(await get("/api/jobs"));
      // ROOT-CAUSE FIX (browser E2E, run-status milestone): the open
      // experiment's runs table was fetched once on click and never
      // refreshed, so live QUEUED/RUNNING/COMPLETED transitions and the
      // WebSocket-driven progress never reached the detail view. Reload it
      // whenever the backend reports activity.
      if (selected) {
        setSelected(await get(`/api/experiments/${selected.id}`));
      }
    } catch { /* backend offline indicator covers this */ }
  };

  useEffect(() => { refresh(); }, []);
  useEffect(() => {
    // Live job progress over WebSocket (directive §118).
    try {
      const ws = new WebSocket(`${API.replace(/^http/, "ws")}/ws/jobs`);
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
        if (msg.type === "job.progress") refresh();
      };
      wsRef.current = ws;
      return () => ws.close();
    } catch { return undefined; }
  }, []);

  useInterval(refresh, selected ? 1500 : null);

  const createFromTemplate = async (name: string) => {
    setError(null);
    try {
      const t = TEMPLATES[name];
      await post("/api/experiments", { name, ...t });
      await refresh();
    } catch (e: any) { setError(e.message); }
  };

  const openExperiment = async (expId: number) => {
    setError(null);
    try {
      const exp = await get(`/api/experiments/${expId}`);
      setSelected(exp);
      setResultDoc(null);
    } catch (e: any) { setError(e.message); }
  };

  const runAll = async (runIds: number[]) => {
    setError(null);
    try {
      await post("/api/runs/execute-batch", { run_ids: runIds });
      setTimeout(refresh, 400);
    } catch (e: any) { setError(e.message); }
  };

  const loadResult = async (runId: number) => {
    setError(null);
    setReproReport(null);
    try { setResultDoc((await get(`/api/runs/${runId}/result`)).document); }
    catch (e: any) { setResultDoc(null); setError(e.message); }
  };

  const reproduceRun = async (runId: number) => {
    setError(null);
    try {
      setReproReport(await post(`/api/runs/${runId}/reproduce`, {}));
      setTimeout(refresh, 600);
    } catch (e: any) { setError(e.message); }
  };

  const compareRecent = async () => {
    setError(null);
    try {
      const done = (selected?.runs ?? [])
        .filter((r: any) => r.status === "COMPLETED")
        .slice(0, 2);
      if (done.length < 2) {
        setError("Need at least two completed runs to compare.");
        return;
      }
      setCompareDoc(await post("/api/experiments/compare", {
        run_ids: done.map((r: any) => r.id),
      }));
    } catch (e: any) { setError(e.message); }
  };

  const cancelRun = async (runId: number) => {
    setError(null);
    try {
      const jobs = await get("/api/jobs");
      const mine = (jobs as any[]).filter(
        (j) => j.payload?.run_id === runId && (j.status === "QUEUED" || j.status === "RUNNING"),
      );
      if (mine.length === 0) throw new Error("No cancellable job for this run.");
      const job = mine.reduce((a, b) => (a.job_id > b.job_id ? a : b));
      await post(`/api/jobs/${job.job_id}/cancel`);
      setTimeout(refresh, 300);
    } catch (e: any) { setError(e.message); }
  };

  return (
    <div>
      <h1 className="page-title">Experiments</h1>
      <p className="page-sub">
        Every experiment is a definition; every run records its resolved configuration,
        seed, backend, noise model, status, and results — reproducible by construction.
      </p>

      {error && <div className="error-box">{error}</div>}

      <div className="panel">
        <h3>Create from template</h3>
        <div className="row">
          {Object.keys(TEMPLATES).map((name) => (
            <button key={name} className="btn secondary small"
                    onClick={() => createFromTemplate(name)}>
              + {name}
            </button>
          ))}
        </div>
      </div>

      <div className="grid2">
        <div className="panel">
          <h3>Saved experiments</h3>
          <table className="data-table">
            <thead><tr><th>#</th><th>Name</th><th>Module</th><th>Runs</th></tr></thead>
            <tbody>
              {experiments.map((e) => (
                <tr key={e.id} style={{ cursor: "pointer" }} onClick={() => openExperiment(e.id)}>
                  <td>{e.id}</td>
                  <td>{e.name}</td>
                  <td>{e.module}</td>
                  <td>{e.run_count}</td>
                </tr>
              ))}
              {experiments.length === 0 && (
                <tr><td colSpan={4} style={{ color: "var(--text-dim)" }}>None yet — create one from a template.</td></tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="panel">
          <h3>Job queue</h3>
          <table className="data-table">
            <thead><tr><th>Job</th><th>Status</th><th>Progress</th><th>Run</th></tr></thead>
            <tbody>
              {jobs.slice(0, 10).map((j) => (
                <tr key={j.job_id}>
                  <td>#{j.job_id}</td>
                  <td><span className={"badge " + (j.status === "COMPLETED" ? "ok" : j.status === "FAILED" ? "err" : "warn")}>{j.status}</span></td>
                  <td style={{ minWidth: 90 }}>
                    <div className="progress-track"><div className="progress-fill" style={{ width: `${Math.round(j.progress * 100)}%` }} /></div>
                  </td>
                  <td>{j.payload?.run_id}</td>
                </tr>
              ))}
              {jobs.length === 0 && (
                <tr><td colSpan={4} style={{ color: "var(--text-dim)" }}>Idle.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {selected && (
        <div className="panel">
          <h3>Experiment #{selected.id}: {selected.name}</h3>
          <p className="kv">
            Module: <b>{selected.module}</b>
            {selected.objective && <> · Objective: {selected.objective}</>}
            {selected.hypothesis && <> · Hypothesis: {selected.hypothesis}</>}
          </p>
          <table className="data-table">
            <thead>
              <tr><th>Run</th><th>Label</th><th>Status</th><th>Seed</th><th></th></tr>
            </thead>
            <tbody>
              {selected.runs.map((r: any) => (
                <tr key={r.id}>
                  <td>{r.id}</td>
                  <td>{r.label}</td>
                  <td><span className={"badge " + (r.status === "COMPLETED" ? "ok" : r.status === "FAILED" ? "err" : "warn")}>{r.status}</span></td>
                  <td>{r.seed}</td>
                  <td>
                    <span className="row" style={{ gap: 6 }}>
                      {(r.status === "QUEUED" || r.status === "RUNNING") && (
                        <button className="btn small secondary" onClick={() => cancelRun(r.id)}>Cancel</button>
                      )}
                      {r.status === "COMPLETED" && (
                        <>
                          <button className="btn small secondary" onClick={() => loadResult(r.id)}>View result</button>
                          <button className="btn small secondary" onClick={() => reproduceRun(r.id)}>Reproduce</button>
                        </>
                      )}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="row" style={{ marginTop: 10 }}>
            <button className="btn" onClick={() => runAll(selected.runs.map((r: any) => r.id))}>
              Execute all runs
            </button>
            <button className="btn secondary"
                    onClick={() => loadResult(selected.runs.find((r: any) => r.status === "COMPLETED")?.id)}>
              View latest result
            </button>
            <button className="btn secondary" onClick={compareRecent}>
              Compare last two completed runs
            </button>
          </div>
        </div>
      )}

      {compareDoc && (
        <div className="panel">
          <h3>Run comparison</h3>
          <p className="kv">
            Differing configuration parameters:{" "}
            <b>{compareDoc.differing_parameters.length > 0
              ? compareDoc.differing_parameters.join(", ")
              : "none"}</b>
          </p>
          <table className="data-table">
            <thead><tr><th>Run</th><th>Label</th><th>Status</th><th>Seed</th><th>Key metrics</th></tr></thead>
            <tbody>
              {compareDoc.runs.map((r: any) => (
                <tr key={r.run_id}>
                  <td>{r.run_id}</td>
                  <td>{r.label}</td>
                  <td>{r.status}</td>
                  <td>{r.seed}</td>
                  <td style={{ fontSize: 11.5 }}>
                    {r.metrics ? JSON.stringify(r.metrics).slice(0, 300) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {reproReport && (
        <div className="panel">
          <h3>Reproduction report</h3>
          <p className="kv">
            Original run <b>#{reproReport.run_id}</b> → reproduced run{" "}
            <b>#{reproReport.reproduced_run_id}</b>
          </p>
          <p className="kv">
            Verdict:{" "}
            <span className={"badge " + (reproReport.status === "EXACT_MATCH" ? "ok" : "warn")}>
              {reproReport.status}
            </span>
          </p>
          {reproReport.differences?.length > 0 && (
            <ul className="note-list">{reproReport.differences.map((d: string, i: number) => <li key={i}>{d}</li>)}</ul>
          )}
          {reproReport.differences?.length === 0 && <p>No differences between the result documents.</p>}
        </div>
      )}

      {resultDoc && (
        <div className="panel">
          <h3>Result document ({resultDoc.module})</h3>
          {resultDoc.module === "distributed_circuit" ? (
            <DistributedResultView doc={resultDoc} />
          ) : (
            <>
              <div className="metric-cards">
                {Object.entries(resultDoc.metrics).slice(0, 6).map(([k, v]: any) => (
                  <div className="metric-card" key={k}>
                    <div className="value" style={{ fontSize: 15 }}>{typeof v === "number" ? Number(v.toFixed(4)) : String(v)}</div>
                    <div className="label">{k.replace(/_/g, " ")}</div>
                  </div>
                ))}
              </div>
              {resultDoc.artifacts?.table && (
                <table className="data-table">
                  <thead>
                    <tr>{Object.keys(resultDoc.artifacts.table[0]).map((c) => <th key={c}>{c}</th>)}</tr>
                  </thead>
                  <tbody>
                    {resultDoc.artifacts.table.map((row: any, i: number) => (
                      <tr key={i}>{Object.values(row).map((v: any, j: number) => (
                        <td key={j}>{typeof v === "number" ? Number(v.toPrecision(5)) : String(v)}</td>
                      ))}</tr>
                    ))}
                  </tbody>
                </table>
              )}
              {resultDoc.summary && Object.keys(resultDoc.summary).length > 0 && (
                <pre className="event-log">{JSON.stringify(resultDoc.summary, null, 2).slice(0, 1200)}</pre>
              )}
            </>
          )}
          <ul className="note-list">{resultDoc.notes.map((n: string, i: number) => <li key={i}>{n}</li>)}</ul>
        </div>
      )}
    </div>
  );
}

/** Dedicated view for distributed_circuit result documents. Every value shown
 * here is copied from the backend document (metrics / summary / artifacts). */
function DistributedResultView({ doc }: { doc: any }) {
  const eq = doc.summary?.equivalence;
  const dist = doc.artifacts?.distributed_result;
  const grants = doc.artifacts?.entanglement_operations ?? [];
  const remoteOps = doc.artifacts?.remote_operations ?? [];
  const msgs = doc.artifacts?.classical_messages ?? [];
  const probs = doc.artifacts?.output_probabilities ?? {};

  return (
    <>
      <div className="metric-cards">
        <Metric label="Status" value={doc.metrics.status} />
        <Metric label="Protocol" value={doc.metrics.protocol} />
        <Metric label="Ebits consumed" value={String(doc.metrics.ebit_consumption)} />
        <Metric label="Remote CNOTs" value={String(doc.metrics.remote_cnot_count)} />
        <Metric label="Classical bits" value={String(doc.metrics.classical_message_count)} />
        <Metric label="Nodes" value={String(doc.metrics.node_count)} />
        <Metric label="Qubits" value={String(doc.metrics.qubit_count)} />
        {doc.metrics.ebit_noise && <Metric label="Ebit noise" value={doc.metrics.ebit_noise} />}
        {doc.metrics.mean_ebit_fidelity !== undefined && (
          <Metric label="Mean ebit fidelity" value={String(doc.metrics.mean_ebit_fidelity)} />
        )}
      </div>

      {doc.metrics.modeled_network_latency_ms !== undefined && (
        <p className="kv" style={{ marginTop: 8 }}>
          Modelled network latency: <b>{doc.metrics.modeled_network_latency_ms.toFixed(3)} ms</b>{" "}
          <span style={{ color: "var(--text-dim)" }}>(network model — not simulator runtime)</span>
        </p>
      )}

      <div className="panel" style={{ marginTop: 12 }}>
        <h3>Equivalence vs centralized reference</h3>
        {eq ? (
          <p className="kv">
            Verdict:{" "}
            <span className={"badge " + (eq.passed ? "ok" : "err")}>
              {eq.passed ? "MATCHES CENTRALIZED" : "MISMATCH"}
            </span>{" "}
            · Uhlmann fidelity <b>{eq.fidelity}</b> · tolerance {eq.tolerance}
          </p>
        ) : (
          <p className="kv" style={{ color: "var(--text-dim)" }}>Not computed for this run.</p>
        )}
        {eq?.note && (
          <p className="kv" style={{ color: "var(--text-dim)" }}>{eq.note}</p>
        )}
      </div>

      {grants.length > 0 && (
        <>
          <h3 style={{ marginTop: 14 }}>Entanglement resources (from the network model)</h3>
          <table className="data-table">
            <thead><tr><th>Pair</th><th>Model</th><th>Fidelity</th><th>Latency</th><th>Attempts</th><th>Status</th></tr></thead>
            <tbody>
              {grants.map((g: any, i: number) => (
                <tr key={i}>
                  <td>{g.node_a} ↔ {g.node_b}</td>
                  <td>{g.model}</td>
                  <td>{g.fidelity === null ? "—" : Number(g.fidelity).toFixed(4)}</td>
                  <td>{g.latency_ns === null ? "—" : `${(g.latency_ns / 1e6).toFixed(3)} ms`}</td>
                  <td>{g.attempts ?? "—"}</td>
                  <td>{g.success ? <span className="badge ok">granted</span> : <span className="badge err">{g.failure_reason ?? "failed"}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {remoteOps.length > 0 && (
        <>
          <h3 style={{ marginTop: 14 }}>Remote operations</h3>
          <table className="data-table">
            <thead><tr><th>Gate</th><th>Edge</th><th>Protocol</th><th>Ebits</th><th>Ebit F</th><th>Werner sample</th><th>Status</th></tr></thead>
            <tbody>
              {remoteOps.map((r: any, i: number) => (
                <tr key={i}>
                  <td>{r.gate}(q{r.control_qubit},q{r.target_qubit})</td>
                  <td>{r.source_node} → {r.target_node}</td>
                  <td>{r.protocol}</td>
                  <td>{r.ebits_required}</td>
                  <td>{r.ebit_fidelity_applied == null ? "—" : `F = ${Number(r.ebit_fidelity_applied).toFixed(4)}`}</td>
                  <td>{r.ebit_noise == null ? "—" : r.ebit_noise.join(", ")}</td>
                  <td>{r.executed ? <span className="badge ok">executed</span> : <span className="badge err">{r.failure_reason ?? "failed"}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {msgs.length > 0 && (
        <>
          <h3 style={{ marginTop: 14 }}>Classical communication</h3>
          <table className="data-table">
            <thead><tr><th>Order</th><th>Sender</th><th>Receiver</th><th>Bits</th><th>Remote op</th></tr></thead>
            <tbody>
              {msgs.map((m: any, i: number) => (
                <tr key={i}>
                  <td>{m.order}</td><td>{m.source_node}</td><td>{m.target_node}</td>
                  <td>{m.bits}</td><td>{m.remote_op_index}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {Object.keys(probs).length > 0 && (
        <>
          <h3 style={{ marginTop: 14 }}>Output probabilities (logical qubits)</h3>
          <table className="data-table">
            <thead><tr><th>Outcome</th><th>Probability</th></tr></thead>
            <tbody>
              {Object.entries(probs).map(([k, v]: any) => (
                <tr key={k}><td>|{k}⟩</td><td>{Number(v).toFixed(9)}</td></tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {dist && (
        <details style={{ marginTop: 12 }}>
          <summary className="kv" style={{ cursor: "pointer" }}>
            Raw distributed-result document ({dist.schema} v{dist.version})
          </summary>
          <pre className="event-log">{JSON.stringify(dist, null, 2).slice(0, 4000)}</pre>
        </details>
      )}
    </>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-card">
      <div className="value">{value}</div>
      <div className="label">{label}</div>
    </div>
  );
}
