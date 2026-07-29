import { useMemo } from "react";
import { num } from "@/lib/format";

/**
 * Small dependency-free donut chart. Deterministic SVG so it always renders.
 * slices: [{ name, value, color }]
 */
export const DonutChart = ({ slices, size = 168, thickness = 22, centerLabel, centerValue }) => {
  const total = (slices || []).reduce((a, s) => a + (s.value || 0), 0);
  const radius = (size - thickness) / 2;
  const circumference = 2 * Math.PI * radius;

  const segments = useMemo(() => {
    let offset = 0;
    return (slices || []).map((s) => {
      const fraction = total > 0 ? s.value / total : 0;
      const length = fraction * circumference;
      const seg = { ...s, length, offset, fraction };
      offset += length;
      return seg;
    });
  }, [slices, total, circumference]);

  if (!slices || slices.length === 0 || total === 0) {
    return (
      <div
        className="flex items-center justify-center rounded-xl border border-dashed border-border bg-secondary text-xs text-muted-foreground"
        style={{ height: size }}
      >
        No data yet
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center" style={{ minHeight: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label="Verdict distribution">
        <g transform={`rotate(-90 ${size / 2} ${size / 2})`}>
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            style={{ stroke: "var(--surface-alt)" }}
            strokeWidth={thickness}
          />
          {segments.map((s) => (
            <circle
              key={s.name}
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              style={{ stroke: s.color }}
              strokeWidth={thickness}
              strokeDasharray={`${s.length} ${circumference - s.length}`}
              strokeDashoffset={-s.offset}
              strokeLinecap="butt"
            >
              <title>{`${s.name}: ${s.value}`}</title>
            </circle>
          ))}
        </g>
        <text
          x="50%"
          y="46%"
          textAnchor="middle"
          className="num"
          style={{ fontFamily: "var(--font-family)", fontSize: 26, fontWeight: 700, fill: "var(--text-primary)" }}
        >
          {centerValue ?? num(total)}
        </text>
        <text
          x="50%"
          y="60%"
          textAnchor="middle"
          style={{ fontSize: 10, fill: "var(--text-secondary)", letterSpacing: "0.06em", fontWeight: 600 }}
        >
          {centerLabel ?? "SCANS"}
        </text>
      </svg>
    </div>
  );
};

export default DonutChart;
