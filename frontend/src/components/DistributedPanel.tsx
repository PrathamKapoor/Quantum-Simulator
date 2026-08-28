import { useState } from "react";
import { post } from "../lib/api";

/**
 * Distributed-computing workflow for Circuit Studio (§FRONTEND).
 * Every displayed value comes from an actual backend result document
 * (`quantumlab.distributed-result` v1); nothing is decorated locally.
 */

interface RemoteOp {
  op_index: number;
  gate: string;
  qubits: number[];
  control_qubit: number;
  target_qubit: number;
  source_node: string;
  target_node: string;
  protocol: string;
  ebits_required: number;
  classical_messages: number;
  ebit_fidelity: number | null;
  ebit_latency_ns: number | null;
  ebit_attempts: number | null;
  ebit_fidelity_applied: number | null;
  ebit_noise: string[] | null;
  executed: boolean;
  failure_reason: string | null;
}

interface LocalOp {
  node: string;
  op_index: number;
  gate: string | null;
  qubits: number[];
  kind: string;
}

interface EbitGrant {
  node_a: string;
  node_b: string;
  success: boolean;
  fidelity: number | null;
  latency_ns: number | null;
  attempts: number | null;
  model: string;
  failure_reason: string | null;
}

interface ClassicalMessage {
  source_node: string;
  target_node: string;
  bits: number;
  remote_op_index: number;
  order: number;
}

interface Metrics {
  local_gate_count: number;
  remote_gate_count: number;
  remote_cnot_count: number;
  ebit_consumption: number;
  classical_message_count: number;
  communication_cost: number;
  node_count: number;
  qubit_count: number;
  objective: string;
}

interface PartitionPlanDoc {
  assignment: Record<string, string>;
  objective: string;
  nodes: { name: string; qubits: number[] }[];
  local_operations: LocalOp[];
  remote_operations: RemoteOp[];
  metrics: Metrics;
}

interface DistributedResultDoc {
  schema: string;
  status: string;
  protocol: string;
  local_gate_count: number;
  remote_gate_count: number;
  remote_cnot_count: number;
  ebit_consumption: number;
  classical_message_count: number;
  communication_cost: number;
  nodes: { name: string; qubits: number[] }[];
  local_operations: LocalOp[];
  remote_operations: RemoteOp[];
  entanglement_operations: EbitGrant[];
  classical_messages: ClassicalMessage[];
  equivalence: { fidelity: number; passed: boolean; method: string; note?: string } | null;
  output_state: { probabilities: Record<string, number> } | null;
  errors: string[];
  warnings: string[];
}

interface CentralizedResult {
  probabilities: Record<string, number>;
}

type CircuitDoc = Record<string, unknown>;

