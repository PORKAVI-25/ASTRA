import React from "react";
import type { TemporalSeriesSummary } from "../../types/models";

interface SeriesCardProps {
  series: TemporalSeriesSummary;
  isSelected: boolean;
  onSelect: (seriesId: string) => void;
}

export const SeriesCard: React.FC<SeriesCardProps> = ({ series, isSelected, onSelect }) => {
  const isMultiEpoch = series.observationCount >= 2;
  const isDemoSeries = series.observationCount >= 4;

  return (
    <div
      onClick={() => onSelect(series.seriesId)}
      className={`cursor-pointer rounded-xl p-4 transition-all duration-150 border text-left font-mono relative overflow-hidden ${
        isSelected
          ? "bg-slate-900/95 border-cyan-500 shadow-lg shadow-cyan-950/50 ring-1 ring-cyan-500/40"
          : "bg-slate-900/60 hover:bg-slate-900/80 border-slate-800 hover:border-slate-700 shadow-sm"
      }`}
    >
      {/* Selected Accent Bar */}
      {isSelected && (
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-cyan-400 via-emerald-400 to-cyan-500"></div>
      )}

      {/* Top Header: Target badge & Epoch Count */}
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center space-x-1.5 overflow-hidden">
          <span
            className={`w-2 h-2 rounded-full flex-shrink-0 ${
              isSelected ? "bg-cyan-400 animate-pulse" : "bg-slate-500"
            }`}
          ></span>
          <span className="text-xs font-bold text-white truncate" title={series.seriesId}>
            {series.seriesId}
          </span>
        </div>

        <div className="flex items-center space-x-1 flex-shrink-0">
          {isDemoSeries && (
            <span className="px-1.5 py-0.5 text-[10px] font-semibold rounded bg-cyan-950/80 text-cyan-300 border border-cyan-800/80">
              Demo Set
            </span>
          )}
          <span
            className={`px-2 py-0.5 text-[11px] font-bold rounded-full border ${
              isMultiEpoch
                ? "bg-emerald-950/60 text-emerald-300 border-emerald-800/80"
                : "bg-slate-800 text-slate-300 border-slate-700"
            }`}
          >
            {series.observationCount} {series.observationCount === 1 ? "epoch" : "epochs"}
          </span>
        </div>
      </div>

      {/* Date Range & Timespan */}
      <div className="text-xs text-slate-300 mb-2.5 flex items-center justify-between">
        <span className="text-slate-400 font-sans text-[11px]">Interval:</span>
        <span className="font-semibold text-slate-200">
          {series.startDate} → {series.endDate}
        </span>
      </div>

      {/* Timespan duration & Sensors */}
      <div className="flex flex-wrap items-center justify-between gap-1.5 text-[11px] pt-2 border-t border-slate-800/80">
        <div className="text-slate-400">
          Timespan:{" "}
          <span className="text-cyan-300 font-semibold">{series.timespanDays} days</span>
        </div>

        <div className="flex items-center space-x-1">
          {series.platforms.map((plat) => (
            <span
              key={plat}
              className="px-1.5 py-0.2 rounded text-[10px] bg-slate-800 text-slate-300 border border-slate-700"
            >
              {plat}
            </span>
          ))}
          {series.sensors.map((sens) => (
            <span
              key={sens}
              className="px-1.5 py-0.2 rounded text-[10px] bg-slate-950 text-slate-400 border border-slate-800"
            >
              {sens}
            </span>
          ))}
        </div>
      </div>

      {/* Bounding Coordinates snippet if available */}
      {series.boundsWgs84 && (
        <div className="mt-2 text-[10px] text-slate-400 truncate">
          AOI: [{series.boundsWgs84.minLon.toFixed(3)}°, {series.boundsWgs84.minLat.toFixed(3)}°] to [
          {series.boundsWgs84.maxLon.toFixed(3)}°, {series.boundsWgs84.maxLat.toFixed(3)}°]
        </div>
      )}
    </div>
  );
};
