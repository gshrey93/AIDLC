import { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { endpoints } from "@/lib/api";
import { PARSE_STATUS_TONE, bytes, compact, num } from "@/lib/format";

const StatusPill = ({ status }) => (
  <span
    className={`tone ${PARSE_STATUS_TONE[status] || "tone-neutral"} inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold`}
  >
    {status}
  </span>
);

export const FileInventory = ({ scanId, summary, groups }) => {
  const [group, setGroup] = useState("all");
  const [files, setFiles] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    endpoints
      .getFiles(scanId, { group: group === "all" ? undefined : group, limit: 300 })
      .then((res) => {
        if (!alive) return;
        setFiles(res.data.files || []);
        setTotal(res.data.total || 0);
      })
      .catch(() => alive && setFiles([]))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [scanId, group]);

  const availableGroups = (groups || []).filter((g) => summary && summary[g]);

  return (
    <Card
      data-testid="file-inventory"
      className="rounded-xl border border-border bg-card shadow-[var(--shadow-md)]"
    >
      <div className="border-b border-border p-4">
        <h3 className="font-heading text-lg font-bold">File inventory by category</h3>
        <p className="text-xs text-muted-foreground">
          Token estimates use the formula ceil(character_count / 4). Skipped files keep their metadata
          and reason.
        </p>
      </div>

      <div className="grid gap-2 border-b border-border p-4 sm:grid-cols-2 lg:grid-cols-4">
        {Object.entries(summary || {}).map(([name, v]) => (
          <div
            key={name}
            className="rounded-xl border border-border bg-secondary p-3"
            data-testid={`inventory-group-${name.replace(/\s+/g, "-").toLowerCase()}`}
          >
            <p className="text-xs font-medium text-muted-foreground">{name}</p>
            <p className="num font-heading text-lg font-bold">{num(v.count)}</p>
            <p className="num text-[11px] text-muted-foreground">
              {num(v.parsed)} parsed &middot; {num(v.skipped)} skipped &middot; {compact(v.tokens)} tokens
            </p>
          </div>
        ))}
      </div>

      <div className="p-4">
        <Tabs value={group} onValueChange={setGroup}>
          <TabsList className="flex h-auto w-full flex-wrap justify-start gap-1 bg-secondary" data-testid="inventory-tabs">
            <TabsTrigger value="all" className="text-xs" data-testid="inventory-tab-all">
              All files
            </TabsTrigger>
            {availableGroups.map((g) => (
              <TabsTrigger
                key={g}
                value={g}
                className="text-xs"
                data-testid={`inventory-tab-${g.replace(/\s+/g, "-").toLowerCase()}`}
              >
                {g}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        <p className="mt-3 text-xs text-muted-foreground">
          Showing the {Math.min(files.length, 300)} largest of {num(total)} files by estimated tokens.
        </p>

        <div className="mt-2 max-h-[460px] overflow-auto scrollbar-thin">
          <Table className="drl-table">
            <TableHeader className="sticky top-0 bg-card">
              <TableRow>
                <TableHead className="text-xs">Path</TableHead>
                <TableHead className="text-xs">Category</TableHead>
                <TableHead className="text-xs">Status</TableHead>
                <TableHead className="text-right text-xs">Lines</TableHead>
                <TableHead className="text-right text-xs">Size</TableHead>
                <TableHead className="text-right text-xs">Tokens</TableHead>
                <TableHead className="text-xs">Duplicate group</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                Array.from({ length: 6 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={7}>
                      <Skeleton className="h-5 w-full" />
                    </TableCell>
                  </TableRow>
                ))
              ) : files.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="py-8 text-center text-sm text-muted-foreground">
                    No files in this group.
                  </TableCell>
                </TableRow>
              ) : (
                files.map((f) => (
                  <TableRow key={f.id} data-testid="inventory-row">
                    <TableCell className="max-w-[320px] break-all font-mono text-[11px]">{f.path}</TableCell>
                    <TableCell className="text-xs">{f.category}</TableCell>
                    <TableCell>
                      <StatusPill status={f.parse_status} />
                      {f.skip_reason ? (
                        <p className="mt-1 max-w-[220px] text-[11px] leading-4 text-muted-foreground">
                          {f.skip_reason}
                        </p>
                      ) : null}
                    </TableCell>
                    <TableCell className="num text-right text-xs">{num(f.line_count)}</TableCell>
                    <TableCell className="num text-right text-xs">{bytes(f.size_bytes)}</TableCell>
                    <TableCell className="num text-right text-xs">{num(f.estimated_tokens)}</TableCell>
                    <TableCell className="font-mono text-[11px] text-muted-foreground">
                      {f.similarity_group || "-"}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </div>
    </Card>
  );
};

export default FileInventory;
