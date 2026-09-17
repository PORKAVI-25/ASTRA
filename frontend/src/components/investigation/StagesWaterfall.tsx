import React from "react";
import type { StageExecutionSummary } from "../../types/models";

interface StagesWaterfallProps {
  stages: StageExecutionSummary[];
}

const formatStageName = (rawStage: string): { label: string; code: string } => {
  switch (rawStage) {
    case "series_resolution":
      return { label: "Temporal Series Catalog Grounding", code: "Catalog" };
    case "m4b_change_detection":
    case "change_detection":
      return { label: "Connected Component Differencing", code: "M4B" };
    case "m4c_evidence":
    case "m4c_evidence_extraction":
    case "evidence_extraction":
      return { label: "Multi-Spectral Evidence Extraction", code: "M4C-A" };
    case "m4c_classification":
    case "classification":
      return { label: "Candidate Semantic Classification", code: "M4C-B" };
    case "m4d_suppression":
    case "suppression":
    case "screening":
      return { label: "False-Alarm Artifact Screening", code: "M4D" };
    case "m4e_temporal_evidence":
    case "temporal_evidence":
      return { label: "Multi-Epoch Temporal Evidence Reasoning", code: "M4E" };
    default:
      return { label: rawStage.replace(/_/g, " "), code: "Pipeline" };
  }
};

export const StagesWaterfall: React.FC<StagesWaterfallProps> = ({ stages }) => {
  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl text-left font-sans space-y-4">
      <div className="flex items-center justify-between pb-3 border-b border-slate-800">
        <div>
          <div className="flex items-center space-x-2">
            <span className="text-base">⚡</span>
            <h3 className="text-sm font-bold font-mono text-white tracking-wide">
              Pipeline Stage Execution Waterfall
            </h3>
            <span className="px-2 py-0.5 text-[10px] font-mono rounded bg-slate-800 text-slate-300">
              {stages.length} Stages Executed
            </span>
          </div>
          <p className="text-xs text-slate-400 font-mono mt-0.5">
            Deterministic pipeline execution record from spatial ingestion to multi-epoch temporal reasoning.
          </p>
        </div>
      </div>

      <div className="space-y-3 font-mono text-xs">
        {stages.map((stage, idx) => {
          const { label, code } = formatStageName(stage.stage);
          const isCompleted = stage.status === "COMPLETED";
          const statusClass = isCompleted
            ? "bg-emerald-950 text-emerald-300 border-emerald-800"
            : stage.status === "FAILED"
            ? "bg-rose-950 text-rose-300 border-rose-800"
            : "bg-slate-800 text-slate-400 border-slate-700";

          const detailsKeys = Object.keys(stage.details || {});

          return (
            <div
              key={idx}
              className="bg-slate-950/80 rounded-xl p-3.5 border border-slate-800/80 hover:border-slate-700 transition-colors"
            >
              <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                <div className="flex items-center space-x-2.5">
                  <span className="w-5 h-5 rounded-full bg-slate-900 text-cyan-400 border border-cyan-800 flex items-center justify-center font-bold text-[10px]">
                    {idx + 1}
                  </span>
                  <span className="px-1.5 py-0.5 text-[10px] font-bold rounded bg-cyan-950 text-cyan-300 border border-cyan-800">
                    {code}
                  </span>
                  <span className="font-bold text-white tracking-tight">{label}</span>
                </div>

                <div className="flex items-center space-x-2">
                  <span className={`px-2 py-0.5 text-[10px] font-bold rounded-full border ${statusClass}`}>
                    {stage.status}
                  </span>
                  {stage.timestamp && (
                    <span className="text-[10px] text-slate-400">{stage.timestamp}</span>
                  )}
                </div>
              </div>

              {/* Artifact & Provenance identifiers */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px] pt-2 border-t border-slate-900">
                {stage.artifactId && (
                  <div className="truncate text-slate-400">
                    Artifact: <span className="text-slate-300" title={stage.artifactId}>{stage.artifactId}</span>
                  </div>
                )}
                {stage.provenanceId && (
                  <div className="truncate text-slate-400">
                    Provenance: <span className="text-cyan-300" title={stage.provenanceId}>{stage.provenanceId}</span>
                  </div>
                )}
              </div>

              {/* Stage Details summary if present */}
              {detailsKeys.length > 0 && (
                <div className="mt-2 pt-2 border-t border-slate-900/60 flex flex-wrap gap-2 text-[10px]">
                  {detailsKeys.map((k) => {
                    const val = stage.details[k];
                    const valStr =
                      typeof val === "object" ? JSON.stringify(val) : String(val);
                    return (
                      <span
                        key={k}
                        className="bg-slate-900 px-2 py-0.5 rounded border border-slate-800 text-slate-300 truncate max-w-xs"
                      >
                        <span className="text-slate-400">{k}:</span> {valStr}
                      </span>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
