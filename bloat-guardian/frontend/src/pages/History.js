import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Archive,
  ArchiveRestore,
  ChevronDown,
  ChevronRight,
  Download,
  ExternalLink,
  FolderDown,
  Loader2,
  Search,
  Trash2,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import DonutChart from "@/components/DonutChart";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

const ActionTooltip = ({ content, children }) => {
  if (!content) return children;
  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>{children}</TooltipTrigger>
        <TooltipContent side="top" className="z-50 bg-popover text-popover-foreground border border-border shadow-md px-2.5 py-1 text-xs font-medium">
          {content}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};
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
import { ScoreDelta } from "@/components/ScoreDelta";
import { apiError, downloadArchiveBundle, downloadExport, endpoints } from "@/lib/api";
import { SOURCE_LABELS, VERDICT_CHART_COLOR, dateTime, num, relativeDays } from "@/lib/format";

const SORTS = {
  recent: { label: "Most recent run", compare: (a, b) => ts(b.latest_run_at) - ts(a.latest_run_at) },
  worst: { label: "Lowest score first", compare: (a, b) => score(a) - score(b) },
  best: { label: "Highest score first", compare: (a, b) => score(b) - score(a) },
  runs: { label: "Most runs", compare: (a, b) => (b.run_count || 0) - (a.run_count || 0) },
  name: {
    label: "Repository name",
    compare: (a, b) => (a.display_name || "").localeCompare(b.display_name || ""),
  },
};

const ts = (iso) => (iso ? new Date(iso).getTime() || 0 : 0);
const score = (s) => (s.latest_score === null || s.latest_score === undefined ? 999 : s.latest_score);
const isViewable = (status) => status === "completed" || status === "InsufficientData";
const scanPath = (run) => (isViewable(run.status) ? `/scan/${run.id}` : `/scan/${run.id}/progress`);

