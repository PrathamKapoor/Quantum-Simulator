import { useState } from "react";
import { post } from "../lib/api";

export default function Protocols() {
  const [bb84, setBb84] = useState<any>(null);
  const [e91, setE91] = useState<any>(null);
  const [chsh, setChsh] = useState<any>(null);
  const [qrng, setQrng] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const call = async (setter: (v: any) => void, path: string, body: any) => {
    setBusy(true); setError(null);
    try { setter(await post(path, body)); }
    catch (e: any) { setError(e.message + (e.suggestion ? `\nTry: ${e.suggestion}` : "")); }
    finally { setBusy(false); }
  };

  return (
    <div>
      <h1 className="page-title">Quantum Cryptography & Communication</h1>
      <p className="page-sub">
        Protocol simulators for study and experimentation. These demonstrate protocol
        mechanics and statistics — they provide no production security or certified
        randomness.
      </p>

      {error && <div className="error-box">{error}</div>}

      <div className="grid2">
        <div className="panel">
          <h3>BB84 key distribution</h3>
          <p style={{ fontSize: 12.5, color: "var(--text-dim)" }}>
            Run twice — with and without Eve — and compare the QBER. Intercept-resend
            drives QBER toward ≈25% of sifted bits.
          </p>
          <BB84Form busy={busy} onRun={(body: any) => call(setBb84, "/api/protocols/bb84", body)} />
          {bb84 && (
            <>
              <div className="kv" style={{ marginTop: 8 }}>
                QBER: <b>{(bb84.qber * 100).toFixed(2)}%</b> · Eve present:{" "}
                <span className={"badge " + (bb84.eve_present ? "err" : "ok")}>
                  {bb84.eve_present ? "yes" : "no"}
                </span>
                <br />Sifted bits: {bb84.sifted_bits} · sample: {bb84.sample_size}
              </div>
              <ul className="note-list">{bb84.notes.map((n: string, i: number) => <li key={i}>{n}</li>)}</ul>
            </>
          )}
        </div>

        <div className="panel">
          <h3>E91 entanglement-based QKD</h3>
          <E91Form busy={busy} onRun={(body: any) => call(setE91, "/api/protocols/e91", body)} />
          {e91 && (
            <>
              <div className="kv" style={{ marginTop: 8 }}>
                CHSH S = <b>{e91.chsh_statistic.toFixed(3)}</b> · classical bound 2.0 · quantum 2√2 ≈ 2.828
                <br />
                <span className={"badge " + (e91.violates_classical ? "ok" : "warn")}>
                  {e91.violates_classical ? "violates classical bound" : "no violation"}
                </span>{" "}
                · key bits: {e91.key_length} · agreement {(e91.key_agreement * 100).toFixed(1)}%
              </div>
            </>
          )}
        </div>

        <div className="panel">
          <h3>CHSH / Bell test</h3>
          <ChshForm busy={busy} onRun={(body: any) => call(setChsh, "/api/protocols/chsh", body)} />
          {chsh && (
            <>
              <table className="data-table" style={{ marginTop: 8 }}>
                <tbody>
                  {Object.entries(chsh.correlations).map(([k, v]: any) => (
                    <tr key={k}><td>{k}</td><td>{Number(v).toFixed(4)}</td></tr>
                  ))}
                  <tr><td><b>S</b></td><td><b>{chsh.chsh_S.toFixed(4)}</b></td></tr>
                </tbody>
              </table>
              <p className="kv" style={{ marginTop: 6 }}>
                |S| &gt; 2 violates local realism's bound; quantum maximum is 2√2.
                Statistical noise ~2/√N per setting pair.
              </p>
            </>
          )}
        </div>

        <div className="panel">
          <h3>QRNG (simulated device)</h3>
          <button className="btn" disabled={busy}
                  onClick={() => call(setQrng, "/api/protocols/qrng", { n_bits: 8192 })}>
            Generate 8192 bits
          </button>
          {qrng && (
            <>
              <div className="kv" style={{ marginTop: 8 }}>
                Fraction of ones: <b>{qrng.fraction_of_ones.toFixed(4)}</b> · runs z-score:{" "}
                <b>{qrng.runs_test_z_score.toFixed(3)}</b>{" "}
                <span className={"badge " + (qrng.runs_test_passes_5pct ? "ok" : "warn")}>
                  {qrng.runs_test_passes_5pct ? "passes runs test" : "fails runs test"}
                </span>
              </div>
              <pre className="event-log">{qrng.bits_preview}…</pre>
              <p style={{ fontSize: 12, color: "var(--text-dim)" }}>{qrng.disclaimer}</p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function BB84Form({ busy, onRun }: any) {
  const [eve, setEve] = useState(0);
  const [n, setN] = useState(512);
  return (
    <div className="row">
      <label className="field">Signal qubits
        <input type="number" min={16} max={20000} value={n}
               onChange={(e) => setN(+e.target.value || 512)} />
      </label>
      <label className="field">Eve intercept probability
        <input type="number" min={0} max={1} step={0.05} value={eve}
               onChange={(e) => setEve(+e.target.value)} />
      </label>
      <button className="btn" disabled={busy}
              onClick={() => onRun({ n_qubits: n, eve_intercept_probability: eve, seed: Math.floor(Math.random() * 1e6) })}>
        Run BB84
      </button>
    </div>
  );
}

function E91Form({ busy, onRun }: any) {
  const [vis, setVis] = useState(1);
  return (
    <div className="row">
      <label className="field">Source visibility (0–1)
        <input type="number" min={0} max={1} step={0.05} value={vis}
               onChange={(e) => setVis(+e.target.value)} />
      </label>
      <button className="btn" disabled={busy}
              onClick={() => onRun({ n_pairs: 4000, noise_correlation_factor: vis, seed: 9 })}>
        Run E91
      </button>
    </div>
  );
}

function ChshForm({ busy, onRun }: any) {
  const [f, setF] = useState(1);
  return (
    <div className="row">
      <label className="field">Source fidelity
        <input type="number" min={0.25} max={1} step={0.05} value={f}
               onChange={(e) => setF(+e.target.value)} />
      </label>
      <button className="btn" disabled={busy}
              onClick={() => onRun({ state_fidelity: f, shots_per_setting: 5000, seed: 4 })}>
        Test Bell inequality
      </button>
    </div>
  );
}
