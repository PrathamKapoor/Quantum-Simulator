import { useState } from "react";
import { post } from "../lib/api";
import { LineChart, BarChart } from "../lib/charts";

export default function Algorithms() {
  const [grover, setGrover] = useState<any>(null);
  const [dj, setDj] = useState<any>(null);
  const [, setBv] = useState<any>(null);
  const [, setSd] = useState<any>(null);
  const [walk, setWalk] = useState<any>(null);
  const [of_, setOf] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const call = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try { await fn(); } catch (e: any) {
      setError(e.message + (e.suggestion ? `\nTry: ${e.suggestion}` : ""));
    } finally { setBusy(false); }
  };

  return (
    <div>
      <h1 className="page-title">Quantum Algorithms</h1>
      <p className="page-sub">
        Standard algorithm suite running on the shared simulation engine.
        All stochastic outputs are seeded and reproducible.
      </p>

      {error && <div className="error-box">{error}</div>}

      <div className="grid2">
        <div className="panel">
          <h3>Grover search</h3>
          <GroverForm onRun={(r: any) => setGrover(r)} busy={busy} setBusy={setBusy} />
          {grover && (
            <>
              <div className="metric-cards" style={{ marginTop: 10 }}>
                <Metric label="Success P" value={grover.success_probability.toFixed(3)} />
                <Metric label="Optimal iters" value={String(grover.optimal_iterations)} />
              </div>
              <LineChart
                title="P(marked) per iteration"
                xLabel="iteration" yLabel="probability"
                series={[{ name: "P(marked)",
                  points: grover.per_iteration_probabilities.map((p: number, i: number) => ({ x: i + 1, y: p })) }]}
              />
              <BarChart entries={Object.entries(grover.counts)} title="Shot distribution" />
            </>
          )}
        </div>

        <div>
          <div className="panel">
            <h3>Deutsch–Jozsa</h3>
            <button className="btn small" disabled={busy}
                    onClick={() => call(async () => {
                      const kind = Math.random() < 0.5 ? "constant" : "balanced";
                      const r: any = await post("/api/algorithms/deutsch-jozsa", { kind });
                      setDj(r);
                    })}>
              Run with random oracle type
            </button>
            {dj && (
              <div className="kv" style={{ marginTop: 8 }}>
                Verdict: <b>{dj.verdict}</b> — expected {dj.expected} —{" "}
                <span className={"badge " + (dj.correct ? "ok" : "err")}>{dj.correct ? "correct" : "wrong"}</span>
                <br />outcome bits: {dj.outcome_bitstring}
              </div>
            )}
          </div>

          <div className="panel">
            <h3>Bernstein–Vazirani</h3>
            <BvForm onRun={setBv} busy={busy} setBusy={setBusy} />
          </div>

          <div className="panel">
            <h3>Superdense coding</h3>
            <SuperdenseForm onRun={setSd} busy={busy} setBusy={setBusy} />
          </div>
        </div>
      </div>

      <div className="grid2">
        <div className="panel">
          <h3>Bounded order finding (Shor core)</h3>
          <OrderFindingForm onRun={setOf} busy={busy} setBusy={setBusy} />
          {of_ && (
            <div className="kv" style={{ marginTop: 8 }}>
              a^{of_.a} mod {of_.N}: true order <b>{of_.true_order}</b>, recovered{" "}
              <b>{of_.recovered_order ?? "—"}</b>{" "}
              <span className={"badge " + (of_.success ? "ok" : "warn")}>{of_.success ? "success" : "missed"}</span>
              <ul className="note-list">
                {of_.measured_phases_top.slice(0, 4).map((p: number, i: number) => (
                  <li key={i}>measured phase ≈ {p.toFixed(5)}</li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div className="panel">
          <h3>Discrete quantum walk vs classical walk</h3>
          <WalkForm onRun={setWalk} busy={busy} setBusy={setBusy} />
          {walk && (
            <LineChart
              title={`Distribution after ${walk.steps} steps`}
              xLabel="position" yLabel="probability"
              series={[
                { name: "quantum", points: walk.quantum_distribution.map((p: number, x: number) => ({ x, y: p })) },
                { name: "classical", points: walk.classical_distribution.map((p: number, x: number) => ({ x, y: p })) },
              ]}
            />
          )}
          {walk && (
            <p className="kv">Quantum σ = {walk.quantum_std.toFixed(3)} · classical σ = {walk.classical_std.toFixed(3)}</p>
          )}
        </div>
      </div>
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

function GroverForm({ onRun, busy, setBusy }: any) {
  const [n, setN] = useState(4);
  const [marked, setMarked] = useState(9);
  return (
    <div>
      <div className="row">
        <label className="field">Qubits
          <input type="number" min={1} max={10} value={n}
                 onChange={(e) => setN(+e.target.value || 1)} />
        </label>
        <label className="field">Marked index
          <input type="number" min={0} max={(1 << n) - 1} value={marked}
                 onChange={(e) => setMarked(+e.target.value || 0)} />
        </label>
        <button className="btn" disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  try {
                    onRun(await post("/api/algorithms/grover", {
                      n_qubits: n, marked_index: Math.min(marked, (1 << n) - 1),
                      shots: 2048,
                    }));
                  } finally { setBusy(false); }
                }}>
          Run
        </button>
      </div>
    </div>
  );
}

function BvForm({ onRun, busy, setBusy }: any) {
  const [secret, setSecret] = useState("11001");
  return (
    <div className="row">
      <label className="field">Secret bitstring
        <input type="text" value={secret} maxLength={12}
               onChange={(e) => setSecret(e.target.value.replace(/[^01]/g, ""))} />
      </label>
      <button className="btn" disabled={busy}
              onClick={async () => {
                setBusy(true);
                try { onRun(await post("/api/algorithms/bv", { secret })); }
                finally { setBusy(false); }
              }}>
        Run
      </button>
      {onRun && null}
    </div>
  );
}

function SuperdenseForm({ onRun, busy, setBusy }: any) {
  const [bits, setBits] = useState("01");
  return (
    <div className="row">
      <label className="field">Two-bit message
        <input type="text" value={bits} maxLength={2} style={{ width: 60 }}
               onChange={(e) => setBits(e.target.value.replace(/[^01]/g, ""))} />
      </label>
      <button className="btn" disabled={busy}
              onClick={async () => {
                setBusy(true);
                try { onRun(await post("/api/algorithms/superdense", { bits })); }
                finally { setBusy(false); }
              }}>Send via 1 qubit</button>
    </div>
  );
}

function OrderFindingForm({ onRun, busy, setBusy }: any) {
  const [a, setA] = useState(7);
  const [N, setN] = useState(15);
  return (
    <div className="row">
      <label className="field">a
        <input type="number" min={2} value={a} onChange={(e) => setA(+e.target.value || 2)} />
      </label>
      <label className="field">N (odd ≤ 32)
        <input type="number" min={3} max={32} value={N} onChange={(e) => setN(+e.target.value || 15)} />
      </label>
      <button className="btn" disabled={busy}
              onClick={async () => {
                setBusy(true);
                try { onRun(await post("/api/algorithms/order-finding", { a, N })); }
                catch (err) { alert((err as Error).message); }
                finally { setBusy(false); }
              }}>Find order</button>
    </div>
  );
}

function WalkForm({ onRun, busy, setBusy }: any) {
  const [steps, setSteps] = useState(6);
  const [qubits, setQubits] = useState(4);
  return (
    <div className="row">
      <label className="field">Steps
        <input type="number" min={1} max={40} value={steps} onChange={(e) => setSteps(+e.target.value || 1)} />
      </label>
      <label className="field">Position qubits
        <input type="number" min={2} max={8} value={qubits} onChange={(e) => setQubits(+e.target.value || 4)} />
      </label>
      <button className="btn" disabled={busy}
              onClick={async () => {
                setBusy(true);
                try { onRun(await post("/api/algorithms/quantum-walk", { n_position_qubits: qubits, steps })); }
                finally { setBusy(false); }
              }}>Compare walks</button>
    </div>
  );
}
