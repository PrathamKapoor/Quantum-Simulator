import { useState } from "react";
import { get, post } from "../lib/api";

/** Book Laboratory (milestone 22): the McMahon chapter topics as
 * runnable, validated experiments. Every experiment executes through
 * the real process-isolated worker and carries a backend-computed
 * validation section (hypothesis -> prediction -> passed). No numbers
 * are hard-coded in the UI; everything renders from the result
 * document. */

interface BookExperiment {
  module: string;
  chapter: string;
  title: string;
  description: string;
  config: Record<string, unknown>;
}

const EXPERIMENTS: BookExperiment[] = [
  { module: "book_entropy_scan", chapter: "Ch. 1", title: "Shannon entropy scan",
    description: "Entropy of binary distributions vs shape; mutual-information identities.",
    config: { bias_steps: 21 } },
  { module: "book_qubit_state", chapter: "Ch. 2", title: "Qubit state & Bloch sphere",
    description: "Arbitrary single-qubit state: Bloch vector and measurement probabilities.",
    config: { theta: 0.9, phi: 0.4 } },
  { module: "book_operator_report", chapter: "Ch. 3", title: "Operators & uncertainty",
    description: "Eigenvalues, commutators, Robertson uncertainty bound.",
    config: { operator_a: "X", operator_b: "Y" } },
  { module: "book_tensor_identity", chapter: "Ch. 4", title: "Tensor product identity",
    description: "Numerically verifies (A⊗B)(|ψ⟩⊗|φ⟩) = (A|ψ⟩)⊗(B|φ⟩).",
    config: {} },
  { module: "book_density_report", chapter: "Ch. 5", title: "Density operators",
    description: "Purity, partial trace, reduced states, Bloch vector: Bell vs maximally mixed.",
    config: {} },
  { module: "book_povm", chapter: "Ch. 6", title: "POVM & generalized measurement",
    description: "Outcome probabilities, post-measurement states, Kraus completeness.",
    config: {} },
  { module: "book_entanglement_report", chapter: "Ch. 7", title: "Entanglement characterization",
    description: "Schmidt decomposition, concurrence, negativity, EoF, CHSH Bell test.",
    config: { shots: 2000 } },
  { module: "book_gate_decomposition", chapter: "Ch. 8", title: "Gate decompositions",
    description: "CNOT = (I⊗H)·CZ·(I⊗H); Z-Y decomposition; controlled-U via projectors.",
    config: {} },
  { module: "book_grover_scan", chapter: "Ch. 9", title: "Grover amplitude amplification",
    description: "Success probability vs iteration count; optimal ~π/4·√N.",
    config: { n_qubits: 3, target: 5, max_iterations: 4 } },
  { module: "book_teleportation", chapter: "Ch. 10", title: "Teleportation",
    description: "Full five-step protocol with intermediate states and classical bits.",
    config: {} },
  { module: "book_superdense", chapter: "Ch. 10", title: "Superdense coding",
    description: "Two classical bits per sent qubit; all four messages.",
    config: { shots: 256 } },
  { module: "book_b92_scan", chapter: "Ch. 11", title: "B92 QKD under attack",
    description: "Sifting rate and QBER vs intercept-resend probability.",
    config: { shots: 4096 } },
  { module: "book_channel_scan", chapter: "Ch. 12", title: "Noise channels",
    description: "Depolarizing / amplitude / phase damping sweeps: fidelity, purity, Bloch shrinkage.",
    config: {} },
  { module: "book_qi_metrics", chapter: "Ch. 13", title: "QI metrics & no-cloning",
    description: "Trace distance, fidelity, Bures distance, concurrence, EoF, no-cloning.",
    config: {} },
  { module: "book_adiabatic", chapter: "Ch. 14", title: "Adiabatic evolution",
    description: "H(s) interpolation, spectral gap, ground-state overlap vs runtime.",
    config: {} },
  { module: "book_cluster_state", chapter: "Ch. 15", title: "Cluster states",
    description: "Graph-state preparation, stabilizer verification, witness, node measurement.",
    config: { length: 4 } },
];

