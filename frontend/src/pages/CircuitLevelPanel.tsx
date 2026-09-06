import { useState } from "react";
import { post } from "../lib/api";

/** Circuit-level surface-code decoding workflow: explicit ancilla stabilizer
 * circuits with gate/readout/reset/preparation noise, decoded by the
 * repeated-round MWPM. Rendering is strictly backend-derived. */
export default function CircuitLevelPanel() {
  const [d, setD] = useState(3);
  const [rounds, setRounds] = useState(4);
  const [pGate, setPGate] = useState(0.005);
  const [pReadout, setPReadout] = useState(0.005);
  const [pReset, setPReset] = useState(0.003);
  const [pPrep, setPPrep] = useState(0.003);
  const [seed, setSeed] = useState(1);
  const [mcTrials, setMcTrials] = useState(2000);
  const [scheduleMode, setScheduleMode] = useState<"naive" | "optimized">("naive");
  const [extractionModel, setExtractionModel] = useState<
    "baseline_h_cnot_h" | "shor_cat_state">("baseline_h_cnot_h");
  const [decoded, setDecoded] = useState<any>(null);
  const [sim, setSim] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const decode = async () => {
    setBusy(true); setError(null);
    try {
      setDecoded(await post("/api/qec/rotated-surface-code/circuit-level/decode", {
        d, rounds, p_gate: pGate, p_readout: pReadout, p_reset: pReset,
        p_prep: pPrep, seed, extraction_model: extractionModel,
      }));
    } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };
  const runMC = async () => {
    setBusy(true); setError(null);
    try {
      setSim(await post("/api/qec/rotated-surface-code/circuit-level/simulate", {
        d, rounds, p_gate: pGate, p_readout: pReadout, p_reset: pReset,
        p_prep: pPrep, seed, trials: mcTrials, schedule_mode: scheduleMode,
        extraction_model: extractionModel,
      }));
    } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };

  const noise = (label: string, v: number, set: (n: number) => void) => (
    <label className="field">{label}
      <input type="number" min={0} max={1} step={0.001} value={v}
             onChange={(e) => set(Math.max(0, Math.min(1, +e.target.value || 0)))}
             style={{ width: 84 }} />
    </label>
  );

  return (
    <div className="panel">
      <h3>Circuit-level surface code — fault-tolerant stabilizer circuits</h3>
      <p style={{ fontSize: 12.5, color: "var(--text-dim)", marginTop: 0 }}>
        Explicit ancilla stabilizer-measurement circuits (reset → prepare → CNOT
        schedule → measure) with gate, readout, reset, and preparation noise.
        Hook errors — a single ancilla fault propagating to multiple data qubits
        — emerge from the schedule and are recorded. Ideal final-round readout;
        single-qubit gates ideal. No hardware claims.{" "}
        <b>Measured (AD-021):</b> Shor cat-state confines hooks to weight ≤ 2
        (baseline: up to 4) but its ~2× gate exposure makes p_L <i>worse</i>{" "}
        under this decoder and noise model — the comparison is real, not a
        recommendation.
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
        {noise("p_gate", pGate, setPGate)}
        {noise("p_readout", pReadout, setPReadout)}
        {noise("p_reset", pReset, setPReset)}
        {noise("p_prep", pPrep, setPPrep)}
        <label className="field">Seed
          <input type="number" value={seed} onChange={(e) => setSeed(+e.target.value || 0)}
                 style={{ width: 80 }} />
        </label>
        <label className="field">Schedule
          <select value={scheduleMode} onChange={(e) => setScheduleMode(e.target.value as any)}>
            <option value="naive">naive (production)</option>
            <option value="optimized">optimized (catalogue)</option>
          </select>
        </label>
        <label className="field">Extraction
          <select value={extractionModel}
                  onChange={(e) => { setExtractionModel(e.target.value as any); setDecoded(null); setSim(null); }}>
            <option value="baseline_h_cnot_h">baseline (H-CNOT-H)</option>
            <option value="shor_cat_state">Shor cat-state</option>
          </select>
        </label>
        <button className="btn" disabled={busy} onClick={decode}>
          {busy ? "Simulating…" : "Decode circuit-level"}
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
          <div className="metric-cards" style={{ marginTop: 8 }}>
            <Metric label="Hook errors" value={String((decoded.hook_events ?? []).length)} />
            <Metric label="Data X errors" value={String((decoded.data_error?.X ?? []).length)} />
            <Metric label="Data Z errors" value={String((decoded.data_error?.Z ?? []).length)} />
            <Metric label="Rounds" value={String(decoded.rounds)} />
          </div>
          <table className="data-table" style={{ marginTop: 8 }}>
            <thead><tr><th>Layer</th><th>Type</th><th>Pauli</th><th>Weight</th></tr></thead>
            <tbody>
              {(decoded.matching ?? []).map((m: any, i: number) => (
                <tr key={i}>
                  <td>{`t${m.a.layer}${m.b ? ` ↔ t${m.b.layer}` : ""}`}</td>
                  <td>{m.kind}</td>
                  <td>{m.pauli || "—"}</td>
                  <td>{m.weight}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {(decoded.hook_events ?? []).length > 0 && (
            <details style={{ marginTop: 8 }}>
              <summary className="kv" style={{ cursor: "pointer" }}>
                Hook-error events ({decoded.hook_events.length})
              </summary>
              <pre className="event-log">{JSON.stringify(decoded.hook_events, null, 2).slice(0, 1500)}</pre>
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
          Run Monte Carlo (circuit-level)
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

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-card">
      <div className="value">{value}</div>
      <div className="label">{label}</div>
    </div>
  );
}