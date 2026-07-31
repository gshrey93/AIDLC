import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { AlertCircle, CheckCircle2, FileUp, Github, GitBranch, Loader2, Upload } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "@/components/ui/sonner";
import { InfoNote } from "@/components/WarningBanner";
import { apiError, endpoints } from "@/lib/api";
import { BITBUCKET_RE, GITHUB_RE, bytes } from "@/lib/format";

const MAX_BYTES = 250 * 1024 * 1024;
const RIGHTS_TEXT = "I confirm I have the right to analyze this repository content";

const SOURCES = [
  { key: "github", label: "GitHub", icon: Github },
  { key: "bitbucket", label: "Bitbucket", icon: GitBranch },
  { key: "zip", label: "Zip upload", icon: Upload },
  { key: "md", label: "Markdown files", icon: FileUp },
];

export default function NewScan() {
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  const prefill = location.state?.prefill || {};
  const [source, setSource] = useState(prefill.source_type || params.get("source") || "github");
  const [repoUrl, setRepoUrl] = useState(prefill.repo_url || "");
  const [branch, setBranch] = useState(prefill.branch || "");
  const [zipFile, setZipFile] = useState(null);
  const [mdFiles, setMdFiles] = useState([]);
  const [rights, setRights] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const zipInput = useRef(null);
  const mdInput = useRef(null);

  useEffect(() => {
    if (prefill.notice) toast.info(prefill.notice);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const urlError = useMemo(() => {
    if (source !== "github" && source !== "bitbucket") return "";
    if (!repoUrl.trim()) return "";
    const re = source === "github" ? GITHUB_RE : BITBUCKET_RE;
    if (!re.test(repoUrl.trim())) {
      return source === "github"
        ? "Use the form https://github.com/{owner}/{repo}"
        : "Use the form https://bitbucket.org/{workspace}/{repo}";
    }
    return "";
  }, [repoUrl, source]);

  const zipError = useMemo(() => {
    if (source !== "zip" || !zipFile) return "";
    if (!zipFile.name.toLowerCase().endsWith(".zip")) return "Only .zip archives are accepted";
    if (zipFile.size > MAX_BYTES) return `That zip is ${bytes(zipFile.size)} which is over the 250 MB limit`;
    return "";
  }, [zipFile, source]);

  const mdError = useMemo(() => {
    if (source !== "md" || mdFiles.length === 0) return "";
    const bad = mdFiles.filter((f) => !f.name.toLowerCase().endsWith(".md"));
    if (bad.length) return `Only .md files are accepted. Remove: ${bad.map((f) => f.name).join(", ")}`;
    const total = mdFiles.reduce((a, f) => a + f.size, 0);
    if (total > MAX_BYTES) return "Those files add up to more than 250 MB";
    return "";
  }, [mdFiles, source]);

  const inputValid = useMemo(() => {
    if (source === "github" || source === "bitbucket") return Boolean(repoUrl.trim()) && !urlError;
    if (source === "zip") return Boolean(zipFile) && !zipError;
    return mdFiles.length > 0 && !mdError;
  }, [source, repoUrl, urlError, zipFile, zipError, mdFiles, mdError]);

  const canStart = inputValid && rights && !submitting;

  const start = async () => {
    if (!canStart) return;
    setSubmitting(true);
    const form = new FormData();
    form.append("source_type", source);
    form.append("rights_ack", "true");
    if (source === "github" || source === "bitbucket") {
      form.append("repo_url", repoUrl.trim());
      if (branch.trim()) form.append("branch", branch.trim());
    } else if (source === "zip") {
      form.append("zip_file", zipFile);
    } else {
      mdFiles.forEach((f) => form.append("md_files", f));
    }
    try {
      const res = await endpoints.createScan(form);
      toast.success(`Scan ${res.data.id} started`);
      navigate(`/scan/${res.data.id}/progress`);
    } catch (err) {
      toast.error(apiError(err, "The scan could not be started"));
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-h1 font-heading">New scan</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Up to 1,500 files or 250 MB compressed, whichever comes first. Single files over 5 MB are listed
          but not read.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="rounded-xl border border-border bg-card p-5 shadow-[var(--shadow-md)] lg:col-span-2">
          <Label className="text-xs uppercase tracking-wide text-muted-foreground">Scan source</Label>
          <Tabs value={source} onValueChange={setSource} className="mt-2">
            <TabsList
              className="grid h-auto w-full grid-cols-2 gap-1 bg-secondary sm:grid-cols-4"
              data-testid="scan-source-tabs"
            >
              {SOURCES.map((s) => (
                <TabsTrigger
                  key={s.key}
                  value={s.key}
                  className="gap-1.5 text-xs sm:text-sm"
                  data-testid={`scan-source-tab-${s.key}`}
                >
                  <s.icon className="h-3.5 w-3.5" /> {s.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>

          <div className="mt-5 space-y-4">
            {source === "github" || source === "bitbucket" ? (
              <>
                <div>
                  <Label htmlFor="repo-url" className="text-sm">
                    Repository URL
                  </Label>
                  <Input
                    id="repo-url"
                    data-testid="scan-repo-url-input"
                    className="mt-1.5"
                    placeholder={
                      source === "github"
                        ? "https://github.com/owner/repo"
                        : "https://bitbucket.org/workspace/repo"
                    }
                    value={repoUrl}
                    onChange={(e) => setRepoUrl(e.target.value)}
                  />
                  {urlError ? (
                    <p className="mt-1.5 flex items-center gap-1.5 text-xs text-destructive" data-testid="scan-url-error">
                      <AlertCircle className="h-3.5 w-3.5" /> {urlError}
                    </p>
                  ) : repoUrl.trim() ? (
                    <p className="mt-1.5 flex items-center gap-1.5 text-xs score-good">
                      <CheckCircle2 className="h-3.5 w-3.5" /> That URL looks right
                    </p>
                  ) : (
                    <p className="mt-1.5 text-xs text-muted-foreground">
                      Public repositories only in this version.
                    </p>
                  )}
                </div>
                <div>
                  <Label htmlFor="branch" className="text-sm">
                    Branch <span className="text-muted-foreground">(optional)</span>
                  </Label>
                  <Input
                    id="branch"
                    data-testid="scan-branch-input"
                    className="mt-1.5"
                    placeholder="Leave blank to use the default branch"
                    value={branch}
                    onChange={(e) => setBranch(e.target.value)}
                  />
                </div>
              </>
            ) : null}

            {source === "zip" ? (
              <div>
                <Label className="text-sm">Repository zip</Label>
                <div
                  className="mt-1.5 flex flex-col items-start gap-3 rounded-xl border border-dashed border-border bg-secondary p-5"
                  data-testid="scan-zip-dropzone"
                >
                  <input
                    ref={zipInput}
                    type="file"
                    accept=".zip"
                    className="hidden"
                    data-testid="scan-zip-picker"
                    onChange={(e) => setZipFile(e.target.files?.[0] || null)}
                  />
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => zipInput.current?.click()}
                    data-testid="scan-zip-choose-button"
                  >
                    <Upload className="mr-1.5 h-4 w-4" /> Choose a .zip file
                  </Button>
                  {zipFile ? (
                    <p className="break-all font-mono text-xs" data-testid="scan-zip-filename">
                      {zipFile.name} &middot; {bytes(zipFile.size)}
                    </p>
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      Export your repository as a zip, for example from GitHub &rarr; Code &rarr; Download
                      ZIP.
                    </p>
                  )}
                </div>
                {zipError ? (
                  <p className="mt-1.5 flex items-center gap-1.5 text-xs text-destructive" data-testid="scan-zip-error">
                    <AlertCircle className="h-3.5 w-3.5" /> {zipError}
                  </p>
                ) : null}
              </div>
            ) : null}

            {source === "md" ? (
              <div>
                <Label className="text-sm">Markdown files</Label>
                <div
                  className="mt-1.5 flex flex-col items-start gap-3 rounded-xl border border-dashed border-border bg-secondary p-5"
                  data-testid="scan-md-dropzone"
                >
                  <input
                    ref={mdInput}
                    type="file"
                    accept=".md"
                    multiple
                    className="hidden"
                    data-testid="scan-md-picker"
                    onChange={(e) => setMdFiles(Array.from(e.target.files || []))}
                  />
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => mdInput.current?.click()}
                    data-testid="scan-md-choose-button"
                  >
                    <FileUp className="mr-1.5 h-4 w-4" /> Choose .md files
                  </Button>
                  {mdFiles.length ? (
                    <ul className="space-y-0.5" data-testid="scan-md-filelist">
                      {mdFiles.map((f) => (
                        <li key={f.name} className="break-all font-mono text-xs">
                          {f.name} &middot; {bytes(f.size)}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      Upload at least 5 markdown files. Fewer than 5 parsed text files means we cannot score
                      the scan.
                    </p>
                  )}
                </div>
                {mdError ? (
                  <p className="mt-1.5 flex items-center gap-1.5 text-xs text-destructive" data-testid="scan-md-error">
                    <AlertCircle className="h-3.5 w-3.5" /> {mdError}
                  </p>
                ) : mdFiles.length > 0 && mdFiles.length < 5 ? (
                  <p className="mt-1.5 text-xs score-warn" data-testid="scan-md-warning">
                    Only {mdFiles.length} file{mdFiles.length === 1 ? "" : "s"} selected. The scan will finish
                    with the status InsufficientData unless at least 5 files are parsed.
                  </p>
                ) : null}
              </div>
            ) : null}

            <div className="rounded-xl border border-border bg-secondary p-4">
              <label className="flex cursor-pointer items-start gap-3">
                <Checkbox
                  checked={rights}
                  onCheckedChange={(v) => setRights(Boolean(v))}
                  data-testid="scan-rights-checkbox"
                  className="mt-0.5"
                />
                <span className="text-sm leading-6">{RIGHTS_TEXT}</span>
              </label>
              <p className="mt-2 pl-8 text-xs text-muted-foreground">
                Required before a scan can start. We only read text files and never write to your
                repository.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <Button size="lg" disabled={!canStart} onClick={start} data-testid="scan-start-button">
                {submitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                {submitting ? "Starting scan" : "Start scan"}
              </Button>
              {!rights ? (
                <p className="text-xs text-muted-foreground">Tick the confirmation to enable the scan.</p>
              ) : !inputValid ? (
                <p className="text-xs text-muted-foreground">Add a valid source to enable the scan.</p>
              ) : null}
            </div>
          </div>
        </Card>

        <div className="space-y-4">
          <InfoNote testId="newscan-limits">
            <p className="font-semibold">Limits and rules</p>
            <ul className="mt-1.5 space-y-1 text-xs leading-5 text-muted-foreground">
              <li>Up to 1,500 files, up to 250 MB compressed.</li>
              <li>Files over 5 MB are listed as SkippedOversized.</li>
              <li>Unsupported extensions are listed as SkippedUnsupported.</li>
              <li>At least 5 text files must parse or the scan is marked InsufficientData.</li>
              <li>More than 20% skipped adds a PartialScan badge.</li>
            </ul>
          </InfoNote>

          <Card className="rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-md)]">
            <p className="font-heading text-sm font-bold">Supported file types</p>
            <p className="mt-1.5 font-mono text-[11px] leading-5 text-muted-foreground">
              .md .txt .json .yaml .yml .mmd .ts .tsx .js .jsx .py .go .java .rb .rs .cs
            </p>
            <p className="mt-3 font-heading text-sm font-bold">Treated as agent assets</p>
            <p className="mt-1.5 font-mono text-[11px] leading-5 text-muted-foreground">
              *.agent.md, instruction.md, instructions.md, orchestrator.md, workflow.md, context.md,
              prompt.md, memory.md, system.md, /agents/, /skills/, /prompts/, /context/, /memory/
            </p>
          </Card>

          <Card className="rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-md)]">
            <p className="font-heading text-sm font-bold">Hitting GitHub rate limits?</p>
            <p className="mt-1.5 text-xs leading-5 text-muted-foreground">
              Unauthenticated GitHub allows about 60 requests per hour. Add a personal access token in{" "}
              <Link to="/settings" className="text-primary underline">
                Settings
              </Link>{" "}
              for a higher limit.
            </p>
          </Card>
        </div>
      </div>
    </div>
  );
}
