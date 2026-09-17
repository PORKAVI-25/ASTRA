/**
 * ASTRA Milestone D9: Review History Component
 *
 * Displays the complete, local, chronologically ordered revision history
 * for an analyst review on the current candidate region.
 *
 * Rules:
 * - Read-only display of locally recorded revisions.
 * - Explicitly indicates this is a LOCAL review audit trail.
 * - Never alters historical revisions.
 * - Shows transition badges (e.g. "Transitioned from: CONFIRMED").
 * - Displays deterministic SHA-256 audit hashes with one-click copy.
 */

import React, { useState } from "react";
import type { AnalystReviewRecord } from "../../types/models";

interface ReviewHistoryProps {
  history: AnalystReviewRecord[];
  candidateRegionId: string;
  onCopyHash?: (hash: string) => void;
}

export const ReviewHistory: React.FC<ReviewHistoryProps> = ({
  history,
  candidateRegionId,
  onCopyHash,
}) => {
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [expandedHashes, setExpandedHashes] = useState<Record<string, boolean>>({});

  const handleCopy = (hash: string, key: string) => {
    if (onCopyHash) {
      onCopyHash(hash);
    }
    if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(hash).catch(() => {});
    }
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const toggleHashExpansion = (key: string) => {
    setExpandedHashes((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const getDecisionBadge = (decision: string) => {
    const d = (decision || "").toUpperCase();
    if (d === "CONFIRMED" || d === "CONFIRM") {
      return (
        <span className="px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-emerald-950 text-emerald-300 border border-emerald-700">
          CONFIRMED
        </span>
      );
    }
    if (d === "REJECTED" || d === "REJECT") {
      return (
        <span className="px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-rose-950 text-rose-300 border border-rose-700">
          REJECTED
        </span>
      );
    }
    return (
      <span className="px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-amber-950 text-amber-300 border border-amber-700">
        PENDING
      </span>
    );
  };

  if (!history || history.length === 0) {
    return (
      <div className="bg-slate-950/60 border border-dashed border-slate-800 rounded-2xl p-6 text-center font-mono text-xs space-y-2">
        <div className="text-slate-400 font-bold">No local analyst review has been recorded.</div>
        <div className="text-slate-500 text-[11px]">
          Select an analyst decision above and click &quot;Save Review Revision&quot; to establish Revision #1 for candidate {candidateRegionId}.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3 font-mono text-xs">
      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
        <div className="flex items-center space-x-2">
          <span className="text-sm">📜</span>
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300">
            Local Revision Audit History ({history.length} {history.length === 1 ? "revision" : "revisions"})
          </h4>
        </div>
        <span className="text-[10px] text-slate-500">
          Candidate: <strong className="text-cyan-400">{candidateRegionId}</strong> (Newest First)
        </span>
      </div>

      <div className="space-y-3">
        {history.map((rev, idx) => {
          const hashKey = `hist_hash_${rev.reviewId}_${idx}`;
          const isExpanded = expandedHashes[hashKey];
          const isLatest = idx === 0;

          return (
            <div
              key={rev.reviewId || idx}
              className={`p-4 rounded-xl border transition-all ${
                isLatest
                  ? "bg-slate-900/90 border-cyan-800/80 shadow-md ring-1 ring-cyan-500/20"
                  : "bg-slate-950/70 border-slate-800/80"
              }`}
            >
              {/* Revision Header */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800/60 pb-2.5">
                <div className="flex items-center space-x-2 flex-wrap gap-y-1">
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-800 text-slate-300 border border-slate-700">
                    Revision #{rev.revisionNumber || history.length - idx}
                  </span>
                  {getDecisionBadge(rev.decision)}
                  {rev.previousDecision && rev.previousDecision !== rev.decision && (
                    <span className="text-[10px] text-slate-400">
                      (Changed from <span className="font-bold text-slate-300">{rev.previousDecision}</span>)
                    </span>
                  )}
                  {isLatest && (
                    <span className="px-1.5 py-0.2 rounded text-[9px] font-bold bg-cyan-950 text-cyan-300 border border-cyan-800">
                      CURRENT
                    </span>
                  )}
                </div>

                <div className="text-[10px] text-slate-400 flex items-center space-x-2">
                  <span>Analyst: <strong className="text-slate-200">{rev.analystId || "analyst_local"}</strong></span>
                  <span>•</span>
                  <span>{rev.updatedAt || rev.createdAt || rev.timestamp || "—"}</span>
                </div>
              </div>

              {/* Revision Content */}
              <div className="pt-2.5 space-y-2 text-xs">
                {rev.selectedReason && (
                  <div>
                    <span className="text-[10px] uppercase text-slate-500 font-bold mr-1.5">
                      Selected Justification:
                    </span>
                    <span className="text-slate-200 font-semibold">{rev.selectedReason}</span>
                  </div>
                )}

                <div>
                  <span className="text-[10px] uppercase text-slate-500 font-bold block mb-0.5">
                    Analyst Notes:
                  </span>
                  <p className="text-slate-300 whitespace-pre-wrap leading-relaxed text-[11px] bg-slate-950/60 p-2.5 rounded-lg border border-slate-800/60">
                    {rev.analystNote || rev.comments || "(No detailed analyst comments entered.)"}
                  </p>
                </div>

                {/* Audit Hash */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1.5 pt-1 text-[10px] text-slate-400">
                  <div className="flex items-center space-x-1.5 truncate">
                    <span className="text-slate-500 shrink-0">SHA-256 Audit Hash:</span>
                    <span className="font-mono text-amber-300 truncate" title={rev.auditHash}>
                      {isExpanded ? rev.auditHash : `${rev.auditHash.slice(0, 24)}...`}
                    </span>
                  </div>

                  <div className="flex items-center space-x-1 shrink-0 self-end sm:self-auto">
                    {rev.auditHash.length > 24 && (
                      <button
                        onClick={() => toggleHashExpansion(hashKey)}
                        className="px-1.5 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 cursor-pointer"
                      >
                        {isExpanded ? "Less" : "Full"}
                      </button>
                    )}
                    <button
                      onClick={() => handleCopy(rev.auditHash, hashKey)}
                      className="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 cursor-pointer"
                    >
                      {copiedKey === hashKey ? "✓ Copied" : "Copy Hash"}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
