import { useState } from "react";
import { post } from "../lib/api";

/** Circuit-aware hybrid decoder workflow (milestone 13, AD-019).
 * Renders decoder-comparison MC results from the backend
 * /circuit-aware/simulate endpoint. Every value is backend-derived. */
export default function CircuitAwarePanel() {
  const [d, setD] = useState(3);
  const [rounds, setRounds] = useState(4);
  const [pGate, setPGate] = useState(0.005);
  const [pReadout, setPReadout] = useState(0.005);
  const [pReset, setPReset] = useState(0.003);
  const [pPrep, setPPrep] = useState(0.003);
  const [seed, setSeed] = useState(11);
  const [trials, setTrials] = useState(500);
  const [mc, setMc] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runMC = async () => {
    setBusy(true); setError(null);
    try {
      setMc(await post(
        "/api/qec/rotated-surface-code/circuit-aware/simulate",
        { d, rounds, p_gate: pGate, p_readout: pReadout,
          p_reset: pReset, p_prep: pPrep, seed, trials }));
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
      <h3>Circuit-aware hybrid decoder (AD-019)</h3>
      <p style={{ fontSize: 12.5, color: "var(--text-dim)", marginTop: 0 }}>
        The v1 hybrid decoder combines the circuit-derived pair-edge
        graph with multi-event post-processing (Approach 3, directive §9).
        Shares the temporal chain reconstruction with the
        phenomenological MWPM (the graph is the extension, the matcher
        is reused — directive §23). Wilson 95% CI reported honestly.
      </p>
      <div className="row" style={{ flexWrap: "wrap", gap: 10 }}>
        <label className="field">Distance
          <select value={d} onChange={(e) => { setD(+e.target.value); setMc(null); }}>
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
        <label className="field">MC trials
          <input type="number" min={100} max={50000} value={trials}
                 onChange={(e) => setTrials(+e.target.value || 500)}
                 style={{ width: 100 }} />
        </label>
        <button className="btn" disabled={busy} onClick={runMC}>
          {busy ? "Running…" : "Run hybrid decoder MC"}
        </button>
      </div>

      {error && <div className="error-box">{error}</div>}

      {mc && (
        <>
          <p className="kv" style={{ marginTop: 8 }}>
            d={mc.d}, rounds={mc.rounds}: logical error rate p_L ={" "}
            <b>{(mc.logical_error_rate * 100).toFixed(2)}%</b> · Wilson 95% CI [
            {mc.ci95[0].toFixed(4)}, {mc.ci95[1].toFixed(4)}] ·{" "}
            {mc.logical_failures}/{mc.trials} failures
          </p>
          <p className="kv">
            Decoder: <b>{mc.decoder}</b> ·{" "}
            Multi-event mechanisms considered:{" "}
            <b>{mc.multi_event_mechanisms_considered}</b> ·{" "}
            Multi-event mass total:{" "}
            <b>{mc.multi_event_mass_total.toFixed(4)}</b>
          </p>
          <p style={{ fontSize: 11.5, color: "var(--text-dim)" }}>{mc.note}</p>
        </>
      )}
    </div>
  );
}
