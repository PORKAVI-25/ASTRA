import { useCallback, useEffect, useState } from "react";
import { Header } from "./components/Header";
import { Sidebar } from "./components/Sidebar";
import { HealthCard } from "./components/HealthCard";
import { ModuleGrid } from "./components/ModuleGrid";
import { DataContractsPreview } from "./components/DataContractsPreview";
import { SeriesExplorer } from "./components/series/SeriesExplorer";
import { InvestigationLauncher } from "./components/investigation/InvestigationLauncher";
import { DossierView } from "./components/investigation/DossierView";
import { DEMO_INVESTIGATION_DOSSIER } from "./services/demoDossier";
import { transformInvestigationDossier } from "./services/transformers";
import { fetchHealth } from "./services/api";
import type { HealthResponse } from "./types";
import type { InvestigationDossier } from "./types/api";
import type { InvestigationSummary } from "./types/models";

export function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const queryParams = typeof window !== "undefined" ? new URLSearchParams(window.location.search) : null;
  const initialTabParam = queryParams?.get("tab");
  const isDemoRequested = queryParams?.get("demo") === "true";

  const [activeTab, setActiveTab] = useState<"dossier" | "launcher" | "explorer" | "foundation">(() => {
    if (initialTabParam === "dossier" || initialTabParam === "explorer" || initialTabParam === "foundation") {
      return initialTabParam;
    }
    return "launcher";
  });
  const [selectedSeriesId, setSelectedSeriesId] = useState<string | null>(null);
  const [activeDossier, setActiveDossier] = useState<{
    raw: InvestigationDossier;
    summary: InvestigationSummary;
  } | null>(() => {
    if (isDemoRequested || initialTabParam === "dossier") {
      return {
        raw: DEMO_INVESTIGATION_DOSSIER,
        summary: transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER),
      };
    }
    return null;
  });

  const handleLoadDemoDossier = () => {
    const summary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    setActiveDossier({ raw: DEMO_INVESTIGATION_DOSSIER, summary });
    setActiveTab("dossier");
  };

  const checkStatus = useCallback(async () => {
    try {
      const data = await fetchHealth();
      setHealth(data);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to connect to backend");
      setHealth(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let isMounted = true;
    fetchHealth()
      .then((data) => {
        if (isMounted) {
          setHealth(data);
          setError(null);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(err instanceof Error ? err.message : "Failed to connect to backend");
          setHealth(null);
          setLoading(false);
        }
      });

    const timer = setInterval(() => {
      checkStatus();
    }, 10000);

    return () => {
      isMounted = false;
      clearInterval(timer);
    };
  }, [checkStatus]);

  const isConnected = !!health && !error;
  const offlineMode = health ? health.offline_mode : true;
  const version = health ? health.version : "0.1.0";

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex font-sans selection:bg-cyan-500 selection:text-black">
      {/* Persistent Analyst Console Sidebar */}
      <Sidebar
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        activeInvestigationId={activeDossier?.raw.investigation_id || null}
        activeCandidateId={activeDossier?.summary.candidateRegionId || null}
        hasActiveDossier={!!activeDossier}
        onLoadDemo={handleLoadDemoDossier}
        offlineMode={offlineMode}
      />

      {/* Main Workstation Workspace */}
      <div className="flex-1 flex flex-col min-w-0 h-screen overflow-hidden">
        <Header
          isConnected={isConnected}
          offlineMode={offlineMode}
          version={version}
          activeTab={activeTab}
          activeInvestigationId={activeDossier?.raw.investigation_id || null}
          isConnecting={loading}
        />

        <main className="flex-1 overflow-y-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="max-w-7xl mx-auto space-y-6">
            {/* Quick Workspace Switcher Bar */}
            <div className="flex items-center justify-between gap-3 pb-3 border-b border-slate-800/80">
              <div className="flex items-center space-x-2">
                <button
                  onClick={() => setActiveTab("launcher")}
                  className={`px-3.5 py-1.5 rounded-lg text-xs font-mono font-bold transition-all ${
                    activeTab === "launcher"
                      ? "bg-cyan-950 text-cyan-300 border border-cyan-800 shadow-md shadow-cyan-950/40"
                      : "bg-slate-900/60 text-slate-400 hover:text-slate-200 border border-transparent hover:border-slate-800"
                  }`}
                >
                  🎯 Investigation Launcher (D3)
                </button>
                <button
                  onClick={() => setActiveTab("explorer")}
                  className={`px-3.5 py-1.5 rounded-lg text-xs font-mono font-bold transition-all ${
                    activeTab === "explorer"
                      ? "bg-cyan-950 text-cyan-300 border border-cyan-800 shadow-md shadow-cyan-950/40"
                      : "bg-slate-900/60 text-slate-400 hover:text-slate-200 border border-transparent hover:border-slate-800"
                  }`}
                >
                  🛰️ Temporal Series Explorer (D2)
                </button>
                <button
                  onClick={() => setActiveTab("dossier")}
                  className={`px-3.5 py-1.5 rounded-lg text-xs font-mono font-bold transition-all flex items-center space-x-1.5 ${
                    activeTab === "dossier"
                      ? "bg-cyan-950 text-cyan-300 border border-cyan-800 shadow-md shadow-cyan-950/40"
                      : "bg-slate-900/60 text-slate-400 hover:text-slate-200 border border-transparent hover:border-slate-800"
                  }`}
                >
                  <span>📋 Result Dossier (D4–D9)</span>
                  {activeDossier && (
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                  )}
                </button>
                <button
                  onClick={() => setActiveTab("foundation")}
                  className={`px-3.5 py-1.5 rounded-lg text-xs font-mono font-bold transition-all ${
                    activeTab === "foundation"
                      ? "bg-cyan-950 text-cyan-300 border border-cyan-800 shadow-md shadow-cyan-950/40"
                      : "bg-slate-900/60 text-slate-400 hover:text-slate-200 border border-transparent hover:border-slate-800"
                  }`}
                >
                  ⚡ System Architecture & Telemetry
                </button>
              </div>

              <div className="hidden sm:flex items-center space-x-2 text-xs font-mono text-slate-400">
                <span className="text-slate-400">STATUS:</span>
                <span className="text-emerald-400 font-semibold">AIR-GAPPED ANALYST CONSOLE</span>
              </div>
            </div>

            {/* Tab 1: Investigation Launcher (D3) */}
            {activeTab === "launcher" && (
              <section className="space-y-6">
                <InvestigationLauncher
                  initialSeriesId={selectedSeriesId || undefined}
                  onSelectSeries={(id) => setSelectedSeriesId(id)}
                  onInvestigationComplete={(rawDossier, summary) => {
                    setActiveDossier({ raw: rawDossier, summary });
                    setActiveTab("dossier");
                  }}
                />
              </section>
            )}

            {/* Tab 2: Temporal Series Explorer (D2) */}
            {activeTab === "explorer" && (
              <section className="space-y-6">
                <SeriesExplorer
                  onLaunchInvestigation={(seriesId) => {
                    setSelectedSeriesId(seriesId);
                    setActiveTab("launcher");
                  }}
                />
              </section>
            )}

            {/* Tab 3: Result Dossier (D4–D9) */}
            {activeTab === "dossier" && (
              <section className="space-y-6">
                <DossierView
                  dossier={activeDossier?.raw || null}
                  summary={activeDossier?.summary || null}
                  onBackToLauncher={() => setActiveTab("launcher")}
                  onLoadDemoDossier={handleLoadDemoDossier}
                />
              </section>
            )}

            {/* Tab 4: System Architecture & Foundation Telemetry */}
            {activeTab === "foundation" && (
              <div className="space-y-8">
                {/* Project Hero / Problem Statement Context */}
                <section>
                  <div className="relative rounded-xl p-8 overflow-hidden bg-gradient-to-br from-slate-900 via-slate-900/90 to-slate-950 border border-slate-800 shadow-2xl">
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
                          <span>Cryptographic Provenance (Rule 5)</span>
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
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}

export default App;
