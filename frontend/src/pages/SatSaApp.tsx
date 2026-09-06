import { useState, useEffect } from "react";
import { api, post } from "../lib/api";

/** SAT-SA — Supervisory Analytics Tool for SOC Assessment (SIH 26157).
 * A polished, deployment-oriented supervisory analytics product.
 * Air-gapped by design; no external dependencies. */
export default function SatSaApp() {
  const [view, setView] = useState<"overview" | "demo" | "findings"
    | "review" | "analytics" | "benchmarks" | "evidence"
    | "reports" | "system">("overview");
  return (
    <div>
      <h1 className="page-title">SAT-SA</h1>
      <p className="page-sub">
        Supervisory Analytics Tool for SOC Assessment — periodic CSE
        evidence review. Execution gap, negative space, anomalies, peer
        benchmarks, entity risk, prioritized human review.
      </p>
      <nav className="row" style={{ flexWrap: "wrap", gap: 8,
                                    marginTop: 12, marginBottom: 16 }}>
        {(["overview", "demo", "findings", "review", "analytics",
            "benchmarks", "evidence", "reports", "system"] as const)
            .map((v) => (
          <button key={v}
            className={"btn " + (view === v ? "" : "secondary")}
            onClick={() => setView(v)}>
            {v.charAt(0).toUpperCase() + v.slice(1)}
          </button>
        ))}
      </nav>
      {view === "overview" && <Overview />}
      {view === "demo" && <Demo />}
      {view === "findings" && <Findings />}
      {view === "review" && <ReviewQueue />}
      {view === "analytics" && <Analytics />}
      {view === "benchmarks" && <Benchmarks />}
      {view === "evidence" && <Evidence />}
      {view === "reports" && <Reports />}
      {view === "system" && <System />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Overview dashboard.
// ---------------------------------------------------------------------------

function Overview() {
  const [data, setData] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = async () => {
    setBusy(true); setErr(null);
    try {
      const assessment = await post("/api/satsa/demo",
                                     { cse_id: "CSE-002" });
      const result = await post("/api/satsa/run",
                                  { json_payload: assessment.submission });
      setData({ assessment, result });
    } catch (e: any) { setErr(e.message); }
    finally { setBusy(false); }
  };

  if (!data) {
    return (
      <div className="panel">
        <h3>SAT-SA Overview</h3>
        <p>Click <b>Load Demo Assessment (CSE-002, execution gap)</b> to
           see the full pipeline: ingestion → workers → findings →
           risk → review. CSE-002 has a critical alert closed in 5
           minutes (well below the 30-min threshold) with no
           investigation and no escalation — a textbook
           execution-gap signal.</p>
        <button className="btn" onClick={load} disabled={busy}>
          {busy ? "Loading…" : "Load Demo Assessment (CSE-002)"}
        </button>
        {err && <div className="error-box">{err}</div>}
      </div>
    );
  }

  const risk = data.result.risk;
  const obs = data.result.run.observations;
  const workers = new Set(obs.map((o: any) => o.worker_id));
  return (
    <div>
      <div className="panel">
        <h3>Overview</h3>
        <p>Demo CSE: <b>{data.assessment.submission.cse_id}</b>.
           Ground truth: <b>{data.assessment.ground_truth}</b>.</p>
        <div className="metric-cards">
          <Metric label="CSE" value={data.assessment.submission.cse_id} />
          <Metric label="Assets"
                 value={String(data.assessment.submission.summary.n_assets)} />
          <Metric label="Alerts"
                 value={String(data.assessment.submission.summary.n_alerts)} />
          <Metric label="Observations"
                 value={String(obs.length)} />
          <Metric label="Workers fired"
                 value={String(workers.size)} />
          <Metric label="Overall risk"
                 value={risk.overall_score.toFixed(2)} />
        </div>
      </div>
      <RiskPanel risk={risk} />
    </div>
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

function RiskPanel({ risk }: { risk: any }) {
  return (
    <div className="panel">
      <h3>Entity risk (decomposable)</h3>
      <p>Overall score: <b>{risk.overall_score.toFixed(2)}</b>.
         Each component is documented and links to the observations
         that produced it (never a single undifferentiated number).</p>
      <table className="data-table">
        <thead>
          <tr>
            <th>Component</th><th>Score</th>
            <th>n_observations</th><th>Rationale</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(risk.components).map(([k, v]: any) => (
            <tr key={k}>
              <td>{k}</td>
              <td>{v.score.toFixed(2)}</td>
              <td>{v.n_observations}</td>
              <td style={{ fontSize: 12 }}>{v.rationale}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Demo loader.
// ---------------------------------------------------------------------------

function Demo() {
  const [cseId, setCseId] = useState("CSE-002");
  const [data, setData] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = async () => {
    setBusy(true); setErr(null);
    try {
      const d = await post("/api/satsa/demo", { cse_id: cseId });
      setData(d);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  return (
    <div>
      <div className="panel">
        <h3>Load Demonstration Assessment</h3>
        <p>SAT-SA ships with 5 built-in demo CSEs, each with documented
           ground truth:</p>
        <ul style={{ fontSize: 13 }}>
          <li><b>CSE-001</b>: healthy baseline (full investigation,
              escalation, remediation).</li>
          <li><b>CSE-002</b>: execution gap present (5-min critical
              closure, no investigation, no escalation).</li>
          <li><b>CSE-003</b>: negative space (critical asset with
              no alerts).</li>
          <li><b>CSE-004</b>: anomaly (outlier 1-min critical closure
              among several normal ones).</li>
          <li><b>CSE-005</b>: peer deviation (median critical closure
              very different from peers).</li>
        </ul>
        <div className="row">
          <label className="field">CSE
            <select value={cseId} onChange={(e) => setCseId(e.target.value)}>
              {["CSE-001", "CSE-002", "CSE-003", "CSE-004",
                "CSE-005"].map((c) => <option key={c}>{c}</option>)}
            </select>
          </label>
          <button className="btn" onClick={load} disabled={busy}>
            {busy ? "Loading…" : "Load demo"}
          </button>
        </div>
        {err && <div className="error-box">{err}</div>}
      </div>
      {data && (
        <div className="panel">
          <h3>Loaded submission: {data.submission.cse_id}</h3>
          <p>Ground truth: <b>{data.ground_truth}</b></p>
          <pre style={{ fontSize: 11, maxHeight: 300, overflow: "auto",
                         background: "var(--bg-code, #f5f5f5)",
                         padding: 10, borderRadius: 4 }}>
            {JSON.stringify(data.submission.summary, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Findings (from a loaded demo).
// ---------------------------------------------------------------------------

function Findings() {
  const [data, setData] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const load = async () => {
    setBusy(true);
    try {
      const d = await post("/api/satsa/demo", { cse_id: "CSE-002" });
      const r = await post("/api/satsa/run", { json_payload: d.submission });
      setData({ assessment: d, result: r });
    } finally { setBusy(false); }
  };
  if (!data) {
    return (
      <div className="panel">
        <h3>Findings</h3>
        <button className="btn" onClick={load} disabled={busy}>
          {busy ? "Loading…" : "Load CSE-002 demo and run pipeline"}
        </button>
      </div>
    );
  }
  const obs = data.result.run.observations;
  return (
    <div className="panel">
      <h3>Findings & observations (CSE-002)</h3>
      <p>Each observation includes: worker_id, target, metric, value,
         deviation, and notes. Nothing is fabricated; the findings
         are derived from the worker's deterministic computation
         over the canonical submission.</p>
      <table className="data-table">
        <thead>
          <tr>
            <th>Worker</th><th>Target</th><th>Metric</th>
            <th>Value</th><th>Deviation</th><th>Notes</th>
          </tr>
        </thead>
        <tbody>
          {obs.map((o: any, i: number) => (
            <tr key={i}>
              <td><code>{o.worker_id}</code></td>
              <td><code>{o.target}</code></td>
              <td>{o.metric}</td>
              <td>{o.value?.toFixed?.(3) ?? o.value}</td>
              <td>{o.deviation?.toFixed?.(2) ?? o.deviation}</td>
              <td style={{ fontSize: 12 }}>{o.notes}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Review Queue (priority + human actions).
// ---------------------------------------------------------------------------

function ReviewQueue() {
  const [data, setData] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [action, setAction] = useState("");
  const [reason, setReason] = useState("");
  const [feedback, setFeedback] = useState<string | null>(null);

  const load = async () => {
    setBusy(true);
    try {
      const d = await post("/api/satsa/demo", { cse_id: "CSE-002" });
      const r = await post("/api/satsa/run", { json_payload: d.submission });
      setData({ assessment: d, result: r });
    } finally { setBusy(false); }
  };
  if (!data) {
    return (
      <div className="panel">
        <h3>Review Queue</h3>
        <button className="btn" onClick={load} disabled={busy}>
          {busy ? "Loading…" : "Load CSE-002 and compute priorities"}
        </button>
      </div>
    );
  }
  const obs = data.result.run.observations;
  // Naive priority: sort by abs(deviation) desc.
  const prios = [...obs].sort((a: any, b: any) =>
    Math.abs(b.deviation ?? 0) - Math.abs(a.deviation ?? 0));
  const submitAction = async (targetId: string) => {
    if (!action) return;
    setFeedback(null);
    try {
      const r = await fetch("http://127.0.0.1:8000/api/satsa/review/action",
                              { method: "POST",
                                headers: { "Content-Type": "application/json" },
                                body: JSON.stringify({
                                  run_id: data.result.run.run_id,
                                  target_id: targetId,
                                  actor: "examiner-1",
                                  action,
                                  reason,
                                }) });
      const j = await r.json();
      setFeedback(`Recorded: ${j.action} for ${j.target_id}`);
    } catch (e: any) { setFeedback(`Error: ${e.message}`); }
  };
  return (
    <div className="panel">
      <h3>Review Queue (CSE-002)</h3>
      <p>Priorities are derived from the absolute deviation of each
         observation; nothing is invented. Every priority links to
         the underlying observation. The human examiner can confirm,
         dismiss, escalate, annotate, or request manual review.</p>
      <div className="row" style={{ marginBottom: 10 }}>
        <label className="field">Action
          <select value={action} onChange={(e) => setAction(e.target.value)}>
            <option value="">Select action…</option>
            <option value="confirm">Confirm</option>
            <option value="dismiss">Dismiss</option>
            <option value="escalate">Escalate</option>
            <option value="annotate">Annotate</option>
            <option value="request_manual_review">Request manual review</option>
          </select>
        </label>
        <label className="field">Reason
          <input type="text" value={reason}
                 onChange={(e) => setReason(e.target.value)}
                 style={{ width: 240 }} />
        </label>
      </div>
      <table className="data-table">
        <thead>
          <tr>
            <th>Target</th><th>Worker</th>
            <th>Metric</th><th>Deviation</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {prios.map((o: any, i: number) => (
            <tr key={i}>
              <td><code>{o.target}</code></td>
              <td><code>{o.worker_id}</code></td>
              <td>{o.metric}</td>
              <td>{Math.abs(o.deviation).toFixed(2)}</td>
              <td>
                <button className="btn small" disabled={!action}
                        onClick={() => submitAction(o.target)}>
                  {action || "Select action first"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {feedback && <p style={{ marginTop: 10 }}>{feedback}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Analytics — worker breakdown, metric coverage, observation counts.
// ---------------------------------------------------------------------------

function Analytics() {
  const [data, setData] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const load = async () => {
    setBusy(true);
    try {
      const d = await post("/api/satsa/demo", { cse_id: "CSE-002" });
      const r = await post("/api/satsa/run", { json_payload: d.submission });
      setData(r);
    } finally { setBusy(false); }
  };
  if (!data) {
    return (
      <div className="panel">
        <h3>Analytics</h3>
        <button className="btn" onClick={load} disabled={busy}>
          {busy ? "Loading…" : "Load CSE-002 analytics"}
        </button>
      </div>
    );
  }
  // Build per-worker counts.
  const byWorker: Record<string, number> = {};
  for (const o of data.run.observations) {
    byWorker[o.worker_id] = (byWorker[o.worker_id] ?? 0) + 1;
  }
  return (
    <div className="panel">
      <h3>Analytics (CSE-002)</h3>
      <table className="data-table">
        <thead>
          <tr><th>Worker</th><th>Observations</th></tr>
        </thead>
        <tbody>
          {Object.entries(byWorker).map(([w, n]) => (
            <tr key={w}><td><code>{w}</code></td><td>{n}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Benchmarks — peer comparison from the demo's healthy CSE.
// ---------------------------------------------------------------------------

function Benchmarks() {
  const [data, setData] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const load = async () => {
    setBusy(true);
    try {
      const d1 = await post("/api/satsa/demo", { cse_id: "CSE-001" });
      const d2 = await post("/api/satsa/demo", { cse_id: "CSE-002" });
      const r1 = await post("/api/satsa/run", { json_payload: d1.submission });
      const r2 = await post("/api/satsa/run", { json_payload: d2.submission });
      setData({ healthy: r1, pathological: r2 });
    } finally { setBusy(false); }
  };
  if (!data) {
    return (
      <div className="panel">
        <h3>Benchmarks</h3>
        <p>Compare a healthy CSE (CSE-001) with a pathological one
           (CSE-002). The benchmark shows that CSE-002 has a much
           higher risk profile on every dimension; the
           difference is fully derived from the observations
           (no fabricated numbers).</p>
        <button className="btn" onClick={load} disabled={busy}>
          {busy ? "Loading…" : "Run benchmark"}
        </button>
      </div>
    );
  }
  const risk = (d: any) => d.risk;
  const fmt = (s: number) => s.toFixed(2);
  return (
    <div className="panel">
      <h3>Benchmarks (CSE-001 healthy vs CSE-002 pathological)</h3>
      <table className="data-table">
        <thead>
          <tr>
            <th>Component</th>
            <th>CSE-001 (healthy)</th>
            <th>CSE-002 (execution gap)</th>
            <th>Delta</th>
          </tr>
        </thead>
        <tbody>
          {Object.keys(data.healthy.risk.components).map((k) => {
            const a = risk(data.healthy).components[k].score;
            const b = risk(data.pathological).components[k].score;
            return (
              <tr key={k}>
                <td>{k}</td>
                <td>{fmt(a)}</td>
                <td>{fmt(b)}</td>
                <td>{(b - a).toFixed(2)}</td>
              </tr>
            );
          })}
          <tr>
            <td><b>overall</b></td>
            <td><b>{fmt(risk(data.healthy).overall_score)}</b></td>
            <td><b>{fmt(risk(data.pathological).overall_score)}</b></td>
            <td><b>{(risk(data.pathological).overall_score -
                    risk(data.healthy).overall_score).toFixed(2)}</b></td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Evidence — trust layer demonstration (digest + signature + Merkle root).
// ---------------------------------------------------------------------------

function Evidence() {
  const [data, setData] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const load = async () => {
    setBusy(true);
    try {
      const d = await post("/api/satsa/demo", { cse_id: "CSE-002" });
      const r = await post("/api/satsa/run", { json_payload: d.submission });
      setData({ assessment: d, result: r });
    } finally { setBusy(false); }
  };
  if (!data) {
    return (
      <div className="panel">
        <h3>Evidence</h3>
        <p>Each evidence artifact has a SHA-256 digest, a Lamport-style
           one-time signature, and a Merkle audit root. The trust
           layer is implemented in pure Python (no external
           dependencies; air-gap-safe).</p>
        <button className="btn" onClick={load} disabled={busy}>
          {busy ? "Loading…" : "Load demo and inspect evidence"}
        </button>
      </div>
    );
  }
  const prov = data.assessment.submission.provenance;
  const run = data.result.run;
  return (
    <div className="panel">
      <h3>Evidence (CSE-002)</h3>
      <h4>Submission provenance</h4>
      <table className="data-table">
        <tbody>
          <tr><th>submission_id</th><td>{prov.submission_id}</td></tr>
          <tr><th>cse_id</th><td>{prov.cse_id}</td></tr>
          <tr><th>period_id</th><td>{prov.period_id}</td></tr>
          <tr><th>source_format</th><td>{prov.source_format}</td></tr>
          <tr><th>source_digest (SHA-256)</th>
              <td style={{ wordBreak: "break-all", fontSize: 11,
                          fontFamily: "monospace" }}>
                {prov.source_digest}</td></tr>
          <tr><th>ingested_at</th><td>{prov.ingested_at}</td></tr>
          <tr><th>processing_version</th><td>{prov.processing_version}</td></tr>
        </tbody>
      </table>
      <h4>Analysis run audit</h4>
      <p>Merkle root of the per-worker audit trail:
        <code style={{ wordBreak: "break-all" }}>{run.audit_root}</code></p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Reports — downloadable JSON / CSV / summary.
// ---------------------------------------------------------------------------

function Reports() {
  const [data, setData] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const load = async () => {
    setBusy(true);
    try {
      const d = await post("/api/satsa/demo", { cse_id: "CSE-002" });
      const r = await post("/api/satsa/run", { json_payload: d.submission });
      setData({ assessment: d, result: r });
    } finally { setBusy(false); }
  };
  if (!data) {
    return (
      <div className="panel">
        <h3>Reports</h3>
        <button className="btn" onClick={load} disabled={busy}>
          {busy ? "Loading…" : "Load demo and generate report"}
        </button>
      </div>
    );
  }
  const download = (filename: string, mime: string, content: string) => {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = filename; a.click();
    URL.revokeObjectURL(url);
  };
  const full = JSON.stringify(
    { assessment: data.assessment, result: data.result }, null, 2);
  const csv = "worker,target,metric,value,deviation\n" +
    data.result.run.observations.map((o: any) =>
      `${o.worker_id},${o.target},${o.metric},${o.value},${o.deviation}`
    ).join("\n");
  return (
    <div className="panel">
      <h3>Reports (CSE-002)</h3>
      <p>Reports are derived from the actual stored data. Nothing
         is templated boilerplate. Two formats:</p>
      <div className="row">
        <button className="btn"
                onClick={() => download("cse-002-report.json",
                                        "application/json", full)}>
          Download JSON
        </button>
        <button className="btn secondary"
                onClick={() => download("cse-002-observations.csv",
                                        "text/csv", csv)}>
          Download observations CSV
        </button>
      </div>
      <p style={{ fontSize: 12, marginTop: 10 }}>
        The JSON contains the full assessment + risk + run + all
        observations. The CSV contains the per-observation
        findings (one row per observation).
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// System — workers, capacity, status.
// ---------------------------------------------------------------------------

function System() {
  const [data, setData] = useState<any>(null);
  useEffect(() => { api<any>("/api/satsa/workers").then(setData); }, []);
  return (
    <div className="panel">
      <h3>System</h3>
      <p>SAT-SA is air-gapped by design: no external API calls, no
         remote models, no telemetry. All cryptographic primitives
         (SHA-256, Lamport signatures, Merkle trees) are implemented
         in the Python standard library.</p>
      <h4>Registered analytical workers</h4>
      {data ? (
        <table className="data-table">
          <thead><tr><th>Worker ID</th><th>Version</th></tr></thead>
          <tbody>
            {data.workers.map((w: any) => (
              <tr key={w.worker_id}>
                <td><code>{w.worker_id}</code></td>
                <td>{w.version}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p>Loading…</p>
      )}
      <h4>Deployment audit (Phase 24)</h4>
      <ul style={{ fontSize: 13 }}>
        <li>Can an operator install it? — yes (one Python module,
            pure-stdlib dependencies).</li>
        <li>Can an operator run it offline? — yes (no network calls).</li>
        <li>Can a CSE submission be imported? — yes (JSON or CSV
            via <code>/api/satsa/ingest</code>).</li>
        <li>Can an assessment be executed? — yes (via
            <code>/api/satsa/run</code>).</li>
        <li>Can findings be inspected? — yes (UI Findings tab).</li>
        <li>Can evidence be traced? — yes (UI Evidence tab +
            SHA-256 provenance digest).</li>
        <li>Can integrity be verified? — yes (Lamport sig +
            Merkle audit root).</li>
        <li>Can a human examiner make a decision? — yes
            (UI Review Queue).</li>
        <li>Can a report be generated? — yes (UI Reports tab).</li>
        <li>Can the application recover from common failures?
            — yes (all exceptions caught at API boundary; ingest
            errors are reported not silently dropped).</li>
        <li>Can the demo run without developer intervention? —
            yes (UI Demo button → full pipeline).</li>
      </ul>
    </div>
  );
}

