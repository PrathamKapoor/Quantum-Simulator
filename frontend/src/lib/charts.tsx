import { useEffect, useMemo, useRef, useState } from "react";

/** Minimal SVG chart primitives — full control, no heavy dependencies.
 *  Plots always render the actual stored data (directive §266). */

export interface SeriesPoint {
  x: number;
  y: number;
}

export interface Series {
  name: string;
  points: SeriesPoint[];
  color?: string;
  dashed?: boolean;
}

const PALETTE = ["#4aa8ff", "#3fb96f", "#e2a03f", "#e25b5b", "#b07fe0", "#5bc8d6"];

export function LineChart({
  series,
  width = 520,
  height = 260,
  xLabel,
  yLabel,
  title,
  logY = false,
}: {
  series: Series[];
  width?: number;
  height?: number;
  xLabel?: string;
  yLabel?: string;
  title?: string;
  logY?: boolean;
}) {
  const padL = 56, padR = 14, padT = 26, padB = 40;
  const all = series.flatMap((s) => s.points);
  const [hover, setHover] = useState<{ x: number; y: number; label: string } | null>(null);
  if (all.length === 0) {
    return <div className="panel">No data yet — run the experiment first.</div>;
  }
  const xs = all.map((p) => p.x);
  const ysRaw = all.map((p) => (logY ? Math.log10(Math.max(p.y, 1e-9)) : p.y));
  const xmin = Math.min(...xs), xmax = Math.max(...xs);
  let ymin = Math.min(...ysRaw), ymax = Math.max(...ysRaw);
  if (ymax - ymin < 1e-12) { ymax += 0.5; ymin -= 0.5; }
  const spanX = xmax - xmin || 1;
  const spanY = ymax - ymin || 1;

  const sx = (x: number) => padL + ((x - xmin) / spanX) * (width - padL - padR);
  const sy = (y: number) => {
    const yy = logY ? Math.log10(Math.max(y, 1e-9)) : y;
    return height - padB - ((yy - ymin) / spanY) * (height - padT - padB);
  };

  const fmt = (v: number) => {
    if (Math.abs(v) >= 1000 || (Math.abs(v) < 0.001 && v !== 0)) return v.toExponential(1);
    return String(Math.round(v * 10000) / 10000);
  };
  const ticks = useMemo(() => {
    const out: number[] = [];
    for (let i = 0; i <= 4; i++) out.push(ymin + (spanY * i) / 4);
    return out;
  }, [ymin, spanY]);

  return (
    <div>
      {title && (
        <div style={{ fontSize: 12.5, marginBottom: 4, color: "var(--text-dim)" }}>{title}</div>
      )}
      <svg
        width="100%" viewBox={`0 0 ${width} ${height}`} role="img"
        aria-label={title ?? "line chart"} style={{ display: "block" }}
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const rect = (e.target as SVGElement).closest("svg")!.getBoundingClientRect();
          const px = ((e.clientX - rect.left) / rect.width) * width;
          // find nearest point across series
          let best: { d: number; p: SeriesPoint; s: Series } | null = null;
          for (const s of series) for (const p of s.points) {
            const d = Math.abs(sx(p.x) - px);
            if (!best || d < best.d) best = { d, p, s };
          }
          if (best && best.d < 18) {
            setHover({ x: sx(best.p.x), y: sy(best.p.y), label: `${best.s.name}: (${fmt(best.p.x)}, ${fmt(best.p.y)})` });
          } else setHover(null);
        }}
      >
        {/* gridlines */}
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={padL} x2={width - padR} y1={sy(t)} y2={sy(t)} stroke="var(--border)" strokeWidth={0.7} />
            <text x={padL - 6} y={sy(t) + 3.5} textAnchor="end" fontSize={10} fill="var(--text-dim)">
              {logY ? `1e${t.toFixed(1)}` : fmt(t)}
            </text>
          </g>
        ))}
        {/* axes labels */}
        {series[0].points.length > 0 && xs.map(() => null)}
        {[xmin, (xmin + xmax) / 2, xmax].map((v, i) => (
          <text key={i} x={sx(v)} y={height - padB + 16} textAnchor="middle" fontSize={10} fill="var(--text-dim)">
            {fmt(v)}
          </text>
        ))}
        {xLabel && (
          <text x={(padL + width - padR) / 2} y={height - 6} textAnchor="middle" fontSize={11} fill="var(--text-dim)">
            {xLabel}
          </text>
        )}
        {yLabel && (
          <text x={12} y={height / 2} textAnchor="middle" fontSize={11} fill="var(--text-dim)"
                transform={`rotate(-90 12 ${height / 2})`}>
            {yLabel}
          </text>
        )}
        {series.map((s, si) => (
          <polyline
            key={si}
            fill="none"
            stroke={s.color ?? PALETTE[si % PALETTE.length]}
            strokeWidth={1.8}
            strokeDasharray={s.dashed ? "5 4" : undefined}
            points={s.points.map((p) => `${sx(p.x)},${sy(p.y)}`).join(" ")}
          />
        ))}
        {series.map((s, si) =>
          s.points.map((p, pi) => (
            <circle key={`${si}-${pi}`} cx={sx(p.x)} cy={sy(p.y)} r={2.4}
                    fill={s.color ?? PALETTE[si % PALETTE.length]} />
          )),
        )}
        {hover && (
          <g>
            <rect x={Math.min(hover.x + 8, width - 170)} y={hover.y - 24} rx={3}
                  width={160} height={20} fill="var(--bg-raised)" stroke="var(--border)" />
            <text x={Math.min(hover.x + 14, width - 164)} y={hover.y - 10} fontSize={10.5} fill="var(--text)">
              {hover.label}
            </text>
          </g>
        )}
        {/* legend */}
        {series.length > 1 &&
          series.map((s, i) => (
            <g key={`leg-${i}`} transform={`translate(${padL + i * 130}, 12)`}>
              <line x1={0} x2={18} y1={-3} y2={-3} stroke={s.color ?? PALETTE[i % PALETTE.length]} strokeWidth={2.4} />
              <text x={23} y={0.5} fontSize={10.5} fill="var(--text-dim)">{s.name}</text>
            </g>
          ))}
      </svg>
    </div>
  );
}

