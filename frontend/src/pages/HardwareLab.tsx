import { useEffect, useState } from "react";
import { get, post } from "../lib/api";

export default function HardwareLab() {
  const [profiles, setProfiles] = useState<any[]>([]);
  const [selected, setSelected] = useState("NoisyGeneric-8Q");
  const [nQubits, setNQubits] = useState(5);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    get("/api/hardware/profiles").then(setProfiles).catch(() => {});
  }, []);

  const profile = profiles.find((p) => p.name === selected);
  const positions = (i: number, n: number): [number, number] => {
    // simple ring layout for the coupling graph
    const a = (2 * Math.PI * i) / Math.max(n, 1) - Math.PI / 2;
    return [150 + 110 * Math.cos(a), 120 + 95 * Math.sin(a)];
  };

  return (
    <div>
      <h1 className="page-title">Hardware Lab</h1>
      <p className="page-sub">
        Model hardware profiles drive SWAP-insertion mapping. Every mapping is
        verified against the logical circuit under ideal execution — the check
        result is reported per run.
      </p>

      <div className="panel">
        <h3>Model profiles</h3>
        <div className="row">
          <label className="field">Profile
            <select value={selected} onChange={(e) => setSelected(e.target.value)}>
              {profiles.map((p) => (
                <option key={p.name} value={p.name}>{p.name} ({p.n_qubits}q)</option>
              ))}
            </select>
          </label>
          <label className="field">Circuit qubits
            <input type="number" min={2} max={8} value={nQubits}
                   onChange={(e) => setNQubits(+e.target.value || 4)} style={{ width: 70 }} />
          </label>
          <button className="btn" disabled={!profile}
                  onClick={() =>
                    post("/api/hardware/transpile", {
                      circuit: ghzRing(nQubits),
                      profile_name: selected,
                    }).then(setResult).catch((e) => setError(e.message))
                  }>
            Map GHZ + long-range CX
          </button>
        </div>

        {profile && (
          <div style={{ marginTop: 10 }}>
            <p className="kv">Native gates: <b>{profile.native_gates.join(", ")}</b></p>
            <p className="kv">T1 = {profile.t1_us.toLocaleString()} µs · T2 = {profile.t2_us.toLocaleString()} µs · readout p(1|0)={profile.readout.p_read1_given_0}</p>
            <svg viewBox="0 0 300 240" width={300} role="img" aria-label="coupling graph">
              {((): React.ReactNode => {
                const n = profile.n_qubits;
                const pos = Array.from({ length: n }, (_, i) => positions(i, n));
                const edges = profile.coupling_edges.map((e: number[]) => ({ e }));
                return (
                  <>
                    {edges.map(({ e }: any, i: number) => {
                      const [x1, y1] = pos[e[0]];
                      const [x2, y2] = pos[e[1]];
                      return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2}
                                   stroke="var(--border)" strokeWidth={1.6} />;
                    })}
                    {pos.map(([x, y], i) => (
                      <g key={i}>
                        <circle cx={x} cy={y} r={13} fill="var(--bg-raised)"
                                stroke="#4aa8ff" strokeWidth={1.8} />
                        <text x={x} y={y + 4} textAnchor="middle" fontSize={10} fill="var(--text)">{i}</text>
                      </g>
                    ))}
                  </>
                );
              })()}
            </svg>
            <span className="badge warn">{profile.model_label}</span>
          </div>
        )}
      </div>

      {error && <div className="error-box">{error}</div>}

      {result && (
        <div className="panel">
          <h3>Mapping result</h3>
          <div className="metric-cards">
            <Metric label="SWAPs inserted" value={String(result.metrics.swap_count)} />
            <Metric label="Depth before → after"
                    value={`${result.metrics.original_depth} → ${result.metrics.mapped_depth}`} />
            <Metric label="Added 2q gates" value={String(result.metrics.added_two_qubit_gates)} />
            <Metric label="Mapping verified"
                    value={result.verification.verified ? "YES" : "NOT CHECKED"} />
          </div>
          <p className="kv">Final mapping (logical → physical):
            {" "}
            <b>{Object.entries(result.final_mapping).map(([l, p]) => `${l}→${p}`).join(", ")}</b>
          </p>
          <details>
            <summary style={{ cursor: "pointer", fontSize: 12.5 }}>Mapped circuit JSON</summary>
            <pre className="event-log">{JSON.stringify(result.mapped_circuit.operations, null, 1).slice(0, 2000)}</pre>
          </details>
        </div>
      )}
    </div>
  );
}

function ghzRing(n: number) {
  const ops: any[] = [
    { kind: "gate", gate: "H", params: [], qubits: [0], clbits: [], condition: null },
  ];
  for (let q = 0; q + 1 < n; q++) {
    ops.push({ kind: "gate", gate: "CX", params: [], qubits: [q, q + 1], clbits: [], condition: null });
  }
  ops.push({ kind: "gate", gate: "CX", params: [], qubits: [0, n - 1], clbits: [], condition: null });
  return {
    schema: "quantumlab.circuit", version: 1,
    name: "ghz-ring", num_qubits: n, num_clbits: 0,
    metadata: {}, operations: ops,
  };
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-card">
      <div className="value">{value}</div>
      <div className="label">{label}</div>
    </div>
  );
}
