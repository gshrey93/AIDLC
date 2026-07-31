import { AlertCircle, Check, Loader2, MinusCircle } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

const ICONS = {
  done: Check,
  running: Loader2,
  failed: AlertCircle,
  skipped: MinusCircle,
};

export const StageStepper = ({ progress }) => {
  const stages = progress?.stages || [];
  return (
    <Card
      data-testid="scan-stage-stepper"
      className="rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-md)]"
    >
      <div className="flex items-center justify-between gap-3">
        <p className="font-heading text-sm font-bold">Scan stages</p>
        <p className="num text-xs text-muted-foreground">{progress?.percent || 0}% complete</p>
      </div>
      <Progress value={progress?.percent || 0} className="mt-3 h-2" />
      <ol className="mt-4 space-y-2.5">
        {stages.map((stage, index) => {
          const Icon = ICONS[stage.status];
          const dotClass =
            stage.status === "done"
              ? "bg-primary text-primary-foreground border-primary"
              : stage.status === "running"
                ? "bg-accent text-accent-foreground border-primary"
                : stage.status === "failed"
                  ? "bg-destructive text-destructive-foreground border-destructive"
                  : stage.status === "skipped"
                    ? "bg-secondary text-muted-foreground border-border"
                    : "bg-secondary text-muted-foreground border-border";
          return (
            <li
              key={stage.key}
              className="flex items-start gap-3"
              data-testid={`scan-stage-${stage.key}`}
              data-status={stage.status}
            >
              <span
                className={cn(
                  "mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[11px] font-semibold",
                  dotClass,
                )}
              >
                {Icon ? (
                  <Icon className={cn("h-3.5 w-3.5", stage.status === "running" && "animate-spin")} />
                ) : (
                  index + 1
                )}
              </span>
              <div className="min-w-0 flex-1">
                <p
                  className={cn(
                    "text-sm font-medium",
                    stage.status === "pending" ? "text-muted-foreground" : "text-foreground",
                  )}
                >
                  {stage.label}
                </p>
                {stage.detail ? (
                  <p className="mt-0.5 break-words font-mono text-[11px] leading-4 text-muted-foreground">
                    {stage.detail}
                  </p>
                ) : null}
              </div>
              <span className="shrink-0 text-[11px] uppercase tracking-wide text-muted-foreground">
                {stage.status}
              </span>
            </li>
          );
        })}
      </ol>
    </Card>
  );
};

export default StageStepper;
