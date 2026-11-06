// Final ranks across editions (lower is better, so rank 1 is at the top). Editions without a
// result are gaps in the line, never rank 0. The table under it carries the same data as text.
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

export interface RankPoint { label: string; rank: number | null; entrants: number }

const H = 200, PAD = { top: 12, right: 12, bottom: 28, left: 32 };

export default function RankChart({ points }: { points: RankPoint[] }) {
  const { t } = useTranslation();
  // Drawn at the real width so the axis text stays at its CSS size on a phone
  const box = useRef<HTMLDivElement>(null);
  const [W, setW] = useState(640);
  useEffect(() => {
    const ro = new ResizeObserver(([e]) => setW(Math.max(240, Math.round(e.contentRect.width))));
    if (box.current) ro.observe(box.current);
    return () => ro.disconnect();
  }, []);
  // Enough labels to read the axis, never overlapping (about 7px per character at 12px)
  const labelWidth = Math.max(...points.map((p) => p.label.length)) * 7 + 16;
  const labelEvery = Math.max(1, Math.ceil((points.length * labelWidth) / (W - PAD.left - PAD.right)));
  const max = Math.max(3, ...points.map((p) => p.rank ?? 0));
  const x = (i: number) => PAD.left + (points.length > 1 ? (i / (points.length - 1)) * (W - PAD.left - PAD.right) : 0);
  const y = (rank: number) => PAD.top + ((rank - 1) / (max - 1)) * (H - PAD.top - PAD.bottom);
  // One path segment per run of editions with a rank
  const path = points.map((p, i) => (p.rank === null ? "" : `${i && points[i - 1].rank !== null ? "L" : "M"}${x(i)},${y(p.rank)}`)).join("");
  const ticks = [...new Set([1, Math.ceil(max / 2), max])];
  return (
    <figure className="chart">
      <div ref={box}>
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={t("standings.rank")}>
        {ticks.map((r) => (
          <g key={r}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(r)} y2={y(r)} stroke="var(--line)" />
            <text x={PAD.left - 8} y={y(r)} dy="0.35em" textAnchor="end" className="chart-tick">{r}</text>
          </g>
        ))}
        {points.map((p, i) => (i % labelEvery === 0 || i === points.length - 1) && (i === points.length - 1 || points.length - 1 - i >= labelEvery) && (
          <text key={p.label} x={x(i)} y={H - 8} textAnchor={i === 0 ? "start" : i === points.length - 1 ? "end" : "middle"} className="chart-tick">{p.label}</text>
        ))}
        <path d={path} fill="none" stroke="var(--accent)" strokeWidth={2} strokeLinejoin="round" />
        {points.map((p, i) => p.rank !== null && (
          <circle key={p.label} cx={x(i)} cy={y(p.rank)} r={4} fill="var(--accent)"><title>{`${p.label}: ${p.rank}`}</title></circle>
        ))}
      </svg>
      </div>
      <details>
        <summary>{t("chart.asTable")}</summary>
        <table className="list compact">
          <thead><tr><th scope="col">{t("archive.edition")}</th><th scope="col" className="num">{t("standings.rank")}</th><th scope="col" className="num">{t("archive.entrants")}</th></tr></thead>
          <tbody>{points.map((p) => <tr key={p.label}><td>{p.label}</td><td className="num">{p.rank ?? "—"}</td><td className="num">{p.entrants}</td></tr>)}</tbody>
        </table>
      </details>
    </figure>
  );
}
