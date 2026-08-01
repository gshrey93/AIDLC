import { useState } from "react";
import { Copy, Download, FileText, Sparkles } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { toast } from "@/components/ui/sonner";
import { MetaChip } from "@/components/VerdictBadge";
import { apiError, downloadExport, endpoints } from "@/lib/api";
import { num } from "@/lib/format";

export const DraftPreview = ({ scanId, repoName, drafts, candidates, onDraftCreated }) => {
  const [active, setActive] = useState(drafts?.[0]?.source_path || "");
  const [generating, setGenerating] = useState("");
  const list = drafts || [];
  const done = new Set(list.map((d) => d.source_path));
  const pending = (candidates || []).filter((c) => !done.has(c.source_path));

  const copyDraft = async (draft) => {
    try {
      await navigator.clipboard.writeText(draft.draft_content || "");
      toast.success(`${draft.target_filename} copied to clipboard`);
    } catch {
      toast.error("Your browser blocked clipboard access");
    }
  };

  const generate = async (sourcePath) => {
    setGenerating(sourcePath);
    try {
      const res = await endpoints.createDraft(scanId, sourcePath);
      toast.success(`${res.data.target_filename} generated`);
      if (onDraftCreated) await onDraftCreated();
      setActive(res.data.source_path);
    } catch (err) {
      toast.error(apiError(err, "Draft generation failed"));
    } finally {
      setGenerating("");
    }
  };

  const downloadZip = async () => {
    try {
      await downloadExport(scanId, "draft_zip", `${repoName || "scan"}-drafts.zip`);
      toast.success("Draft package downloaded");
    } catch (err) {
      toast.error(apiError(err, "Could not build the draft zip"));
    }
  };

  return (
    <Card
      data-testid="draft-preview"
      className="rounded-xl border border-border bg-card shadow-[var(--shadow-md)]"
    >
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border p-4">
        <div>
          <h3 className="font-heading text-lg font-bold">Draft replacement files</h3>
          <p className="text-xs text-muted-foreground">
            Each draft is a rewritten version of a file that already exists in your repository. The
            filename gets an -optimised suffix so nothing is overwritten. Up to 25 drafts per scan.
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={downloadZip}
          data-testid="draft-download-zip-button"
        >
          <Download className="mr-1.5 h-3.5 w-3.5" /> Download drafts zip
        </Button>
      </div>

      {list.length === 0 ? (
        <div className="p-4">
          <p className="text-sm text-muted-foreground">
            No drafts have been written yet. Pick an eligible file below and we will rewrite it with the
            model.
          </p>
        </div>
      ) : (
        <div className="p-4">
          {/* Identity comes from source_path: it is unique per scan (one draft per file). */}
          <Tabs value={active || list[0].source_path} onValueChange={setActive}>
            <TabsList
              className="flex h-auto w-full flex-wrap justify-start gap-1 bg-secondary"
              data-testid="draft-tabs"
            >
              {list.map((d) => (
                <TabsTrigger
                  key={d.source_path}
                  value={d.source_path}
                  className="text-xs"
                  data-testid={`draft-tab-${d.id}`}
                >
                  {d.target_filename}
                </TabsTrigger>
              ))}
            </TabsList>
            {list.map((d) => (
              <TabsContent key={d.source_path} value={d.source_path} className="mt-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-heading text-sm font-bold">{d.target_filename}</p>
                    <p className="break-all font-mono text-[11px] text-muted-foreground">
                      rewritten from {d.source_path}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => copyDraft(d)}
                    data-testid={`draft-copy-button-${d.id}`}
                  >
                    <Copy className="mr-1.5 h-3.5 w-3.5" /> Copy draft
                  </Button>
                </div>

                <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                  <div className="rounded-xl border border-border bg-secondary p-3">
                    <p className="text-[11px] uppercase text-muted-foreground">Original</p>
                    <p className="num font-heading text-base font-bold">{num(d.original_tokens)} tokens</p>
                  </div>
                  <div className="rounded-xl border border-border bg-secondary p-3">
                    <p className="text-[11px] uppercase text-muted-foreground">Optimised</p>
                    <p className="num font-heading text-base font-bold">{num(d.draft_tokens)} tokens</p>
                  </div>
                  <div className="rounded-xl border border-border bg-secondary p-3">
                    <p className="text-[11px] uppercase text-muted-foreground">Reduction</p>
                    <p className="num font-heading text-base font-bold score-good">
                      -{d.reduction_pct}%
                    </p>
                  </div>
                  <div className="rounded-xl border border-border bg-secondary p-3">
                    <p className="text-[11px] uppercase text-muted-foreground">Written by</p>
                    <p className="font-mono text-[11px] leading-5">{d.model}</p>
                  </div>
                </div>

                <div className="mt-3 flex flex-wrap gap-1.5">
                  <MetaChip label="type" value={d.target_type} />
                  <MetaChip label="impact" value={d.impact} tone={d.impact === "High" ? "bad" : "neutral"} />
                  <MetaChip label="effort" value={d.effort} tone={d.effort === "Small" ? "good" : "neutral"} />
                  <MetaChip label="saves per load" value={`${num(d.tokens_saved_per_load)} tokens`} tone="good" />
                </div>

                <pre
                  className="markdown-preview mt-3 max-h-[420px] overflow-auto rounded-xl border border-border bg-secondary p-3 font-mono text-[11px] leading-5 scrollbar-thin"
                  data-testid={`draft-content-${d.id}`}
                >
                  {d.draft_content}
                </pre>

                {d.quality_warning ? (
                  <div className="alert alert-warning mt-3" data-testid={`draft-quality-warning-${d.id}`}>
                    <p className="text-xs leading-5">{d.quality_warning}</p>
                  </div>
                ) : null}
              </TabsContent>
            ))}
          </Tabs>
        </div>
      )}

      {pending.length > 0 ? (
        <div className="border-t border-border p-4">
          <p className="font-heading text-sm font-bold">
            Eligible files you can still rewrite ({pending.length})
          </p>
          <p className="text-xs text-muted-foreground">
            Only agent, instruction, orchestration, context and memory files are eligible. Source code is
            never rewritten.
          </p>
          <div className="mt-3 max-h-72 overflow-auto scrollbar-thin">
            <Table className="drl-table">
              <TableHeader className="sticky top-0 bg-card">
                <TableRow>
                  <TableHead className="text-xs">File</TableHead>
                  <TableHead className="text-xs">Type</TableHead>
                  <TableHead className="text-right text-xs">Tokens</TableHead>
                  <TableHead className="text-xs">Impact / effort</TableHead>
                  <TableHead className="text-right text-xs">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {pending.slice(0, 25).map((c) => (
                  <TableRow key={c.source_path}>
                    <TableCell className="max-w-[280px] break-all font-mono text-[11px]">
                      {c.source_path}
                      <span className="mt-0.5 flex items-center gap-1 text-[11px] text-muted-foreground">
                        <FileText className="h-3 w-3" /> {c.target_filename}
                      </span>
                    </TableCell>
                    <TableCell className="text-xs">{c.target_type}</TableCell>
                    <TableCell className="num text-right text-xs">{num(c.source_tokens)}</TableCell>
                    <TableCell className="text-xs">
                      <div className="flex gap-1">
                        <MetaChip value={c.impact} />
                        <MetaChip value={c.effort} />
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={Boolean(generating)}
                        onClick={() => generate(c.source_path)}
                        data-testid="draft-generate-button"
                      >
                        <Sparkles className="mr-1.5 h-3.5 w-3.5" />
                        {generating === c.source_path ? "Writing" : "Generate"}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      ) : null}
    </Card>
  );
};

export default DraftPreview;
