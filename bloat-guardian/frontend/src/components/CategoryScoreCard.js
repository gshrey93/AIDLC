import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { CATEGORY_LABELS, num, scoreToneClass } from "@/lib/format";

export const CategoryScoreCard = ({ category, ledger }) => {
  const [open, setOpen] = useState(false);
  const label = category.label || CATEGORY_LABELS[category.category] || category.category;
  const rows = (ledger || []).filter((r) => r.category === category.category);
  return (
    <Card
      data-testid={`category-score-card-${category.category}`}
      className="rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-md)] transition-shadow duration-250 hover:shadow-[var(--shadow-lg)]"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-heading text-sm font-bold">{label}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Weight {Math.round((category.weight || 0) * 100)}% &middot; penalty -{category.penalty_points || 0}
          </p>
        </div>
        <p className={`num font-heading text-2xl font-bold ${scoreToneClass(category.score)}`}>
          {category.score}
          <span className="text-sm font-medium text-muted-foreground">/100</span>
        </p>
      </div>
      <div className="mt-3">
        <Progress value={category.score} className="h-2" />
      </div>
      <p className="mt-3 text-sm leading-6 text-foreground">{category.summary}</p>
      <Button
        variant="ghost"
        size="sm"
        className="mt-2 h-8 px-2 text-xs text-primary"
        onClick={() => setOpen(true)}
        data-testid={`category-ledger-button-${category.category}`}
      >
        How this was calculated <ChevronRight className="ml-1 h-3.5 w-3.5" />
      </Button>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent
          side="right"
          className="w-full overflow-y-auto bg-card sm:max-w-xl"
          data-testid="category-ledger-sheet"
        >
          <SheetHeader>
            <SheetTitle className="font-heading">{label} &middot; score {category.score}/100</SheetTitle>
            <SheetDescription>
              Every deduction that produced this score. Tier 1 rules are the specified penalties with
              hard caps. Tier 2 scales with how much of your monthly agent context budget is wasted.
            </SheetDescription>
          </SheetHeader>
          <div className="mt-4 overflow-x-auto">
            <Table className="drl-table">
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Rule</TableHead>
                  <TableHead className="text-xs">Tier</TableHead>
                  <TableHead className="text-right text-xs">Hits</TableHead>
                  <TableHead className="text-right text-xs">Cap</TableHead>
                  <TableHead className="text-right text-xs">Applied</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} className="text-sm text-muted-foreground">
                      No penalties were applied in this category.
                    </TableCell>
                  </TableRow>
                ) : (
                  rows.map((r, i) => (
                    <TableRow key={i}>
                      <TableCell className="max-w-[280px] text-xs">
                        <span className="block font-medium">{r.rule}</span>
                        {r.detail ? (
                          <span className="mt-1 block font-mono text-[11px] leading-4 text-muted-foreground">
                            {r.detail}
                          </span>
                        ) : null}
                      </TableCell>
                      <TableCell className="text-xs capitalize">{r.tier === "scaling" ? "Tier 2" : "Tier 1"}</TableCell>
                      <TableCell className="num text-right text-xs">{num(r.hits)}</TableCell>
                      <TableCell className="num text-right text-xs">{num(r.cap)}</TableCell>
                      <TableCell className="num text-right text-xs font-semibold">-{num(r.applied)}</TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
          <p className="mt-4 rounded-xl border border-border bg-secondary p-3 text-xs leading-5 text-muted-foreground">
            Category score = 100 minus every applied deduction, clamped to the 0 to 100 range.
            Total applied here: -{num(rows.reduce((a, r) => a + (r.applied || 0), 0))}.
          </p>
        </SheetContent>
      </Sheet>
    </Card>
  );
};

export default CategoryScoreCard;
