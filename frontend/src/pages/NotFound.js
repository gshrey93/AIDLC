import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="flex min-h-[50vh] flex-col items-start justify-center">
      <p className="font-mono text-xs uppercase tracking-wide text-muted-foreground">404</p>
      <h1 className="mt-2 font-heading text-3xl font-semibold">That page does not exist</h1>
      <p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">
        The link you followed is not part of Bloat Guardian. Start a new scan or open your scan history.
      </p>
      <div className="mt-6 flex gap-3">
        <Button asChild data-testid="notfound-new-scan">
          <Link to="/scan/new">Start a new scan</Link>
        </Button>
        <Button asChild variant="secondary" data-testid="notfound-history">
          <Link to="/history">Open scan history</Link>
        </Button>
      </div>
    </div>
  );
}