export default function BookLab() {
  const [selected, setSelected] = useState<BookExperiment>(EXPERIMENTS[5]);
  const [configText, setConfigText] = useState(
    JSON.stringify(EXPERIMENTS[5].config, null, 2));
  const [result, setResult] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setBusy(true); setError(null); setResult(null);
    try {
      let config: Record<string, unknown> = {};
      try {
        config = configText.trim() ? JSON.parse(configText) : {};
      } catch {
        throw new Error("Configuration is not valid JSON.");
      }
      const created = await post("/api/experiments", {
        name: `book: ${selected.title}`,
        module: selected.module,
        config, seed: Math.floor(Math.random() * 1e6),
      });
      const expId = created.experiment_id ?? created.id;
      const runIds: number[] = created.run_ids;
      await post("/api/runs/execute-batch", { run_ids: runIds });
      let finalStatus = "";
      for (let i = 0; i < 600; i++) {
        const exp: any = await get(`/api/experiments/${expId}`);
        const run = (exp.runs ?? []).find(
          (r: any) => r.id === runIds[0]);
        finalStatus = run?.status ?? "";
        if (finalStatus === "COMPLETED" || finalStatus === "FAILED") break;
        await new Promise((r) => setTimeout(r, 250));
      }
      if (finalStatus === "FAILED") throw new Error("experiment failed");
      const doc: any = await get(`/api/runs/${runIds[0]}/result`);
      setResult(doc.document);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel">
      <h3>Book Laboratory — McMahon, Quantum Computing Explained</h3>
      <p style={{ fontSize: 12.5, color: "var(--text-dim)", marginTop: 0 }}>
        Each chapter's concepts as a runnable, seeded experiment. Every run
        executes through the process-isolated worker and returns a
        backend-computed <b>validation</b> section: the predicted invariant
        and whether the simulation satisfied it. No expected value is
        hard-coded — predictions are computed and compared (scientific
        integrity statement applies).
      </p>
      <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
        <label className="field">Experiment
          <select
            value={selected.module}
            onChange={(e) => {
              const ex = EXPERIMENTS.find((x) => x.module === e.target.value)!;
              setSelected(ex);
              setConfigText(JSON.stringify(ex.config, null, 2));
              setResult(null); setError(null);
            }}
            style={{ minWidth: 260 }}
          >
            {EXPERIMENTS.map((ex) => (
              <option key={ex.module} value={ex.module}>
                {ex.chapter} — {ex.title}
              </option>
            ))}
          </select>
        </label>
        <button className="btn" disabled={busy} onClick={run}>
          {busy ? "Running…" : "Run experiment"}
        </button>
      </div>
      <p style={{ fontSize: 12.5, margin: "8px 0" }}>
        <b>{selected.chapter}</b> — {selected.description}
      </p>
      <label className="field" style={{ display: "block" }}>
        Configuration (JSON)
        <textarea
          value={configText}
          onChange={(e) => setConfigText(e.target.value)}
          rows={4}
          style={{ width: "100%", maxWidth: 480, fontFamily: "monospace",
                   fontSize: 12 }}
        />
      </label>
      {error && <div className="error-box">{error}</div>}
      {result && (
        <>
          <p className="kv" style={{ marginTop: 10 }}>
            Result:{" "}
            <span className={"badge " + (result.summary?.validation?.passed
              ? "ok" : "err")}>
              {result.summary?.validation?.passed ? "PASSED" : "FAILED"}
            </span>{" "}
            · module <b>{result.module}</b>
          </p>
          <div className="metric-cards" style={{ marginTop: 8 }}>
            <Metric label="Prediction"
                    value={String(result.summary?.validation?.prediction
                      ?? "—").slice(0, 90)} />
          </div>
          <details open style={{ marginTop: 8 }}>
            <summary className="kv" style={{ cursor: "pointer" }}>
              Validation (backend-computed)
            </summary>
            <pre className="event-log">{JSON.stringify(
              result.summary?.validation, null, 2).slice(0, 2400)}</pre>
          </details>
          <details style={{ marginTop: 6 }}>
            <summary className="kv" style={{ cursor: "pointer" }}>
              Artifacts (observables, raw data)
            </summary>
            <pre className="event-log">{JSON.stringify(
              result.artifacts, null, 2).slice(0, 2400)}</pre>
          </details>
        </>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-card">
      <div className="value" style={{ fontSize: 12 }}>{value}</div>
      <div className="label">{label}</div>
    </div>
  );
}
