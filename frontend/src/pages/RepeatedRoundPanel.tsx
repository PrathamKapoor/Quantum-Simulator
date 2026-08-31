import { useState } from "react";
import { post } from "../lib/api";

/** Repeated-round (space-time) surface-code decoding workflow. Renders the
 * detection events across time layers and the MWPM matching, strictly from
 * the backend document (§67-§73). */
export default function RepeatedRoundPanel() {
  const [d, setD] = useState(3);
  const [rounds, setRounds] = useState(4);
  const [pData, setPData] = useState(0.03);
  const [pMeas, setPMeas] = useState(0.03);
  const [seed, setSeed] = useState(1);
  const [mcTrials, setMcTrials] = useState(2000);
  const [decoded, setDecoded] = useState<any>(null);
  const [sim, setSim] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const decode = async () => {
    setBusy(true); setError(null);
    try {
      setDecoded(await post("/api/qec/rotated-surface-code/repeated-round/decode", {
        d, rounds, p_data: pData, p_measurement: pMeas, seed,
      }));
    } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };
  const runMC = async () => {
    setBusy(true); setError(null);
    try {
      setSim(await post("/api/qec/rotated-surface-code/repeated-round/simulate", {
        d, rounds, p_data: pData, p_measurement: pMeas, seed, trials: mcTrials,
      }));
    } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };

  const layout = decoded?.layout;
  const S = 110, M = 8, gap = 24;
  const px = (v: number) => M + v * (S - 2 * M);
  const checkPos = new Map<number, { x: number; y: number }>();
  layout?.checks.forEach((c: any) => checkPos.set(c.index, { x: px(c.x), y: px(c.y) }));
  const maxLayer = Math.max(0, ...(decoded?.detection_events ?? []).map((e: any) => e.layer));
  const layers = Array.from({ length: maxLayer + 1 }, (_, i) => i + 1);
  const totalW = (maxLayer + 1) * S + maxLayer * gap;

  const evAt = (layer: number) => (decoded?.detection_events ?? [])
    .filter((e: any) => e.layer === layer);

  return (
    <div className="panel">
      <h3>Repeated-round surface code — space-time MWPM</h3>
      <p style={{ fontSize: 12.5, color: "var(--text-dim)", marginTop: 0 }}>
        Temporal decoding of the rotated planar code: persistent per-slot
        depolarizing data noise (p_data) and per-round measurement flips
        (p_measurement; the final round is ideal). Detection events are
        syndrome differences over time; MWPM matches them into spatial (data)
        and temporal (measurement) edges. Phenomenological model — no
        circuit-level or hardware claims.
      </p>
      <div className="row" style={{ flexWrap: "wrap", gap: 10 }}>
        <label className="field">Distance
          <select value={d} onChange={(e) => { setD(+e.target.value); setDecoded(null); setSim(null); }}>
            {[3, 5, 7].map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
        </label>
        <label className="field">Rounds
          <input type="number" min={1} max={16} value={rounds}
                 onChange={(e) => setRounds(Math.max(1, Math.min(16, +e.target.value || 1)))}
                 style={{ width: 70 }} />
        </label>
        <label className="field">p_data
          <input type="number" min={0} max={1} step={0.01} value={pData}
                 onChange={(e) => setPData(Math.max(0, Math.min(1, +e.target.value || 0)))}
                 style={{ width: 80 }} />
        </label>
        <label className="field">p_measurement
          <input type="number" min={0} max={1} step={0.01} value={pMeas}
                 onChange={(e) => setPMeas(Math.max(0, Math.min(1, +e.target.value || 0)))}
                 style={{ width: 80 }} />
        </label>
        <label className="field">Seed
          <input type="number" value={seed} onChange={(e) => setSeed(+e.target.value || 0)}
                 style={{ width: 80 }} />
        </label>
        <button className="btn" disabled={busy} onClick={decode}>
          {busy ? "Decoding…" : "Decode repeated rounds"}
        </button>
      </div>

      {error && <div className="error-box">{error}</div>}

      {decoded && (
        <>
          <p className="kv" style={{ marginTop: 8 }}>
            Outcome:{" "}
            <span className={"badge " + (decoded.outcome === "CORRECTED" ? "ok" : "err")}>
              {decoded.outcome}
            </span>
            {" "}· matching weight <b>{decoded.matching_weight}</b> · detection
            events <b>{decoded.detection_events.length}</b>
          </p>
          <svg viewBox={`0 0 ${totalW} ${S}`} width="100%"
               style={{ overflowX: "auto", marginTop: 8 }}
               role="img" aria-label="space-time detection lattice">
            {layers.map((layer, li) => {
              const ox = li * (S + gap);
              return (
                <g key={layer}>
                  <text x={ox + S / 2} y={10} fontSize={8} fill="var(--text-dim)"
                        textAnchor="middle">{`t=${layer - 1}`}</text>
                  {(decoded.matching ?? [])
                    .filter((m: any) => m.a.layer === layer && m.b)
                    .map((m: any, mi: number) => {
                      const p1 = checkPos.get(m.a.check_index);
                      const p2 = checkPos.get(m.b?.check_index);
                      if (!p1 || !p2) return null;
                      const x2 = m.b.layer === layer ? ox + p2.x : ox + S + gap + p2.x;
                      return <line key={`e${layer}-${mi}`} x1={ox + p1.x} y1={p1.y}
                                   x2={x2} y2={p2.y} stroke={m.pauli === "" ? "#b58900" : "#888"}
                                   strokeWidth={1.4} strokeDasharray={m.pauli === "" ? "2 2" : undefined}
                                   opacity={0.85} />;
                    })}
                  {evAt(layer).map((ev: any, ei: number) => {
                    const p = checkPos.get(ev.check_index);
                    if (!p) return null;
                    return <circle key={`ev${layer}-${ei}`} cx={ox + p.x} cy={p.y} r={3.5}
                                   fill={ev.check_kind === "X" ? "#4aa8ff" : "#3fb96f"} />;
                  })}
                </g>
              );
            })}
          </svg>
          <table className="data-table" style={{ marginTop: 8 }}>
            <thead><tr><th>Layer</th><th>Type</th><th>Pauli</th><th>Weight</th><th>Checks</th></tr></thead>
            <tbody>
              {(decoded.matching ?? []).map((m: any, i: number) => (
                <tr key={i}>
                  <td>{`t${m.a.layer}${m.b ? ` ↔ t${m.b.layer}` : ""}`}</td>
                  <td>{m.kind}</td>
                  <td>{m.pauli || "—"}</td>
                  <td>{m.weight}</td>
                  <td>{`${m.a.check_kind}${m.a.check_index}${m.b ? `↔${m.b.check_kind}${m.b.check_index}` : ""}`}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {decoded.observed_syndromes && (
            <details style={{ marginTop: 8 }}>
              <summary className="kv" style={{ cursor: "pointer" }}>
                Observed syndrome history ({decoded.observed_syndromes.length} rounds)
              </summary>
              <pre className="event-log">
                {JSON.stringify(decoded.observed_syndromes, null, 2).slice(0, 2000)}
              </pre>
            </details>
          )}
        </>
      )}

      <div className="row" style={{ marginTop: 12, alignItems: "flex-end" }}>
        <label className="field">MC trials
          <input type="number" min={100} max={200000} value={mcTrials}
                 onChange={(e) => setMcTrials(+e.target.value || 1000)} style={{ width: 100 }} />
        </label>
        <button className="btn secondary" disabled={busy} onClick={runMC}>
          Run Monte Carlo (repeated-round)
        </button>
      </div>
      {sim && (
        <p className="kv" style={{ marginTop: 8 }}>
          d={sim.d}, rounds={sim.rounds}: logical error rate p_L ={" "}
          <b>{(sim.logical_error_rate * 100).toFixed(2)}%</b> · Wilson 95% CI [
          {sim.ci95[0].toFixed(4)}, {sim.ci95[1].toFixed(4)}] · {sim.logical_failures}/
          {sim.trials} failures
        </p>
      )}
      {sim && <p style={{ fontSize: 11.5, color: "var(--text-dim)" }}>{sim.note}</p>}
    </div>
  );
}