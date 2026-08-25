import { useEffect, useRef, useState } from "react";
import { get, post } from "../lib/api";
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
};

export default function Experiments() {
  const [experiments, setExperiments] = useState<any[]>([]);
  const [selected, setSelected] = useState<any>(null);
  const [resultDoc, setResultDoc] = useState<any>(null);
  const [jobs, setJobs] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const refresh = async () => {
    try {
      setExperiments(await get("/api/experiments"));
      setJobs(await get("/api/jobs"));
    } catch { /* backend offline indicator covers this */ }
  };

  useEffect(() => { refresh(); }, []);
  useEffect(() => {
    // Live job progress over WebSocket (directive §118).
    try {
      const ws = new WebSocket("ws://127.0.0.1:8000/ws/jobs");
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
    try { setResultDoc((await get(`/api/runs/${runId}/result`)).document); }
    catch (e: any) { setResultDoc(null); setError(e.message); }
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
                    {r.status === "COMPLETED" && (
                      <button className="btn small secondary" onClick={() => loadResult(r.id)}>View result</button>
                    )}
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
          </div>
        </div>
      )}

      {resultDoc && (
        <div className="panel">
          <h3>Result document ({resultDoc.module})</h3>
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
          <ul className="note-list">{resultDoc.notes.map((n: string, i: number) => <li key={i}>{n}</li>)}</ul>
        </div>
      )}
    </div>
  );
}
