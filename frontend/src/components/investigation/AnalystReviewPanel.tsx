/**
 * ASTRA Milestone D9: Analyst Review Panel
 *
 * Implements the analyst-in-the-loop triage workflow:
 * - Clear, unambiguous visual separation between machine findings and human decision.
 * - Records analyst decisions: PENDING, CONFIRMED, REJECTED.
 * - Manages sequential revision histories without mutating past records.
 * - Prevents duplicate revisions when inputs are unchanged.
 * - Computes deterministic SHA-256 audit hashes offline.
 * - Supports local JSON export and clipboard hash copying.
 * - 100% offline air-gap compliant (0 external dependencies or remote calls).
 */

import React, { useState } from "react";
import type { InvestigationSummary, ReviewDecision, AnalystReviewRecord } from "../../types/models";
import {
  getReviewHistory,
  saveReviewRevision,
  exportInvestigationReviewJson,
  normalizeDecision,
} from "../../services/reviewStore";
import { ReviewHistory } from "./ReviewHistory";

interface AnalystReviewPanelProps {
  summary: InvestigationSummary;
  onReviewUpdated?: (latest: AnalystReviewRecord) => void;
}

const REASON_PRESETS = [
  "Confirmed ground structural onset",
  "Persistent signature across multi-epoch series",
  "Consistent with linear road development",
  "Water boundary seasonal expansion / contraction",
  "Likely false alarm - seasonal surface variation",
  "Image registration / edge displacement artifact",
  "Cloud / cloud-shadow contamination",
  "Viewing geometry / sensor parallax effect",
  "Insufficient spectral / temporal evidence",
  "Other / Custom analyst justification",
];

