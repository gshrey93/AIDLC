import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Copy, Download, ExternalLink, Info, Terminal } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/components/ui/sonner";
import { apiError, downloadExport, endpoints } from "@/lib/api";

export default function Handoff() {
  const { scanId } = useParams();
  const [data, setData] = useState(null);
  const [scan, setScan] = useState(null);
  const [uriFailed, setUriFailed] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    endpoints
      .handoff(scanId)
      .then((res) => setData(res.data))
      .catch((err) => toast.error(apiError(err, "Could not build the handoff package")));
    endpoints
      .getScan(scanId)
      .then((res) => setScan(res.data))
      .catch(() => setScan(null));
  }, [scanId]);

  const copy = async (text, label) => {
    try {
      await navigator.clipboard.writeText(text || "");
      toast.success(`${label} copied to clipboard`);
    } catch {
      toast.error("Your browser blocked clipboard access");
    }
  };

  const download = async () => {
    setBusy(true);
    try {
      await downloadExport(scanId, "handoff_zip", `${scan?.repo_name || "scan"}-vscode-handoff.zip`);
      toast.success("Handoff package downloaded");
    } catch (err) {
      toast.error(apiError(err, "Could not build the handoff package"));
    } finally {
      setBusy(false);
    }
  };

  const openVsCode = () => {
    try {
      const before = Date.now();
      window.location.href = "vscode://file/";
      window.setTimeout(() => {
        if (Date.now() - before < 2500 && document.visibilityState === "visible") {
          setUriFailed(true);
          toast.info("Your browser did not open VS Code. Follow the manual steps below.");
        }
      }, 1200);
    } catch {
      setUriFailed(true);
      toast.info("Your browser blocked the vscode:// link. Follow the manual steps below.");
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-mono text-xs uppercase tracking-wide text-muted-foreground">{scanId}</p>
          <h1 className="mt-1 text-h1 font-heading">VS Code handoff</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Move the findings into your coding workflow without editing anything in place. Nothing here
            touches your repository.
          </p>
        </div>
        <Button asChild variant="secondary" size="sm" data-testid="handoff-back-button">
          <Link to={`/scan/${scanId}`}>
            <ArrowLeft className="mr-1.5 h-3.5 w-3.5" /> Back to results
          </Link>
        </Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-md)] lg:col-span-2">
          <h3 className="font-heading text-lg font-bold">Summary prompt</h3>
          <p className="text-xs text-muted-foreground">
            Paste this into your coding agent. It lists the top waste drivers and the ranked actions with
            impact and effort.
          </p>
          {data ? (
            <Textarea
              readOnly
              value={data.prompt}
              className="mt-3 h-64 font-mono text-[11px] leading-5"
              data-testid="handoff-prompt-textarea"
            />
          ) : (
            <Skeleton className="mt-3 h-64 w-full" />
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            <Button
              size="sm"
              onClick={() => copy(data?.prompt, "Summary prompt")}
              disabled={!data}
              data-testid="handoff-copy-prompt-button"
            >
              <Copy className="mr-1.5 h-3.5 w-3.5" /> Copy summary prompt
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => copy(data?.summary_markdown, "efficiency-summary.md")}
              disabled={!data}
              data-testid="handoff-copy-summary-button"
            >
              <Copy className="mr-1.5 h-3.5 w-3.5" /> Copy efficiency-summary.md
            </Button>
          </div>
        </Card>

        <div className="space-y-4">
          <Card className="rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-md)]">
            <h3 className="font-heading text-base font-bold">Handoff package</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              A zip containing everything your agent needs.
            </p>
            <ul className="mt-3 space-y-1">
              {(data?.package_files || []).map((f) => (
                <li key={f} className="font-mono text-[11px] leading-5 text-muted-foreground">
                  {f}
                </li>
              ))}
            </ul>
            {data ? (
              <p className="mt-2 text-xs text-muted-foreground">
                Includes {data.draft_count} optimised draft file{data.draft_count === 1 ? "" : "s"} under
                drafts/.
              </p>
            ) : null}
            <Button
              className="mt-3 w-full"
              onClick={download}
              disabled={busy}
              data-testid="handoff-download-package-button"
            >
              <Download className="mr-1.5 h-3.5 w-3.5" /> {busy ? "Building zip" : "Download handoff package"}
            </Button>
          </Card>

          <Card className="rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-md)]">
            <h3 className="font-heading text-base font-bold">Open locally in VS Code</h3>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              Browsers often block custom URI schemes. If nothing happens, use the manual steps.
            </p>
            <Button
              variant="secondary"
              className="mt-3 w-full"
              onClick={openVsCode}
              data-testid="handoff-open-vscode-button"
            >
              <Terminal className="mr-1.5 h-3.5 w-3.5" /> Open in VS Code
            </Button>
            <div
              className="mt-3 rounded-xl border border-border bg-secondary p-3"
              data-testid="handoff-manual-instructions"
            >
              <p className="flex items-center gap-1.5 text-xs font-semibold">
                <Info className="h-3.5 w-3.5 text-primary" /> Manual steps
                {uriFailed ? <span className="text-destructive">(use these)</span> : null}
              </p>
              <ol className="mt-2 list-decimal space-y-1 pl-4">
                {(data?.manual_instructions || []).map((step) => (
                  <li key={step} className="text-xs leading-5 text-muted-foreground">
                    {step}
                  </li>
                ))}
              </ol>
              {data?.vscode_uri_hint ? (
                <p className="mt-2 break-all font-mono text-[11px] text-muted-foreground">
                  {data.vscode_uri_hint}
                </p>
              ) : null}
            </div>
            <Button
              asChild
              variant="ghost"
              size="sm"
              className="mt-2 w-full"
              data-testid="handoff-open-exports-button"
            >
              <Link to={`/scan/${scanId}/exports`}>
                Other export formats <ExternalLink className="ml-1.5 h-3.5 w-3.5" />
              </Link>
            </Button>
          </Card>
        </div>
      </div>
    </div>
  );
}
