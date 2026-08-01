import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  AlertTriangle,
  Copy,
  Download,
  FileCode2,
  Files,
  Layers,
  RefreshCw,
  ShieldQuestion,
  Terminal,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { toast } from "@/components/ui/sonner";
import KpiTile from "@/components/KpiTile";
import VerdictBadge from "@/components/VerdictBadge";
import CategoryScoreCard from "@/components/CategoryScoreCard";
import IssuesTable from "@/components/IssuesTable";
import FileInventory from "@/components/FileInventory";
import DraftPreview from "@/components/DraftPreview";
import WarningBanner from "@/components/WarningBanner";
import { AssumptionsReadout } from "@/components/AssumptionsEditor";
import TopDrivers, { RecommendedActions, ScoreLedger } from "@/components/ResultsSections";
import { apiError, endpoints } from "@/lib/api";
import { ERROR_HELP, SOURCE_LABELS, bytes, compact, dateTime, money, num } from "@/lib/format";

export default function ScanResults() {
  const { scanId } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const res = await endpoints.getResults(scanId);
      setData(res.data);
      setError("");
    } catch (err) {
      setError(apiError(err, "Could not load these results"));
    } finally {
      setLoading(false);
    }
  }, [scanId]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-12 w-96" />
        <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error) {
    return (
      <Card className="rounded-xl border border-border bg-card p-6">
        <h1 className="text-h3 font-heading">We could not open this scan</h1>
        <p className="mt-2 text-sm text-muted-foreground">{error}</p>
        <Button asChild className="mt-4">
          <Link to="/history">Back to history</Link>
        </Button>
      </Card>
    );
  }

  const scan = data.scan;
  const det = data.detections || {};
  const insufficient = scan.status === "InsufficientData";
  const failed = ["ImportFailed", "ParseFailed"].includes(scan.status);
  const skipped = (data.files || []).filter((f) => f.parse_status !== "Scanned");

  const copyPrompt = async () => {
    try {
      await navigator.clipboard.writeText(data.handoff_prompt || "");
      toast.success("Summary prompt copied");
    } catch {
      toast.error("Your browser blocked clipboard access");
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="font-mono text-xs uppercase tracking-wide text-muted-foreground">
            {scan.id}
            {scan.is_seed ? " · seeded demo" : ""}
          </p>
          <h1 className="mt-1 text-h1 font-heading">{scan.repo_name}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {SOURCE_LABELS[scan.source_type] || scan.source_type}
            {scan.repo_owner ? ` · ${scan.repo_owner}` : ""}
            {scan.branch ? ` · branch ${scan.branch}` : ""} &middot; scanned {dateTime(scan.created_at)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="secondary" size="sm" onClick={load} data-testid="results-refresh-button">
            <RefreshCw className="mr-1.5 h-3.5 w-3.5" /> Refresh
          </Button>
          <Button asChild variant="secondary" size="sm" data-testid="results-handoff-button">
            <Link to={`/scan/${scan.id}/handoff`}>
              <Terminal className="mr-1.5 h-3.5 w-3.5" /> VS Code handoff
            </Link>
          </Button>
          <Button asChild size="sm" data-testid="results-export-button">
            <Link to={`/scan/${scan.id}/exports`}>
              <Download className="mr-1.5 h-3.5 w-3.5" /> Export report
            </Link>
          </Button>
        </div>
      </div>

      <Card className="rounded-xl border border-border bg-card p-5 shadow-[var(--shadow-md)]">
        <div className="flex flex-wrap items-center gap-6">
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Overall efficiency score</p>
            <p className="num font-heading text-5xl font-semibold" data-testid="kpi-overall-score">
              {scan.overall_score}
              <span className="text-lg font-medium text-muted-foreground">/100</span>
            </p>
          </div>
          <div className="h-14 w-px bg-border" />
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Verdict</p>
            <div className="mt-1.5">
              <VerdictBadge
                verdict={scan.verdict}
                status={scan.status}
                partialScan={scan.partial_scan}
                size="lg"
              />
            </div>
          </div>
          <div className="h-14 w-px bg-border" />
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Monthly savings range</p>
            <p className="num mt-1 text-h3 font-heading" data-testid="kpi-savings-range">
              {money(scan.estimated_savings_low)} &ndash; {money(scan.estimated_savings_high)}
            </p>
            <p className="text-xs text-muted-foreground">
              Mid point {money(scan.estimated_monthly_dollar_waste)} at +/-
              {Math.round((data.assumptions?.variance_pct || 0.2) * 100)}%
            </p>
          </div>
        </div>
      </Card>

      <WarningBanner
        warnings={data.warnings}
        skippedFiles={scan.skipped_files}
        totalFiles={scan.total_files}
        partialScan={scan.partial_scan}
      />

      {insufficient || failed ? (
        <div className="alert alert-warning" data-testid="results-insufficient-banner">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
            <div>
              <p className="font-heading text-base font-bold">{scan.error_code || scan.status}</p>
              <p className="mt-1 text-sm leading-6">
                {scan.error_message || ERROR_HELP[scan.status]}
              </p>
              <p className="mt-2 text-sm font-bold">Savings were not calculated for this scan.</p>
            </div>
          </div>
        </div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
        <KpiTile
          testId="kpi-estimated-monthly-token-waste"
          label="Monthly token waste"
          value={compact(scan.estimated_monthly_token_waste)}
          helper={`${num(scan.estimated_monthly_credit_waste, 2)} report credits`}
          tone="warn"
        />
        <KpiTile
          testId="kpi-estimated-monthly-dollar-waste"
          label="Monthly dollar waste"
          value={money(scan.estimated_monthly_dollar_waste)}
          helper="Mid point estimate"
          tone="bad"
        />
        <KpiTile testId="kpi-files-scanned" label="Files scanned" value={num(scan.parsed_files)} icon={Files} />
        <KpiTile
          testId="kpi-files-skipped"
          label="Files skipped"
          value={num(scan.skipped_files)}
          helper={`of ${num(scan.total_files)} discovered`}
          tone={scan.skipped_files ? "warn" : undefined}
        />
        <KpiTile
          testId="kpi-tokens-analyzed"
          label="Tokens analysed"
          value={compact(scan.analyzed_tokens)}
          helper="ceil(character_count / 4)"
          icon={FileCode2}
        />
        <KpiTile
          testId="kpi-agent-like-files"
          label="Agent-like files"
          value={num(det.agent_like_files)}
          helper={`${num(det.agent_role_files)} agent roles, ${num(det.skill_files)} skills`}
          icon={Layers}
        />
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <KpiTile
          testId="kpi-duplicate-clusters"
          label="Duplicate clusters found"
          value={num(det.duplicate_clusters_found)}
          helper={`${num(det.repeated_block_groups)} repeated instruction blocks`}
        />
        <KpiTile
          testId="kpi-oversized-context"
          label="Oversized context files"
          value={num(det.oversized_context_files)}
          helper="Over 8,000 estimated tokens"
        />
        <KpiTile
          testId="kpi-overlapping-agents"
          label="Overlapping agent groups"
          value={num(det.overlapping_agent_groups)}
          helper="Agents describing similar work"
        />
        <KpiTile
          testId="kpi-review-stages"
          label="Review stages inferred"
          value={num(det.review_stages_inferred)}
          helper={(det.review_stage_names || []).slice(0, 3).join(", ") || "None detected"}
        />
      </div>

      <section>
        <h2 className="text-h3 font-heading">Category scores</h2>
        <p className="text-sm text-muted-foreground">
          Weighted 25% redundancy, 25% token bloat, 20% review overhead, 20% agent sprawl, 10%
          architecture.
        </p>
        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {(data.category_scores || []).map((c) => (
            <CategoryScoreCard key={c.category} category={c} ledger={data.penalty_ledger} />
          ))}
        </div>
      </section>

      <TopDrivers drivers={data.top_drivers} />

      <IssuesTable issues={data.issues} />

      <ScoreLedger ledger={data.penalty_ledger} />

      <RecommendedActions actions={data.recommended_actions} />

      <DraftPreview
        scanId={scan.id}
        repoName={scan.repo_name}
        drafts={data.drafts}
        candidates={scan.draft_candidates}
        onDraftCreated={load}
      />

      <FileInventory scanId={scan.id} summary={data.inventory_summary} groups={data.inventory_groups} />

      <Card
        className="rounded-xl border border-border bg-card shadow-[var(--shadow-md)]"
        data-testid="skipped-files-panel"
      >
        <div className="border-b border-border p-4">
          <h3 className="font-heading text-lg font-bold">Skipped files and warnings</h3>
          <p className="text-xs text-muted-foreground">
            {skipped.length === 0
              ? "Every discovered file was parsed successfully."
              : `${skipped.length} files were not read. Their metadata is still counted in the report.`}
          </p>
        </div>
        {skipped.length > 0 ? (
          <div className="max-h-80 overflow-auto scrollbar-thin">
            <Table className="drl-table">
              <TableHeader className="sticky top-0 bg-card">
                <TableRow>
                  <TableHead className="text-xs">Path</TableHead>
                  <TableHead className="w-[150px] text-xs">Status</TableHead>
                  <TableHead className="w-[90px] text-right text-xs">Size</TableHead>
                  <TableHead className="text-xs">Reason</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {skipped.slice(0, 200).map((f) => (
                  <TableRow key={f.id} data-testid="skipped-file-row">
                    <TableCell className="max-w-[280px] break-all font-mono text-[11px]">{f.path}</TableCell>
                    <TableCell className="text-xs">{f.parse_status}</TableCell>
                    <TableCell className="num text-right text-xs">{bytes(f.size_bytes)}</TableCell>
                    <TableCell className="text-xs leading-5 text-muted-foreground">{f.skip_reason}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {skipped.length > 200 ? (
              <p className="p-3 text-xs text-muted-foreground">
                Showing the first 200 skipped files of {skipped.length}.
              </p>
            ) : null}
          </div>
        ) : null}
      </Card>

      <AssumptionsReadout assumptions={data.assumptions} />

      <Card className="rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-md)]">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <ShieldQuestion className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
            <div>
              <p className="font-heading text-sm font-bold">Take this to your coding agent</p>
              <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
                Copy a ready-made prompt that lists the top waste drivers and the ranked actions, or download
                the VS Code handoff package.
              </p>
            </div>
          </div>
          <div className="flex gap-2">
            <Button variant="secondary" size="sm" onClick={copyPrompt} data-testid="results-copy-prompt-button">
              <Copy className="mr-1.5 h-3.5 w-3.5" /> Copy summary prompt
            </Button>
            <Button asChild size="sm" data-testid="results-open-handoff-button">
              <Link to={`/scan/${scan.id}/handoff`}>Open handoff</Link>
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}
