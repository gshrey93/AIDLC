import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Download, ExternalLink, Loader2, Trash2 } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import DonutChart from "@/components/DonutChart";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { toast } from "@/components/ui/sonner";
import VerdictBadge from "@/components/VerdictBadge";
import { apiError, downloadExport, endpoints } from "@/lib/api";
import { SOURCE_LABELS, VERDICT_CHART_COLOR, dateTime, num, relativeDays } from "@/lib/format";

export default function History() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [onlyRecent, setOnlyRecent] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await endpoints.listScans({ limit: 200 });
      setData(res.data);
    } catch (err) {
      toast.error(apiError(err, "Could not load your scan history"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const scans = useMemo(() => {
    const rows = data?.scans || [];
    return onlyRecent ? rows.slice(0, data?.keep_recent_scans || 10) : rows;
  }, [data, onlyRecent]);

  const distribution = useMemo(() => {
    const counts = {};
    (data?.scans || []).forEach((s) => {
      const key = s.verdict || s.status;
      counts[key] = (counts[key] || 0) + 1;
    });
    const order = ["Lean", "Watchlist", "Wasteful", "Critical"];
    return Object.entries(counts)
      .sort((a, b) => {
        const ai = order.indexOf(a[0]);
        const bi = order.indexOf(b[0]);
        return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
      })
      .map(([name, value]) => ({
        name,
        value,
        color: VERDICT_CHART_COLOR[name] || "var(--chart-6)",
      }));
  }, [data]);

  const colourFor = (name) => VERDICT_CHART_COLOR[name] || "var(--chart-6)";

  const remove = async () => {
    if (!pendingDelete) return;
    const id = pendingDelete.id;
    setPendingDelete(null);
    try {
      await endpoints.deleteScan(id);
      toast.success(`Scan ${id} deleted`);
      await load();
    } catch (err) {
      toast.error(apiError(err, "Could not delete that scan"));
    }
  };

  const downloadReport = async (scan) => {
    setBusy(scan.id);
    try {
      await downloadExport(scan.id, "pdf_full", `${scan.repo_name}-${scan.id}-full-report.pdf`);
      toast.success("Report downloaded");
    } catch (err) {
      toast.error(apiError(err, "Report generation failed. Try the printable view from the export page."));
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-h1 font-heading">Scan history</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {data
              ? `${data.total} scans stored · ${data.real_total} of your own, ${data.seed_total} seeded demo scans across the last 90 days.`
              : "Loading your scans"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant={onlyRecent ? "default" : "secondary"}
            size="sm"
            onClick={() => setOnlyRecent(!onlyRecent)}
            data-testid="history-toggle-recent"
          >
            {onlyRecent ? `Showing last ${data?.keep_recent_scans || 10}` : "Show last 10 only"}
          </Button>
          <Button asChild size="sm" data-testid="history-new-scan-button">
            <Link to="/scan/new">New scan</Link>
          </Button>
        </div>
      </div>

      <div className="grid gap-4">
        <Card
          className="rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-md)]"
          data-testid="history-verdict-distribution"
        >
          <div className="flex flex-col gap-6 sm:flex-row sm:items-center">
            <div className="shrink-0">
              {loading ? (
                <Skeleton className="skeleton-shimmer h-[132px] w-[132px] rounded-full" />
              ) : (
                <DonutChart slices={distribution} size={132} thickness={18} centerLabel="SCANS" />
              )}
            </div>
            <div className="min-w-0 flex-1">
              <h3 className="font-heading text-base font-bold">Verdict mix</h3>
              <p className="text-xs text-muted-foreground">
                Across every stored scan. Lean is healthy, Critical needs attention now.
              </p>
              <ul className="mt-3 flex flex-wrap gap-x-6 gap-y-2">
                {distribution.map((d) => (
                  <li key={d.name} className="flex items-center gap-2 text-xs">
                    <span
                      className="h-2.5 w-2.5 rounded-full"
                      style={{ backgroundColor: colourFor(d.name) }}
                    />
                    <span className="font-medium">{d.name}</span>
                    <span className="num font-bold">{d.value}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </Card>

        <Card className="rounded-xl border border-border bg-card shadow-[var(--shadow-md)]">
          <div className="overflow-x-auto">
            <Table className="drl-table" data-testid="history-table">
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Scan date</TableHead>
                  <TableHead className="text-xs">Source</TableHead>
                  <TableHead className="text-xs">Repository</TableHead>
                  <TableHead className="text-xs">Branch</TableHead>
                  <TableHead className="text-right text-xs">Score</TableHead>
                  <TableHead className="text-xs">Verdict</TableHead>
                  <TableHead className="text-right text-xs">Scanned</TableHead>
                  <TableHead className="text-right text-xs">Skipped</TableHead>
                  <TableHead className="text-right text-xs">Credits/mo</TableHead>
                  <TableHead className="text-right text-xs">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  Array.from({ length: 8 }).map((_, i) => (
                    <TableRow key={i}>
                      <TableCell colSpan={10}>
                        <Skeleton className="h-5 w-full" />
                      </TableCell>
                    </TableRow>
                  ))
                ) : scans.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={10} className="py-12 text-center">
                      <p className="font-heading text-base font-bold">No scans yet</p>
                      <p className="mt-1 text-sm text-muted-foreground">
                        Run your first scan from GitHub, Bitbucket or a zip upload.
                      </p>
                      <Button asChild className="mt-4" data-testid="history-empty-new-scan">
                        <Link to="/scan/new">Start a scan</Link>
                      </Button>
                    </TableCell>
                  </TableRow>
                ) : (
                  scans.map((s) => (
                    <TableRow key={s.id} data-testid="history-row">
                      <TableCell className="text-xs">
                        <span className="block">{dateTime(s.created_at)}</span>
                        <span className="text-[11px] text-muted-foreground">{relativeDays(s.created_at)}</span>
                      </TableCell>
                      <TableCell className="text-xs">{SOURCE_LABELS[s.source_type] || s.source_type}</TableCell>
                      <TableCell className="text-xs">
                        <Link
                          to={s.status === "completed" || s.status === "InsufficientData" ? `/scan/${s.id}` : `/scan/${s.id}/progress`}
                          className="font-medium text-primary underline-offset-2 hover:underline"
                        >
                          {s.repo_name || "(no name)"}
                        </Link>
                        {s.is_seed ? (
                          <span className="ml-1.5 rounded-full bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
                            demo
                          </span>
                        ) : null}
                        <span className="block font-mono text-[10px] text-muted-foreground">{s.id}</span>
                      </TableCell>
                      <TableCell className="text-xs">{s.branch || "-"}</TableCell>
                      <TableCell className="num text-right text-sm font-semibold">
                        {s.status === "completed" ? s.overall_score : "-"}
                      </TableCell>
                      <TableCell>
                        <VerdictBadge
                          verdict={s.verdict}
                          status={s.status}
                          partialScan={s.partial_scan}
                          testId={`history-verdict-${s.id}`}
                        />
                      </TableCell>
                      <TableCell className="num text-right text-xs">{num(s.parsed_files)}</TableCell>
                      <TableCell className="num text-right text-xs">{num(s.skipped_files)}</TableCell>
                      <TableCell className="num text-right text-xs">
                        {num(s.estimated_monthly_credit_waste, 2)}
                      </TableCell>
                      <TableCell>
                        <div className="flex justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            aria-label="Open scan"
                            onClick={() =>
                              navigate(
                                s.status === "completed" || s.status === "InsufficientData"
                                  ? `/scan/${s.id}`
                                  : `/scan/${s.id}/progress`,
                              )
                            }
                            data-testid="history-open-scan-button"
                          >
                            <ExternalLink className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            aria-label="Download report"
                            disabled={s.status !== "completed" || busy === s.id}
                            onClick={() => downloadReport(s)}
                            data-testid="history-download-report-button"
                          >
                            {busy === s.id ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              <Download className="h-4 w-4" />
                            )}
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-destructive"
                            aria-label="Delete scan"
                            onClick={() => setPendingDelete(s)}
                            data-testid="history-delete-scan-button"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </Card>
      </div>

      <p className="text-xs text-muted-foreground">
        Retention: your {data?.keep_recent_scans || 10} most recent real scans are kept. Imported
        repository content is deleted after 7 days and reports after 30 days. Seeded demo scans are kept
        so the example history stays available.
      </p>

      <AlertDialog open={Boolean(pendingDelete)} onOpenChange={(o) => !o && setPendingDelete(null)}>
        <AlertDialogContent data-testid="history-delete-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this scan?</AlertDialogTitle>
            <AlertDialogDescription>
              {pendingDelete
                ? `${pendingDelete.repo_name || pendingDelete.id} and all of its findings, files and drafts will be removed. This cannot be undone.`
                : ""}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="history-delete-cancel">Keep it</AlertDialogCancel>
            <AlertDialogAction
              onClick={remove}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              data-testid="history-delete-confirm"
            >
              Delete scan
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
