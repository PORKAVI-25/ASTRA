import React from "react";
import type { InvestigationSummary } from "../../types/models";

interface OnsetCardProps {
  onset: InvestigationSummary["onset"];
}

export const OnsetCard: React.FC<OnsetCardProps> = ({ onset }) => {
  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl text-left font-sans space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-slate-800">
        <div>
          <div className="flex items-center space-x-2">
            <span className="text-base">⏱️</span>
            <h3 className="text-sm font-bold font-mono text-white tracking-wide">
              Temporal Onset Bounding Interval
            </h3>
            <span className="px-2 py-0.5 text-[10px] font-mono rounded bg-cyan-950 text-cyan-300 border border-cyan-800">
              {onset.intervalType}
            </span>
          </div>
          <p className="text-xs text-slate-400 font-mono mt-0.5">
            Strict half-open mathematical bounding enclosing the physical emergence of the candidate.
          </p>
        </div>

        <div className="text-right font-mono">
          <div className="text-xs text-slate-400">Physical Gap</div>
          <div className="text-sm font-bold text-cyan-300">{onset.intervalDays} days</div>
        </div>
      </div>

      {/* Visual Interval Graphic */}
      <div className="bg-slate-950/90 rounded-2xl p-6 border border-slate-800/90 relative overflow-hidden font-mono">
        <div className="flex flex-col sm:flex-row items-center justify-between gap-6 relative z-10">
          {/* T_pre Node (Pre-Change Absence) */}
          <div className="w-full sm:w-1/3 bg-slate-900/90 border border-slate-800 p-3.5 rounded-xl text-center space-y-1">
            <div className="flex items-center justify-center space-x-1.5 text-xs text-slate-400 font-bold">
              <span className="text-cyan-400 text-lg font-mono font-bold">(</span>
              <span>T_pre (Absence)</span>
            </div>
            <div className="text-sm font-bold text-white">
              {onset.preChangeDate || "T1"}
            </div>
            <div
              className="text-[10px] text-slate-400 truncate max-w-full"
              title={onset.preChangeObservationId}
            >
              {onset.preChangeObservationId || "Reference baseline observation"}
            </div>
            <div className="text-[10px] text-slate-400 italic">Confirmed absence</div>
          </div>

          {/* Interval Connector */}
          <div className="flex-1 flex flex-col items-center justify-center px-4 w-full sm:w-auto">
            <div className="text-xs font-bold text-cyan-300 mb-1">
              ( T_pre , T_earliest ]
            </div>
            <div className="w-full flex items-center">
              <div className="w-3 h-3 rounded-full bg-cyan-500/80 border border-cyan-300 flex-shrink-0"></div>
              <div className="flex-1 border-t-2 border-dashed border-cyan-500/60 relative">
                <span className="absolute -top-4 left-1/2 transform -translate-x-1/2 text-[10px] text-cyan-400 bg-slate-950 px-2 py-0.5 rounded border border-cyan-900">
                  Δt = {onset.intervalDays}d
                </span>
              </div>
              <div className="w-3 h-3 bg-emerald-400 border border-emerald-200 flex-shrink-0"></div>
            </div>
            <div className="text-[10px] text-slate-400 mt-2 font-mono">
              Emergence occurred in this interval
            </div>
          </div>

          {/* T_earliest Node (Earliest Supporting Detection) */}
          <div className="w-full sm:w-1/3 bg-slate-900/90 border border-emerald-900/60 p-3.5 rounded-xl text-center space-y-1">
            <div className="flex items-center justify-center space-x-1.5 text-xs text-emerald-400 font-bold">
              <span>T_earliest (Support)</span>
              <span className="text-emerald-400 text-lg font-mono font-bold">]</span>
            </div>
            <div className="text-sm font-bold text-white">
              {onset.earliestSupportDate || "T2"}
            </div>
            <div
              className="text-[10px] text-slate-400 truncate max-w-full"
              title={onset.earliestSupportObservationId}
            >
              {onset.earliestSupportObservationId || "First detection observation"}
            </div>
            <div className="text-[10px] text-emerald-400 font-semibold">Earliest verified support</div>
          </div>
        </div>
      </div>

      {/* Interval Details Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs font-mono">
        <div className="bg-slate-950/70 p-3 rounded-xl border border-slate-800">
          <div className="text-[10px] uppercase text-slate-400 font-semibold mb-1">
            Mathematical Interval
          </div>
          <div className="text-sm font-bold text-cyan-300">
            {onset.physicalInterval}
          </div>
          <div className="text-[10px] text-slate-400 mt-0.5">
            Display span: {onset.displaySpan}
          </div>
        </div>

        <div className="bg-slate-950/70 p-3 rounded-xl border border-slate-800">
          <div className="text-[10px] uppercase text-slate-400 font-semibold mb-1">
            Temporal Baseline Gap
          </div>
          <div className="text-sm font-bold text-slate-200">
            {onset.intervalDays} Days
          </div>
          <div className="text-[10px] text-slate-400 mt-0.5">
            Revisit frequency between acquisitions
          </div>
        </div>

        <div className="bg-slate-950/70 p-3 rounded-xl border border-slate-800">
          <div className="text-[10px] uppercase text-slate-400 font-semibold mb-1">
            Interval Classification
          </div>
          <div className="text-sm font-bold text-emerald-400">
            {onset.intervalType}
          </div>
          <div className="text-[10px] text-slate-400 mt-0.5">
            Half-open discrete sampling bound
          </div>
        </div>
      </div>

      {/* Scientific Limitation Callout */}
      <div className="p-3.5 bg-amber-950/30 border border-amber-800/60 rounded-xl text-amber-200/90 text-xs font-mono flex items-start space-x-2.5">
        <span className="text-base flex-shrink-0">⚠️</span>
        <div>
          <div className="font-bold text-amber-100 mb-0.5">
            Temporal Resolution & Sampling Limitation Notice
          </div>
          <p className="text-[11px] leading-relaxed text-amber-200/80">
            {onset.limitationNotice}
          </p>
        </div>
      </div>
    </div>
  );
};
