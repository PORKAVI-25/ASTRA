import React from "react";
import type { TemporalSeriesSummary } from "../../types/models";
import { ObservationTimelineItem } from "./ObservationTimelineItem";

export interface SeriesDetailProps {
  series: TemporalSeriesSummary | null;
  isLoading: boolean;
  onSelectSeries?: (seriesId: string) => void;
  onLaunchInvestigation?: (seriesId: string) => void;
}

export const SeriesDetail: React.FC<SeriesDetailProps> = ({
  series,
  isLoading,
  onLaunchInvestigation,
}) => {
  if (isLoading) {
    return (
      <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-8 flex flex-col items-center justify-center min-h-[420px] text-center font-mono animate-pulse">
        <div className="w-10 h-10 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin mb-4" />
        <div className="text-sm text-slate-300 font-semibold mb-1">Loading Series Observations…</div>
        <div className="text-xs text-slate-400">Fetching chronological metadata from catalog</div>
      </div>
    );
  }

  if (!series) {
    return (
      <div className="bg-slate-900/40 border border-dashed border-slate-800 rounded-2xl p-12 flex flex-col items-center justify-center min-h-[420px] text-center font-mono">
        <div className="w-12 h-12 rounded-xl bg-slate-800/80 border border-slate-700 flex items-center justify-center text-slate-400 mb-4 text-xl">
          📡
        </div>
        <h3 className="text-sm font-semibold text-slate-200 mb-1">No Temporal Series Selected</h3>
        <p className="text-xs text-slate-400 max-w-sm">
          Select a satellite series from the catalog on the left to inspect its multi-temporal acquisition timeline and observation metadata.
        </p>
      </div>
    );
  }

  const bounds = series.boundsWgs84;
  const observations = series.observations || [];

  return (
    <div className="space-y-6 text-left font-sans">
      {/* Series Overview Header Card */}
      <div className="bg-gradient-to-br from-slate-900 via-slate-900/90 to-slate-950 border border-slate-800 rounded-2xl p-6 shadow-xl relative overflow-hidden">
        <div className="absolute top-0 right-0 -mt-8 -mr-8 w-48 h-48 bg-cyan-500/10 rounded-full blur-2xl pointer-events-none" />

        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <div>
            <div className="inline-flex items-center space-x-2 px-2.5 py-0.5 rounded-full text-xs font-mono font-medium bg-cyan-950/80 text-cyan-300 border border-cyan-800 mb-2">
              <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
              <span>Target Series Grounded</span>
            </div>
            <h2 className="text-xl font-bold font-mono text-white tracking-tight break-all">
              {series.seriesId}
            </h2>
          </div>

          <div className="flex items-center space-x-2">
            <span className="px-3 py-1 text-xs font-mono font-bold rounded-lg bg-emerald-950/80 text-emerald-300 border border-emerald-800">
              {series.observationCount} Observations
            </span>
            <span className="px-3 py-1 text-xs font-mono font-bold rounded-lg bg-cyan-950/80 text-cyan-300 border border-cyan-800">
              {series.timespanDays} Day Span
            </span>
            {onLaunchInvestigation && (
              <button
                onClick={() => onLaunchInvestigation(series.seriesId)}
                className="inline-flex items-center space-x-1.5 px-3.5 py-1.5 text-xs font-mono font-bold rounded-lg bg-cyan-500 hover:bg-cyan-400 text-slate-950 shadow-md shadow-cyan-500/20 transition-all cursor-pointer"
                title="Launch multi-epoch investigation on this series"
              >
                <span>🎯 Launch Investigation</span>
              </button>
            )}
          </div>
        </div>

        {/* High-Density Telemetry Bar */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-4 border-t border-slate-800/80 text-xs font-mono">
          <div className="bg-slate-950/70 p-3 rounded-xl border border-slate-800/80">
            <div className="text-[10px] uppercase text-slate-400 font-semibold mb-1">Target Anchor</div>
            <div className="text-slate-200 truncate" title={series.targetId}>
              {series.targetId}
            </div>
          </div>

          <div className="bg-slate-950/70 p-3 rounded-xl border border-slate-800/80">
            <div className="text-[10px] uppercase text-slate-400 font-semibold mb-1">Earliest Epoch (T1)</div>
            <div className="text-cyan-300 font-semibold truncate">{series.startDate}</div>
          </div>

          <div className="bg-slate-950/70 p-3 rounded-xl border border-slate-800/80">
            <div className="text-[10px] uppercase text-slate-400 font-semibold mb-1">Latest Epoch (TN)</div>
            <div className="text-emerald-300 font-semibold truncate">{series.endDate}</div>
          </div>

          <div className="bg-slate-950/70 p-3 rounded-xl border border-slate-800/80">
            <div className="text-[10px] uppercase text-slate-400 font-semibold mb-1">Sensors / Platforms</div>
            <div className="text-slate-200 truncate">
              {series.platforms.join(", ") || "Sentinel-2"} ({series.sensors.join(", ") || "MSI"})
            </div>
          </div>
        </div>

        {/* Geographic Bounds Footprint */}
        {bounds && (
          <div className="mt-3 p-3 bg-slate-950/50 rounded-xl border border-slate-800/60 text-xs font-mono flex flex-wrap items-center justify-between gap-2">
            <span className="text-slate-400 text-[11px]">Geographic Footprint (WGS84):</span>
            <div className="text-slate-300 text-[11px] flex items-center space-x-3">
              <span>Lon: [{bounds.minLon.toFixed(4)}°, {bounds.maxLon.toFixed(4)}°]</span>
              <span>•</span>
              <span>Lat: [{bounds.minLat.toFixed(4)}°, {bounds.maxLat.toFixed(4)}°]</span>
            </div>
          </div>
        )}
      </div>

      {/* Chronological Observation Timeline */}
      <div className="bg-slate-950/80 border border-slate-800/90 rounded-2xl p-6 shadow-xl">
        <div className="flex items-center justify-between mb-6 pb-3 border-b border-slate-800">
          <div>
            <h3 className="text-sm font-bold font-mono text-white tracking-wide flex items-center space-x-2">
              <span>Chronological Observation Timeline</span>
              <span className="px-2 py-0.5 text-[10px] font-mono rounded bg-slate-800 text-slate-300">
                T1 → T{observations.length}
              </span>
            </h3>
            <p className="text-xs text-slate-400 mt-0.5 font-mono">
              Chronologically ordered satellite acquisitions grounded to this grid tile.
            </p>
          </div>

          <div className="text-xs font-mono text-slate-400">
            {observations.length} {observations.length === 1 ? "acquisition" : "acquisitions"} registered
          </div>
        </div>

        {/* Observations list */}
        {observations.length === 0 ? (
          <div className="text-center py-8 text-xs font-mono text-slate-400">
            No observations cataloged in this series.
          </div>
        ) : (
          <div className="space-y-0">
            {observations.map((obs, idx) => (
              <ObservationTimelineItem
                key={obs.observationId}
                observation={obs}
                index={idx}
                total={observations.length}
                isEarliest={idx === 0}
                isLatest={idx === observations.length - 1}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
