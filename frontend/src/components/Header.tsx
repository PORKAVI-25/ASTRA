import React, { useEffect, useState } from "react";

export interface HeaderProps {
  isConnected: boolean;
  offlineMode: boolean;
  version: string;
  activeTab?: "dossier" | "launcher" | "explorer" | "foundation";
  activeInvestigationId?: string | null;
  isConnecting?: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  isConnected,
  offlineMode,
  version,
  activeTab = "launcher",
  activeInvestigationId,
  isConnecting = false,
}) => {
  const [utcTime, setUtcTime] = useState<string>("");

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setUtcTime(now.toISOString().replace("T", " ").substring(0, 19) + " UTC");
    };
    updateTime();
    const timer = setInterval(updateTime, 1000);
    return () => clearInterval(timer);
  }, []);

  const getBreadcrumb = () => {
    switch (activeTab) {
      case "dossier":
        return activeInvestigationId
          ? `DOSSIER // ${activeInvestigationId.slice(0, 14)}…`
          : "ANALYTICAL DOSSIER";
      case "launcher":
        return "INVESTIGATION LAUNCHER // D3 ORCHESTRATION";
      case "explorer":
        return "TEMPORAL EXPLORER // D2 CATALOG";
      case "foundation":
        return "SYSTEM TELEMETRY // MONOLITH ARCHITECTURE";
      default:
        return "GEOINT WORKSTATION";
    }
  };

  return (
    <header className="border-b border-slate-800/80 bg-slate-950/90 backdrop-blur-md sticky top-0 z-40 select-none">
      <div className="w-full px-4 sm:px-6 h-14 flex items-center justify-between">
        {/* Left: Breadcrumbs & Station Telemetry */}
        <div className="flex items-center space-x-3 min-w-0">
          <div className="flex items-center space-x-2 text-xs font-mono text-slate-400 truncate">
            <span className="text-cyan-400 font-bold tracking-wider">A.S.T.R.A.</span>
            <span className="text-slate-400">/</span>
            <span className="text-slate-300 font-semibold tracking-wide truncate">
              {getBreadcrumb()}
            </span>
          </div>

          <span className="hidden md:inline-block px-2 py-0.5 text-[10px] font-mono rounded bg-slate-900 text-slate-400 border border-slate-800">
            v{version}
          </span>
        </div>

        {/* Right: Mission Clock, Analyst ID & Connection Indicator */}
        <div className="flex items-center space-x-3 flex-shrink-0">
          {/* Real-time UTC Mission Clock */}
          <div className="hidden lg:flex items-center space-x-1.5 px-2.5 py-1 rounded-md bg-slate-900/90 border border-slate-800 text-[11px] font-mono text-slate-300">
            <span className="text-cyan-400">⏱</span>
            <span className="tracking-wider">{utcTime || "UTC MISSION CLOCK"}</span>
          </div>

          {/* Active Analyst Token */}
          <div className="hidden sm:flex items-center space-x-1.5 px-2.5 py-1 rounded-md bg-slate-900/90 border border-slate-800 text-[11px] font-mono text-slate-300">
            <span className="w-2 h-2 rounded-full bg-cyan-400/80"></span>
            <span className="text-slate-400 text-[10px]">ANALYST:</span>
            <span className="text-cyan-300 font-semibold">analyst_local</span>
          </div>

          {/* Air-gap / Backend Connectivity */}
          <div
            className={`flex items-center px-2.5 py-1 rounded-md text-[11px] font-mono font-medium border transition-colors ${
              isConnected
                ? "bg-emerald-950/40 text-emerald-300 border-emerald-800/60"
                : isConnecting
                ? "bg-amber-950/40 text-amber-300 border-amber-800/60"
                : "bg-slate-900/80 text-cyan-300 border-slate-700/60"
            }`}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full mr-1.5 ${
                isConnected
                  ? "bg-emerald-400 shadow-sm shadow-emerald-400"
                  : isConnecting
                  ? "bg-amber-400 animate-ping"
                  : "bg-cyan-400"
              }`}
            />
            <span>
              {isConnected
                ? offlineMode
                  ? "AIR-GAPPED (ONLINE)"
                  : "CONNECTED (ONLINE)"
                : isConnecting
                ? "BACKEND CONNECTING..."
                : "AIR-GAPPED (STANDALONE)"}
            </span>
          </div>
        </div>
      </div>
    </header>
  );
};
