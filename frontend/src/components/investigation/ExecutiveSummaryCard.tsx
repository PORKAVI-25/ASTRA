import React from "react";
import type { InvestigationSummary, AnalystReviewRecord } from "../../types/models";
import { getLatestReview } from "../../services/reviewStore";

interface ExecutiveSummaryCardProps {
  summary: InvestigationSummary;
  review?: AnalystReviewRecord | null;
}

export const ExecutiveSummaryCard: React.FC<ExecutiveSummaryCardProps> = ({ summary, review }) => {
  const isCompleted = summary.status === "COMPLETED";

  const currentReview =
    review !== undefined
      ? review
      : summary.analystReview ||
        getLatestReview(summary.investigationId, summary.candidateRegionId);

  const reviewDecision = currentReview ? currentReview.decision : "NOT REVIEWED";
  const reviewColor =
    reviewDecision === "CONFIRMED" || reviewDecision === "CONFIRM"
      ? "text-emerald-300 bg-emerald-950 border-emerald-700"
      : reviewDecision === "REJECTED" || reviewDecision === "REJECT"
      ? "text-rose-300 bg-rose-950 border-rose-700"
      : reviewDecision === "PENDING" || reviewDecision === "FLAG_NEEDS_REVIEW"
      ? "text-amber-300 bg-amber-950 border-amber-700"
      : "text-slate-400 bg-slate-950 border-slate-800";

  const confidenceColor =
    summary.confidenceTier === "high"
      ? "text-emerald-400 bg-emerald-950/80 border-emerald-800"
      : summary.confidenceTier === "medium"
      ? "text-cyan-300 bg-cyan-950/80 border-cyan-800"
      : summary.confidenceTier === "low"
      ? "text-amber-300 bg-amber-950/80 border-amber-800"
      : "text-rose-300 bg-rose-950/80 border-rose-800";

  const supportColor =
    summary.supportStatus === "STRONG_TEMPORAL_SUPPORT" ||
    summary.supportStatus === "PERSISTENT_SUPPORT"
      ? "text-emerald-300 bg-emerald-950/80 border-emerald-800"
      : summary.supportStatus === "FLAGGED_SUPPORT"
      ? "text-amber-300 bg-amber-950/80 border-amber-800"
      : summary.supportStatus === "SUPPRESSED_ARTIFACT" ||
        summary.supportStatus === "NO_TEMPORAL_SUPPORT"
      ? "text-rose-300 bg-rose-950/80 border-rose-800"
      : "text-slate-300 bg-slate-900 border-slate-700";

  const evaluatedCount = summary.timelineNodes.length;
  const supportingCount = summary.timelineNodes.filter(
    (n) => n.status === "EARLIEST_SUPPORTING" || n.status === "PERSISTENT_SUPPORT"
  ).length;

  return (
    <div className="bg-gradient-to-br from-slate-900 via-slate-900/90 to-slate-950 border border-slate-800 rounded-2xl p-6 shadow-xl relative overflow-hidden font-sans text-left">
      <div className="absolute top-0 right-0 -mt-10 -mr-10 w-52 h-52 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none"></div>

      {/* Investigation Dossier Header */}
      <div className="flex flex-wrap items-start justify-between gap-4 mb-5 pb-4 border-b border-slate-800/90">
        <div>
          <div className="flex items-center space-x-2.5 mb-2 flex-wrap gap-y-1">
            <span
              className={`w-2.5 h-2.5 rounded-full ${
                isCompleted ? "bg-emerald-400 animate-pulse" : "bg-rose-400"
              }`}
            ></span>
            <span className="text-xs font-mono font-bold tracking-wider uppercase text-slate-400">
              Investigation Result Dossier
            </span>
            <span
              className={`px-2.5 py-0.5 text-[10px] font-mono font-bold rounded-full border ${
                isCompleted
                  ? "bg-emerald-950 text-emerald-300 border-emerald-800"
                  : "bg-rose-950 text-rose-300 border-rose-800"
              }`}
            >
              {summary.status}
            </span>
            {summary.provenance.isVerified && (
              <span className="px-2 py-0.5 text-[10px] font-mono font-bold rounded-full bg-cyan-950 text-cyan-300 border border-cyan-800">
                ✓ Provenance Verified
              </span>
            )}
            <span className={`px-2.5 py-0.5 text-[10px] font-mono font-bold rounded-full border ${reviewColor}`}>
              Analyst: {reviewDecision}
            </span>
          </div>

          <h2 className="text-xl sm:text-2xl font-bold font-mono text-white tracking-tight break-all">
            {summary.investigationId}
          </h2>

          <div className="flex flex-wrap items-center gap-3 text-xs font-mono text-slate-400 mt-2">
            <div>
              Series: <span className="text-slate-200 font-semibold">{summary.seriesId}</span>
            </div>
            <span>•</span>
            <div>
              Discovery: <span className="text-slate-200 font-semibold">{summary.discoveryPairId}</span>
            </div>
            <span>•</span>
            <div>
              Region:{" "}
              <span className="text-cyan-300 font-bold bg-cyan-950/80 px-2 py-0.5 rounded border border-cyan-800">
                {summary.candidateRegionId}
              </span>
            </div>
          </div>
        </div>

        {/* Content Hash Badge */}
        <div className="bg-slate-950/80 p-3 rounded-xl border border-slate-800 text-xs font-mono text-right">
          <div className="text-[10px] text-slate-400 uppercase font-semibold">Integrity Hash (SHA-256)</div>
          <div className="text-cyan-300 font-bold tracking-wider mt-0.5">
            {summary.contentHash || "N/A"}
          </div>
          <div className="text-[10px] text-slate-400 mt-1">{summary.createdAt}</div>
        </div>
      </div>

      {/* 4-Column Executive Assessment Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5 mb-5 font-mono text-xs">
        {/* Metric 1: Category */}
        <div className="bg-slate-950/80 p-4 rounded-xl border border-slate-800 flex flex-col justify-between">
          <div className="text-[10px] text-slate-400 uppercase font-semibold tracking-wider mb-1.5">
            Primary Category
          </div>
          <div>
            <div className="text-lg font-bold text-white tracking-wide">
              {summary.category.primary}
            </div>
            <div className="text-[11px] text-slate-400 mt-1 flex items-center space-x-1.5">
              <span>{summary.category.isValid ? "✓ Validated trajectory" : "⚠️ Trajectory conflict"}</span>
            </div>
          </div>
        </div>

        {/* Metric 2: Temporal Support */}
        <div className="bg-slate-950/80 p-4 rounded-xl border border-slate-800 flex flex-col justify-between">
          <div className="text-[10px] text-slate-400 uppercase font-semibold tracking-wider mb-1.5">
            Temporal Support
          </div>
          <div>
            <div className="text-sm font-bold truncate">
              <span className={`px-2 py-0.5 rounded-lg border ${supportColor}`}>
                {summary.supportStatus}
              </span>
            </div>
            <div className="text-[11px] text-slate-400 mt-1">
              {supportingCount} of {evaluatedCount} epochs supportive
            </div>
          </div>
        </div>

        {/* Metric 3: Confidence Tier */}
        <div className="bg-slate-950/80 p-4 rounded-xl border border-slate-800 flex flex-col justify-between">
          <div className="text-[10px] text-slate-400 uppercase font-semibold tracking-wider mb-1.5">
            Confidence Tier
          </div>
          <div>
            <div className="text-lg font-bold uppercase">
              <span className={`px-2.5 py-0.5 rounded-lg border text-sm ${confidenceColor}`}>
                {summary.confidenceTier} CONFIDENCE
              </span>
            </div>
            <div className="text-[11px] text-slate-400 mt-1">
              M4E Heuristic Evaluation
            </div>
          </div>
        </div>

        {/* Metric 4: Onset Bounding Window */}
        <div className="bg-slate-950/80 p-4 rounded-xl border border-slate-800 flex flex-col justify-between">
          <div className="text-[10px] text-slate-400 uppercase font-semibold tracking-wider mb-1.5">
            Bounded Onset Interval
          </div>
          <div>
            <div className="text-sm font-bold text-cyan-300 font-mono">
              {summary.onset.physicalInterval}
            </div>
            <div className="text-[11px] text-emerald-400 mt-1">
              Window: {summary.onset.intervalDays} days
            </div>
          </div>
        </div>
      </div>

      {/* Decision Summary Notes */}
      {summary.decisionReasons.length > 0 && (
        <div className="p-3.5 bg-slate-950/60 rounded-xl border border-slate-800 text-xs font-mono space-y-1">
          <div className="text-[10px] text-slate-400 uppercase font-semibold mb-1">
            Evaluator Decision Reasons (M4E)
          </div>
          {summary.decisionReasons.map((reason, idx) => (
            <div key={idx} className="flex items-start space-x-2 text-slate-300 text-[11px]">
              <span className="text-cyan-400 font-bold">•</span>
              <span>{reason}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
