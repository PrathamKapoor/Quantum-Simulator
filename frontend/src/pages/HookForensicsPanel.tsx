import { useState } from "react";
import { get } from "../lib/api";

/** Hook-error forensic analysis (milestone 14, Phase B).
 * Renders the per-stabilizer fault catalogue with danger
 * classification. All values come from the backend. */
export default function HookForensicsPanel() {
  const [d, setD] = useState(3);
  const [round, setRound] = useState(1);
  const [report, setReport] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setBusy(true); setError(null);
    try {
      setReport(await get(
        `/api/qec/rotated-surface-code/hook-forensics?d=${d}&round=${round}`));
    } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };

  return (
    <div className="panel">
      <h3>Hook-error forensics (Phase B)</h3>
      <p style={{ fontSize: 12.5, color: "var(--text-dim)", marginTop: 0 }}>
        Programmatic enumeration of every ancilla Pauli at every CNOT
        position for every stabilizer. Each entry is classified as
        SAFE / STABILIZER_EQUIVALENT / DATA_HOOK / LOGICAL_RISK /
        LOGICAL. Forensic evidence drives any hook-safe schedule design.
      </p>
      <div className="row" style={{ flexWrap: "wrap", gap: 10 }}>
        <label className="field">Distance
          <select value={d} onChange={(e) => { setD(+e.target.value); setReport(null); }}>
            {[3, 5, 7].map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
        </label>
        <label className="field">Round
          <input type="number" min={1} max={16} value={round}
                 onChange={(e) => setRound(Math.max(1, Math.min(16, +e.target.value || 1)))}
                 style={{ width: 70 }} />
        </label>
        <button className="btn" disabled={busy} onClick={load}>
          {busy ? "Running forensic analysis…" : "Run hook forensics"}
        </button>
      </div>

      {error && <div className="error-box">{error}</div>}

      {report && (
        <>
          <div className="metric-cards" style={{ marginTop: 8 }}>
            <Metric label="Total reports"
              value={String(report.summary.total_reports)} />
            <Metric label="SAFE"
              value={String(report.summary.safe_count)} />
            <Metric label="Data hooks"
              value={String(report.summary.data_hook_count)} />
            <Metric label="Logical risk"
              value={String(report.summary.logical_risk_count)} />
            <Metric label="Max hook weight"
              value={String(report.summary.max_hook_weight)} />
            <Metric label="Boundary data hooks"
              value={String(report.summary.boundary_data_hook_count)} />
          </div>
          <table className="data-table" style={{ marginTop: 8 }}>
            <thead>
              <tr>
                <th>Stabilizer</th>
                <th>Data hook</th>
                <th>Logical risk</th>
                <th>Max w</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(report.summary.by_stabilizer)
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([stb, v]: any) => (
                  <tr key={stb}>
                    <td>{stb}</td>
                    <td>{v.data_hook}</td>
                    <td>{v.logical_risk}</td>
                    <td>{v.weight_max}</td>
                  </tr>
                ))}
            </tbody>
          </table>
          <p style={{ fontSize: 11.5, color: "var(--text-dim)", marginTop: 8 }}>
            {report.note}
          </p>
        </>
      )}
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
