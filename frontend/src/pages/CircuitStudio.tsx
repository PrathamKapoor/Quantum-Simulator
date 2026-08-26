import { useEffect, useState } from "react";
import { post, emptyCircuit } from "../lib/api";
import type { ExecutedCircuit } from "../lib/api";
import { BarChart } from "../lib/charts";
import DistributedPanel from "../components/DistributedPanel";

const GATES: Record<string, { arity: number; params: string[] }> = {
  H: { arity: 1, params: [] },
  X: { arity: 1, params: [] },
  Y: { arity: 1, params: [] },
  Z: { arity: 1, params: [] },
  S: { arity: 1, params: [] },
  T: { arity: 1, params: [] },
  RX: { arity: 1, params: ["theta"] },
  RY: { arity: 1, params: ["theta"] },
  RZ: { arity: 1, params: ["theta"] },
  CX: { arity: 2, params: [] },
  CZ: { arity: 2, params: [] },
  SWAP: { arity: 2, params: [] },
};

interface PlacedGate {
  id: number;
  gate: string;
  qubits: number[];
  params: number[];
}

export default function CircuitStudio() {
  const [nQubits, setNQubits] = useState(3);
  const [selectedGate, setSelectedGate] = useState("H");
  const [placed, setPlaced] = useState<PlacedGate[]>([
    { id: 1, gate: "H", qubits: [0], params: [] },
    { id: 2, gate: "CX", qubits: [0, 1], params: [] },
  ]);
  const [nextId, setNextId] = useState(3);
  const [shots, setShots] = useState(1024);
  const [seed, setSeed] = useState(42);
  const [result, setResult] = useState<ExecutedCircuit | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const gateInfo = GATES[selectedGate];

  const placeAt = (qubit: number) => {
    const arity = gateInfo.arity;
    if (arity === 1) {
      setPlaced((g) => [...g, { id: nextId, gate: selectedGate, qubits: [qubit], params: gateInfo.params.map(() => Math.PI / 4) }]);
      setNextId((i) => i + 1);
    } else if (arity === 2 && qubit + 1 < nQubits) {
      setPlaced((g) => [...g, { id: nextId, gate: selectedGate, qubits: [qubit, qubit + 1], params: [] }]);
      setNextId((i) => i + 1);
    }
  };

  const removeGate = (id: number) => setPlaced((g) => g.filter((x) => x.id !== id));

  const updateParam = (gateId: number, idx: number, value: number) => {
    setPlaced((gs) =>
      gs.map((g) =>
        g.id === gateId ? { ...g, params: g.params.map((p, i) => (i === idx ? value : p)) } : g
      )
    );
  };

  const buildDocument = () => {
    const c = emptyCircuit(nQubits, nQubits, "studio-circuit");
    let clbit = 0;
    for (const g of placed) {
      c.operations.push({
        kind: "gate",
        gate: g.gate.toUpperCase(),
        params: g.params,
        qubits: g.qubits,
        clbits: [],
        condition: null,
      });
      void clbit;
    }
    // final measurement of all qubits
    c.operations.push({
      kind: "measure",
      qubits: Array.from({ length: nQubits }, (_, i) => i),
      clbits: Array.from({ length: nQubits }, (_, i) => i),
    });
    return c;
  };

  const execute = async () => {
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const circuit = buildDocument();
      const res = await post<ExecutedCircuit>("/api/circuits/execute", {
        circuit,
        shots,
        seed,
        mode: "statevector",
      });
      setResult(res);
    } catch (e: any) {
      setError(e.message + (e.suggestion ? `\nTry: ${e.suggestion}` : ""));
    } finally {
      setRunning(false);
    }
  };

  useEffect(() => {
    // keep placed gates within bounds when shrinking qubit count
    setPlaced((gs) => gs.filter((g) => g.qubits.every((q) => q < nQubits)));
  }, [nQubits]);

  return (
    <div>
      <h1 className="page-title">Circuit Studio</h1>
      <p className="page-sub">
        Build circuits on the shared simulation engine. Select a gate from the palette,
        click a qubit row to place it; two-qubit gates span adjacent qubit pairs.
      </p>

      <div className="panel">
        <h3>Gate palette</h3>
        <div className="gate-palette">
          {Object.entries(GATES).map(([name]) => (
            <button
              key={name}
              className={"palette-gate" + (selectedGate === name ? " selected" : "")}
              onClick={() => setSelectedGate(name)}
              title={`Place ${name}`}
            >
              {name}
            </button>
          ))}
          <button className="btn secondary small" onClick={() => setPlaced([])} style={{ marginLeft: 8 }}>
            Clear all
          </button>
        </div>

        <div style={{ marginTop: 14 }} className="circuit-editor">
          <div className="row" style={{ marginBottom: 10 }}>
            <label className="field">Qubits
              <input type="number" min={1} max={12} value={nQubits}
                     onChange={(e) => setNQubits(Math.max(1, Math.min(12, +e.target.value || 1)))} />
            </label>
            <span style={{ color: "var(--text-dim)", fontSize: 12 }}>
              Click a cell to place <b>{selectedGate}</b>. Click a placed gate to delete it.
            </span>
          </div>
          {Array.from({ length: nQubits }, (_, q) => (
            <div className="qubit-row" key={q}>
              <span className="qubit-label">|q{q}⟩</span>
              <div
                className="gate-cell"
                style={{ borderRadius: "50%", opacity: 0.35 }}
                onClick={() => placeAt(q)}
                role="button"
                aria-label={`place ${selectedGate} on qubit ${q}`}
              >+</div>
              {placed.map((g) =>
                g.qubits.includes(q) ? (
                  <div
                    key={g.id}
                    className="gate-cell filled"
                    onClick={() => removeGate(g.id)}
                    title="click to remove"
                  >
                    {g.gate.toUpperCase()}
                    {g.params.length > 0 && (
                      <sub style={{ fontSize: 8 }}>{g.params[0].toFixed(2)}</sub>
                    )}
                    {g.gate === "CX" && g.qubits[0] === q && <span>•</span>}
                  </div>
                ) : null
              )}
            </div>
          ))}
        </div>

        {placed.filter((g) => g.params.length > 0).length > 0 && (
          <div className="row" style={{ marginTop: 10 }}>
            {placed.filter((g) => g.params.length > 0).map((g) => (
              <label className="field" key={g.id}>
                θ for {g.gate}{g.qubits[0]} (rad)
                <input type="number" step={0.05} value={g.params[0]}
                       onChange={(e) => updateParam(g.id, 0, +e.target.value)} />
              </label>
            ))}
          </div>
        )}

        <div className="row" style={{ marginTop: 14 }}>
          <label className="field">Shots
            <input type="number" min={1} max={10000000} value={shots}
                   onChange={(e) => setShots(Math.max(1, +e.target.value || 1))} />
          </label>
          <label className="field">Seed
            <input type="number" value={seed} onChange={(e) => setSeed(+e.target.value || 0)} />
          </label>
          <button className="btn" disabled={running} onClick={execute}>
            {running ? "Running…" : "Run circuit"}
          </button>
        </div>
      </div>

      {error && <div className="error-box">{error}</div>}

      {result && (
        <div className="grid2">
          <div className="panel">
            <h3>Measurement distribution</h3>
            <BarChart entries={Object.entries(result.counts)} title="Counts per outcome" />
            <table className="data-table" style={{ marginTop: 8 }}>
              <thead><tr><th>Outcome</th><th>Probability</th></tr></thead>
              <tbody>
                {Object.entries(result.probabilities).map(([k, v]) => (
                  <tr key={k}><td>{k}</td><td>{v.toFixed(4)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>          <div className="panel">
            <h3>State inspection</h3>
            {result.statevector && (
              <table className="data-table">
                <thead><tr><th>Basis</th><th>Amplitude</th><th>P</th></tr></thead>
                <tbody>
                  {Object.entries(result.statevector).map(([basis, a]) => (
                    <tr key={basis}>
                      <td>|{basis}⟩</td>
                      <td className="kv">{a.re.toFixed(4)} {a.im >= 0 ? "+" : "−"} {Math.abs(a.im).toFixed(4)}i</td>
                      <td>{a.p.toFixed(6)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {result.bloch_vector && (
              <p className="kv" style={{ marginTop: 10 }}>
                Bloch vector: <b>x={result.bloch_vector[0]}</b> y={result.bloch_vector[1]} z={result.bloch_vector[2]}
              </p>
            )}
            {result.entanglement_entropy_bits && (
              <p className="kv" style={{ marginTop: 10 }}>
                Entropy of entanglement per qubit (bits):{" "}
                <b>{result.entanglement_entropy_bits.map((v) => v.toFixed(3)).join(", ")}</b>
              </p>
            )}
            {result.density_summary && (
              <p className="kv">Purity {result.density_summary.purity}, entropy {result.density_summary.entropy_bits} bits</p>
            )}
            {result.warnings?.length > 0 && (
              <ul className="note-list">{result.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
            )}
          </div>
        </div>
      )}

      <DistributedPanel buildCircuit={buildDocument} nQubits={nQubits} seed={seed} />
    </div>
  );
}
