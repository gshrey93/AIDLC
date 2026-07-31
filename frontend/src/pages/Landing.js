import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  Copy,
  FileSearch,
  Gauge,
  Github,
  ListChecks,
  ShieldCheck,
  Sparkles,
  Upload,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import KpiTile from "@/components/KpiTile";
import { endpoints } from "@/lib/api";
import { compact, money, num } from "@/lib/format";

const STEPS = [
  {
    icon: Upload,
    title: "1. Point us at your repository",
    body: "Import a public GitHub or Bitbucket repo, or upload a zip export or a handful of markdown files.",
  },
  {
    icon: FileSearch,
    title: "2. We read your agent files",
    body: "We classify agents, skills, prompts, context and memory files, count tokens, and look for repeated instructions.",
  },
  {
    icon: ListChecks,
    title: "3. You get a verdict and a to-do list",
    body: "A 0 to 100 efficiency score, a plain-language list of what is costing you money, and rewritten files you can copy.",
  },
];

export default function Landing() {
  const [stats, setStats] = useState(null);

  useEffect(() => {
    endpoints
      .overview()
      .then((res) => setStats(res.data))
      .catch(() => setStats(null));
  }, []);

  return (
    <div className="space-y-10">
      <section className="bg-hero -mx-4 rounded-none px-4 py-10 sm:-mx-6 sm:px-6 sm:py-14 lg:-mx-8 lg:rounded-3xl lg:px-10">
        <div className="flex flex-wrap items-center gap-2">
          <p className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1 text-xs font-medium text-muted-foreground">
            <Gauge className="h-3.5 w-3.5 text-primary" /> Agentic repository efficiency audit
          </p>
          <p className="inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
            <Sparkles className="h-3.5 w-3.5" /> Built by AI for AI Agents
          </p>
        </div>
        <h1 className="mt-5 max-w-3xl text-h1 font-heading tracking-tight">
          Find out how much your agent instructions are quietly costing you.
        </h1>
        <p className="mt-4 max-w-2xl text-base leading-7 text-muted-foreground md:text-lg">
          Bloat Guardian is an AI tool built by AI to analyze the markdown and config files driving your coding agents — finding duplicated instructions, oversized context files, and extra review loops, and telling you in plain language what to delete and what it saves.
        </p>
        <div className="mt-7 flex flex-wrap gap-3">
          <Button asChild size="lg" className="rounded-xl" data-testid="landing-scan-github-button">
            <Link to="/scan/new?source=github">
              <Github className="mr-2 h-4 w-4" /> Scan a GitHub repo
            </Link>
          </Button>
          <Button
            asChild
            size="lg"
            variant="secondary"
            className="rounded-xl border border-border"
            data-testid="landing-upload-zip-button"
          >
            <Link to="/scan/new?source=zip">
              <Upload className="mr-2 h-4 w-4" /> Upload repo zip
            </Link>
          </Button>
          <Button asChild size="lg" variant="ghost" className="rounded-xl" data-testid="landing-history-button">
            <Link to="/history">
              See example scans <ArrowRight className="ml-2 h-4 w-4" />
            </Link>
          </Button>
        </div>
      </section>

      <section>
        <div className="flex items-end justify-between gap-3">
          <div>
            <h2 className="text-h3 font-heading">What Bloat Guardian has found so far</h2>
            <p className="text-sm text-muted-foreground">
              Totals across every completed scan in this workspace, including the seeded demo history.
            </p>
          </div>
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <KpiTile
            testId="landing-metric-duplicate-clusters"
            label="Redundant file groups found"
            value={num(stats?.duplicate_clusters_found)}
            helper="Groups of near-identical files across all scans"
            loading={!stats}
            icon={Copy}
          />
          <KpiTile
            testId="landing-metric-token-waste"
            label="Estimated monthly token waste"
            value={compact(stats?.estimated_monthly_token_waste)}
            helper={`About ${num(stats?.estimated_monthly_credit_waste, 0)} report credits per month`}
            loading={!stats}
            tone="warn"
          />
          <KpiTile
            testId="landing-metric-dollar-waste"
            label="Estimated monthly cost of waste"
            value={money(stats?.estimated_monthly_dollar_waste)}
            helper="Using your savings assumptions"
            loading={!stats}
            tone="bad"
          />
          <KpiTile
            testId="landing-metric-consolidate"
            label="Files recommended to consolidate"
            value={num(stats?.files_recommended_to_consolidate)}
            helper="Agent, instruction, context and memory files"
            loading={!stats}
          />
        </div>
      </section>

      <section>
        <h2 className="text-h3 font-heading">How it works</h2>
        <div className="accent-rule mt-2" />
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          {STEPS.map((s) => (
            <Card key={s.title} className="rounded-xl border border-border bg-card p-5 shadow-[var(--shadow-md)]">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-accent-foreground">
                <s.icon className="h-5 w-5" />
              </span>
              <h3 className="mt-3 font-heading text-base font-bold">{s.title}</h3>
              <p className="mt-1.5 text-sm leading-6 text-muted-foreground">{s.body}</p>
            </Card>
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-h3 font-heading">What we score</h2>
        <div className="accent-rule mt-2" />
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {[
            ["Redundancy", "25%", "Near-identical files and instruction blocks pasted in more than once."],
            ["Token bloat", "25%", "Context and memory files that are far bigger than a healthy budget."],
            ["Review overhead", "20%", "Approval chains and review gates that repeat the same work."],
            ["Agent sprawl", "20%", "More agent, skill and prompt files than the repository needs."],
            ["Architecture", "10%", "Service layout that does not match the amount of code in it."],
          ].map(([title, weight, body]) => (
            <Card key={title} className="rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-md)]">
              <div className="flex items-center justify-between">
                <p className="font-heading text-sm font-bold">{title}</p>
                <span className="num rounded-full bg-secondary px-2 py-0.5 text-[11px] font-semibold">
                  {weight}
                </span>
              </div>
              <p className="mt-2 text-xs leading-5 text-muted-foreground">{body}</p>
            </Card>
          ))}
        </div>
      </section>

      <section>
        <Card className="rounded-xl border border-border bg-card p-5 shadow-[var(--shadow-md)]">
          <div className="flex items-start gap-3">
            <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
            <div>
              <h3 className="font-heading text-base font-bold">Your content, your call</h3>
              <p className="mt-1.5 max-w-3xl text-sm leading-6 text-muted-foreground">
                Before any scan starts you have to confirm that you have the right to analyse the
                repository content. We never write to your repository. Imported content is deleted after 7
                days and derived reports after 30 days. Redacted reports replace exact file names with
                aliases so you can share findings safely.
              </p>
            </div>
          </div>
        </Card>
      </section>
    </div>
  );
}
