import { Link, useLocation } from "react-router-dom";
import { Gauge, History as HistoryIcon, Plus, Settings as SettingsIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import ThemeToggle from "@/components/ThemeToggle";

const NAV = [
  { to: "/history", label: "Scan history", icon: HistoryIcon, testId: "nav-history" },
  { to: "/settings", label: "Settings", icon: SettingsIcon, testId: "nav-settings" },
];

export const AppShell = ({ children }) => {
  const location = useLocation();
  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <header className="app-navbar sticky top-0" style={{ zIndex: "var(--z-sticky)" }}>
        <div className="mx-auto flex h-16 w-full max-w-[1260px] items-center justify-between px-4 sm:px-6">
          <Link to="/" className="flex items-center gap-2.5" data-testid="nav-logo">
            <span
              className="flex h-9 w-9 items-center justify-center rounded-xl"
              style={{ background: "rgba(255,255,255,0.18)", color: "#fff" }}
            >
              <Gauge className="h-5 w-5" />
            </span>
            <span className="hidden font-heading text-lg font-bold tracking-tight text-white sm:inline">
              Bloat Guardian
            </span>
          </Link>
          <nav className="flex items-center gap-1 sm:gap-2">
            {NAV.map((item) => {
              const active = location.pathname.startsWith(item.to);
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  data-testid={item.testId}
                  className={cn(
                    "app-navbar-link flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold",
                    active && "active",
                  )}
                >
                  <item.icon className="h-4 w-4" />
                  <span className="hidden sm:inline">{item.label}</span>
                </Link>
              );
            })}
            <ThemeToggle />
            <Button
              asChild
              size="sm"
              className="ml-1 rounded-xl border-0 font-bold"
              style={{ background: "#fff", color: "var(--primary-dark)", backgroundImage: "none" }}
              data-testid="nav-new-scan"
            >
              <Link to="/scan/new">
                <Plus className="h-4 w-4 sm:mr-1.5" /> <span className="hidden sm:inline">New scan</span>
              </Link>
            </Button>
          </nav>
        </div>
      </header>
      <main className="mx-auto w-full max-w-[1260px] flex-1 px-4 py-6 sm:px-6 sm:py-8">{children}</main>
      <footer className="border-t border-border bg-card">
        <div className="mx-auto flex w-full max-w-[1260px] flex-col gap-1 px-4 py-6 text-xs text-muted-foreground sm:px-6">
          <p>
            Bloat Guardian analyses agentic repositories for duplicated instructions, oversized context
            files and review overhead. It never edits your repository.
          </p>
          <p>Imported repository content is kept for 7 days. Scan reports are kept for 30 days.</p>
        </div>
      </footer>
    </div>
  );
};

export default AppShell;
