import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, Copy, Eye, Search } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { toast } from "@/components/ui/sonner";
import { SeverityChip, MetaChip } from "@/components/VerdictBadge";
import { CATEGORY_LABELS, compact, money, num } from "@/lib/format";

const PAGE_SIZE = 25;
const SEVERITY_ORDER = { critical: 0, high: 1, medium: 2, low: 3 };

export const IssuesTable = ({ issues }) => {
  const [query, setQuery] = useState("");
  const [severity, setSeverity] = useState("all");
  const [category, setCategory] = useState("all");
  const [sortKey, setSortKey] = useState("estimated_token_waste");
  const [sortDir, setSortDir] = useState("desc");
  const [page, setPage] = useState(0);
  const [active, setActive] = useState(null);

  const categories = useMemo(
    () => Array.from(new Set((issues || []).map((i) => i.category))),
    [issues],
  );

  const filtered = useMemo(() => {
    let rows = [...(issues || [])];
    if (severity !== "all") rows = rows.filter((r) => r.severity === severity);
    if (category !== "all") rows = rows.filter((r) => r.category === category);
    if (query.trim()) {
      const q = query.trim().toLowerCase();
      rows = rows.filter(
        (r) =>
          (r.title || "").toLowerCase().includes(q) ||
          (r.id || "").toLowerCase().includes(q) ||
          (r.evidence || "").toLowerCase().includes(q) ||
          (r.impacted_files || []).some((f) => f.toLowerCase().includes(q)),
      );
    }
    rows.sort((a, b) => {
      let av;
      let bv;
      if (sortKey === "severity") {
        av = SEVERITY_ORDER[a.severity] ?? 9;
        bv = SEVERITY_ORDER[b.severity] ?? 9;
      } else if (sortKey === "title" || sortKey === "category") {
        av = (a[sortKey] || "").toLowerCase();
        bv = (b[sortKey] || "").toLowerCase();
      } else {
        av = Number(a[sortKey] || 0);
        bv = Number(b[sortKey] || 0);
      }
      if (av < bv) return sortDir === "asc" ? -1 : 1;
      if (av > bv) return sortDir === "asc" ? 1 : -1;
      return 0;
    });
    return rows;
  }, [issues, severity, category, query, sortKey, sortDir]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const rows = filtered.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE);

  const sortButton = (key, label, align = "left") => (
    <button
      type="button"
      onClick={() => {
        if (sortKey === key) setSortDir(sortDir === "asc" ? "desc" : "asc");
        else {
          setSortKey(key);
          setSortDir("desc");
        }
      }}
      aria-sort={sortKey === key ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
      data-testid={`issues-sort-${key}`}
      className={`flex w-full items-center gap-1 text-xs font-semibold ${align === "right" ? "justify-end" : ""}`}
    >
      {label}
      {sortKey === key ? (
        sortDir === "asc" ? (
          <ArrowUp className="h-3 w-3" />
        ) : (
          <ArrowDown className="h-3 w-3" />
        )
      ) : null}
    </button>
  );

  const copyRecommendation = async (issue) => {
    try {
      await navigator.clipboard.writeText(`${issue.title}\n\n${issue.recommendation}`);
      toast.success("Recommendation copied to clipboard");
    } catch {
      toast.error("Your browser blocked clipboard access");
    }
  };

  const copyTable = async () => {
    const header = "issue_id\tseverity\tcategory\ttitle\ttokens_per_month\tcredits_per_month\tdollars_per_month";
    const body = filtered
      .map((r) =>
        [
          r.id,
          r.severity,
          r.category,
          r.title,
          r.estimated_token_waste,
          r.estimated_credit_waste,
          r.estimated_dollar_waste,
        ].join("\t"),
      )
      .join("\n");
    try {
      await navigator.clipboard.writeText(`${header}\n${body}`);
      toast.success(`Copied ${filtered.length} findings to clipboard`);
    } catch {
      toast.error("Your browser blocked clipboard access");
    }
  };

  return (
    <Card className="rounded-xl border border-border bg-card shadow-[var(--shadow-md)]">
      <div className="flex flex-col gap-3 border-b border-border p-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h3 className="font-heading text-lg font-bold">Findings</h3>
          <p className="text-xs text-muted-foreground">
            {filtered.length} of {(issues || []).length} issues shown. Open any row to see the evidence
            and the formula behind it.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setPage(0);
              }}
              placeholder="Search findings or file paths"
              className="h-9 w-full pl-8 sm:w-56"
              data-testid="issues-search-input"
            />
          </div>
          <Select
            value={severity}
            onValueChange={(v) => {
              setSeverity(v);
              setPage(0);
            }}
          >
            <SelectTrigger className="h-9 w-[130px]" data-testid="issues-severity-filter">
              <SelectValue placeholder="Severity" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All severities</SelectItem>
              <SelectItem value="critical">Critical</SelectItem>
              <SelectItem value="high">High</SelectItem>
              <SelectItem value="medium">Medium</SelectItem>
              <SelectItem value="low">Low</SelectItem>
            </SelectContent>
          </Select>
          <Select
            value={category}
            onValueChange={(v) => {
              setCategory(v);
              setPage(0);
            }}
          >
            <SelectTrigger className="h-9 w-[170px]" data-testid="issues-category-filter">
              <SelectValue placeholder="Category" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All categories</SelectItem>
              {categories.map((c) => (
                <SelectItem key={c} value={c}>
                  {CATEGORY_LABELS[c] || c}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant="secondary"
            size="sm"
            className="h-9"
            onClick={copyTable}
            data-testid="issues-copy-table-button"
          >
            <Copy className="mr-1.5 h-3.5 w-3.5" /> Copy table
          </Button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <Table className="drl-table" data-testid="issues-table">
          <TableHeader>
            <TableRow>
              <TableHead className="w-[110px]">{sortButton("id", "Issue")}</TableHead>
              <TableHead className="w-[90px]">{sortButton("severity", "Severity")}</TableHead>
              <TableHead className="w-[130px]">{sortButton("category", "Category")}</TableHead>
              <TableHead>{sortButton("title", "What we found")}</TableHead>
              <TableHead className="w-[80px] text-right">
                {sortButton("impacted_file_count", "Files", "right")}
              </TableHead>
              <TableHead className="w-[110px] text-right">
                {sortButton("estimated_token_waste", "Tokens/mo", "right")}
              </TableHead>
              <TableHead className="w-[105px] text-right">
                {sortButton("estimated_credit_waste", "Credits/mo", "right")}
              </TableHead>
              <TableHead className="w-[95px] text-right">
                {sortButton("estimated_dollar_waste", "$/mo", "right")}
              </TableHead>
              <TableHead className="w-[90px] text-right text-xs">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={9} className="py-10 text-center text-sm text-muted-foreground">
                  {(issues || []).length === 0
                    ? "No major waste was detected. Keep your repo lean by consolidating instructions every quarter."
                    : "No findings match these filters."}
                </TableCell>
              </TableRow>
            ) : (
              rows.map((issue) => (
                <TableRow key={issue.id} data-testid="issues-row" className="align-top">
                  <TableCell className="font-mono text-[11px] text-muted-foreground">{issue.id}</TableCell>
                  <TableCell>
                    <SeverityChip severity={issue.severity} />
                  </TableCell>
                  <TableCell className="text-xs">{CATEGORY_LABELS[issue.category] || issue.category}</TableCell>
                  <TableCell className="max-w-[340px]">
                    <p className="text-sm font-medium leading-5">{issue.title}</p>
                    <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">
                      {issue.description}
                    </p>
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      <MetaChip label="impact" value={issue.impact} tone={issue.impact === "High" ? "bad" : "neutral"} />
                      <MetaChip label="effort" value={issue.effort} tone={issue.effort === "Small" ? "good" : "neutral"} />
                    </div>
                  </TableCell>
                  <TableCell className="num text-right text-sm">{num(issue.impacted_file_count)}</TableCell>
                  <TableCell className="num text-right text-sm" title={num(issue.estimated_token_waste)}>
                    {compact(issue.estimated_token_waste)}
                  </TableCell>
                  <TableCell className="num text-right text-sm">{num(issue.estimated_credit_waste, 2)}</TableCell>
                  <TableCell className="num text-right text-sm font-medium">
                    {money(issue.estimated_dollar_waste)}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                        aria-label="View evidence"
                        onClick={() => setActive(issue)}
                        data-testid="issues-row-view-evidence-button"
                      >
                        <Eye className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                        aria-label="Copy recommendation"
                        onClick={() => copyRecommendation(issue)}
                        data-testid="issues-row-copy-recommendation-button"
                      >
                        <Copy className="h-4 w-4" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {pageCount > 1 ? (
        <div className="flex items-center justify-between border-t border-border p-3">
          <p className="text-xs text-muted-foreground">
            Page {safePage + 1} of {pageCount}
          </p>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              disabled={safePage === 0}
              onClick={() => setPage(safePage - 1)}
              data-testid="issues-prev-page"
            >
              Previous
            </Button>
            <Button
              variant="secondary"
              size="sm"
              disabled={safePage >= pageCount - 1}
              onClick={() => setPage(safePage + 1)}
              data-testid="issues-next-page"
            >
              Next
            </Button>
          </div>
        </div>
      ) : null}

      <Sheet open={Boolean(active)} onOpenChange={(o) => !o && setActive(null)}>
        <SheetContent
          side="right"
          className="w-full overflow-y-auto bg-card sm:max-w-2xl"
          data-testid="evidence-drawer"
        >
          {active ? (
            <>
              <SheetHeader>
                <div className="flex items-center gap-2">
                  <SeverityChip severity={active.severity} />
                  <span className="font-mono text-[11px] text-muted-foreground">{active.id}</span>
                </div>
                <SheetTitle className="font-heading text-left">{active.title}</SheetTitle>
                <SheetDescription className="text-left text-sm leading-6 text-foreground">
                  {active.description}
                </SheetDescription>
              </SheetHeader>

              <div className="mt-5 grid grid-cols-3 gap-2">
                <div className="rounded-xl border border-border bg-secondary p-3">
                  <p className="text-[11px] uppercase text-muted-foreground">Tokens / month</p>
                  <p className="num font-heading text-lg font-bold">{compact(active.estimated_token_waste)}</p>
                </div>
                <div className="rounded-xl border border-border bg-secondary p-3">
                  <p className="text-[11px] uppercase text-muted-foreground">Credits / month</p>
                  <p className="num font-heading text-lg font-bold">{num(active.estimated_credit_waste, 2)}</p>
                </div>
                <div className="rounded-xl border border-border bg-secondary p-3">
                  <p className="text-[11px] uppercase text-muted-foreground">Dollars / month</p>
                  <p className="num font-heading text-lg font-bold">{money(active.estimated_dollar_waste)}</p>
                </div>
              </div>

              <div className="mt-5">
                <p className="font-heading text-sm font-bold">Evidence</p>
                <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded-xl border border-border bg-secondary p-3 font-mono text-[11px] leading-5">
                  {active.evidence || "No evidence captured."}
                </pre>
              </div>

              <div className="mt-4">
                <p className="font-heading text-sm font-bold">How the waste was estimated</p>
                <pre className="mt-2 whitespace-pre-wrap rounded-xl border border-border bg-secondary p-3 font-mono text-[11px] leading-5">
                  {active.formula}
                </pre>
              </div>

              <div className="mt-4">
                <p className="font-heading text-sm font-bold">What to do</p>
                <p className="mt-1 text-sm leading-6">{active.recommendation}</p>
                <div className="mt-2 flex gap-1.5">
                  <MetaChip label="impact" value={active.impact} />
                  <MetaChip label="effort" value={active.effort} />
                </div>
              </div>

              <div className="mt-4">
                <p className="font-heading text-sm font-bold">
                  Impacted files ({(active.impacted_files || []).length})
                </p>
                <ul className="mt-2 max-h-56 space-y-1 overflow-auto rounded-xl border border-border bg-secondary p-3">
                  {(active.impacted_files || []).length === 0 ? (
                    <li className="text-xs text-muted-foreground">No specific files recorded.</li>
                  ) : (
                    (active.impacted_files || []).map((f) => (
                      <li key={f} className="break-all font-mono text-[11px] leading-5">
                        {f}
                      </li>
                    ))
                  )}
                </ul>
              </div>
            </>
          ) : null}
        </SheetContent>
      </Sheet>
    </Card>
  );
};

export default IssuesTable;
