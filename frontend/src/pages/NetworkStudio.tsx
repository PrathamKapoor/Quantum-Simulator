import { useRef, useState } from "react";
import { post } from "../lib/api";

interface NetNode { name: string; type: string; memory_slots: number; x?: number; y?: number }
interface NetLink { source: string; destination: string; distance_km: number; base_fidelity: number }

const DEFAULT_NODES: NetNode[] = [
  { name: "Alice", type: "end", memory_slots: 8, x: 80, y: 150 },
  { name: "R1", type: "repeater", memory_slots: 6, x: 260, y: 90 },
  { name: "R2", type: "repeater", memory_slots: 6, x: 430, y: 200 },
  { name: "Bob", type: "end", memory_slots: 8, x: 600, y: 130 },
];
const DEFAULT_LINKS: NetLink[] = [
  { source: "Alice", destination: "R1", distance_km: 25, base_fidelity: 0.99 },
  { source: "R1", destination: "R2", distance_km: 30, base_fidelity: 0.98 },
  { source: "R2", destination: "Bob", distance_km: 25, base_fidelity: 0.99 },
];

export default function NetworkStudio() {
  const [nodes, setNodes] = useState<NetNode[]>(DEFAULT_NODES);
  const [links, setLinks] = useState<NetLink[]>(DEFAULT_LINKS);
  const [selected, setSelected] = useState<string | null>(null);
  const [linkFrom, setLinkFrom] = useState<string | null>(null);
  const [strategy, setStrategy] = useState("min_expected_time");
  const [simTime, setSimTime] = useState(300);
  const [chaosNodes, setChaosNodes] = useState(0);
  const [result, setResult] = useState<any>(null);
  const [routeInfo, setRouteInfo] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const svgRef = useRef<SVGSVGElement>(null);

  const nodeAt = (name: string | null) => nodes.find((n) => n.name === name);

  const addNode = () => {
    let i = nodes.length;
    let name = `N${i}`;
    while (nodes.some((n) => n.name === name)) name = `N${++i}`;
    setNodes([...nodes, { name, type: "repeater", memory_slots: 6, x: 120 + (i % 4) * 140, y: 100 + ((i * 67) % 160) }]);
  };

  const handleNodeClick = (name: string) => {
    if (linkFrom && linkFrom !== name) {
      if (!links.some((l) =>
        (l.source === linkFrom && l.destination === name) ||
        (l.source === name && l.destination === linkFrom))) {
        setLinks([...links, {
          source: linkFrom, destination: name,
          distance_km: 20 + Math.round(Math.random() * 30),
          base_fidelity: 0.98,
        }]);
      }
      setLinkFrom(null);
    } else {
      setSelected(name === selected ? null : name);
    }
  };

  const startLink = () => setLinkFrom(selected);

  const deleteSelected = () => {
    if (!selected) return;
    setNodes(nodes.filter((n) => n.name !== selected));
    setLinks(links.filter((l) => l.source !== selected && l.destination !== selected));
    setSelected(null);
  };

  const simulate = async () => {
    setBusy(true);
    setError(null);
    try {
      const body = {
        nodes: nodes.map(({ name, type, memory_slots }) => ({ name, type, memory_slots })),
        links,
        requests: [{ source: nodes[0].name, destination: nodes[nodes.length - 1].name }],
        routing_strategy: strategy,
        sim_time_ms: simTime,
        node_failure_rate_per_s: chaosNodes > 0 ? chaosNodes : 0,
        seed: 7,
        trace_mode: "summary",
      };
      setResult(await post("/api/network/simulate", body));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const explainRoute = async () => {
    try {
      const r = await post("/api/network/route", {
        nodes: nodes.map(({ name, type, memory_slots }) => ({ name, type, memory_slots })),
        links,
        requests: [{ source: nodes[0].name, destination: nodes[nodes.length - 1].name }],
        routing_strategy: strategy,
      });
      setRouteInfo(r.routes[0]);
    } catch (e: any) { setError(e.message); }
  };

  // Drag to move nodes.
  const dragRef = useRef<{ name: string; dx: number; dy: number } | null>(null);
  const onSvgMouseMove = (e: React.MouseEvent) => {
    if (!dragRef.current || !svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const scale = 700 / rect.width;
    const x = (e.clientX - rect.left) * scale;
    const y = (e.clientY - rect.top) * scale;
    setNodes((ns) => ns.map((n) =>
      n.name === dragRef.current!.name
        ? { ...n, x: Math.max(30, Math.min(670, x - dragRef.current!.dx)), y: Math.max(30, Math.min(270, y - dragRef.current!.dy)) }
        : n
    ));
  };

  return (
    <div>
      <h1 className="page-title">Network Studio</h1>
      <p className="page-sub">
        Discrete-event quantum network simulator. Drag nodes, connect links, then run
        entanglement requests. Simulated time is logical time — runs are fast regardless
        of the simulated durations.
      </p>

      <div className="row" style={{ marginBottom: 12 }}>
        <button className="btn secondary small" onClick={addNode}>+ Add node</button>
        <button className="btn secondary small" disabled={!selected} onClick={startLink}>
          Link from: {linkFrom ?? "(select a node)"}
        </button>
        <button className="btn secondary small" disabled={!selected} onClick={deleteSelected}>
          Delete selected
        </button>
        <label className="field">Routing strategy
          <select value={strategy} onChange={(e) => setStrategy(e.target.value)}>
            <option value="shortest_path">Shortest path</option>
            <option value="min_loss">Min loss</option>
            <option value="max_fidelity">Max fidelity</option>
            <option value="min_expected_time">Min expected time</option>
            <option value="resource_aware">Resource aware</option>
          </select>
        </label>
        <label className="field">Sim time (ms)
          <input type="number" min={10} max={60000} value={simTime}
                 onChange={(e) => setSimTime(+e.target.value || 100)} style={{ width: 90 }} />
        </label>
        <label className="field">Chaos: node failures/s
          <input type="number" min={0} max={100} value={chaosNodes}
                 onChange={(e) => setChaosNodes(+e.target.value || 0)} style={{ width: 70 }} />
        </label>
        <button className="btn small" onClick={explainRoute}>Explain route</button>
        <button className="btn" disabled={busy} onClick={simulate}>
          {busy ? "Simulating…" : "Run simulation"}
        </button>
      </div>

      {error && <div className="error-box">{error}</div>}

      <div className="netcanvas-wrap panel" style={{ padding: 0 }}>
        <svg ref={svgRef} viewBox="0 0 700 300" width="100%" style={{ display: "block", background: "var(--bg)" }}
             onMouseMove={onSvgMouseMove}
             onMouseUp={() => (dragRef.current = null)}
             onMouseLeave={() => (dragRef.current = null)}>
          {/* links */}
          {links.map((l, i) => {
            const a = nodeAt(l.source), b = nodeAt(l.destination);
            if (a?.x == null || a.y == null || b?.x == null || b.y == null) return null;
            const down = result?.outcomes && false;
            return (
              <g key={i}>
                <line x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                      stroke={down ? "var(--bad)" : "var(--accent-dim)"} strokeWidth={2}
                      strokeDasharray={down ? "5 5" : undefined} />
                <text x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 - 6} textAnchor="middle"
                      fontSize={10} fill="var(--text-dim)">
                  {l.distance_km} km · F≈{l.base_fidelity}
                </text>
              </g>
            );
          })}
          {/* nodes */}
          {nodes.map((n) => (
            <g key={n.name}
               transform={`translate(${n.x},${n.y})`}
               style={{ cursor: "grab" }}
               onMouseDown={(e) => {
                 e.stopPropagation();
                 const rect = svgRef.current!.getBoundingClientRect();
                 const scale = 700 / rect.width;
                 dragRef.current = {
                   name: n.name,
                   dx: (e.clientX - rect.left) * scale - n.x!,
                   dy: (e.clientY - rect.top) * scale - n.y!,
                 };
               }}
               onClick={() => handleNodeClick(n.name)}>
              <circle r={17} fill="var(--bg-raised)"
                      stroke={selected === n.name ? "#e2a03f" : n.type === "end" ? "#4aa8ff" : "#3fb96f"}
                      strokeWidth={2.2} />
              <circle r={17} fill="transparent" stroke="var(--border)" strokeWidth={0} />
              <text y={4} textAnchor="middle" fontSize={9} fill="var(--text)">
                M{String(n.memory_slots).padStart(2, "0")}
              </text>
              <text y={32} textAnchor="middle" fontSize={11.5} fill="var(--text)">{n.name}</text>
            </g>
          ))}
        </svg>
      </div>

      {selected && (() => {
        const n = nodeAt(selected)!;
        const conn = links.filter((l) => l.source === selected || l.destination === selected);
        return (
          <div className="panel" style={{ marginTop: 12 }}>
            <h3>Inspector: {n.name}</h3>
            <div className="kv">
              Type: <b>{n.type}</b> · Memory slots: <b>{n.memory_slots}</b> · Connections: <b>{conn.length}</b>
            </div>
          </div>
        );
      })()}

      {routeInfo && (
        <div className="panel">
          <h3>Route explanation</h3>
          <p className="kv">{routeInfo.explanation ?? "No route available."}</p>
        </div>
      )}

      {result && (
        <>
          <div className="metric-cards">
            <Metric label="Requests" value={`${result.success_count + result.failure_count}`} />
            <Metric label="Successes" value={String(result.success_count)} />
            <Metric label="Failures" value={String(result.failure_count)} />
            <Metric label="Avg fidelity" value={result.avg_fidelity ? result.avg_fidelity.toFixed(4) : "—"} />
            <Metric label="Swaps" value={String(result.stats.swaps_performed)} />
            <Metric label="Events" value={String(result.stats.events_processed)} />
            <Metric label="Sim time" value={`${(result.sim_time_ns / 1e6).toFixed(1)} ms`} />
          </div>
          <div className="grid2">
            <div className="panel">
              <h3>Request outcomes</h3>
              <table className="data-table">
                <thead><tr><th>#</th><th>Path</th><th>OK</th><th>Fidelity</th><th>Reason</th></tr></thead>
                <tbody>
                  {result.outcomes.map((o: any) => (
                    <tr key={o.request_id}>
                      <td>{o.request_id}</td>
                      <td>{o.route ? o.route.join(" → ") : `${o.source}→${o.destination}`}</td>
                      <td><span className={"badge " + (o.success ? "ok" : "err")}>{o.success ? "yes" : "no"}</span></td>
                      <td>{o.fidelity != null ? o.fidelity.toFixed(4) : "—"}</td>
                      <td>{o.failure_reason ?? ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="panel">
              <h3>Event log</h3>
              <div className="event-log">{result.event_log.join("\n")}</div>
            </div>
          </div>
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
