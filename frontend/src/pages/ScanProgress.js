import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AlertTriangle, ArrowRight, Loader2, RefreshCw, Upload } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import StageStepper from "@/components/StageStepper";
import KpiTile from "@/components/KpiTile";
import VerdictBadge from "@/components/VerdictBadge";
import { apiError, endpoints } from "@/lib/api";
import { ERROR_HELP, SOURCE_LABELS, compact, num } from "@/lib/format";

const TERMINAL = ["completed", "ImportFailed", "ParseFailed", "InsufficientData"];

export default function ScanProgress() {
  const { scanId } = useParams();
  const navigate = useNavigate();
  const [scan, setScan] = useState(null);
  const [error, setError] = useState("");
  const timer = useRef(null);

  const load = useCallback(async () => {
    try {
      const res = await endpoints.getScan(scanId);
      setScan(res.data);
      return res.data;
    } catch (err) {
      // Only surface a hard error if we have never managed to load this scan.
      // A transient poll failure must not latch the error state or stop polling.
      setScan((current) => {
        if (!current) setError(apiError(err, "Could not load this scan"));
        return current;
      });
      return null;
    }
  }, [scanId]);

  useEffect(() => {
    let stop = false;
    const tick = async () => {
      const data = await load();
      if (stop) return;
      if (data === null) {
        // transient failure - back off briefly and keep polling
        timer.current = window.setTimeout(tick, 3000);
        return;
      }
      if (TERMINAL.includes(data.status)) {
        if (data.status === "completed") {
          window.setTimeout(() => navigate(`/scan/${scanId}`), 900);
        }
        return;
      }
      timer.current = window.setTimeout(tick, 1500);
    };
    tick();
    return () => {
      stop = true;
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [load, navigate, scanId]);

  if (error) {
    return (
      <Card className="rounded-xl border border-border bg-card p-6">
        <h1 className="text-h3 font-heading">Scan not found</h1>
        <p className="mt-2 text-sm text-muted-foreground">{error}</p>
        <Button asChild className="mt-4" data-testid="progress-back-history">
          <Link to="/history">Back to history</Link>
        </Button>
      </Card>
    );
  }

  if (!scan) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  const failed = ["ImportFailed", "ParseFailed"].includes(scan.status);
  const insufficient = scan.status === "InsufficientData";
  const running = !TERMINAL.includes(scan.status);
  const kpis = scan.kpis || {};

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-mono text-xs uppercase tracking-wide text-muted-foreground">{scan.id}</p>
          <h1 className="mt-1 text-h1 font-heading">
            {scan.repo_name || "Importing repository"}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {SOURCE_LABELS[scan.source_type] || scan.source_type}
            {scan.branch ? ` · branch ${scan.branch}` : ""}
            {scan.repo_owner ? ` · ${scan.repo_owner}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <VerdictBadge status={scan.status} verdict={scan.verdict} size="lg" testId="progress-status-badge" />
          {running ? <Loader2 className="h-4 w-4 animate-spin text-primary" /> : null}
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5" data-testid="scan-progress-kpis">
        <KpiTile testId="progress-kpi-discovered" label="Files discovered" value={num(kpis.files_discovered)} />
        <KpiTile testId="progress-kpi-parsed" label="Files parsed" value={num(kpis.files_parsed)} />
        <KpiTile
          testId="progress-kpi-skipped"
          label="Files skipped"
          value={num(kpis.files_skipped)}
          tone={kpis.files_skipped ? "warn" : undefined}
        />
        <KpiTile testId="progress-kpi-agentlike" label="Agent-like files" value={num(kpis.agent_like_files)} />
        <KpiTile
          testId="progress-kpi-tokens"
          label="Tokens analysed"
          value={compact(kpis.tokens_analyzed)}
          helper="ceil(character_count / 4)"
        />
      </div>

      <StageStepper progress={scan.progress} />

      {failed || insufficient ? (
        <div className={`alert ${failed ? "alert-error" : "alert-warning"}`} data-testid="scan-progress-error-state">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
            <div className="min-w-0">
              <p className="font-heading text-base font-bold" data-testid="scan-error-code">
                {scan.error_code || scan.status}
              </p>
              <p className="mt-1 text-sm leading-6">{scan.error_message}</p>
              {ERROR_HELP[scan.error_code] ? (
                <p className="mt-2 text-sm leading-6">{ERROR_HELP[scan.error_code]}</p>
              ) : null}
              {scan.retry_after_minutes ? (
                <p className="mt-2 text-sm font-bold">Retry in {scan.retry_after_minutes} minutes.</p>
              ) : null}

              <div className="mt-4 flex flex-wrap gap-2">
                <Button
                  variant="secondary"
                  data-testid="scan-progress-upload-zip-fallback"
                  onClick={() =>
                    navigate("/scan/new?source=zip", {
                      state: {
                        prefill: {
                          source_type: "zip",
                          repo_url: scan.source_url || "",
                          branch: scan.branch || "",
                          notice:
                            "Your scan settings were kept. Upload a zip export of the same repository to continue.",
                        },
                      },
                    })
                  }
                >
                  <Upload className="mr-1.5 h-4 w-4" /> Upload a zip instead
                </Button>
                <Button
                  variant="secondary"
                  data-testid="scan-progress-retry"
                  onClick={() =>
                    navigate(`/scan/new?source=${scan.source_type}`, {
                      state: {
                        prefill: {
                          source_type: scan.source_type,
                          repo_url: scan.source_url || "",
                          branch: scan.branch || "",
                          notice: "Your previous scan settings were kept.",
                        },
                      },
                    })
                  }
                >
                  <RefreshCw className="mr-1.5 h-4 w-4" /> Try again with the same settings
                </Button>
                {insufficient ? (
                  <Button asChild data-testid="scan-progress-open-partial">
                    <Link to={`/scan/${scan.id}`}>
                      Open what we did find <ArrowRight className="ml-1.5 h-4 w-4" />
                    </Link>
                  </Button>
                ) : null}
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {scan.status === "completed" ? (
        <Card className="rounded-xl border border-border bg-card p-5">
          <p className="font-heading text-base font-bold">Scan complete</p>
          <p className="mt-1 text-sm text-muted-foreground">Opening your results now.</p>
          <Button asChild className="mt-3" data-testid="progress-open-results">
            <Link to={`/scan/${scan.id}`}>
              Open results <ArrowRight className="ml-1.5 h-4 w-4" />
            </Link>
          </Button>
        </Card>
      ) : null}

      {running ? (
        <p className="text-xs text-muted-foreground">
          This page updates itself every second and a half. Large repositories can take a couple of
          minutes, and drafting rewrites with the model takes the longest.
        </p>
      ) : null}
    </div>
  );
}
