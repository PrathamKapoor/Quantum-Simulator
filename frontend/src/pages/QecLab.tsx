import { useState } from "react";
import { get, post } from "../lib/api";
import { LineChart } from "../lib/charts";

export default function QecLab() {
  const [codes, setCodes] = useState<any[]>([]);
  const [code, setCode] = useState("bit-flip-3");
  const [rates, setRates] = useState("1,5,10,50");
  const [trials, setTrials] = useState(3000);
  const [sweep, setSweep] = useState<any>(null);
  const [surface, setSurface] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (codes.length === 0) {
    get("/api/qec/codes").then(setCodes).catch(() => {});
  }

  const runSweep = async () => {
    setBusy(true); setError(null);
    try {
      const rates_list = rates.split(",").map((v) => parseFloat(v.trim()) / 1000);
      const r = await post("/api/qec/sweep", {
        code, physical_error_rates: rates_list, trials,
      });
      setSweep(r);
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  };

  const runSurface = async (d: number) => {
    setBusy(true); setError(null);
    try {
      const r = await post("/api/qec/surface-code", { d, physical_error_rate: 0.02, trials: 2000 });
      setSurface(r);
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  };

  return (
    <div>
      <h1 className="page-title">Quantum Error Correction</h1>
      <p className="page-sub">
        Encode → noise → syndrome extraction → decode → recover, benchmarked with
        Monte Carlo over physical error rates. Wilson score confidence intervals;
        trends are reported statistically rather than asserted exactly.
      </p>

      {error && <div className="error-box">{error}</div>}

      <div className="panel">
        <h3>Logical vs physical error rate</h3>
        <div className="row">
          <label className="field">Code
            <select value={code} onChange={(e) => setCode(e.target.value)}>
              {codes.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name} (n={c.n}, d={c.distance}, corrects {c.corrects_paulis.join("/")})
                </option>
              ))}
            </select>
          </label>
          <label className="field">Physical error rates (‰)
            <input type="text" value={rates} onChange={(e) => setRates(e.target.value)} />
          </label>
          <label className="field">Trials / point
            <input type="number" min={100} max={1000000} value={trials}
                   onChange={(e) => setTrials(+e.target.value || 500)} style={{ width: 100 }} />
          </label>
          <button className="btn" disabled={busy} onClick={runSweep}>
            {busy ? "Running…" : "Run sweep"}
          </button>
        </div>

        {sweep && (
          <>
            <LineChart
              title={`Logical error rate — ${sweep.code}`}
              xLabel="physical error rate p"
              yLabel="logical error rate"
              series={[{
                name: "measured",
                points: sweep.table.map((t: any) => ({ x: t.physical_error_rate, y: t.logical_error_rate })),
              }]}
            />
            <table className="data-table">
              <thead>
                <tr><th>p</th><th>logical rate</th><th>95% CI</th><th>failures</th><th>trials</th></tr>
              </thead>
              <tbody>
                {sweep.table.map((t: any, i: number) => (
                  <tr key={i}>
                    <td>{t.physical_error_rate.toFixed(4)}</td>
                    <td>{t.logical_error_rate.toFixed(4)}</td>
                    <td>[{t.ci95_low.toFixed(4)}, {t.ci95_high.toFixed(4)}]</td>
                    <td>{t.logical_failures}</td>
                    <td>{t.trials}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>

      <div className="panel">
        <h3>Toric surface code (educational simulator)</h3>
        <p style={{ fontSize: 12.5, color: "var(--text-dim)", marginTop: 0 }}>
          Periodic torus layout, weight-1 lookup decoder; multi-qubit patterns without a
          unique weight-1-consistent syndrome count as failures. Capabilities are not overstated.
        </p>
        <div className="row">
          {[2, 3, 4].map((d) => (
            <button key={d} className="btn secondary small" disabled={busy}
                    onClick={() => runSurface(d)}>
              Run d={d}
            </button>
          ))}
        </div>
        {surface && (
          <>
            <p className="kv" style={{ marginTop: 8 }}>
              d={surface.d}: logical error rate <b>{(surface.logical_error_rate * 100).toFixed(2)}%</b>{" "}
              at p={surface.physical_error_rate} · CI [{surface.ci95[0].toFixed(4)}, {surface.ci95[1].toFixed(4)}]
            </p>
            <svg viewBox="0 0 220 220" width={240} role="img" aria-label="toric layout">
              {surface.layout.edges.map((e: any, i: number) => (
                <line key={i}
                      x1={10 + e.from[0] * 190 + (e.kind === "h" ? 8 : 8)}
                      y1={10 + e.from[1] * 190 + (e.kind === "h" ? 8 : -8)}
                      x2={10 + e.to[0] * 190 + (e.kind === "h" ? -8 : 8)}
                      y2={10 + e.to[1] * 190 + (e.kind === "h" ? -8 : 8)}
                      stroke={e.kind === "h" ? "#4aa8ff" : "#3fb96f"} strokeWidth={2.5} opacity={0.75}>
                  <title>{`edge ${e.index}`}</title>
                </line>
              ))}
              {Array.from({ length: surface.layout.d }, (_, i) =>
                Array.from({ length: surface.layout.d }, (_, j) => (
                  <circle key={`${i}-${j}`} cx={18 + i * (190 / Math.max(surface.layout.d - 1, 1))}
                          cy={18 + j * (190 / Math.max(surface.layout.d - 1, 1))} r={3} fill="var(--text-dim)" />
                ))
              )}
            </svg>
            <p className="note-list">Blue: horizontal edges · green: vertical edges · data qubits on edges.</p>
          </>
        )}
      </div>
    </div>
  );
}
