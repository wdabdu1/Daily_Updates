interface Series {
  label: string;
  color: string;
  points: { x: string; y: number }[];
}

/** Minimal dependency-free line chart. Not trying to be a full charting
 * library -- just enough to visually compare a couple of series (FX rate
 * types, or a cover gap trend) over a date range without pulling in a
 * heavy dependency for Phase 4. */
export function LineChart({ series, height = 260 }: { series: Series[]; height?: number }) {
  const width = 900;
  const padding = { top: 16, right: 16, bottom: 28, left: 64 };
  const allXs = Array.from(new Set(series.flatMap((s) => s.points.map((p) => p.x)))).sort();
  const allYs = series.flatMap((s) => s.points.map((p) => p.y));

  if (allXs.length === 0 || allYs.length === 0) {
    return <div className="empty-state">Not enough data to chart yet.</div>;
  }

  const minY = Math.min(0, ...allYs);
  const maxY = Math.max(...allYs);
  const yRange = maxY - minY || 1;

  const innerW = width - padding.left - padding.right;
  const innerH = height - padding.top - padding.bottom;

  const xIndex = new Map(allXs.map((x, i) => [x, i]));
  const xScale = (x: string) =>
    padding.left + (allXs.length <= 1 ? 0 : (xIndex.get(x)! / (allXs.length - 1)) * innerW);
  const yScale = (y: number) => padding.top + innerH - ((y - minY) / yRange) * innerH;

  const zeroY = yScale(0);

  const tickCount = Math.min(6, allXs.length);
  const tickIdxs = Array.from({ length: tickCount }, (_, i) =>
    Math.round((i / Math.max(1, tickCount - 1)) * (allXs.length - 1))
  );

  return (
    <div style={{ overflowX: "auto" }}>
      <svg viewBox={`0 0 ${width} ${height}`} style={{ width: "100%", height }}>
        <line
          x1={padding.left}
          y1={zeroY}
          x2={width - padding.right}
          y2={zeroY}
          stroke="var(--color-border)"
          strokeWidth={1}
        />
        {tickIdxs.map((i) => (
          <text
            key={i}
            x={xScale(allXs[i])}
            y={height - 6}
            fontSize={11}
            fill="var(--color-text-muted)"
            textAnchor="middle"
          >
            {allXs[i]}
          </text>
        ))}
        {[minY, (minY + maxY) / 2, maxY].map((v, i) => (
          <text
            key={i}
            x={padding.left - 8}
            y={yScale(v) + 4}
            fontSize={11}
            fill="var(--color-text-muted)"
            textAnchor="end"
          >
            {v.toLocaleString("en-US", { maximumFractionDigits: 1 })}
          </text>
        ))}
        {series.map((s) => {
          const pts = s.points.filter((p) => xIndex.has(p.x));
          if (pts.length === 0) return null;
          const d = pts
            .map((p, i) => `${i === 0 ? "M" : "L"} ${xScale(p.x)} ${yScale(p.y)}`)
            .join(" ");
          return <path key={s.label} d={d} fill="none" stroke={s.color} strokeWidth={2} />;
        })}
      </svg>
      <div style={{ display: "flex", gap: "1.25rem", flexWrap: "wrap", marginTop: "0.5rem" }}>
        {series.map((s) => (
          <div key={s.label} style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.85rem" }}>
            <span style={{ width: 12, height: 12, borderRadius: 2, background: s.color, display: "inline-block" }} />
            <span className="muted">{s.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