export function BarChart({
  entries,
  width = 520,
  height = 240,
  title,
  maxBars = 24,
}: {
  entries: [string, number][];
  width?: number;
  height?: number;
  title?: string;
  maxBars?: number;
}) {
  if (entries.length === 0) {
    return <div className="panel">No data yet.</div>;
  }
  const shown = entries.slice(0, maxBars);
  const padL = 34, padB = 30, padT = 22, padR = 8;
  const vmax = Math.max(...shown.map(([, v]) => v), 1e-12);
  const bw = (width - padL - padR) / shown.length;
  return (
    <div>
      {title && <div style={{ fontSize: 12.5, marginBottom: 4, color: "var(--text-dim)" }}>{title}</div>}
      <svg width="100%" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title ?? "bar chart"}>
        {[0, 0.25, 0.5, 0.75, 1].map((f, i) => (
          <g key={i}>
            <line x1={padL} x2={width - padR} y1={height - padB - f * (height - padT - padB)}
                  y2={height - padB - f * (height - padT - padB)} stroke="var(--border)" strokeWidth={0.7} />
            <text x={padL - 5} y={height - padB - f * (height - padT - padB) + 3.5}
                  textAnchor="end" fontSize={10} fill="var(--text-dim)">
              {(vmax * f).toFixed(2)}
            </text>
          </g>
        ))}
        {shown.map(([label, value], i) => {
          const hgt = (value / vmax) * (height - padT - padB);
          return (
            <g key={label}>
              <rect x={padL + i * bw + bw * 0.15} y={height - padB - hgt}
                    width={bw * 0.7} height={hgt} fill="#4aa8ff" rx={2} opacity={0.85}>
                <title>{`${label}: ${value}`}</title>
              </rect>
              <text x={padL + i * bw + bw / 2} y={height - padB + 13}
                    textAnchor="middle" fontSize={9.5} fill="var(--text-dim)"
                    transform={shown.length > 10 ? `rotate(-35 ${padL + i * bw + bw / 2} ${height - padB + 13})` : undefined}>
                {label.length > 9 ? label.slice(0, 8) + "…" : label}
              </text>
            </g>
          );
        })}
        {entries.length > maxBars && (
          <text x={width - padR} y={height - 6} textAnchor="end" fontSize={10} fill="var(--text-dim)">
            showing top {maxBars} of {entries.length} — raw data retained in results
          </text>
        )}
      </svg>
    </div>
  );
}

export function useInterval(callback: () => void, ms: number | null) {
  const ref = useRef(callback);
  ref.current = callback;
  useEffect(() => {
    if (ms === null) return;
    const id = setInterval(() => ref.current(), ms);
    return () => clearInterval(id);
  }, [ms]);
}
