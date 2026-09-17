import React from "react";
import type { InvestigationSummary } from "../../types/models";

interface SamplingCaveatsCardProps {
  summary: InvestigationSummary;
}

export const SamplingCaveatsCard: React.FC<SamplingCaveatsCardProps> = ({ summary }) => {
  const isAmbiguous =
    summary.supportStatus === "AMBIGUOUS_EVIDENCE" ||
    summary.supportStatus === "INSUFFICIENT_DATA" ||
    summary.confidenceTier === "uncertain" ||
    summary.confidenceTier === "low";

  const isSuppressedOrFlagged =
    summary.suppression.overallScreeningOutcome === "FLAGGED_RISK" ||
    summary.suppression.overallScreeningOutcome === "SUPPRESSED" ||
    summary.supportStatus === "FLAGGED_SUPPORT" ||
    summary.supportStatus === "SUPPRESSED_ARTIFACT";

  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl text-left font-sans space-y-4">
      <div className="flex items-center justify-between pb-3 border-b border-slate-800">
        <div>
          <div className="flex items-center space-x-2">
            <span className="text-base">🔬</span>
            <h3 className="text-sm font-bold font-mono text-white tracking-wide">
              Temporal Sampling & Evidence Limitations
            </h3>
            <span className="px-2 py-0.5 text-[10px] font-mono rounded bg-slate-800 text-slate-300">
              Audit Justification
            </span>
          </div>
          <p className="text-xs text-slate-400 font-mono mt-0.5">
            Transparent evidentiary caveats and satellite acquisition uncertainties required by SIH26227.
          </p>
        </div>
      </div>

      {/* Ambiguity or Insufficient Evidence Banner if applicable */}
      {isAmbiguous && (
        <div className="p-4 bg-amber-950/40 border border-amber-800/80 rounded-xl text-amber-200 font-mono text-xs space-y-1">
          <div className="font-bold flex items-center space-x-2 text-amber-100">
            <span>⚠️</span>
            <span>Ambiguous or Low-Confidence Temporal Support</span>
          </div>
          <p className="text-[11px] text-amber-300/80 leading-relaxed">
            The multi-temporal observation sequence does not provide high-confidence persistent support.
            Manual analyst verification or supplementary sensor collection is strongly advised.
          </p>
        </div>
      )}

      {/* Suppression or Cloud Risk Banner if applicable */}
      {isSuppressedOrFlagged && (
        <div className="p-4 bg-rose-950/40 border border-rose-800/80 rounded-xl text-rose-200 font-mono text-xs space-y-1">
          <div className="font-bold flex items-center space-x-2 text-rose-100">
            <span>🛡️</span>
            <span>False-Alarm Risk or Artifact Screening Active</span>
          </div>
          <p className="text-[11px] text-rose-300/80 leading-relaxed">
            One or more epochs were flagged or suppressed during M4D screening.
            Check cloud masking and co-registration alignment before confirming this physical emergence.
          </p>
        </div>
      )}

      {/* Evidentiary Limitations */}
      <div className="space-y-2 font-mono text-xs">
        <div className="text-[11px] font-bold text-slate-300 uppercase tracking-wide">
          Observed Data Limitations ({summary.evidenceLimitations.length})
        </div>

        {summary.evidenceLimitations.length === 0 ? (
          <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800/80 text-slate-400 text-[11px] italic">
            No specific acquisition limitations flagged by backend temporal evaluator.
          </div>
        ) : (
          <div className="space-y-1.5">
            {summary.evidenceLimitations.map((lim, idx) => (
              <div
                key={idx}
                className="p-3 bg-slate-950/70 rounded-xl border border-slate-800/80 text-slate-300 text-[11px] flex items-start space-x-2"
              >
                <span className="text-amber-400 font-bold">•</span>
                <span className="leading-relaxed">{lim}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Evaluator Decision Reasons */}
      <div className="space-y-2 font-mono text-xs pt-2 border-t border-slate-800/80">
        <div className="text-[11px] font-bold text-slate-300 uppercase tracking-wide">
          Evaluator Decision Rationale ({summary.decisionReasons.length})
        </div>

        {summary.decisionReasons.length === 0 ? (
          <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800/80 text-slate-400 text-[11px] italic">
            Standard deterministic rules applied.
          </div>
        ) : (
          <div className="space-y-1.5">
            {summary.decisionReasons.map((reason, idx) => (
              <div
                key={idx}
                className="p-3 bg-slate-950/70 rounded-xl border border-slate-800/80 text-slate-300 text-[11px] flex items-start space-x-2"
              >
                <span className="text-cyan-400 font-bold">•</span>
                <span className="leading-relaxed">{reason}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
