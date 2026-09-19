"use client";
/* ==========================================================================
   369 Mart admin — charts (plain SVG, no library)
   Palette: brand blue #0a78ab · orange #f7931e · green #1a7f3c · violet #7b5cd6
   (validated: lightness band, chroma, CVD separation, normal-vision floor;
   orange sits under 3:1 on white, so every series is also direct-labelled or
   named in the legend — never colour alone.)
   Every chart: recessive grid, thin marks, one y axis, hover crosshair /
   per-mark tooltip, and a table fallback behind "Data".
   ========================================================================== */
import { useMemo, useRef, useState } from "react";
import { inr, inrShort } from "./adminData";

export const SERIES = ["#0a78ab", "#f7931e", "#1a7f3c", "#7b5cd6"];

function useHover() {
  const [hit, setHit] = useState(null);
  return [hit, setHit];
}

/* ---------------- lines + area (revenue by day, 2 series) ---------------- */
export function LineChart({ rows, series, fmt = inr, height = 210 }) {
  const [hit, setHit] = useHover();
  const wrap = useRef(null);
  const W = 720, H = height, pad = { l: 46, r: 14, t: 12, b: 24 };
  const max = Math.max(1, ...rows.flatMap((r) => series.map((s) => r[s.key])));
  const top = Math.ceil(max / 500) * 500;
  const x = (i) => pad.l + (i * (W - pad.l - pad.r)) / Math.max(1, rows.length - 1);
  const y = (v) => H - pad.b - (v / top) * (H - pad.t - pad.b);
  const path = (key) => rows.map((r, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(r[key]).toFixed(1)}`).join(" ");
  const area = (key) => `${path(key)} L${x(rows.length - 1)} ${H - pad.b} L${pad.l} ${H - pad.b} Z`;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(top * f));

  const move = (e) => {
    const r = wrap.current.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    const i = Math.max(0, Math.min(rows.length - 1, Math.round(((px - pad.l) / (W - pad.l - pad.r)) * (rows.length - 1))));
    setHit(i);
  };
  return (
    <div className="ad-chart" ref={wrap} onPointerMove={move} onPointerLeave={() => setHit(null)}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Revenue by day">
        <defs>
          {series.map((s, k) => (
            <linearGradient key={s.key} id={`adg${k}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={s.color} stopOpacity="0.22" /><stop offset="100%" stopColor={s.color} stopOpacity="0" />
            </linearGradient>
          ))}
        </defs>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} className="ad-grid" />
            <text x={pad.l - 8} y={y(t) + 4} className="ad-axis" textAnchor="end">{inrShort(t)}</text>
          </g>
        ))}
        {rows.map((r, i) => (i % 2 === 0 || i === rows.length - 1) && (
          <text key={r.label} x={x(i)} y={H - 6} className="ad-axis" textAnchor="middle">{r.short}</text>
        ))}
        {series.map((s, k) => <path key={s.key + "a"} d={area(s.key)} fill={`url(#adg${k})`} />)}
        {series.map((s) => <path key={s.key} d={path(s.key)} fill="none" stroke={s.color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" className="ad-line" />)}
        {hit != null && (
          <g>
            <line x1={x(hit)} x2={x(hit)} y1={pad.t} y2={H - pad.b} className="ad-cross" />
            {series.map((s) => <circle key={s.key} cx={x(hit)} cy={y(rows[hit][s.key])} r="5" fill="#fff" stroke={s.color} strokeWidth="2.5" />)}
          </g>
        )}
      </svg>
      {hit != null && (
        <div className="ad-tip" style={{ left: `${(x(hit) / W) * 100}%`, top: `${(Math.min(...series.map((s) => y(rows[hit][s.key]))) / H) * 100}%` }}>
          <b>{rows[hit].label}</b>
          {series.map((s) => (
            <span key={s.key}><i style={{ background: s.color }} />{s.label}<em>{fmt(rows[hit][s.key])}</em></span>
          ))}
          <span className="ad-tip-sub">{rows[hit].orders} orders</span>
        </div>
      )}
    </div>
  );
}

/* ---------------- bars (orders per hour) ---------------- */
export function BarChart({ rows, color = SERIES[0], height = 190, fmt = (v) => v, label = "Orders per hour" }) {
  const [hit, setHit] = useHover();
  const W = 720, H = height, pad = { l: 34, r: 8, t: 12, b: 22 };
  const max = Math.max(1, ...rows.map((r) => r.value));
  const top = Math.max(4, Math.ceil(max / 4) * 4);
  const bw = (W - pad.l - pad.r) / rows.length;
  const y = (v) => H - pad.b - (v / top) * (H - pad.t - pad.b);
  return (
    <div className="ad-chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
        {[0, 0.5, 1].map((f) => (
          <g key={f}>
            <line x1={pad.l} x2={W - pad.r} y1={y(top * f)} y2={y(top * f)} className="ad-grid" />
            <text x={pad.l - 8} y={y(top * f) + 4} className="ad-axis" textAnchor="end">{Math.round(top * f)}</text>
          </g>
        ))}
        {rows.map((r, i) => {
          const h = Math.max(r.value ? 3 : 0, H - pad.b - y(r.value));
          return (
            <g key={r.label} onPointerEnter={() => setHit(i)} onPointerLeave={() => setHit(null)}>
              <rect x={pad.l + i * bw} y={pad.t} width={bw} height={H - pad.t - pad.b} fill="transparent" />
              <rect x={pad.l + i * bw + 3} y={H - pad.b - h} width={Math.max(2, bw - 6)} height={h} rx="4" fill={color} opacity={hit == null || hit === i ? 1 : 0.55} className="ad-bar" style={{ "--i": i }} />
              {i % 2 === 0 && <text x={pad.l + i * bw + bw / 2} y={H - 6} className="ad-axis" textAnchor="middle">{r.label}</text>}
            </g>
          );
        })}
      </svg>
      {hit != null && (
        <div className="ad-tip" style={{ left: `${((pad.l + hit * bw + bw / 2) / W) * 100}%`, top: `${(y(rows[hit].value) / H) * 100}%` }}>
          <b>{rows[hit].full || rows[hit].label}</b><span><em>{fmt(rows[hit].value)}</em></span>
        </div>
      )}
    </div>
  );
}

/* ---------------- horizontal bars with direct labels (category sales) ---- */
export function RankBars({ rows, color = SERIES[2], fmt = inr }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <ul className="ad-rank">
      {rows.map((r, i) => (
        <li key={r.label} style={{ "--i": i }}>
          <span className="ad-rank-l">{r.label}</span>
          <span className="ad-rank-bar"><i style={{ "--w": (r.value / max) * 100 + "%", background: color }} /></span>
          <b>{fmt(r.value)}</b>
        </li>
      ))}
    </ul>
  );
}

/* ---------------- sparkline for stat tiles ---------------- */
export function Spark({ values, color = SERIES[0] }) {
  const d = useMemo(() => {
    const max = Math.max(...values), min = Math.min(...values), span = max - min || 1;
    return values.map((v, i) => `${i ? "L" : "M"}${(i / (values.length - 1)) * 100} ${26 - ((v - min) / span) * 22}`).join(" ");
  }, [values]);
  return (
    <svg className="ad-spark" viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true">
      <path d={`${d} L100 30 L0 30 Z`} fill={color} opacity="0.12" />
      <path d={d} fill="none" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/* ---------------- legend + data table fallback ---------------- */
export function Legend({ series }) {
  return (
    <div className="ad-legend">
      {series.map((s) => <span key={s.label}><i style={{ background: s.color }} />{s.label}</span>)}
    </div>
  );
}

export function DataTable({ head, rows }) {
  return (
    <div className="ad-datatable">
      <table>
        <thead><tr>{head.map((h) => <th key={h}>{h}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, k) => <td key={k}>{c}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}
