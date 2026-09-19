import { useEffect, useRef, useState } from "react";
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
  { module: "book_adiabatic_well", chapter: "Ch. 14", title: "Expanding well (Example 14.2)",
    description: "Infinite well a -> 3a: adiabatic following of the ground state vs sudden expansion.",
    config: { grid_points: 601, expansion_steps: 640, total_time: 200 } },
  { module: "book_adiabatic_hadamard", chapter: "Ch. 14", title: "Adiabatic Hadamard (Example 14.3)",
    description: "H_init = diag(-1,1), H_final = -X: slow evolution implements H|0> = |+>.",
    config: { total_time: 200, steps: 800 } },
  { module: "book_cluster_state", chapter: "Ch. 15", title: "Cluster states",
    description: "Graph-state preparation, stabilizer verification, witness, node measurement.",
    config: { length: 4 } },
  { module: "book_gram_schmidt", chapter: "Ch. 2-3", title: "Gram-Schmidt & independence",
    description: "Orthonormalization, span preservation, and the numerical linear-independence test.",
    config: { dimension: 4 } },
  { module: "book_purification", chapter: "Ch. 7", title: "Purification of a mixed state",
    description: "Pure extension |Psi>_AB with Tr_B|Psi><Psi| = rho; Schmidt spectrum oracle.",
    config: {} },
  { module: "book_entanglement_swapping", chapter: "Ch. 10", title: "Entanglement swapping",
    description: "Bell measurement on two pairs entangles the untouched outer qubits.",
    config: {} },
  { module: "book_qec_codes", chapter: "Ch. 12-13", title: "Error-correcting codes",
    description: "Bit-flip/phase-flip, Shor-9, Steane-7, 5-qubit: encode, inject, syndrome-decode, verify.",
    config: {} },
  { module: "book_state_tomography", chapter: "Ch. 6", title: "State tomography",
    description: "Pauli measurements, raw inversion and physical Bloch-ball reconstruction; statistical shot noise.",
    config: { theta: 1.1, phi: 0.5, shots: 20000 } },
  { module: "book_rabi_oscillations", chapter: "Ch. 14", title: "Rabi oscillations",
    description: "Driven two-level system: resonant and detuned Rabi dynamics vs the closed form.",
    config: { rabi_frequency: 1.0 } },
  { module: "book_helstrom", chapter: "Ch. 6 / 13", title: "Helstrom state discrimination",
    description: "Optimal binary measurement, unequal priors and mixed states against the Helstrom bound.",
    config: { theta: 1.5707963267948966, phi: 0.4, prior: 0.5, mixing: 0 } },
  { module: "book_channel_algebra", chapter: "Ch. 12", title: "Channel composition and Choi",
    description: "Noncommuting noise channels, Choi positivity and process/average gate fidelity.",
    config: { flip_probability: 0.3, gamma: 0.4 } },
  { module: "book_mbqc", chapter: "Ch. 15", title: "Adaptive cluster-state computation",
    description: "Two equatorial measurements with outcome-conditioned angles; all four branches vs a circuit oracle.",
    config: { theta: 1.0, phi: 0.37, alpha: 0.4, beta: 1.1 } },
  { module: "book_simon", chapter: "Research", title: "Simon's algorithm (rank acquisition)",
    description: "Hidden-mask recovery from rank-acquired equations; honest budget exhaustion.",
    config: { n_qubits: 3, secret: 5, shots: 64 } },
  { module: "book_qft", chapter: "Ch. 9", title: "Quantum Fourier Transform",
    description: "Exact vs approximate QFT: cutoff drops CP(2*pi/2^m) rotations; DFT oracle.",
    config: { n_qubits: 3, cutoff_exponent: 2, input_mode: "basis", basis_state: 3 } },
  { module: "book_qpe", chapter: "Ch. 9", title: "Phase estimation",
    description: "Arbitrary complex eigenvector; exact geometric-sum probability oracle.",
    config: { theta: 1.0, phi: 0.3, eigenphase: 0.375, precision_bits: 4, shots: 128 } },
  { module: "book_multigrover", chapter: "Ch. 9", title: "Multi-target Grover",
    description: "Marked sets with analytic sin^2((2k+1)asin(sqrt(M/N))) trajectories.",
    config: { n_qubits: 3, marked_indices: [1, 5], max_iterations: 4, shots: 128 } },
  { module: "book_classical_info", chapter: "Ch. 1", title: "Classical code & counting worksheets",
    description: "Code lengths (Ex. 1.1), storage message count (Ex. 1.3), income mode/mean/variance (Ex. 1.6).",
    config: {} },
  { module: "book_beamsplitter", chapter: "Ch. 9", title: "Beam splitter (Ex. 9.2)",
    description: "B = iI/sqrt(2)+X/sqrt(2): actions, tensor product, double application B^2 = iX.",
    config: {} },
  { module: "book_hubbard", chapter: "Ch. 8", title: "Hubbard units (Ex. 8.2-8.3)",
    description: "Four X^{mn} units on Hadamard states; Pauli operators in the Hubbard basis.",
    config: {} },
  { module: "book_rsa_toy", chapter: "Ch. 11", title: "Toy RSA baseline",
    description: "Small-prime key setup, encryption and recovery (educational arithmetic only).",
    config: {} },
  { module: "book_ghz_superdense", chapter: "Ch. 10", title: "GHZ superdense coding (Ex. 10.6)",
    description: "Two bits via one sent qubit + shared GHZ; orthogonal encodings and full decode.",
    config: {} },
  { module: "book_adiabatic_nonlinear", chapter: "Ch. 14", title: "Nonlinear adiabatic path (Ex. 14.4)",
    description: "s(1-s) coupling opens the crossing; eigenbranch mapping onto the CNOT permutation.",
    config: { coupling_strength: 1.0, total_time: 120, steps: 600 } },
  { module: "book_qutrit_measurement", chapter: "Ch. 6 / 3", title: "Qutrit measurement worksheet",
    description: "Three-level projectors, Born probabilities, post-states, energy expectation.",
    config: { preset: "ch06_ex2" } },
  { module: "book_operator_worksheet", chapter: "Ch. 3", title: "Operator worksheet",
    description: "Normal/Hermitian/unitary classification, spectra, polar decomposition, SVD.",
    config: {} },
  { module: "book_density_worksheet", chapter: "Ch. 5", title: "Density-matrix worksheet",
    description: "Validity (Hermitian/trace/PSD), purity, Bloch vector, basis probabilities.",
    config: {} },
];