export default function History() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("recent");
  const [expanded, setExpanded] = useState({});
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [busy, setBusy] = useState("");
  const [pendingDelete, setPendingDelete] = useState(null);

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const res = await endpoints.listSeries({ include_archived: true });
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

  const allSeries = useMemo(() => data?.series || [], [data]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const match = (s) =>
      !q ||
      [s.display_name, s.repo_name, s.repo_owner, s.branch, s.source_type, s.id]
        .filter(Boolean)
        .some((v) => String(v).toLowerCase().includes(q));
    const compare = (SORTS[sort] || SORTS.recent).compare;
    return {
      active: allSeries.filter((s) => !s.archived && match(s)).sort(compare),
      archived: allSeries.filter((s) => s.archived && match(s)).sort(compare),
    };
  }, [allSeries, query, sort]);

  const distribution = useMemo(() => {
    const counts = {};
    allSeries.forEach((s) => {
      const key = s.latest_verdict || s.latest_status || "Unscored";
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
  }, [allSeries]);

  const toggleRow = (id) => setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));

  const setArchived = async (series, archived) => {
    setBusy(series.id);
    try {
      await endpoints.setSeriesArchived(series.id, archived);
      toast.success(
        archived
          ? `${series.display_name} moved to the archive`
          : `${series.display_name} restored to active`,
      );
      await load(true);
    } catch (err) {
      toast.error(apiError(err, "Could not update that repository"));
    } finally {
      setBusy("");
    }
  };

  const downloadReport = async (run) => {
    setBusy(run.id);
    try {
      await downloadExport(run.id, "pdf_full", `${run.repo_name}-${run.id}-full-report.pdf`);
      toast.success("Report downloaded");
    } catch (err) {
      toast.error(
        apiError(err, "Report generation failed. Try the printable view from the export page."),
      );
    } finally {
      setBusy("");
    }
  };

  const downloadBundle = async () => {
    setBusy("archive-bundle");
    try {
      const stamp = new Date().toISOString().slice(0, 10);
      await downloadArchiveBundle(`bloat-guardian-archive-${stamp}.zip`);
      toast.success("Archive bundle downloaded");
    } catch (err) {
      toast.error(apiError(err, "The archive bundle could not be built"));
    } finally {
      setBusy("");
    }
  };

  const confirmDelete = async () => {
    const target = pendingDelete;
    setPendingDelete(null);
    if (!target) return;
    try {
      if (target.kind === "series") {
        const res = await endpoints.deleteSeries(target.series.id);
        toast.success(
          `${target.series.display_name} deleted with ${res.data.runs_deleted} run(s)`,
        );
      } else {
        await endpoints.deleteScan(target.run.id);
        toast.success(`Run ${target.run.id} deleted`);
      }
      await load(true);
    } catch (err) {
      toast.error(apiError(err, "Could not delete that entry"));
    }
  };

  const renderRuns = (series) => (
    <TableRow className="bg-muted/40 hover:bg-muted/40" data-testid={`series-runs-${series.id}`}>
      <TableCell colSpan={10} className="p-0">
        <div className="border-l-2 border-primary/50 px-4 py-3">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {series.run_count} run{series.run_count === 1 ? "" : "s"} on {series.display_name}
            {series.branch ? ` @ ${series.branch}` : ""}
          </p>
          <div className="overflow-x-auto scrollbar-thin">
            <Table className="drl-table min-w-[860px]">
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Run</TableHead>
                  <TableHead className="text-xs">Scan date</TableHead>
                  <TableHead className="text-right text-xs">Score</TableHead>
                  <TableHead className="text-xs">Change</TableHead>
                  <TableHead className="text-xs">Verdict</TableHead>
                  <TableHead className="text-right text-xs">Scanned</TableHead>
                  <TableHead className="text-right text-xs">Skipped</TableHead>
                  <TableHead className="text-right text-xs">Credits/mo</TableHead>
                  <TableHead className="text-right text-xs">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(series.runs || []).map((run) => (
                  <TableRow key={run.id} data-testid="series-run-row">
                    <TableCell className="text-xs">
                      <span className="num font-semibold">#{run.run_number || "-"}</span>
                    </TableCell>
                    <TableCell className="text-xs">
                      <Link
                        to={scanPath(run)}
                        className="font-medium text-primary underline-offset-2 hover:underline"
                        data-testid={`run-link-${run.id}`}
                      >
                        {dateTime(run.created_at)}
                      </Link>
                      <span className="block font-mono text-[10px] text-muted-foreground">
                        {run.id}
                      </span>
                    </TableCell>
                    <TableCell className="num text-right text-sm font-semibold">
                      {run.status === "completed" ? run.overall_score : "-"}
                    </TableCell>
                    <TableCell>
                      <ScoreDelta delta={run.score_delta} testId={`run-delta-${run.id}`} />
                    </TableCell>
                    <TableCell>
                      <VerdictBadge
                        verdict={run.verdict}
                        status={run.status}
                        partialScan={run.partial_scan}
                        testId={`run-verdict-${run.id}`}
                      />
                    </TableCell>
                    <TableCell className="num text-right text-xs">{num(run.parsed_files)}</TableCell>
                    <TableCell className="num text-right text-xs">{num(run.skipped_files)}</TableCell>
                    <TableCell className="num text-right text-xs">
                      {num(run.estimated_monthly_credit_waste, 2)}
                    </TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-1">
                        <ActionTooltip content="Open scan results">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            title="Open scan results"
                            aria-label="Open run"
                            onClick={() => navigate(scanPath(run))}
                            data-testid="run-open-button"
                          >
                            <ExternalLink className="h-4 w-4" />
                          </Button>
                        </ActionTooltip>
                        <ActionTooltip content={busy === run.id ? "Building PDF report..." : "Download PDF report"}>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            title="Download PDF report"
                            aria-label="Download run report"
                            disabled={run.status !== "completed" || busy === run.id}
                            onClick={() => downloadReport(run)}
                            data-testid="run-download-button"
                          >
                            {busy === run.id ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              <Download className="h-4 w-4" />
                            )}
                          </Button>
                        </ActionTooltip>
                        <ActionTooltip content="Delete scan run">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-destructive hover:bg-destructive/10"
                            title="Delete scan run"
                            aria-label="Delete run"
                            onClick={() => setPendingDelete({ kind: "run", run, series })}
                            data-testid="run-delete-button"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </ActionTooltip>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      </TableCell>
    </TableRow>
  );

  const renderTable = (rows, kind) => (
    <div className="overflow-x-auto scrollbar-thin">
      <Table className="drl-table min-w-[1060px]" data-testid={`${kind}-series-table`}>
        <TableHeader>
          <TableRow>
            <TableHead className="w-8 text-xs" />
            <TableHead className="text-xs">Repository</TableHead>
            <TableHead className="text-xs">Source</TableHead>
            <TableHead className="text-xs">Branch</TableHead>
            <TableHead className="text-right text-xs">Runs</TableHead>
            <TableHead className="text-right text-xs">Latest score</TableHead>
            <TableHead className="text-xs">Verdict</TableHead>
            <TableHead className="text-xs">Change</TableHead>
            <TableHead className="text-xs">Last run</TableHead>
            <TableHead className="text-right text-xs">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.length === 0 ? (
            <TableRow>
              <TableCell colSpan={10} className="py-12 text-center">
                <p className="font-heading text-base font-bold">
                  {kind === "archived" ? "Nothing archived" : "No repositories yet"}
                </p>
                <p className="mt-1 text-sm text-muted-foreground">
                  {kind === "archived"
                    ? "Archive a repository to park it here without losing its run history."
                    : query
                      ? "No repository matches that search."
                      : "Run your first scan from GitHub, Bitbucket, a zip or markdown upload."}
                </p>
                {kind === "active" && !query ? (
                  <Button asChild className="mt-4" data-testid="history-empty-new-scan">
                    <Link to="/scan/new">Start a scan</Link>
                  </Button>
                ) : null}
              </TableCell>
            </TableRow>
          ) : (
            rows.flatMap((s) => {
              const open = Boolean(expanded[s.id]);
              const latestRun = (s.runs || [])[0];
              const rowsOut = [
                <TableRow key={s.id} data-testid="series-row">
                  <TableCell className="w-8">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7"
                      aria-label={open ? "Hide runs" : "Show runs"}
                      aria-expanded={open}
                      onClick={() => toggleRow(s.id)}
                      data-testid={`series-expand-${s.id}`}
                    >
                      {open ? (
                        <ChevronDown className="h-4 w-4" />
                      ) : (
                        <ChevronRight className="h-4 w-4" />
                      )}
                    </Button>
                  </TableCell>
                  <TableCell className="text-xs">
                    <button
                      type="button"
                      onClick={() => toggleRow(s.id)}
                      className="text-left font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      data-testid={`series-name-${s.id}`}
                    >
                      {s.display_name}
                    </button>
                    {s.is_seed ? (
                      <span className="ml-1.5 rounded-full bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
                        demo
                      </span>
                    ) : null}
                    <span className="block font-mono text-[10px] text-muted-foreground">{s.id}</span>
                  </TableCell>
                  <TableCell className="text-xs">
                    {SOURCE_LABELS[s.source_type] || s.source_type}
                  </TableCell>
                  <TableCell className="text-xs">{s.branch || "n/a"}</TableCell>
                  <TableCell className="num text-right text-xs font-semibold">
                    {num(s.run_count)}
                  </TableCell>
                  <TableCell
                    className="num text-right text-sm font-semibold"
                    data-testid={`series-score-${s.id}`}
                  >
                    {s.latest_score === null || s.latest_score === undefined ? "-" : s.latest_score}
                  </TableCell>
                  <TableCell>
                    <VerdictBadge
                      verdict={s.latest_verdict}
                      status={s.latest_status}
                      partialScan={latestRun?.partial_scan}
                      testId={`series-verdict-${s.id}`}
                    />
                  </TableCell>
                  <TableCell>
                    <ScoreDelta delta={s.score_delta} testId={`series-delta-${s.id}`} />
                  </TableCell>
                  <TableCell className="text-xs">
                    <span className="block">{dateTime(s.latest_run_at)}</span>
                    <span className="text-[11px] text-muted-foreground">
                      {relativeDays(s.latest_run_at)}
                    </span>
                  </TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-1">
                      <ActionTooltip content={latestRun ? "View latest scan results" : "No scan results available"}>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          title={latestRun ? "View latest scan results" : "No scan results available"}
                          aria-label="Open latest run"
                          disabled={!latestRun}
                          onClick={() => latestRun && navigate(scanPath(latestRun))}
                          data-testid="series-open-button"
                        >
                          <ExternalLink className="h-4 w-4" />
                        </Button>
                      </ActionTooltip>
                      <ActionTooltip
                        content={
                          busy === s.latest_completed_scan_id
                            ? "Building PDF report..."
                            : s.latest_completed_scan_id
                              ? "Download latest PDF report"
                              : "No report available"
                        }
                      >
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          title={
                            s.latest_completed_scan_id ? "Download latest PDF report" : "No report available"
                          }
                          aria-label="Download latest report"
                          disabled={!s.latest_completed_scan_id || busy === s.latest_completed_scan_id}
                          onClick={() =>
                            downloadReport(
                              (s.runs || []).find((r) => r.id === s.latest_completed_scan_id) ||
                                latestRun,
                            )
                          }
                          data-testid="series-download-button"
                        >
                          {busy === s.latest_completed_scan_id ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Download className="h-4 w-4" />
                          )}
                        </Button>
                      </ActionTooltip>
                      <ActionTooltip content={s.archived ? "Restore repository from archive" : "Archive repository"}>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          title={s.archived ? "Restore repository from archive" : "Archive repository"}
                          aria-label={s.archived ? "Restore from archive" : "Archive repository"}
                          disabled={busy === s.id}
                          onClick={() => setArchived(s, !s.archived)}
                          data-testid={s.archived ? "series-unarchive-button" : "series-archive-button"}
                        >
                          {busy === s.id ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : s.archived ? (
                            <ArchiveRestore className="h-4 w-4" />
                          ) : (
                            <Archive className="h-4 w-4" />
                          )}
                        </Button>
                      </ActionTooltip>
                      <ActionTooltip content="Delete repository and all runs">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-destructive hover:bg-destructive/10"
                          title="Delete repository and all runs"
                          aria-label="Delete repository and all runs"
                          onClick={() => setPendingDelete({ kind: "series", series: s })}
                          data-testid="series-delete-button"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </ActionTooltip>
                    </div>
                  </TableCell>
                </TableRow>,
              ];
              if (open) rowsOut.push(renderRuns(s));
              return rowsOut;
            })
          )}
        </TableBody>
      </Table>
    </div>
  );

  const counts = data?.counts || {};

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-h1 font-heading">Scan history</h1>
          <p className="mt-1 text-sm text-muted-foreground" data-testid="history-subtitle">
            {data
              ? `${counts.total} repositories tracked · ${counts.runs} runs stored · ${counts.active} active, ${counts.archived} archived. Each branch is tracked separately.`
              : "Loading your repositories"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild size="sm" data-testid="history-new-scan-button">
            <Link to="/scan/new">New scan</Link>
          </Button>
        </div>
      </div>

      <Card
        className="rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-md)]"
        data-testid="history-verdict-distribution"
      >
        <div className="flex flex-col gap-6 sm:flex-row sm:items-center">
          <div className="shrink-0">
            {loading ? (
              <Skeleton className="skeleton-shimmer h-[132px] w-[132px] rounded-full" />
            ) : (
              <DonutChart slices={distribution} size={132} thickness={18} centerLabel="REPOS" />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="font-heading text-base font-bold">Latest verdict mix</h3>
            <p className="text-xs text-muted-foreground">
              The most recent run of every tracked repository. Lean is healthy, Critical needs
              attention now.
            </p>
            <ul className="mt-3 flex flex-wrap gap-x-6 gap-y-2">
              {distribution.map((d) => (
                <li key={d.name} className="flex items-center gap-2 text-xs">
                  <span
                    className="h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: d.color }}
                  />
                  <span className="font-medium">{d.name}</span>
                  <span className="num font-bold">{d.value}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </Card>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-[220px] flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by repository, owner or branch"
            className="pl-9"
            aria-label="Search repositories"
            data-testid="history-search-input"
          />
        </div>
        <Select value={sort} onValueChange={setSort}>
          <SelectTrigger className="w-[200px]" aria-label="Sort repositories" data-testid="history-sort-select">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {Object.entries(SORTS).map(([key, cfg]) => (
              <SelectItem key={key} value={key} data-testid={`history-sort-${key}`}>
                {cfg.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Card className="rounded-xl border border-border bg-card shadow-[var(--shadow-md)]">
        <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
          <h2 className="font-heading text-base font-bold">
            Active repositories{" "}
            <span className="num text-sm font-semibold text-muted-foreground">
              {filtered.active.length}
            </span>
          </h2>
          <p className="hidden text-xs text-muted-foreground sm:block">
            Expand a row to see every run and how the score moved.
          </p>
        </div>
        {loading ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-9 w-full" />
            ))}
          </div>
        ) : (
          renderTable(filtered.active, "active")
        )}
      </Card>

      <Collapsible open={archiveOpen} onOpenChange={setArchiveOpen}>
        <Card className="rounded-xl border border-border bg-card shadow-[var(--shadow-md)]">
          <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
            <CollapsibleTrigger asChild>
              <Button
                variant="ghost"
                className="h-auto gap-2 px-2 py-1"
                data-testid="archive-section-toggle"
              >
                {archiveOpen ? (
                  <ChevronDown className="h-4 w-4" />
                ) : (
                  <ChevronRight className="h-4 w-4" />
                )}
                <span className="font-heading text-base font-bold">Archive</span>
                <span className="num rounded-full bg-secondary px-2 py-0.5 text-xs font-semibold text-muted-foreground">
                  {filtered.archived.length}
                </span>
              </Button>
            </CollapsibleTrigger>
            <Button
              variant="secondary"
              size="sm"
              className="gap-2"
              disabled={busy === "archive-bundle" || (counts.archived || 0) === 0}
              onClick={downloadBundle}
              data-testid="archive-download-bundle-button"
            >
              {busy === "archive-bundle" ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <FolderDown className="h-4 w-4" />
              )}
              Download archive bundle
            </Button>
          </div>
          <CollapsibleContent>
            <div className="border-t border-border">
              <p className="px-4 py-2 text-xs text-muted-foreground">
                Archived repositories keep their full run history and stay downloadable. The bundle
                contains the latest report and findings CSV for each one, plus a manifest.
              </p>
              {loading ? (
                <div className="space-y-2 p-4">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <Skeleton key={i} className="h-9 w-full" />
                  ))}
                </div>
              ) : (
                renderTable(filtered.archived, "archived")
              )}
            </div>
          </CollapsibleContent>
        </Card>
      </Collapsible>

      <p className="text-xs text-muted-foreground">
        Every run is kept: scanning the same repository and branch again appends a run to its series
        instead of replacing it. Imported repository content is deleted after 7 days, and report
        metadata for your own scans after 30 days. Seeded demo repositories start in the archive.
      </p>

      <AlertDialog open={Boolean(pendingDelete)} onOpenChange={(o) => !o && setPendingDelete(null)}>
        <AlertDialogContent data-testid="history-delete-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>
              {pendingDelete?.kind === "series" ? "Delete this repository?" : "Delete this run?"}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {pendingDelete?.kind === "series"
                ? `${pendingDelete.series.display_name} and all ${pendingDelete.series.run_count} of its runs, findings, files and drafts will be removed. This cannot be undone.`
                : pendingDelete
                  ? `Run ${pendingDelete.run.id} and its findings, files and drafts will be removed. The rest of ${pendingDelete.series.display_name} is kept.`
                  : ""}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="history-delete-cancel">Keep it</AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              data-testid="history-delete-confirm"
            >
              {pendingDelete?.kind === "series" ? "Delete repository" : "Delete run"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
