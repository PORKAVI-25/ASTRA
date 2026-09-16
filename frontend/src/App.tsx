import { useEffect, useState } from "react";
import { Header } from "./components/Header";
import { HealthCard } from "./components/HealthCard";
import { ModuleGrid } from "./components/ModuleGrid";
import { DataContractsPreview } from "./components/DataContractsPreview";
import { fetchHealth } from "./services/api";
import type { HealthResponse } from "./types";

export function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const checkStatus = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchHealth();
      setHealth(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to connect to backend");
      setHealth(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    checkStatus();
    // Periodically refresh telemetry every 10 seconds
    const timer = setInterval(checkStatus, 10000);
    return () => clearInterval(timer);
  }, []);

  const isConnected = !!health && !error;
  const offlineMode = health ? health.offline_mode : true;
  const version = health ? health.version : "0.1.0";

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-cyan-500 selection:text-black">
      <Header isConnected={isConnected} offlineMode={offlineMode} version={version} />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Project Hero / Problem Statement Context */}
        <section className="mb-8">
          <div className="relative rounded-2xl p-8 overflow-hidden bg-gradient-to-br from-slate-900 via-slate-900/90 to-slate-950 border border-slate-800 shadow-2xl">
            <div className="absolute top-0 right-0 -mt-12 -mr-12 w-96 h-96 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none"></div>
            <div className="absolute bottom-0 left-1/3 -mb-12 w-80 h-80 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none"></div>

            <div className="relative z-10 max-w-3xl">
              <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full text-xs font-mono font-medium bg-cyan-950/80 text-cyan-300 border border-cyan-800/80 mb-4">
                <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
                <span>Smart India Hackathon 2026 • SIH26227 / PS227</span>
              </div>
              <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-white mb-3 font-sans">
                Semantic Retrieval & Multi-Temporal Change Analysis
              </h1>
              <p className="text-sm sm:text-base text-slate-300 leading-relaxed">
                Project A.S.T.R.A. is an air-gapped, modular earth observation architecture delivering semantic natural language search and pixel-accurate temporal change tracking across multi-spectral satellite imagery collections.
              </p>

              <div className="flex flex-wrap items-center gap-3 mt-6 pt-6 border-t border-slate-800/80 text-xs font-mono">
                <div className="flex items-center space-x-2 text-slate-300 bg-slate-950/60 px-3 py-1.5 rounded-lg border border-slate-800">
                  <span className="text-emerald-400">✓</span>
                  <span>Modular Monolith</span>
                </div>
                <div className="flex items-center space-x-2 text-slate-300 bg-slate-950/60 px-3 py-1.5 rounded-lg border border-slate-800">
                  <span className="text-emerald-400">✓</span>
                  <span>Strict Offline Operation</span>
                </div>
                <div className="flex items-center space-x-2 text-slate-300 bg-slate-950/60 px-3 py-1.5 rounded-lg border border-slate-800">
                  <span className="text-emerald-400">✓</span>
                  <span>Stable Tile ID (Rule 3)</span>
                </div>
                <div className="flex items-center space-x-2 text-slate-300 bg-slate-950/60 px-3 py-1.5 rounded-lg border border-slate-800">
                  <span className="text-emerald-400">✓</span>
                  <span>Immutable Provenance (Rule 5)</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Real-time Health Telemetry */}
        <section>
          <HealthCard health={health} loading={loading} error={error} onRefresh={checkStatus} />
        </section>

        {/* Modular Monolith Architecture */}
        <section>
          <ModuleGrid moduleStates={health?.modules} />
        </section>

        {/* Data Contracts Inspector */}
        <section>
          <DataContractsPreview />
        </section>
      </main>

      <footer className="border-t border-slate-800/80 bg-slate-950/60 py-6 mt-12 text-xs text-slate-500 font-mono">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-2">
          <div>A.S.T.R.A. • Automated Semantic Tracking and Retrieval Architecture</div>
          <div>Phase 0 Foundation • SIH26227 / PS227 • Strictly Air-Gapped Ready</div>
        </div>
      </footer>
    </div>
  );
}

export default App;
