import { useState } from "react";
import { post } from "../lib/api";
import { LineChart, BarChart } from "../lib/charts";

export default function OptimizeLab() {
  const [vqe, setVqe] = useState<any>(null);
  const [qaoa, setQaoa] = useState<any>(null);
  const [curve, setCurve] = useState<any>(null);
  const [qml, setQml] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const call = async (key: string, setter: (v: any) => void, path: string, body: any) => {
    setBusy(key); setError(null);
    try { setter(await post(path, body)); }
    catch (e: any) { setError(e.message + (e.suggestion ? `\nTry: ${e.suggestion}` : "")); }
    finally { setBusy(null); }
  };

  return (
    <div>
      <h1 className="page-title">Optimization & Quantum Machine Learning</h1>
      <p className="page-sub">
        VQE and QAOA with classical optimizers on the noiseless statevector engine,
        compared against exact classical baselines. Approximation ratios are reported
        honestly — no quantum-advantage claims.
      </p>

      {error && <div className="error-box">{error}</div>}

      <div className="grid2">
        <div className="panel">
          <h3>VQE — variational eigensolver</h3>
          <div className="row">
            <label className="field">System
              <select id="vqe-system">
                <option value="h2">H2 molecule (2-qubit effective model)</option>
                <option value="tfim">Transverse-field Ising</option>
              </select>
            </label>
            <button className="btn" disabled={busy !== null}
                    onClick={() => {
                      const system = (document.getElementById("vqe-system") as HTMLSelectElement).value;
                      call("vqe", setVqe, "/api/optimize/vqe", {
                        system, bond_length_angstrom: 0.735, max_iter: 150, seed: 1,
                      });
                    }}>
              Run VQE
            </button>
          </div>
          {vqe && (
            <>
              <div className="kv" style={{ margin: "10px 0" }}>
                E(VQE) = <b>{vqe.estimated_energy.toFixed(6)}</b>
                {vqe.exact_energy != null && (
                  <> · E(exact) = <b>{vqe.exact_energy.toFixed(6)}</b> · error <b>{vqe.error?.toExponential(2)}</b></>
                )}
              </div>
              <LineChart title="Energy convergence" xLabel="iteration" yLabel="energy"
                         series={[{ name: "best energy",
                           points: vqe.energy_history.map((y: number, x: number) => ({ x, y })) }]} />
            </>
          )}
        </div>

        <div className="panel">
          <h3>QAOA — MaxCut</h3>
          <p style={{ fontSize: 12.5, color: "var(--text-dim)" }}>Square graph preset; optimum cut = 4.</p>
          <button className="btn" disabled={busy !== null}
                  onClick={() => call("qaoa", setQaoa, "/api/optimize/qaoa", {
                    edges: [[0, 1], [1, 2], [2, 3], [3, 0]], n_nodes: 4, p_layers: 2,
                  })}>
            Run QAOA
          </button>
          {qaoa && (
            <>
              <div className="metric-cards" style={{ marginTop: 10 }}>
                <Metric label="QAOA cut" value={String(qaoa.best_cut_value)} />
                <Metric label="Exact optimum" value={String(qaoa.exact_optimum)} />
                <Metric label="Ratio" value={qaoa.approximation_ratio.toFixed(3)} />
              </div>
              <BarChart entries={qaoa.probability_distribution_top.map(([b, p]: any) => [b, p])}
                        title="Most likely states after QAOA" />
              <ul className="note-list">{qaoa.notes.map((n: string, i: number) => <li key={i}>{n}</li>)}</ul>
            </>
          )}
        </div>
      </div>

      <div className="panel">
        <h3>H2 dissociation curve</h3>
        <button className="btn" disabled={busy !== null}
                onClick={() => call("h2", setCurve, "/api/optimize/h2-curve", {
                  lengths: [0.35, 0.5, 0.65, 0.735, 0.9, 1.1], seed: 0,
                })}>
          Compute curve (8 VQE runs)
        </button>
        {curve && (
          <LineChart
            title="Energy vs bond length (effective 2-qubit model, Hartree)"
            xLabel="bond length (Å)" yLabel="energy"
            series={[
              { name: "VQE", points: curve.points.map((p: any) => ({ x: p.bond_length_angstrom, y: p.vqe_hartree })) },
              { name: "exact", points: curve.points.map((p: any) => ({ x: p.bond_length_angstrom, y: p.exact_hartree })) },
            ]}
          />
        )}
      </div>

      <div className="panel">
        <h3>Variational quantum classifier</h3>
        <div className="row">
          <select id="qml-ds">
            <option value="blobs">Gaussian blobs</option>
            <option value="circles">Concentric circles</option>
            <option value="iris">Iris sample</option>
          </select>
          <button className="btn" disabled={busy !== null}
                  onClick={() => call("qml", setQml, "/api/optimize/qml", {
                    dataset: (document.getElementById("qml-ds") as HTMLSelectElement).value,
                    max_iter: 60, compare_noisy: true,
                  })}>
            Train + evaluate (ideal vs noisy)
          </button>
        </div>
        {qml && (
          <>
            <div className="metric-cards" style={{ marginTop: 10 }}>
              <Metric label="Ideal accuracy" value={(qml.ideal_metrics.accuracy * 100).toFixed(1) + "%"} />
              {qml.noisy_metrics && (
                <Metric label="Noisy accuracy" value={(qml.noisy_metrics.accuracy * 100).toFixed(1) + "%"} />
              )}
            </div>
            <LineChart title="Training loss" xLabel="iteration" yLabel="loss"
                       series={[{ name: "ideal",
                         points: qml.loss_history.map((y: number, x: number) => ({ x, y })) }]}/>
            {qml.noisy_metrics && (
              <table className="data-table">
                <thead><tr><th>Metric</th><th>Ideal</th><th>Noisy</th></tr></thead>
                <tbody>
                  {["accuracy", "precision", "recall", "f1"].map((m) => (
                    <tr key={m}>
                      <td>{m}</td>
                      <td>{(qml.ideal_metrics[m] * 100).toFixed(1)}%</td>
                      <td>{(qml.noisy_metrics[m] * 100).toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <ul className="note-list">{qml.notes.map((n: string, i: number) => <li key={i}>{n}</li>)}</ul>
          </>
        )}
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