export default function DistributedPanel({
  buildCircuit,
  nQubits,
  seed,
}: {
  buildCircuit: () => CircuitDoc;
  nQubits: number;
  seed: number;
}) {
  const [numNodes, setNumNodes] = useState(2);
  const [autoAssign, setAutoAssign] = useState(false);
  const [mapping, setMapping] = useState<Record<number, string>>({});
  const [ebitNoise, setEbitNoise] = useState<"ideal" | "network_fidelity" | "fixed">("ideal");
  const [ebitNoiseFidelity, setEbitNoiseFidelity] = useState(0.9);
  const [plan, setPlan] = useState<PartitionPlanDoc | null>(null);
  const [result, setResult] = useState<DistributedResultDoc | null>(null);
  const [central, setCentral] = useState<CentralizedResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const nodeName = (i: number) => `node_${i}`;
  const nodeNames = Array.from({ length: numNodes }, (_, i) => nodeName(i));
  const effectiveMapping: Record<number, string> | null =
    autoAssign ? null : Object.fromEntries(
      Array.from({ length: nQubits }, (_, q) => [q, mapping[q] ?? nodeName(q % numNodes)])
    );

  const payload = () => {
    const body: Record<string, unknown> = { circuit: buildCircuit(), seed };
    if (!autoAssign) body.qubit_to_node = effectiveMapping;
    return body;
  };

  const runPartition = async () => {
    setBusy("partition"); setError(null); setPlan(null);
    try {
      const body = payload();
      setPlan(await post<PartitionPlanDoc>("/api/distributed/partition", body));
    } catch (e: any) { setError(e.message); } finally { setBusy(null); }
  };

  const runDistributed = async () => {
    setBusy("dist"); setError(null); setResult(null);
    try {
      const body = payload();
      body.protocol = "single_ebit";
      body.ebit_noise = ebitNoise;
      if (ebitNoise === "fixed") body.ebit_noise_fidelity = ebitNoiseFidelity;
      setResult(await post<DistributedResultDoc>("/api/distributed/simulate", body));
    } catch (e: any) { setError(e.message); } finally { setBusy(null); }
  };

  const runComparison = async () => {
    setBusy("cmp"); setError(null); setCentral(null);
    try {
      setCentral(await post<CentralizedResult>("/api/circuits/execute", {
        circuit: buildCircuit(), seed, mode: "statevector",
      }));
      const body = payload();
      body.protocol = "single_ebit";
      body.ebit_noise = ebitNoise;
      if (ebitNoise === "fixed") body.ebit_noise_fidelity = ebitNoiseFidelity;
      setResult(await post<DistributedResultDoc>("/api/distributed/simulate", body));
    } catch (e: any) { setError(e.message); } finally { setBusy(null); }
  };

  // Comparison derived strictly from the two backend probability documents.
  const basisUnion = central && result?.output_state
    ? Array.from(new Set([...Object.keys(central.probabilities),
                           ...Object.keys(result.output_state.probabilities)])).sort()
    : null;
  const maxDiff = basisUnion && central && result?.output_state
    ? Math.max(...basisUnion.map((b) =>
        Math.abs((central.probabilities[b] ?? 0) - (result.output_state!.probabilities[b] ?? 0))))
    : null;

  return (
    <div className="panel" style={{ marginTop: 16 }}>
      <h3>Distributed computation</h3>
      <p style={{ fontSize: 12, color: "var(--text-dim)" }}>
        Partitions this circuit across compute nodes and executes cross-node CNOTs through the
        genuine single-ebit protocol (entanglement + teleportation + Pauli corrections).
        Modelled network resources are reported separately from simulation runtime.
      </p>

      <div className="row" style={{ flexWrap: "wrap", gap: 10 }}>
        <label className="field">Nodes
          <input type="number" min={2} max={8} value={numNodes}
                 onChange={(e) => setNumNodes(Math.max(2, Math.min(8, +e.target.value || 2)))} />
        </label>
        <label className="field" style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
          <input type="checkbox" checked={autoAssign}
                 onChange={(e) => setAutoAssign(e.target.checked)} />
          Auto-assign qubits (minimize cross-node gates)
        </label>
      </div>

      <div className="row" style={{ flexWrap: "wrap", gap: 10, marginTop: 8 }}>
        <label className="field">Ebit noise
          <select value={ebitNoise} onChange={(e) => setEbitNoise(e.target.value as typeof ebitNoise)}>
            <option value="ideal">Ideal entanglement (F = 1)</option>
            <option value="network_fidelity">Network-modeled (Werner, grant fidelity)</option>
            <option value="fixed">Fixed Werner fidelity</option>
          </select>
        </label>
        {ebitNoise === "fixed" && (
          <label className="field">Werner ebit fidelity F
            <input type="number" min={0} max={1} step={0.01} value={ebitNoiseFidelity}
                   onChange={(e) => setEbitNoiseFidelity(Math.max(0, Math.min(1, +e.target.value || 0)))} />
          </label>
        )}
      </div>

      {!autoAssign && (
        <div className="row" style={{ flexWrap: "wrap", gap: 8, marginTop: 8 }}>
          {Array.from({ length: nQubits }, (_, q) => (
            <label className="field" key={q} style={{ minWidth: 90 }}>
              q{q} →
              <select value={mapping[q] ?? nodeName(q % numNodes)}
                      onChange={(e) => setMapping((m) => ({ ...m, [q]: e.target.value }))}>
                {nodeNames.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
          ))}
        </div>
      )}

      <div className="row" style={{ marginTop: 12 }}>
        <button className="btn secondary" disabled={busy !== null} onClick={runPartition}>
          {busy === "partition" ? "Partitioning…" : "Partition"}
        </button>
        <button className="btn" disabled={busy !== null} onClick={runDistributed}>
          {busy === "dist" ? "Executing…" : "Run distributed"}
        </button>
        <button className="btn secondary" disabled={busy !== null} onClick={runComparison}>
          {busy === "cmp" ? "Comparing…" : "Compare centralized vs distributed"}
        </button>
      </div>

      {error && <div className="error-box">{error}</div>}

      {result && result.status !== "success" && (
        <div className="error-box">
          <b>Distributed execution failed.</b>
          <ul className="note-list">
            {result.errors.map((e, i) => <li key={i}>{e}</li>)}
          </ul>
        </div>
      )}

      {(plan || result) && (
        <>
          <div className="metric-cards" style={{ marginTop: 12 }}>
            <Metric label="Local gates"
                    value={String(result ? result.local_gate_count : plan!.metrics.local_gate_count)} />
            <Metric label="Remote gates"
                    value={String(result ? result.remote_gate_count : plan!.metrics.remote_gate_count)} />
            <Metric label="Remote CNOTs"
                    value={String(result ? result.remote_cnot_count : plan!.metrics.remote_cnot_count)} />
            <Metric label="Ebits consumed"
                    value={String(result ? result.ebit_consumption : plan!.metrics.ebit_consumption)} />
            <Metric label="Classical bits"
                    value={String(result ? result.classical_message_count : plan!.metrics.classical_message_count)} />
            <Metric label="Nodes"
                    value={String(result ? result.nodes.length : plan!.metrics.node_count)} />
          </div>

          <div className="grid2" style={{ marginTop: 12 }}>
            <div>
              <h3 style={{ marginBottom: 6 }}>
                <span className="badge ok">LOCAL</span> operations per node
              </h3>
              {(result ? result.nodes : plan!.nodes).map((n) => (
                <div key={n.name} style={{ marginBottom: 8 }}>
                  <p className="kv"><b>{n.name}</b> — qubits [{n.qubits.join(", ")}]</p>
                  <OpList ops={(result ?? plan!).local_operations.filter((o) => o.node === n.name)}
                          kind="local" />
                </div>
              ))}
            </div>

            <div>
              <h3 style={{ marginBottom: 6 }}>
                <span className="badge warn">REMOTE</span> cross-node operations
              </h3>
              {(result?.remote_operations.length ?? plan!.remote_operations.length) === 0 ? (
                <p style={{ color: "var(--text-dim)" }}>No cross-node gates — fully local execution.</p>
              ) : (
                <table className="data-table">
                  <thead>
                    <tr><th>#</th><th>Gate</th><th>Edge</th><th>Ebits</th><th>Cbits</th>
                        {result !== null && <><th>Ebit F</th><th>Werner sample</th></>}<th>Status</th></tr>
                  </thead>
                  <tbody>
                    {(result ? result.remote_operations : plan!.remote_operations).map((r) => (
                      <tr key={r.op_index}>
                        <td>{r.op_index}</td>
                        <td>{r.gate}(q{r.control_qubit},q{r.target_qubit})</td>
                        <td>{r.source_node} → {r.target_node}</td>
                        <td>{r.ebits_required}</td>
                        <td>{r.classical_messages}</td>
                        {result !== null && (
                          <>
                            <td>{r.ebit_fidelity_applied === null || r.ebit_fidelity_applied === undefined
                              ? "—"
                              : `F = ${r.ebit_fidelity_applied.toFixed(4)}`}</td>
                            <td>{r.ebit_noise === null || r.ebit_noise === undefined
                              ? "—"
                              : r.ebit_noise.join(", ")}</td>
                          </>
                        )}
                        <td>
                          {result === null
                            ? <span className="badge">planned</span>
                            : r.executed
                              ? <span className="badge ok">executed</span>
                              : <span className="badge err">{r.failure_reason ?? "failed"}</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </>
      )}

      {result && result.entanglement_operations.length > 0 && (
        <>
          <h3 style={{ marginTop: 14 }}>Entanglement resources</h3>
          <table className="data-table">
            <thead><tr><th>Pair</th><th>Model</th><th>Fidelity</th><th>Latency (modelled)</th><th>Attempts</th></tr></thead>
            <tbody>
              {result.entanglement_operations.map((g, i) => (
                <tr key={i}>
                  <td>{g.node_a} ↔ {g.node_b}</td>
                  <td>{g.model}</td>
                  <td>{g.fidelity === null ? "—" : g.fidelity.toFixed(4)}</td>
                  <td>{g.latency_ns === null ? "—" : `${(g.latency_ns / 1000).toFixed(1)} µs`}</td>
                  <td>{g.attempts ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {result && result.classical_messages.length > 0 && (
        <>
          <h3 style={{ marginTop: 14 }}>Classical communication</h3>
          <table className="data-table">
            <thead><tr><th>Order</th><th>Sender</th><th>Receiver</th><th>Bits</th><th>For remote op</th></tr></thead>
            <tbody>
              {result.classical_messages.map((m, i) => (
                <tr key={i}>
                  <td>{m.order}</td>
                  <td>{m.source_node}</td>
                  <td>{m.target_node}</td>
                  <td>{m.bits}</td>
                  <td>{m.remote_op_index}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {result?.equivalence && (
        <div className="panel" style={{ marginTop: 14 }}>
          <h3>Equivalence vs centralized reference</h3>
          <p className="kv">
            Verdict:{" "}
            <span className={"badge " + (result.equivalence.passed ? "ok" : "err")}>
              {result.equivalence.passed ? "MATCHES CENTRALIZED" : "MISMATCH"}
            </span>{" "}
            · fidelity {result.equivalence.fidelity.toFixed(9)}
          </p>
          <p style={{ fontSize: 12, color: "var(--text-dim)" }}>{result.equivalence.method}</p>
          {result.equivalence.note && (
            <p style={{ fontSize: 12, color: "var(--text-dim)" }}>{result.equivalence.note}</p>
          )}
        </div>
      )}

      {basisUnion && central && result?.output_state && (
        <div className="panel" style={{ marginTop: 14 }}>
          <h3>Output probabilities — centralized vs distributed</h3>
          <table className="data-table">
            <thead><tr><th>Basis</th><th>Centralized</th><th>Distributed</th><th>|Δ|</th></tr></thead>
            <tbody>
              {basisUnion.map((b) => {
                const cp = central.probabilities[b] ?? 0;
                const dp = result.output_state!.probabilities[b] ?? 0;
                return (
                  <tr key={b}>
                    <td>|{b}⟩</td>
                    <td>{cp.toFixed(6)}</td>
                    <td>{dp.toFixed(6)}</td>
                    <td>{Math.abs(cp - dp).toFixed(9)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {maxDiff !== null && (
            <p className="kv" style={{ marginTop: 8 }}>
              Max |Δ| over basis outcomes: <b>{maxDiff.toExponential(3)}</b>
            </p>
          )}
        </div>
      )}

      {result?.warnings && result.warnings.length > 0 && (
        <ul className="note-list" style={{ marginTop: 10 }}>
          {result.warnings.map((w, i) => <li key={i}>{w}</li>)}
        </ul>
      )}
    </div>
  );
}

function OpList({ ops, kind }: { ops: LocalOp[]; kind: "local" }) {
  if (ops.length === 0) return <p style={{ color: "var(--text-dim)", fontSize: 12 }}>none</p>;
  void kind;
  return (
    <div className="row" style={{ flexWrap: "wrap", gap: 4 }}>
      {ops.map((o, i) => (
        <span key={i} className="badge ok" title={`op ${o.op_index}`}>
          {(o.gate ?? o.kind).toUpperCase()}
          {o.qubits.length > 0 && <sub>({o.qubits.join(",")})</sub>}
        </span>
      ))}
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
