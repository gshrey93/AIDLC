import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import ExportPanel from "@/components/ExportPanel";
import { endpoints } from "@/lib/api";
import { SOURCE_LABELS } from "@/lib/format";

export default function ExportsPage() {
  const { scanId } = useParams();
  const [scan, setScan] = useState(null);

  useEffect(() => {
    endpoints
      .getScan(scanId)
      .then((res) => setScan(res.data))
      .catch(() => setScan(null));
  }, [scanId]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-mono text-xs uppercase tracking-wide text-muted-foreground">{scanId}</p>
          <h1 className="mt-1 text-h1 font-heading">Export report</h1>
          {scan ? (
            <p className="mt-1 text-sm text-muted-foreground">
              {scan.repo_name} &middot; {SOURCE_LABELS[scan.source_type] || scan.source_type}
              {scan.branch ? ` · branch ${scan.branch}` : ""}
            </p>
          ) : (
            <Skeleton className="mt-2 h-4 w-56" />
          )}
        </div>
        <Button asChild variant="secondary" size="sm" data-testid="exports-back-button">
          <Link to={`/scan/${scanId}`}>
            <ArrowLeft className="mr-1.5 h-3.5 w-3.5" /> Back to results
          </Link>
        </Button>
      </div>

      <ExportPanel scanId={scanId} repoName={scan?.repo_name} />
    </div>
  );
}
