import { AlertTriangle } from "lucide-react";
import { SEVERITY_LABEL, SEVERITY_TONE, STATUS_TONE, VERDICT_TONE } from "@/lib/format";

export const VerdictBadge = ({ verdict, status, partialScan, size = "md", testId = "verdict-badge" }) => {
  const label = verdict || status || "No verdict";
  const tone = VERDICT_TONE[label] || STATUS_TONE[label] || "tone-neutral";
  const pad = size === "lg" ? "px-4 py-1.5 text-sm" : "px-2.5 py-1 text-xs";
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <span
        data-testid={testId}
        className={`tone ${tone} inline-flex items-center rounded-full font-semibold ${pad}`}
      >
        {label}
      </span>
      {partialScan ? (
        <span
          data-testid="partial-scan-badge"
          className="tone tone-warning inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold"
          title="More than 20% of files were skipped"
        >
          <AlertTriangle className="h-3 w-3" /> PartialScan
        </span>
      ) : null}
    </span>
  );
};

export const SeverityChip = ({ severity, testId }) => (
  <span
    data-testid={testId || "severity-chip"}
    className={`tone ${SEVERITY_TONE[severity] || "tone-neutral"} inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold`}
  >
    {SEVERITY_LABEL[severity] || severity}
  </span>
);

export const MetaChip = ({ label, value, tone = "neutral" }) => {
  const toneClass =
    tone === "good"
      ? "tone-success"
      : tone === "warn"
        ? "tone-warning"
        : tone === "bad"
          ? "tone-error"
          : tone === "brand"
            ? "tone-brand"
            : "tone-neutral";
  return (
    <span
      className={`tone ${toneClass} inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium`}
    >
      {label ? <span className="opacity-75">{label}</span> : null}
      <span className="font-semibold">{value}</span>
    </span>
  );
};

export default VerdictBadge;
