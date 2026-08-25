import { useState } from "react";
import { post } from "../lib/api";

const PRESETS: Record<string, { label: string; ops: any[]; n: number }> = {
  bell: {
    label: "Bell pair |Φ+⟩",
    n: 2,
    ops: [
      { kind: "gate", gate: "H", params: [], qubits: [0], clbits: [], condition: null },
      { kind: "gate", gate: "CX", params: [], qubits: [0, 1], clbits: [], condition: null },
    ],
  },
  ghz3: {
    label: "GHZ-3",
    n: 3,
    ops: [
      { kind: "gate", gate: "H", params: [], qubits: [0], clbits: [], condition: null },
      { kind: "gate", gate: "CX", params: [], qubits: [0, 1], clbits: [], condition: null },
      { kind: "gate", gate: "CX", params: [], qubits: [1, 2], clbits: [], condition: null },
    ],
  },
  w3: {
    label: "W-3",
    n: 3,
    ops: [
      { kind: "gate", gate: "RY", params: [1.91063324], qubits: [0], clbits: [], condition: null },
      { kind: "gate", gate: "CX", params: [], qubits: [0, 1], clbits: [], condition: null },
      { kind: "gate", gate: "RY", params: [1.5707963], qubits: [1], clbits: [], condition: null },
      { kind: "gate", gate: "CX", params: [], qubits: [1, 2], clbits: [], condition: null },
      { kind: "gate", gate: "CX", params: [], qubits: [0, 1], clbits: [], condition: null },
      { kind: "gate", gate: "X", params: [], qubits: [0], clbits: [], condition: null },
    ],
  },
  product: {
    label: "Product |+⟩|0⟩",
    n: 2,
    ops: [{ kind: "gate", gate: "H", params: [], qubits: [0], clbits: [], condition: null }],
  },
};

export default function InfoTheoryLab() {
  const [preset, setPreset] = useState<keyof typeof PRESETS | string>("bell");
  const [report, setReport] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const analyze = async () => {
    setBusy(true); setError(null); setReport(null);
    const p = PRESETS[preset];
    try {
      const r = await post("/api/quantum-info/state-report", {
        circuit: {
          schema: "quantumlab.circuit", version: 1,
          name: preset as string, num_qubits: p.n, num_clbits: 0,
          metadata: {}, operations: p.ops,
        },
      });
      setReport(r);
    } catch (e: any) {
      setError(e.message);
    } finally { setBusy(false); }
  };

  return (
    <div>
      <h1 className="page-title">Quantum Information Lab</h1>
      <p className="page-sub">
        Exact information measures over prepared pure states (eigendecomposition).
        Entropies in bits; conditional entropy may be negative for entangled
        states — that is physically meaningful.
      </p>

      <div className="panel">
        <h3>State preparation</h3>
        <div className="row">
          <label className="field">Preset state
            <select value={preset} onChange={(e) => setPreset(e.target.value)}>
              {Object.entries(PRESETS).map(([k, v]) => (
                <option key={k} value={k}>{v.label}</option>
              ))}
            </select>
          </label>
          <button className="btn" disabled={busy} onClick={analyze}>
            {busy ? "Computing…" : "Analyze"}
          </button>
        </div>
      </div>

      {error && <div className="error-box">{error}</div>}

      {report && (
        <>
          <div className="metric-cards">
            <Metric label="Purity" value={report.report.purity.toFixed(6)} />
            <Metric label="S(ρ) bits" value={report.report.von_neumann_entropy_bits.toFixed(4)} />
            <Metric label="S₂ bits" value={report.report.renyi_entropy_bits_alpha2.toFixed(4)} />
            <Metric label="H_min bits" value={report.report.min_entropy_bits.toFixed(4)} />
            <Metric label="Linear entropy" value={report.report.linear_entropy.toFixed(4)} />
          </div>

          <div className="grid2">
            <div className="panel">
              <h3>Bipartite measures</h3>
              <table className="data-table">
                <tbody>
                  <tr><td>Mutual information I(A:B)</td><td>{fmt(report.report.mutual_information_bits)} bits</td></tr>
                  <tr><td>Conditional entropy S(A|B)</td><td>{fmt(report.report.conditional_entropy_bits)} bits</td></tr>
                  {report.report.concurrence !== undefined && (
                    <tr><td>Concurrence (2-qubit)</td><td>{fmt(report.report.concurrence)}</td></tr>
                  )}
                  {report.report.negativity !== undefined && (
                    <>
                      <tr><td>Negativity</td><td>{fmt(report.report.negativity)}</td></tr>
                      <tr><td>Log-negativity</td><td>{fmt(report.report.logarithmic_negativity_bits)} bits</td></tr>
                    </>
                  )}
                </tbody>
              </table>
              {report.report.correlation_matrix && (
                <>
                  <h3 style={{ marginTop: 12 }}>Correlation matrix ⟨σᵢ⊗σⱼ⟩</h3>
                  <table className="data-table">
                    <thead><tr><th></th><th>X</th><th>Y</th><th>Z</th></tr></thead>
                    <tbody>
                      {["X", "Y", "Z"].map((r, i) => (
                        <tr key={r}>
                          <td>{r}</td>
                          {report.report.correlation_matrix[i].map((v: number, j: number) => (
                            <td key={j}>{v.toFixed(4)}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}
            </div>

            <div className="panel">
              <h3>Separability diagnostics</h3>
              <p className="kv">Verdict: <span className={"badge " + (report.report.separability.verdict === "separable" ? "ok" : report.report.separability.verdict.includes("inconclusive") ? "warn" : "err")}>
                {report.report.separability.verdict}
              </span></p>
              <p style={{ fontSize: 12, color: "var(--text-dim)" }}>
                {report.report.separability.basis}
              </p>
              <h3 style={{ marginTop: 14 }}>Model labels</h3>
              <ul className="note-list">
                <li>{report.model_labels.computation}</li>
                <li>{report.model_labels.separability_test}</li>
                {(report.notes ?? []).map((n: string, i: number) => <li key={i}>{n}</li>)}
              </ul>
            </div>
          </div>
        </>
      )}

      {!report && !error && (
        <div className="panel">
          <p style={{ color: "var(--text-dim)" }}>
            Select a preset state and press Analyze to compute entropy,
            entanglement, and separability measures.
          </p>
        </div>
      )}
    </div>
  );
}

function fmt(v: any): string {
  return typeof v === "number" ? v.toFixed(6) : String(v);
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-card">
      <div className="value">{value}</div>
      <div className="label">{label}</div>
    </div>
  );
}
