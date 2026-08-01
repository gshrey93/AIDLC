import { Card } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { MetaChip } from "@/components/VerdictBadge";
import { CATEGORY_LABELS, compact, money, num } from "@/lib/format";

export const TopDrivers = ({ drivers }) => (
  <Card
    data-testid="results-top-drivers"
    className="rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-md)]"
  >
    <h3 className="font-heading text-lg font-bold">Top 5 waste drivers</h3>
    <p className="text-xs text-muted-foreground">
      Written in plain language so you can share it without translating anything.
    </p>
    <div className="accent-rule mt-3" />
    {(drivers || []).length === 0 ? (
      <p className="mt-3 text-sm text-muted-foreground">
        No waste drivers were detected. Nothing needs consolidating right now.
      </p>
    ) : (
      <ol className="mt-3 space-y-4">
        {drivers.map((d) => (
          <li key={d.issue_id || d.rank} className="flex gap-3" data-testid="top-driver-item">
            <span className="num mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent font-heading text-sm font-bold text-accent-foreground">
              {d.rank}
            </span>
            <div className="min-w-0">
              <p className="font-heading text-sm font-bold">{d.title}</p>
              <p className="mt-1 text-sm leading-6 text-foreground">{d.plain_language}</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <MetaChip label="category" value={d.category} />
                <MetaChip label="tokens/mo" value={compact(d.estimated_token_waste)} tone="warn" />
                <MetaChip label="credits/mo" value={num(d.estimated_credit_waste, 2)} tone="warn" />
                <MetaChip label="cost/mo" value={money(d.estimated_dollar_waste)} tone="bad" />
              </div>
            </div>
          </li>
        ))}
      </ol>
    )}
  </Card>
);

export const RecommendedActions = ({ actions }) => (
  <Card
    data-testid="results-recommended-actions"
    className="rounded-xl border border-border bg-card shadow-[var(--shadow-md)]"
  >
    <div className="border-b border-border p-4">
      <h3 className="font-heading text-lg font-bold">Recommended actions</h3>
      <p className="text-xs text-muted-foreground">
        Ranked by impact first, then by how little effort it takes. Start at the top.
      </p>
    </div>
    <div className="overflow-x-auto scrollbar-thin">
      <Table className="drl-table min-w-[860px]">
        <TableHeader>
          <TableRow>
            <TableHead className="w-[40px] text-xs">#</TableHead>
            <TableHead className="text-xs">Action</TableHead>
            <TableHead className="w-[140px] text-xs">Category</TableHead>
            <TableHead className="w-[90px] text-xs">Impact</TableHead>
            <TableHead className="w-[90px] text-xs">Effort</TableHead>
            <TableHead className="w-[110px] text-right text-xs">Tokens/mo</TableHead>
            <TableHead className="w-[100px] text-right text-xs">$/mo</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {(actions || []).length === 0 ? (
            <TableRow>
              <TableCell colSpan={7} className="py-8 text-center text-sm text-muted-foreground">
                Nothing to act on. This repository is already lean.
              </TableCell>
            </TableRow>
          ) : (
            actions.map((a, i) => (
              <TableRow key={a.issue_id || i} data-testid="recommended-action-row">
                <TableCell className="num text-xs text-muted-foreground">{i + 1}</TableCell>
                <TableCell className="max-w-[420px] text-sm leading-6">{a.action}</TableCell>
                <TableCell className="text-xs">{a.category}</TableCell>
                <TableCell>
                  <MetaChip value={a.impact} tone={a.impact === "High" ? "bad" : "neutral"} />
                </TableCell>
                <TableCell>
                  <MetaChip value={a.effort} tone={a.effort === "Small" ? "good" : "neutral"} />
                </TableCell>
                <TableCell className="num text-right text-sm">
                  {compact(a.estimated_token_reduction)}
                </TableCell>
                <TableCell className="num text-right text-sm font-medium">
                  {money(a.estimated_dollar_savings)}
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  </Card>
);

export const ScoreLedger = ({ ledger }) => (
  <Card
    data-testid="results-score-ledger"
    className="rounded-xl border border-border bg-card shadow-[var(--shadow-md)]"
  >
    <div className="border-b border-border p-4">
      <h3 className="font-heading text-lg font-bold">How the score was calculated</h3>
      <p className="text-xs text-muted-foreground">
        Tier 1 is the specified penalty rules with hard caps. Tier 2 scales with how much of your
        monthly agent context budget each category wastes.
      </p>
    </div>
    <div className="overflow-x-auto scrollbar-thin">
      <Table className="drl-table min-w-[680px]">
        <TableHeader>
          <TableRow>
            <TableHead className="text-xs">Rule</TableHead>
            <TableHead className="w-[70px] text-xs">Tier</TableHead>
            <TableHead className="w-[150px] text-xs">Category</TableHead>
            <TableHead className="w-[70px] text-right text-xs">Hits</TableHead>
            <TableHead className="w-[60px] text-right text-xs">Cap</TableHead>
            <TableHead className="w-[90px] text-right text-xs">Applied</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {(ledger || []).map((r, i) => (
            <TableRow key={i} data-testid="score-ledger-row">
              <TableCell className="max-w-[380px] text-xs">
                <span className="block font-medium leading-5">{r.rule}</span>
                {r.points_each ? (
                  <span className="mt-0.5 block text-[11px] text-muted-foreground">
                    -{r.points_each} points per hit
                  </span>
                ) : null}
                {r.detail ? (
                  <span className="mt-1 block break-words font-mono text-[11px] leading-4 text-muted-foreground">
                    {r.detail}
                  </span>
                ) : null}
              </TableCell>
              <TableCell className="text-xs">{r.tier === "scaling" ? "Tier 2" : "Tier 1"}</TableCell>
              <TableCell className="text-xs">{CATEGORY_LABELS[r.category] || r.category}</TableCell>
              <TableCell className="num text-right text-xs">{num(r.hits)}</TableCell>
              <TableCell className="num text-right text-xs">{num(r.cap)}</TableCell>
              <TableCell className="num text-right text-xs font-bold">-{num(r.applied)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  </Card>
);

export default TopDrivers;
