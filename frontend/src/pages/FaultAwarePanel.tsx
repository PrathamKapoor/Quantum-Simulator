import { useState } from "react";
import { post } from "../lib/api";

/** Fault-aware stabilizer-schedule + circuit-derived decoder-graph
 * workflow (milestone 12). Every value rendered comes from a backend
 * endpoint — no scientific calculation is duplicated in TypeScript. */
export default function FaultAwarePanel() {
  const [d, setD] = useState(3);
  const [exhaustive, setExhaustive] = useState(false);
  const [scheduleReport, setScheduleReport] = useState<any>(null);
  const [busySched, setBusySched] = useState(false);

  const [faultStabType, setFaultStabType] = useState<"X" | "Z">("X");
  const [faultStabIdx, setFaultStabIdx] = useState(0);
  const [faultLocation, setFaultLocation] = useState<
    "ANCILLA_RESET" | "ANCILLA_PREP" | "CNOT_PRE" | "READOUT"
  >("ANCILLA_RESET");
  const [faultPauli, setFaultPauli] = useState<"X" | "Y" | "Z">("X");
  const [faultGateIdx, setFaultGateIdx] = useState(0);
  const [faultRound, setFaultRound] = useState(1);
  const [faultResult, setFaultResult] = useState<any>(null);
  const [busyFault, setBusyFault] = useState(false);

  const [pGate, setPGate] = useState(0.005);
  const [pReadout, setPReadout] = useState(0.005);
  const [pReset, setPReset] = useState(0.003);
  const [pPrep, setPPrep] = useState(0.003);
  const [graphRounds, setGraphRounds] = useState(4);
  const [graph, setGraph] = useState<any>(null);
  const [busyGraph, setBusyGraph] = useState(false);

  const [trials, setTrials] = useState(500);
  const [seed, setSeed] = useState(5);
  const [mc, setMc] = useState<any>(null);
  const [busyMc, setBusyMc] = useState(false);

  const [error, setError] = useState<string | null>(null);

  const analyzeSchedule = async () => {
    setBusySched(true); setError(null);
    try {
      setScheduleReport(await post(
        "/api/qec/rotated-surface-code/schedule/analyze",
        { d, exhaustive }));
    } catch (e: any) { setError(e.message); } finally { setBusySched(false); }
  };
  const analyzeFault = async () => {
    setBusyFault(true); setError(null);
    try {
      setFaultResult(await post(
        "/api/qec/rotated-surface-code/fault/analyze",
        {
          d, stabilizer_type: faultStabType, stabilizer_index: faultStabIdx,
          fault_location: faultLocation, pauli_fault: faultPauli,
          gate_index: faultGateIdx, round: faultRound,
        }));
    } catch (e: any) { setError(e.message); } finally { setBusyFault(false); }
  };
  const buildGraph = async () => {
    setBusyGraph(true); setError(null);
    try {
      setGraph(await post(
        "/api/qec/rotated-surface-code/circuit-derived/graph",
        { d, rounds: graphRounds, p_gate: pGate, p_readout: pReadout,
          p_reset: pReset, p_prep: pPrep }));
    } catch (e: any) { setError(e.message); } finally { setBusyGraph(false); }
  };
  const runMC = async () => {
    setBusyMc(true); setError(null);
    try {
      setMc(await post(
        "/api/qec/rotated-surface-code/circuit-derived/simulate",
        { d, rounds: graphRounds, p_gate: pGate, p_readout: pReadout,
          p_reset: pReset, p_prep: pPrep, trials, seed }));
    } catch (e: any) { setError(e.message); } finally { setBusyMc(false); }
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
      <h3>Fault-aware scheduling &amp; circuit-derived decoder graph</h3>
      <p style={{ fontSize: 12.5, color: "var(--text-dim)", marginTop: 0 }}>
        Reproducible, computationally derived single-fault catalogue and
        schedule optimizer; circuit-derived detector-event graph with
        honest multi-event-mechanism coverage. Decoder semantics
        preserved: the phenomenological MWPM (AD-016/AD-017) decodes the
        circuit-level noise history; the graph is structural metadata.
        No threshold or hardware claims.
      </p>
      <div className="row" style={{ flexWrap: "wrap", gap: 10 }}>
        <label className="field">Distance
          <select value={d} onChange={(e) => { setD(+e.target.value); setScheduleReport(null); setFaultResult(null); setGraph(null); setMc(null); }}>
            {[3, 5, 7].map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
        </label>
        <label className="field">Rounds (graph + MC)
          <input type="number" min={1} max={16} value={graphRounds}
                 onChange={(e) => setGraphRounds(Math.max(1, Math.min(16, +e.target.value || 1)))}
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
      </div>

      {error && <div className="error-box">{error}</div>}

      {/* --- Schedule comparison --- */}
      <details open style={{ marginTop: 8 }}>
        <summary className="kv" style={{ cursor: "pointer" }}>
          Schedule comparison (naive vs optimized, deterministic)
        </summary>
        <div className="row" style={{ marginTop: 6, alignItems: "flex-end" }}>
          <label className="field">
            <input type="checkbox" checked={exhaustive}
                   onChange={(e) => setExhaustive(e.target.checked)} />
            Exhaustive (24 perms at d=3; 120 at d=5 weight-5)
          </label>
          <button className="btn" disabled={busySched} onClick={analyzeSchedule}>
            {busySched ? "Analyzing…" : "Run schedule analysis"}
          </button>
        </div>
        {scheduleReport && (
          <>
            <p className="kv" style={{ marginTop: 8 }}>
              Changed stabilizers:{" "}
              <b>{scheduleReport.stabilizers_with_changed_schedule}</b>
              {" / "}{scheduleReport.per_stabilizer.length} ·{" "}
              Naive total hooks: <b>{scheduleReport.naive_total_hooks}</b>{" "}
              · Optimized total hooks:{" "}
              <b>{scheduleReport.optimized_total_hooks}</b>{" "}
              · Naive logical-risk hooks:{" "}
              <b>{scheduleReport.naive_total_logical_risk_hooks}</b>{" "}
              · Optimized logical-risk hooks:{" "}
              <b>{scheduleReport.optimized_total_logical_risk_hooks}</b>
            </p>
            <table className="data-table" style={{ marginTop: 4 }}>
              <thead>
                <tr>
                  <th>Stabilizer</th><th>Naive order</th>
                  <th>n_h</th><th>max_w</th><th>LR</th>
                  <th>Optimized order</th>
                  <th>n_h</th><th>max_w</th><th>LR</th>
                </tr>
              </thead>
              <tbody>
                {scheduleReport.per_stabilizer.map((e: any, i: number) => (
                  <tr key={i}>
                    <td>{e.stabilizer}</td>
                    <td><code>{e.naive.candidate.order.join(",")}</code></td>
                    <td>{e.naive.n_hooks}</td>
                    <td>{e.naive.max_hook_weight}</td>
                    <td>{e.naive.n_logical_risk_hooks}</td>
                    <td><code>{e.optimized.candidate.order.join(",")}</code></td>
                    <td>{e.optimized.n_hooks}</td>
                    <td>{e.optimized.max_hook_weight}</td>
                    <td>{e.optimized.n_logical_risk_hooks}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p style={{ fontSize: 11.5, color: "var(--text-dim)" }}>
              {scheduleReport.note}
            </p>
          </>
        )}
      </details>

      {/* --- Single fault inspection --- */}
      <details style={{ marginTop: 8 }}>
        <summary className="kv" style={{ cursor: "pointer" }}>
          Single-fault inspection (catalogue mechanism)
        </summary>
        <div className="row" style={{ marginTop: 6, flexWrap: "wrap", gap: 8 }}>
          <label className="field">Stab. type
            <select value={faultStabType} onChange={(e) => setFaultStabType(e.target.value as any)}>
              <option>X</option><option>Z</option>
            </select>
          </label>
          <label className="field">Stab. idx
            <input type="number" min={0} max={20} value={faultStabIdx}
                   onChange={(e) => setFaultStabIdx(Math.max(0, Math.min(20, +e.target.value || 0)))}
                   style={{ width: 70 }} />
          </label>
          <label className="field">Fault location
            <select value={faultLocation} onChange={(e) => setFaultLocation(e.target.value as any)}>
              <option value="ANCILLA_RESET">ANCILLA_RESET</option>
              <option value="ANCILLA_PREP">ANCILLA_PREP</option>
              <option value="CNOT_PRE">CNOT_PRE</option>
              <option value="READOUT">READOUT</option>
            </select>
          </label>
          <label className="field">Pauli
            <select value={faultPauli} onChange={(e) => setFaultPauli(e.target.value as any)}>
              <option>X</option><option>Y</option><option>Z</option>
            </select>
          </label>
          <label className="field">Gate idx
            <input type="number" min={0} value={faultGateIdx}
                   onChange={(e) => setFaultGateIdx(Math.max(0, +e.target.value || 0))}
                   style={{ width: 70 }} />
          </label>
          <label className="field">Round
            <input type="number" min={1} max={16} value={faultRound}
                   onChange={(e) => setFaultRound(Math.max(1, Math.min(16, +e.target.value || 1)))}
                   style={{ width: 70 }} />
          </label>
          <button className="btn" disabled={busyFault} onClick={analyzeFault}>
            {busyFault ? "Looking up…" : "Inspect mechanism"}
          </button>
        </div>
        {faultResult && (
          <pre className="event-log" style={{ marginTop: 6 }}>
            {JSON.stringify(faultResult.mechanism, null, 2).slice(0, 1800)}
          </pre>
        )}
      </details>

      {/* --- Circuit-derived graph --- */}
      <details open style={{ marginTop: 8 }}>
        <summary className="kv" style={{ cursor: "pointer" }}>
          Circuit-derived detector graph (exact pairwise coverage)
        </summary>
        <div className="row" style={{ marginTop: 6, alignItems: "flex-end" }}>
          <button className="btn" disabled={busyGraph} onClick={buildGraph}>
            {busyGraph ? "Building…" : "Build graph"}
          </button>
        </div>
        {graph && (
          <>
            <p className="kv" style={{ marginTop: 6 }}>
              Vertices: <b>{graph.n_vertices}</b> · Edges:{" "}
              <b>{graph.n_edges}</b> · Exit edges: <b>{graph.n_exits}</b>
            </p>
            <div className="metric-cards" style={{ marginTop: 6 }}>
              <Metric label="Exact pairwise coverage"
                value={`${(graph.coverage.coverage_ratio * 100).toFixed(1)}%`} />
              <Metric label="Multi-event excluded"
                value={`${(graph.coverage.excluded_ratio * 100).toFixed(1)}%`} />
              <Metric label="Zero-event mechanisms"
                value={String(graph.coverage.zero_event_mechanisms)} />
              <Metric label="Boundary mechanisms"
                value={String(graph.coverage.boundary_mechanisms)} />
              <Metric label="Edge mechanisms"
                value={String(graph.coverage.edge_mechanisms)} />
              <Metric label="Multi-event mechanisms"
                value={String(graph.coverage.multi_event_mechanisms)} />
            </div>
            <p style={{ fontSize: 11.5, color: "var(--text-dim)", marginTop: 6 }}>
              {graph.note}
            </p>
          </>
        )}
      </details>

      {/* --- MC with circuit-derived coverage --- */}
      <div className="row" style={{ marginTop: 10, alignItems: "flex-end" }}>
        <label className="field">MC trials
          <input type="number" min={100} max={200000} value={trials}
                 onChange={(e) => setTrials(+e.target.value || 1000)}
                 style={{ width: 100 }} />
        </label>
        <button className="btn secondary" disabled={busyMc} onClick={runMC}>
          {busyMc ? "Running…" : "Run MC with graph coverage"}
        </button>
      </div>
      {mc && (
        <>
          <p className="kv" style={{ marginTop: 6 }}>
            d={mc.d}, rounds={mc.rounds}: logical error rate p_L ={" "}
            <b>{(mc.logical_error_rate * 100).toFixed(2)}%</b> · Wilson 95% CI [
            {mc.ci95[0].toFixed(4)}, {mc.ci95[1].toFixed(4)}] ·{" "}
            {mc.logical_failures}/{mc.trials} failures
          </p>
          <p className="kv" style={{ marginTop: 4 }}>
            Graph coverage:{" "}
            <b>{(mc.graph_coverage.coverage_ratio * 100).toFixed(1)}%</b>{" "}
            exact pairwise ·{" "}
            <b>{(mc.graph_coverage.excluded_ratio * 100).toFixed(1)}%</b>{" "}
            multi-event-excluded
          </p>
          <p style={{ fontSize: 11.5, color: "var(--text-dim)" }}>{mc.note}</p>
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
