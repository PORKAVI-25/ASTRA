import React from "react";

export interface SidebarProps {
  activeTab: "dossier" | "launcher" | "explorer" | "foundation";
  onSelectTab: (tab: "dossier" | "launcher" | "explorer" | "foundation") => void;
  activeInvestigationId?: string | null;
  activeCandidateId?: string | null;
  hasActiveDossier: boolean;
  onLoadDemo: () => void;
  offlineMode: boolean;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onSelectTab,
  activeInvestigationId,
  activeCandidateId,
  hasActiveDossier,
  onLoadDemo,
  offlineMode,
}) => {
  const navItems: Array<{
    id: "launcher" | "explorer" | "dossier" | "foundation";
    label: string;
    sublabel: string;
    icon: string;
    tag: string;
    badge?: string;
    hasIndicator?: boolean;
  }> = [
    {
      id: "launcher",
      label: "Investigation Launcher",
      sublabel: "Pairwise change orchestration",
      icon: "🎯",
      tag: "D3",
    },
    {
      id: "explorer",
      label: "Temporal Explorer",
      sublabel: "Multi-epoch imagery catalog",
      icon: "🛰️",
      tag: "D2",
    },
    {
      id: "dossier",
      label: "Analytical Dossier",
      sublabel: "Multi-evidence assessment",
      icon: "📋",
      tag: "D4–D9",
      badge: hasActiveDossier ? "ACTIVE" : undefined,
      hasIndicator: hasActiveDossier,
    },
    {
      id: "foundation",
      label: "System Telemetry",
      sublabel: "Monolith contracts & health",
      icon: "⚡",
      tag: "SYS",
    },
  ];

  return (
    <aside
      aria-label="Workstation Navigation Sidebar"
      className="w-64 flex-shrink-0 bg-slate-950 border-r border-slate-800/80 flex flex-col justify-between select-none"
    >
      {/* Top Console Brand */}
      <div>
        <div className="p-4 border-b border-slate-800/80 bg-slate-950/60">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-500 to-slate-900 p-0.5 shadow-lg shadow-cyan-950/50 flex items-center justify-center">
              <div className="w-full h-full bg-slate-950 rounded-[10px] flex items-center justify-center">
                <span className="text-cyan-400 font-black text-lg font-mono tracking-tighter">▲</span>
              </div>
            </div>
            <div>
              <div className="flex items-center space-x-1.5">
                <span className="font-mono font-black text-white text-base tracking-wider">A.S.T.R.A.</span>
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-cyan-950/80 text-cyan-400 border border-cyan-800/60 font-semibold">
                  GEOINT
                </span>
              </div>
              <div className="text-[10px] font-mono text-slate-400 tracking-tight">
                WORKSTATION CONSOLE
              </div>
            </div>
          </div>
        </div>

        {/* Operational Section Title */}
        <div className="px-4 pt-5 pb-2">
          <div className="text-[10px] font-mono font-bold tracking-widest text-slate-400 uppercase">
            Workspaces
          </div>
        </div>

        {/* Navigation List */}
        <nav className="px-2 space-y-1">
          {navItems.map((item) => {
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onSelectTab(item.id)}
                className={`w-full text-left px-3 py-2.5 rounded-lg text-xs font-mono transition-all flex items-center justify-between group ${
                  isActive
                    ? "bg-cyan-950/60 text-cyan-300 border border-cyan-800/70 shadow-sm shadow-cyan-950/50"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-900/60 border border-transparent"
                }`}
              >
                <div className="flex items-center space-x-2.5 min-w-0">
                  <span className="text-sm flex-shrink-0">{item.icon}</span>
                  <div className="min-w-0">
                    <div className="font-semibold truncate flex items-center space-x-1.5">
                      <span className={isActive ? "text-cyan-200 font-bold" : "text-slate-300"}>
                        {item.label}
                      </span>
                      {item.hasIndicator && (
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse flex-shrink-0" />
                      )}
                    </div>
                    <div className="text-[10px] text-slate-400 font-sans truncate">{item.sublabel}</div>
                  </div>
                </div>

                <div className="flex items-center space-x-1 flex-shrink-0 ml-1">
                  {item.badge && (
                    <span className="text-[9px] px-1 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 font-mono font-bold">
                      {item.badge}
                    </span>
                  )}
                  <span className="text-[9px] text-slate-400 font-mono px-1 py-0.5 rounded bg-slate-900 border border-slate-800">
                    {item.tag}
                  </span>
                </div>
              </button>
            );
          })}
        </nav>

        {/* Active Context Card */}
        <div className="px-3 mt-6">
          <div className="text-[10px] font-mono font-bold tracking-widest text-slate-400 uppercase mb-2 px-1">
            Active Context
          </div>
          {hasActiveDossier && activeInvestigationId ? (
            <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800 text-xs font-mono space-y-2">
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-slate-400">INVESTIGATION:</span>
                <span className="text-cyan-400 font-bold">
                  {activeInvestigationId.slice(0, 12)}…
                </span>
              </div>
              {activeCandidateId && (
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-slate-400">CANDIDATE:</span>
                  <span className="text-emerald-400 font-semibold">{activeCandidateId}</span>
                </div>
              )}
              <div className="pt-1">
                <button
                  onClick={() => onSelectTab("dossier")}
                  className="w-full py-1 text-[10px] font-bold text-center rounded bg-cyan-950 hover:bg-cyan-900 text-cyan-300 border border-cyan-800/80 transition-colors"
                >
                  Jump to Dossier →
                </button>
              </div>
            </div>
          ) : (
            <div className="p-3 rounded-lg bg-slate-900/40 border border-dashed border-slate-800 text-center space-y-2">
              <p className="text-[11px] text-slate-400 font-sans">No investigation loaded</p>
              <button
                onClick={onLoadDemo}
                className="w-full py-1 text-[10px] font-mono font-bold rounded bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-700 transition-colors"
              >
                Load Reference Dossier
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Bottom Telemetry & Air-Gap Compliance Footer */}
      <div className="p-3 border-t border-slate-800/80 bg-slate-950/80 space-y-2">
        <div
          className={`px-2.5 py-1.5 rounded-lg text-[10px] font-mono flex items-center justify-between border ${
            offlineMode
              ? "bg-emerald-950/40 text-emerald-300 border-emerald-800/60"
              : "bg-amber-950/40 text-amber-300 border-amber-800/60"
          }`}
        >
          <div className="flex items-center space-x-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-400 shadow-sm shadow-emerald-400" />
            <span className="font-bold uppercase tracking-wider">Air-Gapped Console</span>
          </div>
          <span className="text-[9px] text-slate-400 font-mono">100% OFFLINE</span>
        </div>

        <div className="px-1 text-[10px] font-mono text-slate-400 flex items-center justify-between">
          <span>SIH26227 / PS227</span>
          <span className="text-slate-400">SECURE LOCAL</span>
        </div>
      </div>
    </aside>
  );
};
