import React from "react";
import type { InvestigationSummary } from "../../types/models";

interface LineageCardProps {
  summary: InvestigationSummary;
}

export const LineageCard: React.FC<LineageCardProps> = ({ summary }) => {
  const prov = summary.provenance;
  const correspondence = summary.spatialCorrespondence;
  const hashEntries = Object.entries(prov.upstreamHashes || {});

  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl text-left font-sans space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-slate-800">
        <div>
          <div className="flex items-center space-x-2">
            <span className="text-base">🔗</span>
            <h3 className="text-sm font-bold font-mono text-white tracking-wide">
              Cryptographic Lineage & Provenance Ledger
            </h3>
            <span className="px-2 py-0.5 text-[10px] font-mono rounded bg-emerald-950 text-emerald-300 border border-emerald-800">
              Rule 5 Cryptographic Provenance
            </span>
          </div>
          <p className="text-xs text-slate-400 font-mono mt-0.5">
            Full upstream artifact ancestry, SHA-256 input digests, and candidate spatial correspondence tracking.
          </p>
        </div>

        <div className="font-mono text-xs text-right">
          <span className="text-slate-400">Integrity: </span>
          <span className="text-cyan-300 font-bold">
            {prov.isVerified ? "VERIFIED DETERMINISTIC" : "UNVERIFIED"}
          </span>
        </div>
      </div>

      {/* Provenance IDs High-Density Bar */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs font-mono">
        <div className="bg-slate-950/70 p-3 rounded-xl border border-slate-800">
          <div className="text-[10px] uppercase text-slate-400 font-semibold mb-1">
            Investigation Provenance ID
          </div>
          <div className="text-cyan-300 font-bold truncate" title={prov.investigationProvenanceId}>
            {prov.investigationProvenanceId || "prov_inv_unassigned"}
          </div>
        </div>

        <div className="bg-slate-950/70 p-3 rounded-xl border border-slate-800">
          <div className="text-[10px] uppercase text-slate-400 font-semibold mb-1">
            Temporal Evidence Provenance ID
          </div>
          <div className="text-emerald-300 font-bold truncate" title={prov.temporalEvidenceProvenanceId}>
            {prov.temporalEvidenceProvenanceId || "prov_tem_unassigned"}
          </div>
        </div>

        <div className="bg-slate-950/70 p-3 rounded-xl border border-slate-800">
          <div className="text-[10px] uppercase text-slate-400 font-semibold mb-1">
            Deterministic Content Hash
          </div>
          <div className="text-white font-bold truncate" title={prov.contentHash}>
            {prov.contentHash || "hash_unassigned"}
          </div>
        </div>
      </div>

      {/* Cross-Epoch Candidate Spatial Correspondence Tracking */}
      {correspondence.epochs.length > 0 && (
        <div className="space-y-2.5 font-mono text-xs">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold text-slate-300 uppercase tracking-wide">
              Cross-Epoch Spatial Candidate Correspondence (M4F)
            </span>
            <span className="text-[10px] text-slate-400">
              Avg IoU: <span className="text-cyan-300 font-bold">{correspondence.averageIou}</span> • Max Drift:{" "}
              <span className="text-slate-200 font-bold">{correspondence.maxCentroidDriftM}m</span>
            </span>
          </div>

          <div className="overflow-x-auto rounded-xl border border-slate-800">
            <table className="w-full text-left text-xs bg-slate-950/70">
              <thead className="bg-slate-900/90 text-[10px] uppercase text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="p-2.5">Evaluated Pair</th>
                  <th className="p-2.5">Reference ID</th>
                  <th className="p-2.5">Matched ID</th>
                  <th className="p-2.5">ID Shift?</th>
                  <th className="p-2.5">IoU (WGS84)</th>
                  <th className="p-2.5">Centroid Drift</th>
                  <th className="p-2.5">Relationship</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/80 text-[11px]">
                {correspondence.epochs.map((epoch, idx) => (
                  <tr key={idx} className="hover:bg-slate-900/50">
                    <td className="p-2.5 font-bold text-slate-300 truncate max-w-xs" title={epoch.targetPairId}>
                      {epoch.targetPairId}
                    </td>
                    <td className="p-2.5 text-cyan-300">{epoch.referenceCandidateId}</td>
                    <td className="p-2.5 text-emerald-300 font-bold">
                      {epoch.matchedRegionId || "NONE"}
                    </td>
                    <td className="p-2.5">
                      {epoch.isIdShifted ? (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-950 text-amber-300 border border-amber-800">
                          SHIFT: {epoch.referenceCandidateId} → {epoch.matchedRegionId}
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-900 text-slate-400 border border-slate-800">
                          EXACT
                        </span>
                      )}
                    </td>
                    <td className="p-2.5 text-slate-200 font-bold">
                      {epoch.metricIou.toFixed(2)}
                    </td>
                    <td className="p-2.5 text-slate-300">{epoch.centroidDistanceM}m</td>
                    <td className="p-2.5">
                      <span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-900 text-cyan-300 border border-slate-800">
                        {epoch.relationship}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Upstream SHA-256 Hashes Table */}
      {hashEntries.length > 0 && (
        <div className="space-y-2 font-mono text-xs pt-2 border-t border-slate-800/80">
          <div className="text-[11px] font-bold text-slate-300 uppercase tracking-wide">
            Upstream Artifact Hashes ({hashEntries.length})
          </div>

          <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
            {hashEntries.map(([artifact, hash]) => (
              <div
                key={artifact}
                className="p-2.5 bg-slate-950/70 rounded-xl border border-slate-800/80 flex flex-col sm:flex-row sm:items-center justify-between gap-1 text-[11px]"
              >
                <span className="text-slate-300 truncate max-w-sm" title={artifact}>
                  {artifact}
                </span>
                <span className="text-cyan-300 font-mono text-[10px] bg-slate-900 px-2 py-0.5 rounded border border-slate-800 truncate" title={hash}>
                  {hash}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
