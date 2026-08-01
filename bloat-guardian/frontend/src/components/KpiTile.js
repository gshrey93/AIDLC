import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export const KpiTile = ({ label, value, helper, tone, loading, testId, icon: Icon, className }) => {
  const toneClass =
    tone === "bad"
      ? "score-bad"
      : tone === "warn"
        ? "score-warn"
        : tone === "good"
          ? "score-good"
          : "text-foreground";
  return (
    <Card
      data-testid={testId}
      className={cn(
        "rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-md)] transition-shadow duration-250 hover:shadow-[var(--shadow-lg)]",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">{label}</p>
        {Icon ? <Icon className="h-4 w-4 shrink-0 text-muted-foreground" /> : null}
      </div>
      {loading ? (
        <Skeleton className="skeleton-shimmer mt-2 h-7 w-24" />
      ) : (
        <p className={cn("num mt-1.5 font-heading text-2xl font-bold sm:text-[26px]", toneClass)}>
          {value}
        </p>
      )}
      {helper ? <p className="mt-1 text-xs leading-5 text-muted-foreground">{helper}</p> : null}
    </Card>
  );
};

export default KpiTile;
