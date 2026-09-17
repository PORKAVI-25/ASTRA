import React, { useState, useMemo } from "react";
import type { InvestigationSummary, TemporalTimelineNode } from "../../types/models";
import {
  getNodeStatusDetails,
  getM4dDecisionDetails,
  formatMathematicalOnset,
  matchNodeCorrespondence,
  sortTimelineNodesChronologically,
  formatDisplayDateTime,
} from "../../services/transformers";

interface TemporalTimelineProps {
  summary: InvestigationSummary;
  onSelectEpoch?: (node: TemporalTimelineNode, index: number) => void;
}

type FilterCategory = "all" | "supporting" | "flagged_suppressed" | "absence";

export const TemporalTimeline: React.FC<TemporalTimelineProps> = ({
  summary,
  onSelectEpoch,
}) => {
  const [filter, setFilter] = useState<FilterCategory>("all");
  const [expandedNodes, setExpandedNodes] = useState<Record<string, boolean>>({});

  // Ensure chronological order
  const chronologicalNodes = useMemo(() => {
    return sortTimelineNodesChronologically(summary.timelineNodes || []);
  }, [summary.timelineNodes]);

  // Mathematical Onset calculation
  const onset = useMemo(() => {
    return formatMathematicalOnset(
      summary.onset?.preChangeDate,
      summary.onset?.earliestSupportDate,
      summary.onset?.preChangeObservationId,
      summary.onset?.earliestSupportObservationId,
      summary.onset?.intervalDays,
      summary.onset?.intervalType
    );
  }, [summary.onset]);

  // Counts for filters
  const counts = useMemo(() => {
    let supporting = 0;
    let flaggedOrSuppressed = 0;
    let absence = 0;

    for (const node of chronologicalNodes) {
      if (node.status === "EARLIEST_SUPPORTING" || node.status === "PERSISTENT_SUPPORT") {
        supporting++;
      } else if (
        node.status === "FLAGGED_SUPPORT" ||
        node.status === "SUPPRESSED_ARTIFACT" ||
        node.m4dDecision === "FLAGGED" ||
        node.m4dDecision === "SUPPRESSED"
      ) {
        flaggedOrSuppressed++;
      } else if (node.status === "PRE_CHANGE_ABSENCE") {
        absence++;
      }
    }

    return {
      all: chronologicalNodes.length,
      supporting,
      flagged_suppressed: flaggedOrSuppressed,
      absence,
    };
  }, [chronologicalNodes]);

  // Filtered nodes
  const filteredNodes = useMemo(() => {
    if (filter === "all") return chronologicalNodes;
    if (filter === "supporting") {
      return chronologicalNodes.filter(
        (n) => n.status === "EARLIEST_SUPPORTING" || n.status === "PERSISTENT_SUPPORT"
      );
    }
    if (filter === "flagged_suppressed") {
      return chronologicalNodes.filter(
        (n) =>
          n.status === "FLAGGED_SUPPORT" ||
          n.status === "SUPPRESSED_ARTIFACT" ||
          n.m4dDecision === "FLAGGED" ||
          n.m4dDecision === "SUPPRESSED"
      );
    }
    if (filter === "absence") {
      return chronologicalNodes.filter((n) => n.status === "PRE_CHANGE_ABSENCE");
    }
    return chronologicalNodes;
  }, [chronologicalNodes, filter]);

  const toggleNodeExpansion = (obsId: string) => {
    setExpandedNodes((prev) => ({
      ...prev,
      [obsId]: !prev[obsId],
    }));
  };

  // Safe empty state
  if (!chronologicalNodes || chronologicalNodes.length === 0) {
    return (
      <div className="bg-slate-900/60 border border-dashed border-slate-800 rounded-2xl p-8 text-center font-mono space-y-3">
        <div className="text-3xl">⏱️</div>
        <h3 className="text-sm font-bold text-slate-300">No Temporal Timeline Nodes</h3>
        <p className="text-xs text-slate-400 max-w-md mx-auto">
          The dossier does not contain evaluated timeline nodes for this candidate region.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6 text-left font-sans">
      {/* 1. SECTION HEADER & ONSET BOUNDING INTERVAL */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-800">
          <div>
            <div className="flex items-center space-x-2">
              <span className="text-xl">⏱️</span>
              <h3 className="text-base font-bold font-mono text-white tracking-wide">
                Temporal Reasoning & Observation Timeline
              </h3>
              <span className="px-2 py-0.5 text-[10px] font-mono rounded bg-cyan-950 text-cyan-300 border border-cyan-800">
                Milestone D5
              </span>
            </div>
            <p className="text-xs text-slate-400 font-mono mt-1">
              Chronological progression of satellite acquisitions from pre-change absence to persistent support.
            </p>
          </div>

          <div className="flex items-center space-x-3 font-mono text-xs">
            <div className="bg-slate-950 px-3 py-1.5 rounded-xl border border-slate-800 text-slate-300">
              <span className="text-slate-400">Total Epochs: </span>
              <span className="font-bold text-cyan-300">{chronologicalNodes.length}</span>
            </div>
            <div className="bg-slate-950 px-3 py-1.5 rounded-xl border border-slate-800 text-slate-300">
              <span className="text-slate-400">Status: </span>
              <span className="font-bold text-emerald-400">{summary.supportStatus}</span>
            </div>
          </div>
        </div>

        {/* Bounded Onset Math Callout */}
        <div className="bg-slate-950/90 rounded-2xl p-5 border border-slate-800/90 font-mono space-y-4">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <div className="text-[11px] uppercase tracking-wider text-slate-400 font-bold flex items-center space-x-1.5">
                <span>MATHEMATICAL ONSET INTERVAL</span>
                <span className="px-1.5 py-0.2 text-[9px] rounded bg-cyan-950 text-cyan-400 border border-cyan-800">
                  {onset.intervalType}
                </span>
              </div>
              <div className="text-2xl font-black text-cyan-300 tracking-tight mt-1">
                {summary.onset?.physicalInterval || onset.formattedInterval}
              </div>
              <div className="text-xs text-slate-400 mt-0.5">
                Display span: <span className="text-slate-300">{summary.onset?.displaySpan || `[${onset.preDateFormatted}, ${onset.earliestDateFormatted}]`}</span>
              </div>
            </div>

            <div className="flex items-center space-x-4 bg-slate-900/90 px-4 py-3 rounded-xl border border-slate-800">
              <div className="text-center">
                <div className="text-[10px] uppercase text-slate-400">T_pre (Absence)</div>
                <div className="text-xs font-bold text-white mt-0.5">{onset.preDateFormatted}</div>
                <div className="text-[9px] text-slate-400 truncate max-w-[120px]" title={onset.preObservationId}>
                  {onset.preObservationId || "Baseline observation"}
                </div>
              </div>

              <div className="text-cyan-400 font-bold text-sm">→</div>

              <div className="text-center">
                <div className="text-[10px] uppercase text-emerald-400">T_earliest (Support)</div>
                <div className="text-xs font-bold text-white mt-0.5">{onset.earliestDateFormatted}</div>
                <div className="text-[9px] text-slate-400 truncate max-w-[120px]" title={onset.earliestObservationId}>
                  {onset.earliestObservationId || "First detection"}
                </div>
              </div>

              <div className="border-l border-slate-800 pl-3 text-center">
                <div className="text-[10px] uppercase text-slate-400">Sampling Gap</div>
                <div className="text-sm font-bold text-cyan-300">{onset.intervalDays}d</div>
              </div>
            </div>
          </div>

          {/* Explicit Rigorous Explanation Notice */}
          <div className="p-3.5 bg-slate-900/90 border border-slate-800/80 rounded-xl space-y-1 text-xs text-slate-300 font-mono">
            <div className="flex items-center space-x-2 text-cyan-300 font-bold">
              <span>📐</span>
              <span>Half-Open Bounding Interpretation: (T_pre, T_earliest]</span>
            </div>
            <ul className="list-disc list-inside text-[11px] text-slate-300 space-y-1 pl-1">
              <li>
                <strong className="text-white">T_pre</strong> ({onset.preDateFormatted}) is the latest observation supporting absence/pre-change baseline evidence.
              </li>
              <li>
                <strong className="text-emerald-300">T_earliest</strong> ({onset.earliestDateFormatted}) is the earliest observation supporting the detected candidate change.
              </li>
              <li>
                {onset.eventTimeExplanation}
              </li>
              <li className="text-amber-300/90 font-semibold">
                {onset.noDateFabricationNotice}
              </li>
            </ul>
          </div>
        </div>
      </div>

      {/* 2. CHRONOLOGICAL TRAJECTORY RIBBON (Visual Flow) */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg space-y-4">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-bold font-mono uppercase tracking-wider text-slate-300 flex items-center space-x-2">
            <span>🔄</span>
            <span>Chronological Trajectory Flow</span>
          </h4>
          <span className="text-[11px] font-mono text-slate-400">
            PRE-CHANGE → EARLIEST SUPPORT → PERSISTENCE
          </span>
        </div>

        <div className="overflow-x-auto pb-2">
          <div className="flex items-center space-x-2 min-w-max font-mono">
            {chronologicalNodes.map((node, idx) => {
              const statusInfo = getNodeStatusDetails(node.status);
              const isLast = idx === chronologicalNodes.length - 1;

              return (
                <React.Fragment key={node.observationId || idx}>
                  <div
                    onClick={() => {
                      toggleNodeExpansion(node.observationId);
                      onSelectEpoch?.(node, idx);
                    }}
                    className={`cursor-pointer transition-all p-3 rounded-xl border flex flex-col space-y-1.5 min-w-[170px] ${statusInfo.bgClasses} ${statusInfo.borderClasses} hover:scale-[1.02] shadow-sm`}
                  >
                    <div className="flex items-center justify-between text-[10px]">
                      <span className="text-slate-400">Epoch {idx + 1}</span>
                      <span className="text-sm">{statusInfo.icon}</span>
                    </div>

                    <div className="text-xs font-bold text-white truncate" title={node.displayDate}>
                      {node.displayDate}
                    </div>

                    <div className="text-[10px] text-slate-400 truncate" title={node.observationId}>
                      {node.observationId.split("_").slice(-2).join("_")}
                    </div>

                    <div className={`px-2 py-0.5 rounded text-[9px] font-bold border text-center truncate ${statusInfo.badgeClasses}`}>
                      {statusInfo.shortLabel}
                    </div>

                    {node.m4dDecision && (
                      <div className="text-[9px] text-slate-400 flex items-center justify-between pt-0.5">
                        <span>M4D:</span>
                        <span className={node.m4dDecision === "RETAINED" ? "text-emerald-400 font-bold" : "text-amber-400 font-bold"}>
                          {node.m4dDecision}
                        </span>
                      </div>
                    )}
                  </div>

                  {!isLast && (
                    <div className="flex flex-col items-center justify-center px-1 text-slate-400">
                      <span className="text-xs font-bold">→</span>
                      {idx === 0 && (
                        <span className="text-[8px] text-cyan-400 uppercase tracking-tighter">Onset</span>
                      )}
                    </div>
                  )}
                </React.Fragment>
              );
            })}
          </div>
        </div>
      </div>

      {/* 3. MULTI-EPOCH CORRESPONDENCE RIBBON */}
      {summary.spatialCorrespondence && summary.spatialCorrespondence.epochs.length > 0 && (
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg space-y-3 font-mono">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center space-x-2">
              <span>🔗</span>
              <span>Multi-Epoch Candidate Correspondence & Region ID Tracking</span>
            </h4>
            <div className="text-[11px] text-slate-400">
              Reference: <strong className="text-cyan-300">{summary.candidateRegionId}</strong>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {summary.spatialCorrespondence.epochs.map((epoch, eIdx) => {
              return (
                <div
                  key={epoch.targetPairId || eIdx}
                  className="bg-slate-950/80 p-3.5 rounded-xl border border-slate-800 text-xs space-y-1.5"
                >
                  <div className="flex items-center justify-between text-[10px] text-slate-400">
                    <span className="truncate max-w-[120px]" title={epoch.targetPairId}>
                      {epoch.targetPairId}
                    </span>
                    <span className="px-1.5 py-0.2 rounded text-[9px] bg-slate-800 text-slate-300">
                      {epoch.status}
                    </span>
                  </div>

                  <div className="flex items-center space-x-2 text-xs">
                    <span className="text-slate-400">{epoch.referenceCandidateId}</span>
                    <span className="text-cyan-400 font-bold">→</span>
                    <span className={`font-bold ${epoch.isIdShifted ? "text-amber-300" : "text-emerald-300"}`}>
                      {epoch.matchedRegionId || "Unmatched"}
                    </span>
                    {epoch.isIdShifted && (
                      <span className="text-[9px] px-1.5 py-0.2 rounded bg-amber-950/80 text-amber-300 border border-amber-800" title="Local region ID shifted across pairs">
                        ID Shift
                      </span>
                    )}
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-[10px] text-slate-400 pt-1 border-t border-slate-800/80">
                    <div>
                      IoU: <span className="text-white font-bold">{epoch.metricIou}</span>
                    </div>
                    <div>
                      Drift: <span className="text-white font-bold">{epoch.centroidDistanceM}m</span>
                    </div>
                  </div>

                  {epoch.resolutionNotes && epoch.resolutionNotes.length > 0 && (
                    <div className="text-[9px] text-slate-400 italic truncate" title={epoch.resolutionNotes[0]}>
                      {epoch.resolutionNotes[0]}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <p className="text-[10px] text-slate-400 italic">
            Note: Local candidate region IDs are not assumed stable across independent scene pairs. ASTRA maintains correspondence via georeferenced spatial bounding box IoU and centroid drift.
          </p>
        </div>
      )}

      {/* 4. FILTER CONTROLS */}
      <div className="flex flex-wrap items-center justify-between gap-3 font-mono text-xs">
        <div className="flex items-center space-x-2">
          <span className="text-slate-400">Filter Nodes:</span>
          <button
            onClick={() => setFilter("all")}
            className={`px-3 py-1 rounded-lg border transition-all cursor-pointer ${
              filter === "all"
                ? "bg-cyan-950 text-cyan-300 border-cyan-800 font-bold"
                : "bg-slate-900 text-slate-400 border-slate-800 hover:text-white"
            }`}
          >
            All Epochs ({counts.all})
          </button>
          <button
            onClick={() => setFilter("supporting")}
            className={`px-3 py-1 rounded-lg border transition-all cursor-pointer ${
              filter === "supporting"
                ? "bg-emerald-950 text-emerald-300 border-emerald-800 font-bold"
                : "bg-slate-900 text-slate-400 border-slate-800 hover:text-white"
            }`}
          >
            Supporting ({counts.supporting})
          </button>
          <button
            onClick={() => setFilter("flagged_suppressed")}
            className={`px-3 py-1 rounded-lg border transition-all cursor-pointer ${
              filter === "flagged_suppressed"
                ? "bg-amber-950 text-amber-300 border-amber-800 font-bold"
                : "bg-slate-900 text-slate-400 border-slate-800 hover:text-white"
            }`}
          >
            Flagged / Suppressed ({counts.flagged_suppressed})
          </button>
          <button
            onClick={() => setFilter("absence")}
            className={`px-3 py-1 rounded-lg border transition-all cursor-pointer ${
              filter === "absence"
                ? "bg-slate-800 text-slate-200 border-slate-700 font-bold"
                : "bg-slate-900 text-slate-400 border-slate-800 hover:text-white"
            }`}
          >
            Absence ({counts.absence})
          </button>
        </div>

        <div className="text-slate-400 text-[11px]">
          Showing {filteredNodes.length} of {chronologicalNodes.length} observation epochs
        </div>
      </div>

      {/* 5. DETAILED OBSERVATION CARDS */}
      <div className="space-y-4 font-mono">
        {filteredNodes.map((node, nodeIdx) => {
          const statusInfo = getNodeStatusDetails(node.status);
          const m4dInfo = getM4dDecisionDetails(node.m4dDecision);
          const correspondence = matchNodeCorrespondence(
            node,
            nodeIdx,
            summary.spatialCorrespondence?.epochs || [],
            summary.candidateRegionId
          );
          const isExpanded = expandedNodes[node.observationId] ?? true;

          return (
            <div
              key={node.observationId || nodeIdx}
              className={`bg-slate-900/90 border rounded-2xl p-5 transition-all shadow-md ${statusInfo.borderClasses}`}
            >
              {/* Card Top Row */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-800">
                <div className="flex items-center space-x-3">
                  <div className="w-8 h-8 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-center text-base">
                    {statusInfo.icon}
                  </div>
                  <div>
                    <div className="flex items-center space-x-2">
                      <span className="text-sm font-bold text-white">
                        {node.displayDate}
                      </span>
                      <span className="text-xs text-slate-400">
                        ({node.acquisitionTime ? formatDisplayDateTime(node.acquisitionTime) : "Time N/A"})
                      </span>
                    </div>
                    <div className="text-[11px] text-slate-400 flex items-center space-x-2 mt-0.5">
                      <span className="text-cyan-300 font-semibold">{node.observationId}</span>
                      <span>•</span>
                      <span>{node.platform || "Platform N/A"} ({node.sensor || "Sensor N/A"})</span>
                      {node.isCrossSensor && (
                        <span className="px-1.5 py-0.2 rounded bg-purple-950 text-purple-300 border border-purple-800 text-[9px]">
                          Cross-Sensor
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  {/* Status Badge */}
                  <div className={`px-2.5 py-1 rounded-lg text-xs font-bold border flex items-center space-x-1.5 ${statusInfo.badgeClasses}`}>
                    <span>{statusInfo.icon}</span>
                    <span>{statusInfo.label}</span>
                  </div>

                  {/* M4D Screening Badge */}
                  {node.m4dDecision && (
                    <div className={`px-2.5 py-1 rounded-lg text-xs font-bold border flex items-center space-x-1 ${m4dInfo.badgeClasses}`}>
                      <span>{m4dInfo.icon}</span>
                      <span>{m4dInfo.label}</span>
                    </div>
                  )}

                  <button
                    onClick={() => toggleNodeExpansion(node.observationId)}
                    className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs transition-colors cursor-pointer"
                    aria-label="Toggle node details"
                  >
                    {isExpanded ? "▲ Collapse" : "▼ Expand"}
                  </button>
                </div>
              </div>

              {/* Collapsible Card Details */}
              {isExpanded && (
                <div className="pt-4 space-y-4 text-xs">
                  {/* Status Definition Callout */}
                  <div className={`p-3 rounded-xl border ${statusInfo.bgClasses} ${statusInfo.borderClasses} text-slate-200 text-xs`}>
                    <div className="font-bold flex items-center space-x-1.5 mb-0.5">
                      <span>{statusInfo.icon}</span>
                      <span>Evidentiary Role: {statusInfo.label}</span>
                    </div>
                    <p className="text-[11px] text-slate-300">
                      {statusInfo.description}
                    </p>
                  </div>

                  {/* Metrics & Correspondence Grid */}
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    {/* Support Score */}
                    <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 space-y-1.5">
                      <div className="text-[10px] uppercase text-slate-400 font-semibold">
                        Heuristic Support Score
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-base font-bold text-cyan-300">
                          {Math.round(node.supportScore * 100)}%
                        </span>
                        <span className="text-xs text-slate-400">
                          {node.supportScore} / 1.0
                        </span>
                      </div>
                      <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
                        <div
                          className="bg-cyan-400 h-1.5 rounded-full"
                          style={{ width: `${Math.min(100, Math.max(0, node.supportScore * 100))}%` }}
                        />
                      </div>
                      {node.isEarliestSupportEligible && (
                        <div className="text-[9px] text-emerald-400 font-semibold flex items-center space-x-1 pt-0.5">
                          <span>✓</span>
                          <span>Eligible for Earliest Support</span>
                        </div>
                      )}
                    </div>

                    {/* Candidate Region Correspondence */}
                    <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 space-y-1">
                      <div className="text-[10px] uppercase text-slate-400 font-semibold">
                        Spatial Correspondence
                      </div>
                      <div className="text-xs font-bold text-white flex items-center space-x-1">
                        <span>{correspondence.shiftDisplay}</span>
                      </div>
                      <div className="text-[10px] text-slate-400 flex items-center justify-between pt-0.5">
                        <span>IoU: <strong className="text-white">{correspondence.metricIou}</strong></span>
                        <span>Drift: <strong className="text-white">{correspondence.centroidDistanceM}m</strong></span>
                      </div>
                      <div className="text-[9px] text-slate-400 truncate" title={correspondence.relationship}>
                        Relationship: <span className="text-slate-300">{correspondence.relationship}</span>
                      </div>
                    </div>

                    {/* Category Observed */}
                    <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 space-y-1">
                      <div className="text-[10px] uppercase text-slate-400 font-semibold">
                        Observed Classification
                      </div>
                      <div className="text-xs font-bold text-amber-300 uppercase">
                        {node.categoryObserved || "No Change Detected"}
                      </div>
                      <div className="text-[10px] text-slate-400">
                        Confidence: <span className="text-white font-semibold">{node.categoryConfidence || "N/A"}</span>
                      </div>
                      {node.m4dDecision && (
                        <div className="text-[9px] text-slate-400 truncate" title={m4dInfo.description}>
                          Screening: <span className="text-slate-300">{m4dInfo.label}</span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Decision Reasons & Data Limitations */}
                  {((node.reasons && node.reasons.length > 0) ||
                    (node.limitations && node.limitations.length > 0)) && (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                      {node.reasons && node.reasons.length > 0 && (
                        <div className="bg-slate-950/70 p-3 rounded-xl border border-slate-800/80">
                          <div className="text-[10px] uppercase tracking-wider text-slate-400 font-bold mb-1 flex items-center space-x-1">
                            <span>📋</span>
                            <span>Audit Decision Reasons</span>
                          </div>
                          <ul className="list-disc list-inside text-[11px] text-slate-300 space-y-0.5">
                            {node.reasons.map((r, rIdx) => (
                              <li key={rIdx}>{r}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {node.limitations && node.limitations.length > 0 && (
                        <div className="bg-amber-950/20 p-3 rounded-xl border border-amber-900/40">
                          <div className="text-[10px] uppercase tracking-wider text-amber-300 font-bold mb-1 flex items-center space-x-1">
                            <span>⚠️</span>
                            <span>Observation Limitations</span>
                          </div>
                          <ul className="list-disc list-inside text-[11px] text-amber-200/80 space-y-0.5">
                            {node.limitations.map((l, lIdx) => (
                              <li key={lIdx}>{l}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
