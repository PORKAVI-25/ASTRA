import React from "react";

interface HeaderProps {
  isConnected: boolean;
  offlineMode: boolean;
  version: string;
}

export const Header: React.FC<HeaderProps> = ({ isConnected, offlineMode, version }) => {
  return (
    <header className="border-b border-slate-800/80 bg-slate-950/80 backdrop-blur-md sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="w-9 h-9 rounded-lg bg-gradient-to-tr from-cyan-500 to-emerald-400 p-0.5 shadow-lg shadow-cyan-500/20 flex items-center justify-center">
            <div className="w-full h-full bg-slate-950 rounded-[7px] flex items-center justify-center">
              <span className="text-cyan-400 font-bold text-lg font-mono">A</span>
            </div>
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-lg font-semibold tracking-wide text-white font-mono">A.S.T.R.A.</h1>
              <span className="px-2 py-0.5 text-xs font-mono rounded bg-slate-800 text-slate-300 border border-slate-700">
                v{version}
              </span>
            </div>
            <p className="text-[11px] text-slate-400">Automated Semantic Tracking and Retrieval Architecture</p>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          <div className="hidden sm:flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-cyan-950/60 text-cyan-300 border border-cyan-800/60">
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 mr-2 animate-pulse"></span>
            SIH 2026 • PS227
          </div>

          <div
            className={`flex items-center px-3 py-1 rounded-full text-xs font-mono font-medium border transition-colors ${
              isConnected
                ? "bg-emerald-950/50 text-emerald-300 border-emerald-800/60"
                : "bg-amber-950/50 text-amber-300 border-amber-800/60"
            }`}
          >
            <span
              className={`w-2 h-2 rounded-full mr-2 ${
                isConnected ? "bg-emerald-400 shadow-sm shadow-emerald-400" : "bg-amber-400 animate-ping"
              }`}
            ></span>
            {isConnected ? (offlineMode ? "ONLINE (OFFLINE-READY)" : "CONNECTED") : "BACKEND CONNECTING..."}
          </div>
        </div>
      </div>
    </header>
  );
};
