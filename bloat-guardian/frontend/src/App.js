import { useEffect } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import "@/App.css";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import AppShell from "@/components/AppShell";
import Landing from "@/pages/Landing";
import NewScan from "@/pages/NewScan";
import ScanProgress from "@/pages/ScanProgress";
import ScanResults from "@/pages/ScanResults";
import ExportsPage from "@/pages/ExportsPage";
import History from "@/pages/History";
import Handoff from "@/pages/Handoff";
import SettingsPage from "@/pages/SettingsPage";
import NotFound from "@/pages/NotFound";

function App() {
  useEffect(() => {
    document.title = "Bloat Guardian - agentic repository efficiency";
  }, []);

  return (
    <TooltipProvider delayDuration={200}>
      <BrowserRouter>
        <AppShell>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/scan/new" element={<NewScan />} />
            <Route path="/scan/:scanId/progress" element={<ScanProgress />} />
            <Route path="/scan/:scanId/exports" element={<ExportsPage />} />
            <Route path="/scan/:scanId/handoff" element={<Handoff />} />
            <Route path="/scan/:scanId" element={<ScanResults />} />
            <Route path="/history" element={<History />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </AppShell>
      </BrowserRouter>
      <Toaster position="top-right" richColors />
    </TooltipProvider>
  );
}

export default App;
