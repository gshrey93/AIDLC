import { AlertTriangle, Info } from "lucide-react";

export const WarningBanner = ({ warnings, skippedFiles, totalFiles, partialScan }) => {
  if (!warnings || warnings.length === 0) return null;
  return (
    <div data-testid="partial-scan-warning" className="alert alert-warning">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
        <div className="min-w-0">
          <p className="font-heading text-sm font-bold">
            {partialScan ? "Partial scan" : "Some files were skipped"}
            {typeof skippedFiles === "number" && typeof totalFiles === "number"
              ? ` \u2014 ${skippedFiles} of ${totalFiles} files`
              : ""}
          </p>
          <ul className="mt-1.5 space-y-1">
            {warnings.map((w, i) => (
              <li key={i} className="text-sm leading-6">
                {w}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
};

export const InfoNote = ({ children, testId }) => (
  <div
    data-testid={testId}
    className="flex items-start gap-3 rounded-xl border border-border bg-secondary p-4"
  >
    <Info className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
    <div className="text-sm leading-6 text-foreground">{children}</div>
  </div>
);

export default WarningBanner;
