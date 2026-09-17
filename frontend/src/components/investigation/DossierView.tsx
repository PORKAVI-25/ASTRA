import React, { useState } from "react";
import { transformInvestigationDossier } from "../../services/transformers";
import { getLatestReview } from "../../services/reviewStore";
import type { InvestigationDossier } from "../../types/api";
import type { InvestigationSummary } from "../../types/models";
import { AnalystReviewPanel } from "./AnalystReviewPanel";
import { EvidenceFalseAlarmPanel } from "./EvidenceFalseAlarmPanel";
import { ExecutiveSummaryCard } from "./ExecutiveSummaryCard";
import { OnsetCard } from "./OnsetCard";
import { ProvenanceLineagePanel } from "./ProvenanceLineagePanel";
import { SamplingCaveatsCard } from "./SamplingCaveatsCard";
import { SpatialCandidatePanel } from "./SpatialCandidatePanel";
import { StagesWaterfall } from "./StagesWaterfall";
import { TemporalTimeline } from "./TemporalTimeline";

interface DossierViewProps {
  dossier: InvestigationDossier | null;
  summary: InvestigationSummary | null;
  onBackToLauncher?: () => void;
  onLoadDemoDossier?: () => void;
}

export const DossierView: React.FC<DossierViewProps> = ({
  dossier,
  summary: propSummary,
  onBackToLauncher,
  onLoadDemoDossier,
}) => {
  const urlSubTab = typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("subtab") : null;
  const [activeSubTab, setActiveSubTab] = useState<
    "overview" | "timeline" | "spatial" | "evidence" | "review" | "stages" | "caveats" | "lineage"
  >(() => {
    if (
      urlSubTab === "timeline" ||
      urlSubTab === "spatial" ||
      urlSubTab === "evidence" ||
      urlSubTab === "review" ||
      urlSubTab === "stages" ||
      urlSubTab === "caveats" ||
      urlSubTab === "lineage"
    ) {
      return urlSubTab;
    }
    return "overview";
  });
  const [copiedHash, setCopiedHash] = useState<boolean>(false);
  const [, setReviewUpdateCounter] = useState<number>(0);

  // Derive summary if not provided directly
  const summary: InvestigationSummary | null =
    propSummary || (dossier ? transformInvestigationDossier(dossier) : null);

  if (!summary) {
    return (
      <div className="bg-slate-900/40 border border-dashed border-slate-800 rounded-2xl p-12 flex flex-col items-center justify-center min-h-[420px] text-center font-mono space-y-4">
        <div className="w-14 h-14 rounded-2xl bg-slate-800/80 border border-slate-700 flex items-center justify-center text-2xl shadow-lg">
          📋
        </div>
        <div className="max-w-md space-y-1">
          <h3 className="text-base font-bold text-slate-200">No Investigation Dossier Loaded</h3>
          <p className="text-xs text-slate-400">
            Execute a multi-temporal pipeline run in the Investigation Launcher to generate an investigation dossier with cryptographic lineage.
          </p>
        </div>

        <div className="flex flex-wrap items-center justify-center gap-3 pt-2">
          {onBackToLauncher && (
            <button
              onClick={onBackToLauncher}
              className="px-4 py-2 rounded-xl text-xs font-mono font-bold bg-cyan-500 hover:bg-cyan-400 text-slate-950 shadow-md shadow-cyan-500/20 transition-all cursor-pointer"
            >
              🚀 Go to Investigation Launcher (D3)
            </button>
          )}
          {onLoadDemoDossier && (
            <button
              onClick={onLoadDemoDossier}
              className="px-4 py-2 rounded-xl text-xs font-mono font-bold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-all cursor-pointer"
            >
              📂 Load Verified Demo Dossier
            </button>
          )}
        </div>
      </div>
    );
  }

  const currentReview = getLatestReview(summary.investigationId, summary.candidateRegionId);

  const handleCopyHash = () => {
    if (summary.contentHash) {
      navigator.clipboard?.writeText(summary.contentHash);
      setCopiedHash(true);
      setTimeout(() => setCopiedHash(false), 2000);
    }
  };

  const handleDownloadJson = () => {
    const dataToExport = dossier || summary;
    const jsonStr = JSON.stringify(dataToExport, null, 2);
    const blob = new Blob([jsonStr], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `astra_dossier_${summary.investigationId}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6 text-left font-sans">
      {/* Dossier Control Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-slate-900/80 border border-slate-800/90 rounded-2xl p-4 sm:p-5 backdrop-blur-md shadow-lg">
        <div>
          <div className="flex items-center space-x-2">
            <h2 className="text-lg font-bold font-mono text-white tracking-wide">
              Investigation Result Dossier
            </h2>
            <span className="px-2 py-0.5 text-xs font-mono rounded bg-cyan-950/80 text-cyan-300 border border-cyan-800">
              Milestone D4 • ASTRA-DC-v0.1
            </span>
          </div>
          <p className="text-xs text-slate-400 font-mono mt-1">
            Official multi-epoch investigation dossier with verified cryptographic integrity and temporal bounds.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5 font-mono text-xs">
          {onBackToLauncher && (
            <button
              onClick={onBackToLauncher}
              className="px-3.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-colors cursor-pointer"
            >
              ← Launcher
            </button>
          )}

          <button
            onClick={handleCopyHash}
            className="px-3.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-cyan-300 border border-slate-700 transition-colors cursor-pointer"
            title="Copy deterministic content hash"
          >
            {copiedHash ? "✓ Hash Copied" : "Copy Hash"}
          </button>

          <button
            onClick={handleDownloadJson}
            className="px-3.5 py-1.5 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold shadow-md shadow-cyan-500/20 transition-all cursor-pointer"
            title="Export complete dossier JSON offline"
          >
            Download Dossier JSON
          </button>
        </div>
      </div>

      {/* Sub-Section Filter Tabs */}
      <div className="flex items-center space-x-2 border-b border-slate-800 pb-2 text-xs font-mono overflow-x-auto">
        <button
          onClick={() => setActiveSubTab("overview")}
          className={`px-3 py-1.5 rounded-lg transition-all whitespace-nowrap cursor-pointer ${
            activeSubTab === "overview"
              ? "bg-cyan-950 text-cyan-300 font-bold border border-cyan-800"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          Executive Summary & Onset
        </button>
        <button
          onClick={() => setActiveSubTab("timeline")}
          className={`px-3 py-1.5 rounded-lg transition-all whitespace-nowrap cursor-pointer flex items-center space-x-1.5 ${
            activeSubTab === "timeline"
              ? "bg-cyan-950 text-cyan-300 font-bold border border-cyan-800 shadow-sm"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <span>⏱️ Temporal Timeline</span>
          <span className="px-1.5 py-0.2 rounded text-[10px] bg-slate-800 text-cyan-300 border border-slate-700">
            {summary.timelineNodes.length}
          </span>
        </button>
        <button
          onClick={() => setActiveSubTab("spatial")}
          className={`px-3 py-1.5 rounded-lg transition-all whitespace-nowrap cursor-pointer flex items-center space-x-1.5 ${
            activeSubTab === "spatial"
              ? "bg-cyan-950 text-cyan-300 font-bold border border-cyan-800 shadow-sm"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <span>📍 Spatial Candidate</span>
          <span className="px-1.5 py-0.2 rounded text-[10px] bg-slate-800 text-cyan-300 border border-slate-700">
            {summary.candidateRegionId}
          </span>
        </button>
        <button
          onClick={() => setActiveSubTab("evidence")}
          className={`px-3 py-1.5 rounded-lg transition-all whitespace-nowrap cursor-pointer flex items-center space-x-1.5 ${
            activeSubTab === "evidence"
              ? "bg-cyan-950 text-cyan-300 font-bold border border-cyan-800 shadow-sm"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <span>🔬 Evidence & False-Alarm</span>
          <span className="px-1.5 py-0.2 rounded text-[10px] bg-slate-800 text-cyan-300 border border-slate-700 uppercase">
            {summary.category.primary}
          </span>
        </button>
        <button
          onClick={() => setActiveSubTab("review")}
          className={`px-3 py-1.5 rounded-lg transition-all whitespace-nowrap cursor-pointer flex items-center space-x-1.5 ${
            activeSubTab === "review"
              ? "bg-cyan-950 text-cyan-300 font-bold border border-cyan-800 shadow-sm"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <span>📝 Analyst Review</span>
          <span className={`px-1.5 py-0.2 rounded text-[10px] font-mono font-bold ${
            currentReview?.decision === "CONFIRMED"
              ? "bg-emerald-950 text-emerald-300 border border-emerald-800"
              : currentReview?.decision === "REJECTED"
              ? "bg-rose-950 text-rose-300 border border-rose-800"
              : currentReview?.decision === "PENDING"
              ? "bg-amber-950 text-amber-300 border border-amber-800"
              : "bg-slate-800 text-slate-400 border border-slate-700"
          }`}>
            {currentReview ? currentReview.decision : "Not Reviewed"}
          </span>
        </button>
        <button
          onClick={() => setActiveSubTab("stages")}
          className={`px-3 py-1.5 rounded-lg transition-all whitespace-nowrap cursor-pointer ${
            activeSubTab === "stages"
              ? "bg-cyan-950 text-cyan-300 font-bold border border-cyan-800"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          Pipeline Stages ({summary.provenance.stages.length})
        </button>
        <button
          onClick={() => setActiveSubTab("caveats")}
          className={`px-3 py-1.5 rounded-lg transition-all whitespace-nowrap cursor-pointer ${
            activeSubTab === "caveats"
              ? "bg-cyan-950 text-cyan-300 font-bold border border-cyan-800"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          Sampling Limitations ({summary.evidenceLimitations.length})
        </button>
        <button
          onClick={() => setActiveSubTab("lineage")}
          className={`px-3 py-1.5 rounded-lg transition-all whitespace-nowrap cursor-pointer flex items-center space-x-1.5 ${
            activeSubTab === "lineage"
              ? "bg-cyan-950 text-cyan-300 font-bold border border-cyan-800 shadow-sm"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <span>🔗 Provenance & Lineage</span>
          <span className="px-1.5 py-0.2 rounded text-[10px] bg-slate-800 text-cyan-300 border border-slate-700">
            {summary.provenance.isVerified ? "SHA-256" : "Audit"}
          </span>
        </button>
      </div>

      {/* Dossier Content Sub-Views */}
      {activeSubTab === "overview" && (
        <div className="space-y-6">
          <ExecutiveSummaryCard summary={summary} review={currentReview} />
          <OnsetCard onset={summary.onset} />

          {/* Quick jump to full timeline, spatial panel, evidence panel, lineage, and review */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3 font-mono text-xs">
            <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4 flex flex-col justify-between gap-3">
              <div className="flex items-center space-x-2 text-slate-300">
                <span className="text-base">⏱️</span>
                <span>
                  Multi-epoch temporal timeline with <strong>{summary.timelineNodes.length} observation epochs</strong>.
                </span>
              </div>
              <button
                onClick={() => setActiveSubTab("timeline")}
                className="px-3.5 py-1.5 rounded-xl bg-cyan-950 hover:bg-cyan-900 text-cyan-300 border border-cyan-800 font-bold transition-all cursor-pointer whitespace-nowrap text-center"
              >
                Open Timeline (D5) →
              </button>
            </div>

            <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4 flex flex-col justify-between gap-3">
              <div className="flex items-center space-x-2 text-slate-300">
                <span className="text-base">📍</span>
                <span>
                  Spatial footprint and correspondence for candidate <strong>{summary.candidateRegionId}</strong>.
                </span>
              </div>
              <button
                onClick={() => setActiveSubTab("spatial")}
                className="px-3.5 py-1.5 rounded-xl bg-cyan-950 hover:bg-cyan-900 text-cyan-300 border border-cyan-800 font-bold transition-all cursor-pointer whitespace-nowrap text-center"
              >
                Open Spatial Panel (D6) →
              </button>
            </div>

            <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4 flex flex-col justify-between gap-3">
              <div className="flex items-center space-x-2 text-slate-300">
                <span className="text-base">🔬</span>
                <span>
                  Explainable rules & M4D screening for <strong>{summary.category.primary}</strong>.
                </span>
              </div>
              <button
                onClick={() => setActiveSubTab("evidence")}
                className="px-3.5 py-1.5 rounded-xl bg-cyan-950 hover:bg-cyan-900 text-cyan-300 border border-cyan-800 font-bold transition-all cursor-pointer whitespace-nowrap text-center"
              >
                Open Evidence & Screening (D7) →
              </button>
            </div>

            <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4 flex flex-col justify-between gap-3">
              <div className="flex items-center space-x-2 text-slate-300">
                <span className="text-base">🔗</span>
                <span>
                  Cryptographic lineage & SHA-256 digests for <strong>{summary.provenance.stages.length} stages</strong>.
                </span>
              </div>
              <button
                onClick={() => setActiveSubTab("lineage")}
                className="px-3.5 py-1.5 rounded-xl bg-cyan-950 hover:bg-cyan-900 text-cyan-300 border border-cyan-800 font-bold transition-all cursor-pointer whitespace-nowrap text-center"
              >
                Open Lineage & Provenance (D8) →
              </button>
            </div>

            <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4 flex flex-col justify-between gap-3">
              <div className="flex items-center space-x-2 text-slate-300">
                <span className="text-base">📝</span>
                <span>
                  Analyst triage review status: <strong>{currentReview ? currentReview.decision : "NOT REVIEWED"}</strong>.
                </span>
              </div>
              <button
                onClick={() => setActiveSubTab("review")}
                className="px-3.5 py-1.5 rounded-xl bg-cyan-950 hover:bg-cyan-900 text-cyan-300 border border-cyan-800 font-bold transition-all cursor-pointer whitespace-nowrap text-center"
              >
                Open Analyst Review (D9) →
              </button>
            </div>
          </div>
        </div>
      )}

      {activeSubTab === "timeline" && (
        <div className="space-y-6">
          <TemporalTimeline summary={summary} />
        </div>
      )}

      {activeSubTab === "spatial" && (
        <div className="space-y-6">
          <SpatialCandidatePanel summary={summary} />
        </div>
      )}

      {activeSubTab === "evidence" && (
        <div className="space-y-6">
          <EvidenceFalseAlarmPanel summary={summary} />
        </div>
      )}

      {activeSubTab === "review" && (
        <div className="space-y-6">
          <AnalystReviewPanel
            summary={summary}
            onReviewUpdated={() => setReviewUpdateCounter((c) => c + 1)}
          />
        </div>
      )}

      {activeSubTab === "stages" && (
        <div className="space-y-6">
          <StagesWaterfall stages={summary.provenance.stages} />
        </div>
      )}

      {activeSubTab === "caveats" && (
        <div className="space-y-6">
          <SamplingCaveatsCard summary={summary} />
        </div>
      )}

      {activeSubTab === "lineage" && (
        <div className="space-y-6">
          <ProvenanceLineagePanel summary={summary} />
        </div>
      )}

      {/* Next Dashboard Stage Preview Banners */}
      <div className="p-4 bg-slate-900/60 rounded-2xl border border-slate-800 text-xs font-mono flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-slate-400">
        <div className="flex items-center space-x-2">
          <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
          <span>Dossier Grounded: {summary.timelineNodes.length} observation epochs cataloged across series.</span>
        </div>
        <div className="flex items-center space-x-3 text-slate-300">
          <span>Stage Progress:</span>
          <span className="px-2 py-0.5 rounded bg-cyan-950 border border-cyan-800 text-cyan-300 font-bold">
            ✓ D5: Temporal Timeline
          </span>
          <span className="px-2 py-0.5 rounded bg-cyan-950 border border-cyan-800 text-cyan-300 font-bold">
            ✓ D6: Spatial Candidate Panel
          </span>
          <span className="px-2 py-0.5 rounded bg-cyan-950 border border-cyan-800 text-cyan-300 font-bold">
            ✓ D7: Evidence & False-Alarm Panel
          </span>
          <span className="px-2 py-0.5 rounded bg-cyan-950 border border-cyan-800 text-cyan-300 font-bold">
            ✓ D8: Provenance & Lineage
          </span>
          <span className="px-2 py-0.5 rounded bg-cyan-950 border border-cyan-800 text-cyan-300 font-bold">
            ✓ D9: Analyst Review & Audit Trail
          </span>
        </div>
      </div>
    </div>
  );
};
