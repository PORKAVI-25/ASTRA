import type { HealthResponse } from "../types";

interface HealthCardProps {
  health: HealthResponse | null;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
}

export const HealthCard: React.FC<HealthCardProps> = ({ health, loading, error, onRefresh }) => {
  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-6 backdrop-blur-sm shadow-xl">
      <div className="flex items-center justify-between pb-4 border-b border-slate-800/80">
        <div>
          <h2 className="text-base font-semibold text-slate-100 flex items-center space-x-2">
            <span>System Telemetry & Health</span>
            {health && (
              <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono bg-emerald-950 text-emerald-300 border border-emerald-800">
                HTTP 200 OK
              </span>
            )}
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">Real-time status reported by FastAPI health diagnostic service</p>
        </div>
        <button
          onClick={onRefresh}
          disabled={loading}
          className="px-3 py-1.5 text-xs font-mono rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition cursor-pointer disabled:opacity-50"
        >
          {loading ? "Checking..." : "Refresh Diagnostic"}
        </button>
      </div>

      {error ? (
        <div className="mt-4 p-4 rounded-lg bg-amber-950/40 border border-amber-800/60 text-amber-200 text-xs">
          <div className="font-semibold mb-1 flex items-center space-x-2">
            <span>⚠️ Backend Disconnected</span>
          </div>
          <p className="text-slate-400 mb-2">
            The FastAPI backend service is not currently responding at <code className="text-amber-300">http://127.0.0.1:8000</code>.
          </p>
          <div className="bg-slate-950/80 p-2.5 rounded font-mono text-[11px] text-slate-300">
            Start backend: <code>python -m uvicorn backend.main:app --reload --port 8000</code>
          </div>
        </div>
      ) : health ? (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-4">
          <div className="p-3 bg-slate-950/50 rounded-lg border border-slate-800/60">
            <span className="text-[11px] font-mono uppercase text-slate-500">Service Status</span>
            <div className="text-sm font-semibold text-emerald-400 mt-1 flex items-center space-x-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
              <span className="capitalize">{health.status}</span>
            </div>
          </div>

          <div className="p-3 bg-slate-950/50 rounded-lg border border-slate-800/60">
            <span className="text-[11px] font-mono uppercase text-slate-500">Air-Gap / Offline Mode</span>
            <div className="text-sm font-semibold text-cyan-300 mt-1 flex items-center space-x-1.5">
              <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
              <span>{health.offline_mode ? "Strict Offline (Rule 1)" : "Standard"}</span>
            </div>
          </div>

          <div className="p-3 bg-slate-950/50 rounded-lg border border-slate-800/60">
            <span className="text-[11px] font-mono uppercase text-slate-500">Environment</span>
            <div className="text-sm font-semibold text-slate-200 mt-1 capitalize font-mono">
              {health.environment}
            </div>
          </div>

          <div className="p-3 bg-slate-950/50 rounded-lg border border-slate-800/60">
            <span className="text-[11px] font-mono uppercase text-slate-500">Service Version</span>
            <div className="text-sm font-semibold text-slate-200 mt-1 font-mono">
              v{health.version}
            </div>
          </div>
        </div>
      ) : (
        <div className="mt-4 text-xs text-slate-400 animate-pulse">Querying health endpoint...</div>
      )}
    </div>
  );
};
