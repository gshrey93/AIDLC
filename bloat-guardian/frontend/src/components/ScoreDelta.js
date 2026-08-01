import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

/* A higher score means a leaner repository, so a positive delta is an improvement. */
export const ScoreDelta = ({ delta, testId, showFirstRun = true }) => {
  if (delta === null || delta === undefined) {
    return showFirstRun ? (
      <span className="text-[11px] text-muted-foreground" data-testid={testId}>
        first run
      </span>
    ) : null;
  }
  const value = Number(delta);
  if (value === 0) {
    return (
      <span
        className="inline-flex items-center gap-1 rounded-full bg-secondary px-2 py-0.5 text-[11px] font-semibold text-muted-foreground"
        data-testid={testId}
      >
        <Minus className="h-3 w-3" aria-hidden="true" />
        no change
      </span>
    );
  }
  const improved = value > 0;
  const Icon = improved ? ArrowUpRight : ArrowDownRight;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${
        improved ? "tone-success" : "tone-error"
      }`}
      title={improved ? "Leaner than the previous run" : "More bloated than the previous run"}
      data-testid={testId}
    >
      <Icon className="h-3 w-3" aria-hidden="true" />
      <span className="num">
        {improved ? "+" : ""}
        {value}
      </span>
    </span>
  );
};

export default ScoreDelta;
