import { useEffect, useState } from "react";
import { AppProvider, useApp } from "./lib/appstate";

import Dashboard from "./pages/Dashboard";
import CircuitStudio from "./pages/CircuitStudio";
import Algorithms from "./pages/Algorithms";
import NetworkStudio from "./pages/NetworkStudio";
import QecLab from "./pages/QecLab";
import Protocols from "./pages/Protocols";
import OptimizeLab from "./pages/OptimizeLab";
import Experiments from "./pages/Experiments";
import InfoTheoryLab from "./pages/InfoTheoryLab";
import HardwareLab from "./pages/HardwareLab";
import DocsPage from "./pages/DocsPage";

const PAGES: Record<string, { label: string; component: React.ComponentType }> = {
  dashboard: { label: "Dashboard", component: Dashboard },
  circuit: { label: "Circuit Studio", component: CircuitStudio },
  algorithms: { label: "Algorithms", component: Algorithms },
  network: { label: "Network Studio", component: NetworkStudio },
  qec: { label: "Error Correction", component: QecLab },
  protocols: { label: "Cryptography", component: Protocols },
  optimize: { label: "Optimization & QML", component: OptimizeLab },
  info: { label: "Information Theory", component: InfoTheoryLab },
  hardware: { label: "Hardware Lab", component: HardwareLab },
  experiments: { label: "Experiments", component: Experiments },
  docs: { label: "Documentation", component: DocsPage },
};

function Shell() {
  const { theme, toggleTheme, backendOk } = useApp();
  const [page, setPage] = useState<string>(() => location.hash.slice(1) || "dashboard");

  useEffect(() => {
    const onHash = () => setPage(location.hash.slice(1) || "dashboard");
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const navigate = (p: string) => {
    location.hash = p;
    setPage(p);
  };
  const Active = PAGES[page]?.component ?? Dashboard;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="logo">QUANTUM<span>LAB</span></div>
        <nav aria-label="Main navigation">
          {Object.entries(PAGES).map(([key, p]) => (
            <a
              key={key}
              className={"nav-item" + (page === key ? " active" : "")}
              onClick={() => navigate(key)}
              href={`#${key}`}
            >
              {p.label}
            </a>
          ))}
        </nav>
        <div style={{ padding: "10px 18px", borderTop: "1px solid var(--border)" }}>
          <button className="btn secondary small" onClick={toggleTheme} aria-label="Toggle color theme">
            {theme === "dark" ? "Light mode" : "Dark mode"}
          </button>
        </div>
      </aside>
      <div className="main">
        <header className="toolbar">
          <strong style={{ fontSize: 13 }}>{PAGES[page]?.label ?? "Dashboard"}</strong>
          <span style={{ color: "var(--text-dim)", fontSize: 12 }}>Project: default</span>
          <div style={{ flex: 1 }} />
          <span className={"badge " + (backendOk === null ? "warn" : backendOk ? "ok" : "err")}>
            {backendOk === null ? "Checking backend…" : backendOk ? "Backend connected" : "Backend offline"}
          </span>
        </header>
        <main className="workspace" id="workspace">
          <Active />
        </main>
        <footer className="statusbar">
          <span>Backend: {backendOk ? "Connected" : backendOk === false ? "Offline" : "…"}</span>
          <span>Simulation: Idle</span>
          <span>v0.1.0</span>
          <span style={{ marginLeft: "auto" }}>Quantum computing · information · networking</span>
        </footer>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <AppProvider>
      <Shell />
    </AppProvider>
  );
}
