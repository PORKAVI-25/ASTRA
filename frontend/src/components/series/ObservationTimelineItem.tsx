import React from "react";
import type { TemporalObservationSummary } from "../../types/models";

interface ObservationTimelineItemProps {
  observation: TemporalObservationSummary;
  index: number;
  total: number;
  isEarliest?: boolean;
  isLatest?: boolean;
}

export const ObservationTimelineItem: React.FC<ObservationTimelineItemProps> = ({
  observation,
  index,
  total,
  isEarliest,
  isLatest,
}) => {
  const epochLabel = `T${index + 1}`;
  const bounds = observation.boundsWgs84;

  return (
    <div className="relative flex items-start space-x-4 group">
      {/* Timeline spine */}
      <div className="flex flex-col items-center">
        <div
          className={`w-9 h-9 rounded-lg flex items-center justify-center font-mono text-xs font-bold border transition-colors shadow-sm ${
            isEarliest
              ? "bg-cyan-950/80 text-cyan-300 border-cyan-700/80 shadow-cyan-500/20"
              : isLatest
              ? "bg-emerald-950/80 text-emerald-300 border-emerald-700/80 shadow-emerald-500/20"
              : "bg-slate-900 text-slate-300 border-slate-700"
          }`}
        >
          {epochLabel}
        </div>
        {index < total - 1 && (
          <div className="w-0.5 h-full min-h-[48px] bg-gradient-to-b from-slate-700 to-slate-800 my-1"></div>
        )}
      </div>

      {/* Observation content card */}
      <div className="flex-1 bg-slate-900/90 hover:bg-slate-900 border border-slate-800 hover:border-slate-700 rounded-xl p-4 transition-all duration-150 shadow-md mb-3">
        {/* Header row: Epoch badge, platform, sensor, date */}
        <div className="flex flex-wrap items-center justify-between gap-2 mb-2 pb-2 border-b border-slate-800/80">
          <div className="flex items-center space-x-2">
            <span className="text-xs font-mono font-bold text-white tracking-wide">
              Epoch {index + 1}
            </span>
            {isEarliest && (
              <span className="px-2 py-0.5 text-[10px] font-mono font-medium rounded-full bg-cyan-950/90 text-cyan-300 border border-cyan-800">
                Baseline (T1)
              </span>
            )}
            {isLatest && (
              <span className="px-2 py-0.5 text-[10px] font-mono font-medium rounded-full bg-emerald-950/90 text-emerald-300 border border-emerald-800">
                Latest (TN)
              </span>
            )}
            <span className="px-2 py-0.5 text-[11px] font-mono rounded bg-slate-800 text-slate-200 border border-slate-700">
              {observation.platform}
            </span>
            <span className="px-2 py-0.5 text-[11px] font-mono rounded bg-slate-800/80 text-cyan-300 border border-slate-700">
              {observation.sensor}
            </span>
          </div>

          <div className="text-right">
            <div className="text-xs font-mono font-semibold text-slate-200">
              {observation.displayDate}
            </div>
            <div className="text-[10px] font-mono text-slate-400">
              {observation.acquisitionTime}
            </div>
          </div>
        </div>

        {/* Metadata Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2.5 text-xs font-mono pt-1">
          {/* Observation & Tile Identifiers */}
          <div className="space-y-1 bg-slate-950/60 p-2.5 rounded-lg border border-slate-800/60">
            <div className="text-[10px] uppercase text-slate-400 font-semibold tracking-wider">
              Identifiers
            </div>
            <div className="text-[11px] text-slate-300 truncate" title={observation.observationId}>
              <span className="text-slate-400">Obs: </span>
              {observation.observationId}
            </div>
            <div className="text-[11px] text-slate-300 truncate" title={observation.tileId}>
              <span className="text-slate-400">Tile: </span>
              {observation.tileId}
            </div>
            <div className="text-[11px] text-slate-300 truncate" title={observation.sceneId}>
              <span className="text-slate-400">Scene: </span>
              {observation.sceneId}
            </div>
          </div>

          {/* Spatial & CRS Metadata */}
          <div className="space-y-1 bg-slate-950/60 p-2.5 rounded-lg border border-slate-800/60">
            <div className="text-[10px] uppercase text-slate-400 font-semibold tracking-wider">
              Spatial Reference
            </div>
            <div className="text-[11px] text-slate-300">
              <span className="text-slate-400">CRS: </span>
              <span className="text-emerald-400 font-medium">{observation.crs}</span>
            </div>
            {bounds && (
              <div className="text-[10px] text-slate-400 leading-tight">
                <div>Lon: [{bounds.minLon.toFixed(4)}°, {bounds.maxLon.toFixed(4)}°]</div>
                <div>Lat: [{bounds.minLat.toFixed(4)}°, {bounds.maxLat.toFixed(4)}°]</div>
              </div>
            )}
          </div>

          {/* Quality & Acquisition Flags */}
          <div className="space-y-1 bg-slate-950/60 p-2.5 rounded-lg border border-slate-800/60">
            <div className="text-[10px] uppercase text-slate-400 font-semibold tracking-wider">
              Quality & Provenance
            </div>
            <div className="flex items-center justify-between text-[11px]">
              <span className="text-slate-400">Cloud Cover:</span>
              <span className="font-semibold text-slate-200">
                {observation.cloudCoverPct.toFixed(1)}%
              </span>
            </div>
            {observation.validPixelRatio !== undefined && (
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-slate-400">Valid Pixels:</span>
                <span className="font-semibold text-emerald-400">
                  {(observation.validPixelRatio * 100).toFixed(1)}%
                </span>
              </div>
            )}
            <div className="flex items-center justify-between text-[11px]">
              <span className="text-slate-400">Data Origin:</span>
              <span
                className={`px-1.5 py-0.2 rounded text-[10px] font-medium ${
                  observation.isSynthetic
                    ? "bg-purple-950/80 text-purple-300 border border-purple-800/60"
                    : "bg-emerald-950/80 text-emerald-300 border border-emerald-800/60"
                }`}
              >
                {observation.isSynthetic ? "Synthetic (Demo)" : "Operational"}
              </span>
            </div>
            {observation.sourceHash && (
              <div className="text-[10px] text-slate-400 truncate pt-0.5" title={observation.sourceHash}>
                <span className="text-slate-400">Hash: </span>
                {observation.sourceHash.slice(0, 16)}…
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