export const AnalystReviewPanel: React.FC<AnalystReviewPanelProps> = ({
  summary,
  onReviewUpdated,
}) => {
  const invId = summary.investigationId || "inv_unknown";
  const regId = summary.candidateRegionId || "reg_unknown";

  const currentKey = `${invId}:${regId}`;
  const [prevKey, setPrevKey] = useState<string>(currentKey);

  const [history, setHistory] = useState<AnalystReviewRecord[]>(() => getReviewHistory(invId, regId));
  const initialLatest = history[0];

  const [selectedDecision, setSelectedDecision] = useState<ReviewDecision>(() => initialLatest?.decision || "PENDING");
  const [selectedReason, setSelectedReason] = useState<string>(() => {
    if (!initialLatest) return REASON_PRESETS[0];
    return REASON_PRESETS.includes(initialLatest.selectedReason) ? initialLatest.selectedReason : "Other / Custom analyst justification";
  });
  const [customReason, setCustomReason] = useState<string>(() => {
    if (!initialLatest) return "";
    return REASON_PRESETS.includes(initialLatest.selectedReason) ? "" : initialLatest.selectedReason;
  });
  const [analystNote, setAnalystNote] = useState<string>(() => initialLatest?.analystNote || initialLatest?.comments || "");
  const [analystId, setAnalystId] = useState<string>(() => initialLatest?.analystId || "analyst_local");
  const [statusMessage, setStatusMessage] = useState<{ type: "success" | "info" | "error"; text: string } | null>(null);
  const [copiedHash, setCopiedHash] = useState<boolean>(false);

  // Sync state if investigationId or candidateRegionId changes
  if (prevKey !== currentKey) {
    setPrevKey(currentKey);
    const records = getReviewHistory(invId, regId);
    setHistory(records);
    if (records.length > 0) {
      const latest = records[0];
      setSelectedDecision(latest.decision);
      if (REASON_PRESETS.includes(latest.selectedReason)) {
        setSelectedReason(latest.selectedReason);
        setCustomReason("");
      } else {
        setSelectedReason("Other / Custom analyst justification");
        setCustomReason(latest.selectedReason);
      }
      setAnalystNote(latest.analystNote || latest.comments || "");
      if (latest.analystId) {
        setAnalystId(latest.analystId);
      }
    } else {
      setSelectedDecision("PENDING");
      setSelectedReason(REASON_PRESETS[0]);
      setCustomReason("");
      setAnalystNote("");
    }
    setStatusMessage(null);
  }

  const latestReview = history.length > 0 ? history[0] : null;

  // Form changed check (Confirmation Guard)
  const currentNormalizedDecision = normalizeDecision(selectedDecision);
  const effectiveReason = selectedReason === "Other / Custom analyst justification" && customReason.trim()
    ? customReason.trim()
    : selectedReason;

  const isFormChanged =
    !latestReview ||
    latestReview.decision !== currentNormalizedDecision ||
    (latestReview.analystNote || latestReview.comments || "").trim() !== analystNote.trim() ||
    (latestReview.selectedReason || "").trim() !== effectiveReason.trim();

  const handleSaveReview = () => {
    setStatusMessage(null);

    const result = saveReviewRevision({
      investigationId: invId,
      candidateRegionId: regId,
      seriesId: summary.seriesId,
      discoveryPairId: summary.discoveryPairId,
      decision: currentNormalizedDecision,
      analystNote: analystNote.trim(),
      selectedReason: effectiveReason,
      reasonCode: effectiveReason.toLowerCase().replace(/[^a-z0-9]+/g, "_"),
      analystId: analystId.trim() || "analyst_local",
    });

    const updatedHistory = getReviewHistory(invId, regId);
    setHistory(updatedHistory);

    if (result.isDuplicate) {
      setStatusMessage({
        type: "info",
        text: `No change detected. Decision and notes are identical to current Revision #${result.revisionNumber}; duplicate revision skipped.`,
      });
    } else {
      setStatusMessage({
        type: "success",
        text: `✓ Review Revision #${result.revisionNumber} saved successfully with deterministic SHA-256 audit hash.`,
      });
      if (onReviewUpdated) {
        onReviewUpdated(result.review);
      }
    }
  };

  const handleExportJson = () => {
    try {
      const jsonStr = exportInvestigationReviewJson(invId, regId);
      const blob = new Blob([jsonStr], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `astra_review_${invId}_${regId}.json`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch {
      // Graceful fallback
    }
  };

  const handleCopyCurrentHash = () => {
    if (latestReview?.auditHash && typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(latestReview.auditHash).then(() => {
        setCopiedHash(true);
        setTimeout(() => setCopiedHash(false), 2000);
      });
    }
  };

  return (
    <div className="space-y-6 text-left font-sans">
      {/* 1. Header Banner & Non-Overclaim Notice */}
      <div className="p-4 bg-slate-900/90 border border-slate-800 rounded-2xl flex flex-col md:flex-row md:items-center justify-between gap-3 shadow-lg">
        <div className="space-y-1">
          <div className="flex items-center space-x-2">
            <span className="text-base">📝</span>
            <span className="text-xs font-mono font-bold text-cyan-300 uppercase tracking-wider">
              Analyst Review & Local Audit Trail • Milestone D9
            </span>
            <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-cyan-950 text-cyan-300 border border-cyan-800">
              Human-in-the-Loop
            </span>
          </div>
          <p className="text-xs text-slate-300 font-mono leading-relaxed">
            Record independent human analyst decisions (Confirm, Reject, Pending) on candidate {regId}. Analyst decisions are strictly decoupled from machine classification models and stored locally with deterministic SHA-256 integrity digests.
          </p>
        </div>

        <div className="flex items-center space-x-2 shrink-0">
          <button
            onClick={handleExportJson}
            className="px-3 py-1.5 rounded-xl bg-cyan-950 hover:bg-cyan-900 text-cyan-300 border border-cyan-800 font-mono text-xs font-bold transition-all cursor-pointer shadow-sm"
            title="Export full analyst review revision history as JSON"
          >
            📥 Export Review JSON
          </button>
        </div>
      </div>

      {/* 2. Side-by-Side: Machine Assessment vs Analyst Decision */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 font-mono text-xs">
        {/* Left Column: Machine-Derived Assessment (Strictly Read-Only) */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div>
              <span className="text-[10px] uppercase tracking-wider text-slate-400 font-bold">
                Automated Pipeline Outputs
              </span>
              <h3 className="text-sm font-bold text-white mt-0.5">
                Machine-Derived Assessment
              </h3>
            </div>
            <span className="px-2 py-0.5 rounded text-[10px] bg-slate-950 text-slate-400 border border-slate-800">
              READ-ONLY
            </span>
          </div>

          <div className="p-3 bg-slate-950/70 rounded-xl border border-slate-800 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <div className="text-[10px] text-slate-500 uppercase">Classified Category</div>
                <div className="text-sm font-bold text-white mt-0.5 uppercase">
                  {summary.category.primary || "UNCLASSIFIED"}
                </div>
              </div>

              <div>
                <div className="text-[10px] text-slate-500 uppercase">Evidentiary Confidence</div>
                <div className="text-sm font-bold text-cyan-300 mt-0.5 uppercase">
                  {summary.confidenceTier} tier
                </div>
              </div>

              <div>
                <div className="text-[10px] text-slate-500 uppercase">Temporal Support</div>
                <div className="text-xs font-bold text-slate-200 mt-0.5">
                  {summary.supportStatus}
                </div>
              </div>

              <div>
                <div className="text-[10px] text-slate-500 uppercase">Onset Interval Bounds</div>
                <div className="text-xs font-bold text-slate-200 mt-0.5">
                  {summary.onset.physicalInterval || "(T_pre, T_earliest]"}
                </div>
              </div>
            </div>

            <div className="pt-2 border-t border-slate-900 text-[10px] text-slate-400 leading-relaxed">
              Evidentiary stratification represents rule-based model support; it is NOT a calibrated probability. The human review on the right records analyst judgment without overwriting machine features.
            </div>
          </div>

          {/* Current Review State Display */}
          <div className="p-3.5 bg-slate-950/70 rounded-xl border border-slate-800 space-y-2">
            <div className="text-[10px] text-slate-400 uppercase font-bold">
              Current Recorded Review State
            </div>

            {latestReview ? (
              <div className="space-y-1.5 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Current Status:</span>
                  <span className={`font-bold px-2 py-0.5 rounded text-[11px] ${
                    latestReview.decision === "CONFIRMED"
                      ? "bg-emerald-950 text-emerald-300 border border-emerald-700"
                      : latestReview.decision === "REJECTED"
                      ? "bg-rose-950 text-rose-300 border border-rose-700"
                      : "bg-amber-950 text-amber-300 border border-amber-700"
                  }`}>
                    {latestReview.decision}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Revision:</span>
                  <span className="text-white font-bold">
                    Revision #{latestReview.revisionNumber || 1}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Recorded By:</span>
                  <span className="text-slate-200 font-bold">{latestReview.analystId}</span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Last Updated:</span>
                  <span className="text-slate-300">{latestReview.updatedAt || latestReview.createdAt}</span>
                </div>

                <div className="flex items-center justify-between pt-1 border-t border-slate-900">
                  <span className="text-slate-400">Audit Hash:</span>
                  <div className="flex items-center space-x-1">
                    <span className="text-amber-300 truncate max-w-[120px]" title={latestReview.auditHash}>
                      {latestReview.auditHash.slice(0, 14)}...
                    </span>
                    <button
                      onClick={handleCopyCurrentHash}
                      className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 cursor-pointer"
                    >
                      {copiedHash ? "✓" : "Copy"}
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-slate-500 text-[11px] py-1">
                Status: <strong className="text-slate-300">NOT REVIEWED</strong> (No local record)
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Analyst Decision Controls */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div>
              <span className="text-[10px] uppercase tracking-wider text-cyan-400 font-bold">
                Analyst-in-the-Loop Action
              </span>
              <h3 className="text-sm font-bold text-white mt-0.5">
                Record Analyst Decision
              </h3>
            </div>
            <span className="px-2 py-0.5 rounded text-[10px] bg-cyan-950 text-cyan-300 border border-cyan-800">
              CANDIDATE {regId}
            </span>
          </div>

          {/* Decision Selection Cards */}
          <div className="space-y-2">
            <div className="text-[10px] uppercase text-slate-400 font-bold">
              Select Decision:
            </div>
            <div className="grid grid-cols-3 gap-2">
              <label
                className={`p-3 rounded-xl border text-center cursor-pointer transition-all flex flex-col items-center justify-center space-y-1 ${
                  selectedDecision === "CONFIRMED"
                    ? "bg-emerald-950/80 border-emerald-600 text-emerald-300 ring-1 ring-emerald-500/40 font-bold"
                    : "bg-slate-950/60 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200"
                }`}
              >
                <input
                  type="radio"
                  name="review_decision"
                  value="CONFIRMED"
                  checked={selectedDecision === "CONFIRMED"}
                  onChange={() => setSelectedDecision("CONFIRMED")}
                  className="sr-only"
                />
                <span className="text-base">✅</span>
                <span className="text-xs">Confirm</span>
              </label>

              <label
                className={`p-3 rounded-xl border text-center cursor-pointer transition-all flex flex-col items-center justify-center space-y-1 ${
                  selectedDecision === "REJECTED"
                    ? "bg-rose-950/80 border-rose-600 text-rose-300 ring-1 ring-rose-500/40 font-bold"
                    : "bg-slate-950/60 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200"
                }`}
              >
                <input
                  type="radio"
                  name="review_decision"
                  value="REJECTED"
                  checked={selectedDecision === "REJECTED"}
                  onChange={() => setSelectedDecision("REJECTED")}
                  className="sr-only"
                />
                <span className="text-base">❌</span>
                <span className="text-xs">Reject</span>
              </label>

              <label
                className={`p-3 rounded-xl border text-center cursor-pointer transition-all flex flex-col items-center justify-center space-y-1 ${
                  selectedDecision === "PENDING"
                    ? "bg-amber-950/80 border-amber-600 text-amber-300 ring-1 ring-amber-500/40 font-bold"
                    : "bg-slate-950/60 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200"
                }`}
              >
                <input
                  type="radio"
                  name="review_decision"
                  value="PENDING"
                  checked={selectedDecision === "PENDING"}
                  onChange={() => setSelectedDecision("PENDING")}
                  className="sr-only"
                />
                <span className="text-base">⏳</span>
                <span className="text-xs">Pending</span>
              </label>
            </div>
          </div>

          {/* Reason Selection */}
          <div className="space-y-1.5">
            <label className="text-[10px] uppercase text-slate-400 font-bold block">
              Justification / Reason Preset:
            </label>
            <select
              value={selectedReason}
              onChange={(e) => setSelectedReason(e.target.value)}
              className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-200 focus:outline-none focus:border-cyan-500"
            >
              {REASON_PRESETS.map((preset) => (
                <option key={preset} value={preset}>
                  {preset}
                </option>
              ))}
            </select>

            {selectedReason === "Other / Custom analyst justification" && (
              <input
                type="text"
                value={customReason}
                onChange={(e) => setCustomReason(e.target.value)}
                placeholder="Enter custom justification summary..."
                className="w-full px-3 py-1.5 mt-1 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
              />
            )}
          </div>

          {/* Analyst Notes */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-[10px] uppercase text-slate-400 font-bold">
                Analyst Notes & Audit Explanation:
              </label>
              <span className="text-[10px] text-slate-500">{analystNote.length} characters</span>
            </div>
            <textarea
              value={analystNote}
              onChange={(e) => setAnalystNote(e.target.value)}
              placeholder="Enter technical justification, observed spatial details, or reasons for confirmation/rejection..."
              rows={3}
              className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500 resize-y"
            />
          </div>

          {/* Analyst ID input */}
          <div className="flex items-center space-x-2">
            <span className="text-[10px] uppercase text-slate-500 font-bold shrink-0">Analyst ID:</span>
            <input
              type="text"
              value={analystId}
              onChange={(e) => setAnalystId(e.target.value)}
              placeholder="analyst_callsign"
              className="px-2.5 py-1 bg-slate-950 border border-slate-800 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-cyan-500 w-44"
            />
          </div>

          {/* Status message */}
          {statusMessage && (
            <div
              className={`p-2.5 rounded-xl border text-xs leading-relaxed ${
                statusMessage.type === "success"
                  ? "bg-emerald-950/60 border-emerald-800 text-emerald-300"
                  : statusMessage.type === "info"
                  ? "bg-slate-950 border-cyan-800 text-cyan-300"
                  : "bg-rose-950/60 border-rose-800 text-rose-300"
              }`}
            >
              {statusMessage.text}
            </div>
          )}

          {/* Save Action */}
          <div className="pt-2 flex items-center justify-between">
            <div className="text-[10px] text-slate-500">
              {isFormChanged ? "Unsaved changes" : "All changes saved"}
            </div>
            <button
              onClick={handleSaveReview}
              className={`px-4 py-2 rounded-xl font-mono text-xs font-bold shadow-md transition-all cursor-pointer ${
                isFormChanged
                  ? "bg-cyan-500 hover:bg-cyan-400 text-slate-950 shadow-cyan-500/20"
                  : "bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700"
              }`}
            >
              💾 Save Review Revision
            </button>
          </div>
        </div>
      </div>

      {/* 3. Review History Ledger */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg">
        <ReviewHistory
          history={history}
          candidateRegionId={regId}
          onCopyHash={() => {}}
        />
      </div>
    </div>
  );
};
