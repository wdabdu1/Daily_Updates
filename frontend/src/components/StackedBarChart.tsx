import { useState } from "react";
import { formatSDG } from "../format";

export interface StackedBarSlice {
  label: string;
  amount: number;
  color: string;
}

export interface StackedBarSpec {
  key: string;
  label: string;
  // Empty slices renders a single flat-colored bar using `total`/`soloColor`
  // instead (e.g. the Gap bar, which isn't a stack of anything).
  slices: StackedBarSlice[];
  total: number;
  totalLabel?: string;
  // Text color for the total figure above the bar, and fill color when
  // `slices` is empty -- lets the Gap bar go red/green by sign while
  // Receivables/Dues keep their categorical stack colors.
  soloColor?: string;
}

/** Minimal dependency-free stacked bar chart -- same no-external-library
 * approach as LineChart. Renders N bars side by side, each either a stack
 * of colored slices (Receivables by Division, Dues by Bank) or a single
 * flat bar (the Gap). A bold total sits above each bar; a per-slice hover
 * tooltip and a legend/detail list beneath satisfy the relief rule for the
 * palette's sub-3:1 slots (aqua/yellow/magenta) -- values are always
 * readable as text, never color-only. */
export function StackedBarChart({ bars, height = 320 }: { bars: StackedBarSpec[]; height?: number }) {
  const [hover, setHover] = useState<{
    x: number;
    y: number;
    bar: string;
    slice: string;
    amount: number;
    pct: number;
  } | null>(null);

  const barWidth = 108;
  const padding = { top: 60, right: 60, bottom: 36, left: 60 };
  const gapBetween = 64;
  const innerH = height - padding.top - padding.bottom;
  const width =
    padding.left + padding.right + bars.length * barWidth + Math.max(0, bars.length - 1) * gapBetween;

  const maxTotal = Math.max(1, ...bars.map((b) => Math.abs(b.total)));
  const scale = (v: number) => (Math.abs(v) / maxTotal) * innerH;
  const baseline = height - padding.bottom;

  return (
    <div style={{ position: "relative" }}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        style={{ width: "100%", height, maxWidth: width, overflow: "visible" }}
      >
        <line x1={padding.left} y1={baseline} x2={width - padding.right} y2={baseline} stroke="var(--color-border)" strokeWidth={1} />
        {bars.map((bar, bi) => {
          const x = padding.left + bi * (barWidth + gapBetween);
          const segs: (StackedBarSlice & { isSolo?: boolean })[] =
            bar.slices.length > 0
              ? bar.slices
              : [{ label: bar.label, amount: bar.total, color: bar.soloColor || "var(--color-text-muted)", isSolo: true }];

          let y = baseline;
          const rects = segs.map((s, si) => {
            const segH = scale(s.amount);
            const top = y - segH;
            const isTop = si === segs.length - 1;
            y = top;
            const pct = bar.total !== 0 ? (Math.abs(s.amount) / Math.abs(bar.total)) * 100 : 0;
            return (
              <rect
                key={s.label}
                x={x}
                y={top}
                width={barWidth}
                height={Math.max(0, segH)}
                fill={s.color}
                rx={isTop ? 4 : 0}
                stroke={segs.length > 1 ? "var(--color-bg)" : "none"}
                strokeWidth={segs.length > 1 ? 2 : 0}
                onMouseEnter={(e) => {
                  const rect = (e.target as SVGRectElement).getBoundingClientRect();
                  setHover({ x: rect.left + rect.width / 2, y: rect.top, bar: bar.label, slice: s.label, amount: s.amount, pct });
                }}
                onMouseLeave={() => setHover(null)}
              />
            );
          });

          const labelLines = (bar.totalLabel ?? formatSDG(bar.total)).split("\n");
          return (
            <g key={bar.key}>
              <text
                x={x + barWidth / 2}
                y={padding.top - 16 - (labelLines.length - 1) * 15}
                textAnchor="middle"
                fontSize={14}
                fontWeight={700}
                fill={bar.soloColor || "var(--color-navy)"}
              >
                {labelLines.map((line, li) => (
                  <tspan key={li} x={x + barWidth / 2} dy={li === 0 ? 0 : 16}>
                    {line}
                  </tspan>
                ))}
              </text>
              {rects}
              <text x={x + barWidth / 2} y={height - padding.bottom + 22} textAnchor="middle" fontSize={12} fill="var(--color-text-muted)">
                {bar.label}
              </text>
            </g>
          );
        })}
      </svg>
      {hover && (
        <div
          style={{
            position: "fixed",
            left: hover.x,
            top: hover.y - 10,
            transform: "translate(-50%, -100%)",
            background: "var(--color-navy)",
            color: "#fff",
            padding: "0.4rem 0.65rem",
            borderRadius: 6,
            fontSize: 12,
            pointerEvents: "none",
            whiteSpace: "nowrap",
            zIndex: 20,
            boxShadow: "0 4px 14px rgba(0,0,0,0.2)",
          }}
        >
          <strong>{hover.slice}</strong> — {formatSDG(hover.amount)} ({hover.pct.toFixed(1)}%)
        </div>
      )}
    </div>
  );
}