const SESSION_KEY = "quantumlab.book-session.v1";

function readBookSession() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(SESSION_KEY) ?? "null");
    if (saved && EXPERIMENTS.some((ex) => ex.module === saved.module)
        && typeof saved.configText === "string" && Number.isSafeInteger(saved.seed)
        && saved.seed >= 0 && (saved.runId === null ||
          (Number.isSafeInteger(saved.runId) && saved.runId > 0))) return saved;
  } catch { /* Unavailable or invalid session storage starts a fresh worksheet. */ }
  return { module: EXPERIMENTS[5].module,
    configText: JSON.stringify(EXPERIMENTS[5].config, null, 2), seed: 42, runId: null };
}

export default function BookLab() {
  const [saved] = useState(readBookSession);
  const [selected, setSelected] = useState<BookExperiment>(
    EXPERIMENTS.find((ex) => ex.module === saved.module)!);
  const [configText, setConfigText] = useState<string>(saved.configText);
  const [result, setResult] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [seed, setSeed] = useState<number>(saved.seed);
  const [runId, setRunId] = useState<number | null>(saved.runId);
  const requestVersion = useRef(0);

  useEffect(() => {
    try {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify({
        module: selected.module, configText, seed, runId }));
    } catch { /* Backend persistence remains authoritative if storage is unavailable. */ }
  }, [selected.module, configText, seed, runId]);

  useEffect(() => {
    if (runId === null) return;
    let active = true;
    const version = ++requestVersion.current;
    const restore = async () => {
      try {
        const run = await get<{status: string; error_message?: string}>(`/api/runs/${runId}`);
        if (!active || version !== requestVersion.current) return;
        if (run.status !== "COMPLETED") {
          if (["FAILED", "CANCELLED"].includes(run.status)) {
            throw new Error(run.error_message ?? `Run ${run.status.toLowerCase()}.`);
          }
          throw new Error("Saved run is still pending; inspect its status in Experiments.");
        }
        const doc = await get<{document: {module: string}}>(`/api/runs/${runId}/result`);
        if (!active || version !== requestVersion.current) return;
        if (doc.document.module !== selected.module) throw new Error("Saved run does not match the selected experiment.");
        setResult(doc.document);
      } catch (e: unknown) {
        if (active && version === requestVersion.current) setError(e instanceof Error ? e.message : String(e));
      }
    };
    void restore();
    return () => { active = false; };
  }, [runId, selected.module]);

  const run = async () => {
    requestVersion.current += 1;
    setRunId(null);
    setBusy(true); setError(null); setResult(null);
    try {
      let config: Record<string, unknown> = {};
      try {
        config = configText.trim() ? JSON.parse(configText) : {};
      } catch {
        throw new Error("Configuration is not valid JSON.");
      }
      if (config === null || Array.isArray(config) || typeof config !== "object") {
        throw new Error("Configuration must be a JSON object.");
      }
      if (!Number.isSafeInteger(seed) || seed < 0) {
        throw new Error("Seed must be a nonnegative safe integer.");
      }
      const created = await post("/api/experiments", {
        name: `book: ${selected.title}`,
        module: selected.module,
        config, seed,
      });
      const expId = created.experiment_id ?? created.id;
      const runIds: number[] = created.run_ids;
      await post("/api/runs/execute-batch", { run_ids: runIds });
      let finalStatus = "";
      let failureMessage = "Experiment failed.";
      for (let i = 0; i < 600; i++) {
        const exp: any = await get(`/api/experiments/${expId}`);
        const run = (exp.runs ?? []).find(
          (r: any) => r.id === runIds[0]);
        finalStatus = run?.status ?? "";
        failureMessage = run?.error_message ?? failureMessage;
        if (["COMPLETED", "FAILED", "CANCELLED"].includes(finalStatus)) break;
        await new Promise((r) => setTimeout(r, 250));
      }
      if (finalStatus === "FAILED") throw new Error(failureMessage);
      if (finalStatus === "CANCELLED") throw new Error("Experiment was cancelled.");
      if (finalStatus !== "COMPLETED") {
        throw new Error("Run is still pending; inspect its status in Experiments.");
      }
      const doc: any = await get(`/api/runs/${runIds[0]}/result`);
      setResult(doc.document);
      setRunId(runIds[0]);
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
            disabled={busy}
            onChange={(e) => {
              const ex = EXPERIMENTS.find((x) => x.module === e.target.value)!;
              requestVersion.current += 1;
              setRunId(null);
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
        <label className="field">Seed
          <input type="number" min={0} step={1} value={seed}
            disabled={busy} onChange={(e) => setSeed(e.target.valueAsNumber)} />
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
          disabled={busy}
          onChange={(e) => setConfigText(e.target.value)}
          rows={4}
          style={{ width: "100%", maxWidth: 480, fontFamily: "monospace",
                   fontSize: 12 }}
        />
      </label>
      {error && <div className="error-box" role="alert">{error}</div>}
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
          {result.notes?.length > 0 && <ul>
            {result.notes.map((note: string, index: number) => <li key={index}>{note}</li>)}
          </ul>}
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
              result.summary?.validation, null, 2)}</pre>
          </details>
          <details style={{ marginTop: 6 }}>
            <summary className="kv" style={{ cursor: "pointer" }}>
              Artifacts (observables, raw data)
            </summary>
            <pre className="event-log">{JSON.stringify(
              result.artifacts, null, 2)}</pre>
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
