import { useState } from "react";
import { get, post } from "../lib/api";
import { LineChart } from "../lib/charts";
import RepeatedRoundPanel from "./RepeatedRoundPanel";

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

      <RotatedSurfaceCodePanel />

      <RepeatedRoundPanel />

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

/** Rotated planar surface code + exact MWPM decoder workflow. Every visual
 * state is rendered from the backend decode/simulate documents. */

const X_COLOR = "#4aa8ff";
const Z_COLOR = "#3fb96f";
const ERR_X = "#ff6b6b";
const ERR_Z = "#e8b13f";

function RotatedSurfaceCodePanel() {
  const [d, setD] = useState(3);
  const [model, setModel] = useState("depolarizing");
  const [p, setP] = useState(0.05);
  const [seed, setSeed] = useState(11);
  const [mcTrials, setMcTrials] = useState(3000);
  const [decoded, setDecoded] = useState<any>(null);
  const [sim, setSim] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const decode = async () => {
    setBusy(true); setError(null);
    try {
      setDecoded(await post("/api/qec/rotated-surface-code/decode", {
        d, error_model: model, physical_error_rate: p, seed,
      }));
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  };

  const runMonteCarlo = async () => {
    setBusy(true); setError(null);
    try {
      setSim(await post("/api/qec/rotated-surface-code/simulate", {
        d, error_model: model, physical_error_rate: p, seed, trials: mcTrials,
      }));
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  };

  const layout = decoded?.layout;
  const S = 240, M = 14;
  const px = (v: number) => M + v * (S - 2 * M);
  const dataPos = new Map<number, { x: number; y: number }>();
  layout?.data_qubits.forEach((q: any) => dataPos.set(q.index, { x: px(q.x), y: px(q.y) }));
  const checkPos = new Map<number, { x: number; y: number }>();
  layout?.checks.forEach((c: any) => checkPos.set(c.index, { x: px(c.x), y: px(c.y) }));
  const defectIdx = new Set((decoded?.events ?? []).map((e: any) => e.check_index));
  const errX = new Set(decoded?.error_support?.X ?? []);
  const errZ = new Set(decoded?.error_support?.Z ?? []);
  const chainQ = new Map<string, number>();
  (decoded?.matching ?? []).forEach((m: any, i: number) =>
    m.chain.forEach((q: number) => chainQ.set(`${m.pauli}:${q}`, i)));

  return (
    <div className="panel">
      <h3>Rotated planar surface code — MWPM decoder (code capacity)</h3>
      <p style={{ fontSize: 12.5, color: "var(--text-dim)", marginTop: 0 }}>
        Exact minimum-weight perfect matching over the rotated planar lattice with perfect
        syndrome measurement (single round, code-capacity model). Logical X runs top-bottom,
        logical Z runs left-right; Z chains exit left/right, X chains exit top/bottom.
        Simulation study — no hardware or threshold claims.
      </p>
      {error && <div className="error-box">{error}</div>}

      <div className="row" style={{ flexWrap: "wrap", gap: 10 }}>
        <label className="field">Distance
          <select value={d} onChange={(e) => { setD(+e.target.value); setDecoded(null); setSim(null); }}>
            {[3, 5, 7].map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
        </label>
        <label className="field">Error model
          <select value={model} onChange={(e) => setModel(e.target.value)}>
            <option value="depolarizing">depolarizing (p/3 each of X, Y, Z)</option>
            <option value="x_only">X-only</option>
            <option value="z_only">Z-only</option>
          </select>
        </label>
        <label className="field">Physical p
          <input type="number" min={0} max={1} step={0.01} value={p}
                 onChange={(e) => setP(Math.max(0, Math.min(1, +e.target.value || 0)))}
                 style={{ width: 90 }} />
        </label>
        <label className="field">Seed
          <input type="number" value={seed} onChange={(e) => setSeed(+e.target.value || 0)}
                 style={{ width: 80 }} />
        </label>
        <button className="btn" disabled={busy} onClick={decode}>
          {busy ? "Decoding…" : "Generate error & decode"}
        </button>
      </div>

      {decoded && (
        <div className="grid2" style={{ marginTop: 12 }}>
          <div>
            <svg viewBox={`0 0 ${S} ${S}`} width={S} role="img" aria-label="rotated surface code lattice">
              {/* matching edges */}
              {decoded.matching.map((m: any, i: number) => {
                const a = checkPos.get(m.a.check_index);
                const b = m.kind === "pair" && m.b
                  ? checkPos.get(m.b.check_index)
                  : dataPos.get(m.exit_qubit);
                if (!a || !b) return null;
                return (
                  <line key={`m${i}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                        stroke={m.pauli === "Z" ? Z_COLOR : X_COLOR}
                        strokeWidth={1.6} strokeDasharray="4 3" opacity={0.9}>
                    <title>{`${m.kind} match (${m.pauli}-chain), weight ${m.weight}`}</title>
                  </line>
                );
              })}
              {/* checks */}
              {layout.checks.map((c: any) => {
                const pos = checkPos.get(c.index);
                if (!pos) return null;
                const isDefect = defectIdx.has(c.index);
                const col = c.kind === "X" ? X_COLOR : Z_COLOR;
                return (
                  <rect key={`c${c.index}`} x={pos.x - 5} y={pos.y - 5} width={10} height={10}
                        fill={col} opacity={0.55}
                        stroke={isDefect ? "#ffffff" : "none"} strokeWidth={isDefect ? 2 : 0}>
                    <title>{`${c.kind}-check ${c.index} (weight ${c.support.length})${isDefect ? " — DEFECT" : ""}`}</title>
                  </rect>
                );
              })}
              {/* correction chains */}
              {layout.data_qubits.map((q: any) => {
                const zk = chainQ.get(`Z:${q.index}`);
                const xk = chainQ.get(`X:${q.index}`);
                if (zk === undefined && xk === undefined) return null;
                const pos = dataPos.get(q.index)!;
                return (
                  <circle key={`k${q.index}`} cx={pos.x} cy={pos.y} r={7.5} fill="none"
                          stroke={zk !== undefined ? Z_COLOR : X_COLOR} strokeWidth={1.5}
                          strokeDasharray={zk !== undefined && xk !== undefined ? "2 2" : undefined} />
                );
              })}
              {/* data qubits */}
              {layout.data_qubits.map((q: any) => {
                const pos = dataPos.get(q.index)!;
                const hasX = errX.has(q.index), hasZ = errZ.has(q.index);
                return (
                  <circle key={`q${q.index}`} cx={pos.x} cy={pos.y} r={3.2}
                          fill={hasX && hasZ ? ERR_X : hasX ? ERR_X : hasZ ? ERR_Z : "var(--text-dim)"}
                          stroke={hasX || hasZ ? "#ffffff" : "none"} strokeWidth={0.8}>
                    <title>{`data qubit ${q.index}${hasX ? " · X" : ""}${hasZ ? " · Z" : ""}`}</title>
                  </circle>
                );
              })}
            </svg>
            <p style={{ fontSize: 11.5, color: "var(--text-dim)" }}>
              Squares: X (blue) / Z (green) checks, white ring = syndrome defect · dots: data qubits
              (red = X or Y error, amber = Z error) · dashed: MWPM correction chains ·
              ringed dots: correction Paulis.
            </p>
          </div>
          <div>
            <p className="kv">
              Outcome:{" "}
              <span className={"badge " + (decoded.outcome === "CORRECTED" ? "ok" : "err")}>
                {decoded.outcome}
              </span>
            </p>
            <p className="kv">Matching weight: <b>{decoded.matching_weight}</b> ·
              detection events: <b>{decoded.events.length}</b></p>
            {decoded.matching.length > 0 && (
              <table className="data-table">
                <thead><tr><th>Match</th><th>Pauli</th><th>Weight</th><th>Chain</th></tr></thead>
                <tbody>
                  {decoded.matching.map((m: any, i: number) => (
                    <tr key={i}>
                      <td>{m.kind === "pair"
                        ? `${m.a.check_kind}${m.a.check_index} ↔ ${m.b.check_kind}${m.b.check_index}`
                        : `${m.a.check_kind}${m.a.check_index} → boundary (q${m.exit_qubit})`}</td>
                      <td>{m.pauli}</td>
                      <td>{m.weight}</td>
                      <td>{m.chain.length} qubit(s)</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {decoded.decoder_error && <div className="error-box">{decoded.decoder_error}</div>}
          </div>
        </div>
      )}

      <div className="row" style={{ marginTop: 12, alignItems: "flex-end" }}>
        <label className="field">MC trials
          <input type="number" min={100} max={1000000} value={mcTrials}
                 onChange={(e) => setMcTrials(+e.target.value || 1000)} style={{ width: 100 }} />
        </label>
        <button className="btn secondary" disabled={busy} onClick={runMonteCarlo}>
          Run Monte Carlo at this (d, p)
        </button>
      </div>
      {sim && (
        <p className="kv" style={{ marginTop: 8 }}>
          d={sim.d}, p={sim.physical_error_rate}: logical error rate p_L ={" "}
          <b>{(sim.logical_error_rate * 100).toFixed(2)}%</b> · Wilson 95% CI [
          {sim.ci95[0].toFixed(4)}, {sim.ci95[1].toFixed(4)}] · {sim.logical_failures}/
          {sim.trials} failures
        </p>
      )}
      {sim && (
        <p style={{ fontSize: 11.5, color: "var(--text-dim)" }}>{sim.note}</p>
      )}
    </div>
  );
}
