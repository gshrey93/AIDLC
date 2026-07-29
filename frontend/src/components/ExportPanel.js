import { useEffect, useState } from "react";
import { Download, ExternalLink, FileSpreadsheet, FileText, Loader2, Package, Printer } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/sonner";
import { apiError, downloadExport, endpoints, printViewUrl } from "@/lib/api";
import { num } from "@/lib/format";

const ACTIONS = [
  {
    key: "pdf_full",
    label: "Full report PDF",
    description: "Everything: scores, findings with evidence, inventory, drafts. Capped at 40 pages.",
    icon: FileText,
    testId: "export-download-full-pdf",
    ext: "full-report.pdf",
  },
  {
    key: "pdf_redacted",
    label: "Redacted report PDF",
    description: "Safe to share outside your team. File names become aliases, contents removed. Capped at 25 pages.",
    icon: FileText,
    testId: "export-download-redacted-pdf",
    ext: "redacted-report.pdf",
  },
  {
    key: "csv",
    label: "Findings CSV",
    description: "One row per issue with token, credit and dollar waste plus the formula used.",
    icon: FileSpreadsheet,
    testId: "export-download-csv",
    ext: "findings.csv",
  },
  {
    key: "draft_zip",
    label: "Draft files zip",
    description: "Every -optimised draft plus a README explaining how to apply them.",
    icon: Package,
    testId: "export-download-drafts-zip",
    ext: "drafts.zip",
  },
];

export const ExportPanel = ({ scanId, repoName }) => {
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState("");
  const [failed, setFailed] = useState({});

  useEffect(() => {
    endpoints
      .exportPreview(scanId)
      .then((res) => setPreview(res.data))
      .catch(() => setPreview(null));
  }, [scanId]);

  const run = async (action) => {
    setBusy(action.key);
    try {
      await downloadExport(scanId, action.key, `${repoName || "scan"}-${scanId}-${action.ext}`);
      toast.success(`${action.label} downloaded`);
      setFailed((f) => ({ ...f, [action.key]: false }));
    } catch (err) {
      setFailed((f) => ({ ...f, [action.key]: true }));
      toast.error(apiError(err, `${action.label} failed. Use the fallback below.`));
    } finally {
      setBusy("");
    }
  };

  const copyCsvFallback = async () => {
    try {
      const res = await endpoints.getResults(scanId);
      const rows = (res.data.issues || []).map((i) =>
        [
          i.id,
          i.severity,
          i.category,
          (i.title || "").replace(/\t/g, " "),
          i.impacted_file_count,
          i.estimated_token_waste,
          i.estimated_credit_waste,
          i.estimated_dollar_waste,
        ].join("\t"),
      );
      await navigator.clipboard.writeText(
        ["issue_id\tseverity\tcategory\ttitle\tfiles\ttokens_per_month\tcredits_per_month\tdollars_per_month", ...rows].join("\n"),
      );
      toast.success(`Copied ${rows.length} findings to your clipboard`);
    } catch (err) {
      toast.error(apiError(err, "Clipboard copy failed"));
    }
  };

  return (
    <div className="grid gap-4 lg:grid-cols-5" data-testid="export-drawer">
      <Card className="rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-md)] lg:col-span-3">
        <h3 className="font-heading text-lg font-bold">Downloads</h3>
        <p className="text-xs text-muted-foreground">
          Reports are generated on demand from the stored scan data.
        </p>
        <div className="mt-4 space-y-3">
          {ACTIONS.map((action) => (
            <div
              key={action.key}
              className="flex flex-col gap-3 rounded-xl border border-border bg-secondary p-3 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="flex min-w-0 items-start gap-3">
                <action.icon className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
                <div className="min-w-0">
                  <p className="text-sm font-medium">{action.label}</p>
                  <p className="text-xs leading-5 text-muted-foreground">{action.description}</p>
                  {failed[action.key] ? (
                    <p className="mt-1 text-xs font-medium text-destructive">
                      That download failed. Use the fallback on the right.
                    </p>
                  ) : null}
                </div>
              </div>
              <Button
                size="sm"
                onClick={() => run(action)}
                disabled={busy === action.key}
                data-testid={action.testId}
                className="shrink-0"
              >
                {busy === action.key ? (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Download className="mr-1.5 h-3.5 w-3.5" />
                )}
                Download
              </Button>
            </div>
          ))}
        </div>
      </Card>

      <div className="space-y-4 lg:col-span-2">
        <Card className="rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-md)]">
          <h3 className="font-heading text-base font-bold">What is inside</h3>
          {preview ? (
            <>
              <div className="mt-3 grid grid-cols-2 gap-2">
                {[
                  ["Files", num(preview.file_count)],
                  ["Issues", num(preview.issue_count)],
                  ["Drafts", num(preview.draft_count)],
                  ["Skipped files", num(preview.skipped_count)],
                ].map(([k, v]) => (
                  <div key={k} className="rounded-xl border border-border bg-secondary p-2.5">
                    <p className="text-[11px] uppercase text-muted-foreground">{k}</p>
                    <p className="num font-heading text-base font-bold">{v}</p>
                  </div>
                ))}
              </div>
              <p className="mt-3 text-xs font-semibold">Included sections</p>
              <ul className="mt-1 space-y-1">
                {preview.included_sections.map((s) => (
                  <li key={s} className="flex gap-1.5 text-xs leading-5 text-muted-foreground">
                    <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-primary" />
                    {s}
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-xs font-semibold">Redaction rules</p>
              <ul className="mt-1 space-y-1">
                {preview.redaction_rules.map((s) => (
                  <li key={s} className="flex gap-1.5 text-xs leading-5 text-muted-foreground">
                    <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-[color:var(--warning)]" />
                    {s}
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="mt-2 text-sm text-muted-foreground">Loading preview...</p>
          )}
        </Card>

        <Card className="rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-md)]">
          <h3 className="font-heading text-base font-bold">If a download fails</h3>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            PDFs fall back to a printable HTML view. CSV falls back to copy to clipboard.
          </p>
          <div className="mt-3 flex flex-col gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => window.open(printViewUrl(scanId, false), "_blank", "noopener")}
              data-testid="export-print-fallback"
            >
              <Printer className="mr-1.5 h-3.5 w-3.5" /> Open printable full report
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => window.open(printViewUrl(scanId, true), "_blank", "noopener")}
              data-testid="export-print-redacted-fallback"
            >
              <ExternalLink className="mr-1.5 h-3.5 w-3.5" /> Open printable redacted report
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={copyCsvFallback}
              data-testid="export-csv-clipboard-fallback"
            >
              <FileSpreadsheet className="mr-1.5 h-3.5 w-3.5" /> Copy findings to clipboard
            </Button>
          </div>
        </Card>
      </div>
    </div>
  );
};

export default ExportPanel;
