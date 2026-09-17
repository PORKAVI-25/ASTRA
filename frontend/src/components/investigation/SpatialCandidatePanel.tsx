import React, { useState, useMemo } from "react";
import type { InvestigationSummary, CandidateFootprint } from "../../types/models";
import {
  getSpatialStatusDetails,
  getRelationshipDetails,
  formatCoordinatesWgs84,
  formatBoundingBoxWgs84,
  computeSvgFootprint,
} from "../../services/transformers";
import { getChangeMaskUrl } from "../../services/api";

interface SpatialCandidatePanelProps {
  summary: InvestigationSummary;
}

export const SpatialCandidatePanel: React.FC<SpatialCandidatePanelProps> = ({ summary }) => {
  const [showMask, setShowMask] = useState<boolean>(true);
  const [maskError, setMaskError] = useState<boolean>(false);

  const footprint: CandidateFootprint | undefined = summary.candidateFootprint;
  const bboxWgs84 = footprint?.bboxWgs84;
  const centroidWgs84 = footprint?.centroidWgs84;
  const bboxPx = footprint?.bboxPx;
  const features = footprint?.features;

  const bboxDetails = useMemo(() => {
    return formatBoundingBoxWgs84(bboxWgs84);
  }, [bboxWgs84]);

  const svgData = useMemo(() => {
    return computeSvgFootprint(bboxWgs84, centroidWgs84, 380, 220, 36);
  }, [bboxWgs84, centroidWgs84]);

  const maskResultId = summary.changeMaskResultId;
  const maskUrl = maskResultId ? getChangeMaskUrl(maskResultId) : null;

  const epochs = summary.spatialCorrespondence?.epochs || [];
  const referenceCandidateId = summary.candidateRegionId;

  return (
    <div className="space-y-6 text-left font-sans">
      {/* 1. SECTION HEADER & CANDIDATE IDENTITY */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-800">
          <div>
            <div className="flex items-center space-x-2">
              <span className="text-xl">📍</span>
              <h3 className="text-base font-bold font-mono text-white tracking-wide">
                Spatial Candidate Footprint & Multi-Epoch Correspondence
              </h3>
              <span className="px-2 py-0.5 text-[10px] font-mono rounded bg-cyan-950 text-cyan-300 border border-cyan-800">
                Milestone D6
              </span>
            </div>
            <p className="text-xs text-slate-400 font-mono mt-1">
              Geographic footprint, morphological dimensions, and cross-epoch spatial correspondence metrics.
            </p>
          </div>

          <div className="flex items-center space-x-3 font-mono text-xs">
            <div className="bg-slate-950 px-3 py-1.5 rounded-xl border border-slate-800 text-slate-300">
              <span className="text-slate-400">Target Region: </span>
              <span className="font-bold text-cyan-300">{referenceCandidateId}</span>
            </div>
            <div className="bg-slate-950 px-3 py-1.5 rounded-xl border border-slate-800 text-slate-300">
              <span className="text-slate-400">Category: </span>
              <span className="font-bold text-amber-300 uppercase">{summary.category.primary}</span>
            </div>
          </div>
        </div>

        {/* Candidate Identity Metadata Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono text-xs">
          <div className="bg-slate-950/80 p-3 rounded-xl border border-slate-800">
            <div className="text-[10px] uppercase text-slate-400 font-semibold mb-0.5">
              Candidate Region ID
            </div>
            <div className="text-sm font-bold text-white tracking-wide">
              {referenceCandidateId}
            </div>
            <div className="text-[10px] text-slate-400 mt-0.5">
              Discovery reference ID
            </div>
          </div>

          <div className="bg-slate-950/80 p-3 rounded-xl border border-slate-800">
            <div className="text-[10px] uppercase text-slate-400 font-semibold mb-0.5">
              Discovery Scene Pair
            </div>
            <div className="text-xs font-bold text-cyan-300 truncate" title={summary.discoveryPairId}>
              {summary.discoveryPairId}
            </div>
            <div className="text-[10px] text-slate-400 mt-0.5">
              Pairing: {summary.pairingStrategy}
            </div>
          </div>

          <div className="bg-slate-950/80 p-3 rounded-xl border border-slate-800">
            <div className="text-[10px] uppercase text-slate-400 font-semibold mb-0.5">
              Temporal Support Status
            </div>
            <div className="text-xs font-bold text-emerald-400 truncate" title={summary.supportStatus}>
              {summary.supportStatus}
            </div>
            <div className="text-[10px] text-slate-400 mt-0.5">
              Confidence: <strong className="text-white capitalize">{summary.confidenceTier}</strong>
            </div>
          </div>

          <div className="bg-slate-950/80 p-3 rounded-xl border border-slate-800">
            <div className="text-[10px] uppercase text-slate-400 font-semibold mb-0.5">
              Investigation ID
            </div>
            <div className="text-xs font-bold text-slate-200 truncate" title={summary.investigationId}>
              {summary.investigationId}
            </div>
            <div className="text-[10px] text-slate-400 mt-0.5">
              Hash: {summary.contentHash.substring(0, 12)}…
            </div>
          </div>
        </div>
      </div>

      {/* 2. SPATIAL FOOTPRINT & OFFLINE LOCAL VISUALIZER */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Offline SVG Footprint Preview (lg:col-span-7) */}
        <div className="lg:col-span-7 bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg space-y-4">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-bold font-mono uppercase tracking-wider text-slate-300 flex items-center space-x-2">
              <span>🗺️</span>
              <span>Local Offline Footprint Preview</span>
            </h4>
            <span className="px-2 py-0.5 text-[10px] font-mono rounded bg-slate-950 text-cyan-300 border border-slate-800">
              {footprint?.crs || "EPSG:4326 (WGS84)"}
            </span>
          </div>

          {svgData && bboxWgs84 ? (
            <div className="bg-slate-950 rounded-2xl p-4 border border-slate-800 relative overflow-hidden font-mono text-[10px]">
              {/* SVG Canvas */}
              <div className="flex justify-center items-center">
                <svg
                  viewBox={`0 0 ${svgData.svgWidth} ${svgData.svgHeight}`}
                  className="w-full max-w-[440px] h-auto select-none"
                  aria-label="Offline local spatial candidate footprint diagram"
                >
                  <defs>
                    <pattern id="grid-pattern" width="20" height="20" patternUnits="userSpaceOnUse">
                      <path d="M 20 0 L 0 0 0 20" fill="none" stroke="rgba(51, 65, 85, 0.4)" strokeWidth="0.75" />
                    </pattern>
                  </defs>

                  {/* Grid Background */}
                  <rect width={svgData.svgWidth} height={svgData.svgHeight} fill="url(#grid-pattern)" />

                  {/* Outer Viewport Border */}
                  <rect
                    x="2"
                    y="2"
                    width={svgData.svgWidth - 4}
                    height={svgData.svgHeight - 4}
                    fill="none"
                    stroke="rgba(71, 85, 105, 0.4)"
                    strokeWidth="1"
                    rx="8"
                  />

                  {/* Axis Guidelines */}
                  <line
                    x1={svgData.box.x}
                    y1="10"
                    x2={svgData.box.x}
                    y2={svgData.svgHeight - 10}
                    stroke="rgba(100, 116, 139, 0.3)"
                    strokeDasharray="2 2"
                  />
                  <line
                    x1={svgData.box.x + svgData.box.width}
                    y1="10"
                    x2={svgData.box.x + svgData.box.width}
                    y2={svgData.svgHeight - 10}
                    stroke="rgba(100, 116, 139, 0.3)"
                    strokeDasharray="2 2"
                  />
                  <line
                    x1="10"
                    y1={svgData.box.y}
                    x2={svgData.svgWidth - 10}
                    y2={svgData.box.y}
                    stroke="rgba(100, 116, 139, 0.3)"
                    strokeDasharray="2 2"
                  />
                  <line
                    x1="10"
                    y1={svgData.box.y + svgData.box.height}
                    x2={svgData.svgWidth - 10}
                    y2={svgData.box.y + svgData.box.height}
                    stroke="rgba(100, 116, 139, 0.3)"
                    strokeDasharray="2 2"
                  />

                  {/* Candidate Bounding Box Footprint */}
                  <rect
                    x={svgData.box.x}
                    y={svgData.box.y}
                    width={svgData.box.width}
                    height={svgData.box.height}
                    fill="rgba(6, 182, 212, 0.15)"
                    stroke="#06b6d4"
                    strokeWidth="2"
                    rx="3"
                  />

                  {/* Corner Crosshairs */}
                  <path
                    d={`M ${svgData.box.x - 4} ${svgData.box.y} L ${svgData.box.x + 8} ${svgData.box.y} M ${svgData.box.x} ${svgData.box.y - 4} L ${svgData.box.x} ${svgData.box.y + 8}`}
                    stroke="#22d3ee"
                    strokeWidth="1.5"
                  />
                  <path
                    d={`M ${svgData.box.x + svgData.box.width - 8} ${svgData.box.y} L ${svgData.box.x + svgData.box.width + 4} ${svgData.box.y} M ${svgData.box.x + svgData.box.width} ${svgData.box.y - 4} L ${svgData.box.x + svgData.box.width} ${svgData.box.y + 8}`}
                    stroke="#22d3ee"
                    strokeWidth="1.5"
                  />
                  <path
                    d={`M ${svgData.box.x - 4} ${svgData.box.y + svgData.box.height} L ${svgData.box.x + 8} ${svgData.box.y + svgData.box.height} M ${svgData.box.x} ${svgData.box.y + svgData.box.height - 8} L ${svgData.box.x} ${svgData.box.y + svgData.box.height + 4}`}
                    stroke="#22d3ee"
                    strokeWidth="1.5"
                  />
                  <path
                    d={`M ${svgData.box.x + svgData.box.width - 8} ${svgData.box.y + svgData.box.height} L ${svgData.box.x + svgData.box.width + 4} ${svgData.box.y + svgData.box.height} M ${svgData.box.x + svgData.box.width} ${svgData.box.y + svgData.box.height - 8} L ${svgData.box.x + svgData.box.width} ${svgData.box.y + svgData.box.height + 4}`}
                    stroke="#22d3ee"
                    strokeWidth="1.5"
                  />

                  {/* Centroid Marker */}
                  <circle
                    cx={svgData.centroid.x}
                    cy={svgData.centroid.y}
                    r="8"
                    fill="none"
                    stroke="#10b981"
                    strokeWidth="1"
                    strokeDasharray="2 2"
                  />
                  <circle
                    cx={svgData.centroid.x}
                    cy={svgData.centroid.y}
                    r="4"
                    fill="#10b981"
                    stroke="#ffffff"
                    strokeWidth="1.5"
                  />

                  {/* Center Crosshair */}
                  <line
                    x1={svgData.centroid.x - 7}
                    y1={svgData.centroid.y}
                    x2={svgData.centroid.x + 7}
                    y2={svgData.centroid.y}
                    stroke="#10b981"
                    strokeWidth="1"
                  />
                  <line
                    x1={svgData.centroid.x}
                    y1={svgData.centroid.y - 7}
                    x2={svgData.centroid.x}
                    y2={svgData.centroid.y + 7}
                    stroke="#10b981"
                    strokeWidth="1"
                  />

                  {/* Region Identifier Label */}
                  <text
                    x={svgData.box.x + 8}
                    y={svgData.box.y + 16}
                    fill="#e2e8f0"
                    fontSize="11"
                    fontWeight="bold"
                  >
                    {referenceCandidateId}
                  </text>

                  {/* Coordinates / Dimensions Inside Box */}
                  <text
                    x={svgData.box.x + 8}
                    y={svgData.box.y + 30}
                    fill="#94a3b8"
                    fontSize="9"
                  >
                    {footprint?.pixelCount ? `${footprint.pixelCount} px` : ""}
                    {footprint?.areaM2 ? ` • ${(footprint.areaM2 / 1000).toFixed(1)}k m²` : ""}
                  </text>

                  {/* Axis Tick Labels */}
                  {/* West Longitude */}
                  <text
                    x={svgData.box.x}
                    y={svgData.svgHeight - 12}
                    fill="#64748b"
                    fontSize="9"
                    textAnchor="middle"
                  >
                    {svgData.labels.west}
                  </text>

                  {/* East Longitude */}
                  <text
                    x={svgData.box.x + svgData.box.width}
                    y={svgData.svgHeight - 12}
                    fill="#64748b"
                    fontSize="9"
                    textAnchor="middle"
                  >
                    {svgData.labels.east}
                  </text>

                  {/* North Latitude */}
                  <text
                    x={svgData.box.x - 8}
                    y={svgData.box.y + 4}
                    fill="#64748b"
                    fontSize="9"
                    textAnchor="end"
                  >
                    {svgData.labels.north}
                  </text>

                  {/* South Latitude */}
                  <text
                    x={svgData.box.x - 8}
                    y={svgData.box.y + svgData.box.height + 4}
                    fill="#64748b"
                    fontSize="9"
                    textAnchor="end"
                  >
                    {svgData.labels.south}
                  </text>
                </svg>
              </div>

              {/* Analytical Notice Banner */}
              <div className="mt-3 pt-2.5 border-t border-slate-800/80 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-[10px] text-slate-400">
                <div className="flex items-center space-x-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-cyan-400"></span>
                  <span>Local Analytical Footprint (Air-Gapped Vector Canvas)</span>
                </div>
                <div className="text-slate-400 italic">
                  Not a satellite RGB basemap; metric bounding geometry only.
                </div>
              </div>
            </div>
          ) : (
            <div className="bg-slate-950/90 rounded-2xl p-8 border border-dashed border-slate-800 text-center font-mono space-y-2">
              <div className="text-2xl">📐</div>
              <div className="text-xs font-bold text-slate-300">
                Spatial Geometry Unavailable
              </div>
              <p className="text-[11px] text-slate-400 max-w-sm mx-auto">
                No WGS84 bounding box or metric polygon coordinates were recorded for this candidate region in upstream artifacts.
              </p>
            </div>
          )}
        </div>

        {/* Right: Coordinate Extents & Footprint Geometry (lg:col-span-5) */}
        <div className="lg:col-span-5 bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg space-y-3 font-mono">
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center space-x-2">
            <span>📐</span>
            <span>Geographic Extent & Centroid</span>
          </h4>

          {bboxDetails ? (
            <div className="space-y-2.5 text-xs">
              {/* Centroid Card */}
              <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
                <div className="text-[10px] uppercase text-emerald-400 font-semibold mb-0.5">
                  Geodesic Centroid (WGS84)
                </div>
                <div className="text-sm font-bold text-white tracking-tight">
                  {formatCoordinatesWgs84(centroidWgs84?.[0], centroidWgs84?.[1])}
                </div>
                {footprint?.centroidPx && (
                  <div className="text-[10px] text-slate-400 mt-0.5">
                    Pixel Grid Centroid: [{footprint.centroidPx[0].toFixed(1)}, {footprint.centroidPx[1].toFixed(1)}]
                  </div>
                )}
              </div>

              {/* Bounding Box Coordinates */}
              <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 space-y-2">
                <div className="text-[10px] uppercase text-cyan-400 font-semibold">
                  WGS84 Bounding Box
                </div>
                <div className="grid grid-cols-2 gap-2 text-[11px]">
                  <div>
                    <span className="text-slate-400">Min Lat: </span>
                    <strong className="text-white">{bboxDetails.minLatFormatted}</strong>
                  </div>
                  <div>
                    <span className="text-slate-400">Max Lat: </span>
                    <strong className="text-white">{bboxDetails.maxLatFormatted}</strong>
                  </div>
                  <div>
                    <span className="text-slate-400">Min Lon: </span>
                    <strong className="text-white">{bboxDetails.minLonFormatted}</strong>
                  </div>
                  <div>
                    <span className="text-slate-400">Max Lon: </span>
                    <strong className="text-white">{bboxDetails.maxLonFormatted}</strong>
                  </div>
                </div>
                <div className="pt-1.5 border-t border-slate-800/80 text-[10px] text-slate-400 flex justify-between">
                  <span>ΔLat: {bboxDetails.latSpanDeg}°</span>
                  <span>ΔLon: {bboxDetails.lonSpanDeg}°</span>
                </div>
              </div>

              {/* Pixel Dimensions */}
              {bboxPx && (
                <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 text-[11px] space-y-1">
                  <div className="text-[10px] uppercase text-slate-400 font-semibold">
                    Pixel Grid Dimensions
                  </div>
                  <div className="flex justify-between text-slate-300">
                    <span>Rows: {bboxPx.minRow} → {bboxPx.maxRow} ({bboxPx.heightPx} px)</span>
                    <span>Cols: {bboxPx.minCol} → {bboxPx.maxCol} ({bboxPx.widthPx} px)</span>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="bg-slate-950 p-5 rounded-xl border border-dashed border-slate-800 text-center text-xs text-slate-400">
              Bounding box geometry not supplied in dossier.
            </div>
          )}
        </div>
      </div>

      {/* 3. MULTI-EPOCH CORRESPONDENCE & REGION ID LINEAGE */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg space-y-4 font-mono">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center space-x-2">
              <span>🔗</span>
              <span>Multi-Epoch Correspondence & Region ID Lineage</span>
            </h4>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Candidate tracking across sequential scene pairs without assuming static region IDs.
            </p>
          </div>

          <div className="text-xs text-slate-400">
            Reference Candidate: <strong className="text-cyan-300">{referenceCandidateId}</strong>
          </div>
        </div>

        {/* Visual Lineage Flow Cards */}
        {epochs.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {epochs.map((epoch, idx) => {
              const statusDetails = getSpatialStatusDetails(epoch.status);
              const relDetails = getRelationshipDetails(epoch.relationship);
              const isDiscovery = idx === 0 && !epoch.isIdShifted;

              return (
                <div
                  key={epoch.targetPairId || idx}
                  className={`bg-slate-950/90 p-4 rounded-xl border transition-all text-xs space-y-2.5 ${
                    epoch.isIdShifted ? "border-amber-900/60 bg-amber-950/10" : "border-slate-800"
                  }`}
                >
                  {/* Step / Pair Identifier */}
                  <div className="flex items-center justify-between text-[10px] text-slate-400 border-b border-slate-800 pb-1.5">
                    <span className="font-bold text-slate-300">
                      {isDiscovery ? "Discovery Epoch (T1/T2)" : `Epoch ${idx + 1} (${epoch.targetPairId.split("__")[1] || "Pair"})`}
                    </span>
                    <span className="truncate max-w-[110px]" title={epoch.targetPairId}>
                      {epoch.targetPairId}
                    </span>
                  </div>

                  {/* Candidate Region Shift Display */}
                  <div className="space-y-1">
                    <div className="text-[10px] text-slate-400">Candidate Correspondence:</div>
                    <div className="flex items-center space-x-2 text-sm">
                      <span className="text-slate-400 font-semibold">{epoch.referenceCandidateId}</span>
                      <span className="text-cyan-400 font-bold">→</span>
                      <span className={`font-bold ${epoch.isIdShifted ? "text-amber-300 font-mono" : "text-emerald-300"}`}>
                        {epoch.matchedRegionId || "Unmatched"}
                      </span>
                    </div>

                    {epoch.isIdShifted ? (
                      <div className="inline-flex items-center space-x-1 px-2 py-0.5 rounded bg-amber-950/80 text-amber-300 border border-amber-800 text-[10px]">
                        <span>⚠️</span>
                        <span>Local Region ID Shifted</span>
                      </div>
                    ) : (
                      <div className="inline-flex items-center space-x-1 px-2 py-0.5 rounded bg-emerald-950/60 text-emerald-300 border border-emerald-800/60 text-[10px]">
                        <span>✓</span>
                        <span>Exact Discovery Reference</span>
                      </div>
                    )}
                  </div>

                  {/* Spatial Metrics (IoU & Centroid Drift) */}
                  <div className="grid grid-cols-2 gap-2 pt-1 border-t border-slate-800/80 text-[11px]">
                    <div className="bg-slate-900/90 p-2 rounded-lg border border-slate-800">
                      <div className="text-[9px] uppercase text-slate-400">Metric IoU</div>
                      <div className="text-sm font-bold text-cyan-300">
                        {epoch.metricIou != null ? epoch.metricIou.toFixed(2) : "N/A"}
                      </div>
                    </div>
                    <div className="bg-slate-900/90 p-2 rounded-lg border border-slate-800">
                      <div className="text-[9px] uppercase text-slate-400">Centroid Drift</div>
                      <div className="text-sm font-bold text-white">
                        {epoch.centroidDistanceM != null ? `${epoch.centroidDistanceM.toFixed(1)} m` : "N/A"}
                      </div>
                    </div>
                  </div>

                  {/* Status & Relationship Badges */}
                  <div className="flex flex-wrap items-center gap-1.5 pt-1">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${statusDetails.badgeClasses}`}>
                      {statusDetails.icon} {statusDetails.label}
                    </span>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${relDetails.badgeClasses}`}>
                      {relDetails.icon} {relDetails.label}
                    </span>
                  </div>

                  {/* Resolution Notes */}
                  {epoch.resolutionNotes && epoch.resolutionNotes.length > 0 && (
                    <div className="text-[10px] text-slate-400 italic pt-1 border-t border-slate-800/60">
                      {epoch.resolutionNotes[0]}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <div className="bg-slate-950/80 p-6 rounded-xl border border-dashed border-slate-800 text-center text-xs text-slate-400">
            No cross-epoch candidate correspondence evaluations recorded in this dossier.
          </div>
        )}

        {/* Technical Guidance Callout on Local Region IDs */}
        <div className="p-3.5 bg-slate-950 rounded-xl border border-slate-800 text-[11px] text-slate-300 space-y-1">
          <div className="font-bold text-cyan-300 flex items-center space-x-1.5">
            <span>ℹ️</span>
            <span>Why Region IDs Shift Across Temporal Epochs</span>
          </div>
          <p className="text-slate-400 leading-relaxed">
            Local candidate region IDs (<code className="text-slate-200">reg_0001</code>, <code className="text-slate-200">reg_0002</code>, <code className="text-slate-200">reg_0003</code>) are assigned independently per scene-pair by connected-component analysis. They are <strong>not assumed to remain stable</strong> over time. ASTRA maintains evidentiary tracking across independent pairs using projected metric bounding box intersection (IoU) and geodesic centroid drift.
          </p>
        </div>
      </div>

      {/* 4. CANDIDATE FOOTPRINT DETAILS (Morphological Upstream Features) */}
      {features && Object.keys(features).length > 0 && (
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg space-y-3 font-mono">
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center space-x-2">
            <span>📊</span>
            <span>Morphological & Spatial Feature Metrics (Upstream CDR)</span>
          </h4>

          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-2.5 text-xs">
            {features.area != null && (
              <div className="bg-slate-950 p-2.5 rounded-xl border border-slate-800">
                <div className="text-[10px] uppercase text-slate-400 font-semibold">Area</div>
                <div className="text-white font-bold mt-0.5">{Number(features.area).toLocaleString()} m²</div>
              </div>
            )}

            {features.width_px != null && features.height_px != null && (
              <div className="bg-slate-950 p-2.5 rounded-xl border border-slate-800">
                <div className="text-white font-bold mt-0.5">
                  {Number(features.width_px)} × {Number(features.height_px)} px
                </div>
              </div>
            )}

            {features.aspect_ratio != null && (
              <div className="bg-slate-950 p-2.5 rounded-xl border border-slate-800">
                <div className="text-[10px] uppercase text-slate-400 font-semibold">Aspect Ratio</div>
                <div className="text-cyan-300 font-bold mt-0.5">{Number(features.aspect_ratio).toFixed(3)}</div>
              </div>
            )}

            {features.perimeter_px != null && (
              <div className="bg-slate-950 p-2.5 rounded-xl border border-slate-800">
                <div className="text-[10px] uppercase text-slate-400 font-semibold">Perimeter</div>
                <div className="text-white font-bold mt-0.5">{Number(features.perimeter_px).toFixed(1)} px</div>
              </div>
            )}

            {features.compactness != null && (
              <div className="bg-slate-950 p-2.5 rounded-xl border border-slate-800">
                <div className="text-[10px] uppercase text-slate-400 font-semibold">Compactness</div>
                <div className="text-emerald-300 font-bold mt-0.5">{Number(features.compactness).toFixed(3)}</div>
              </div>
            )}

            {features.rectangularity != null && (
              <div className="bg-slate-950 p-2.5 rounded-xl border border-slate-800">
                <div className="text-[10px] uppercase text-slate-400 font-semibold">Rectangularity</div>
                <div className="text-white font-bold mt-0.5">{Number(features.rectangularity).toFixed(3)}</div>
              </div>
            )}

            {features.elongation != null && (
              <div className="bg-slate-950 p-2.5 rounded-xl border border-slate-800">
                <div className="text-[10px] uppercase text-slate-400 font-semibold">Elongation</div>
                <div className="text-white font-bold mt-0.5">{Number(features.elongation).toFixed(2)}</div>
              </div>
            )}

            {features.orientation_deg != null && (
              <div className="bg-slate-950 p-2.5 rounded-xl border border-slate-800">
                <div className="text-[10px] uppercase text-slate-400 font-semibold">Orientation</div>
                <div className="text-white font-bold mt-0.5">{Number(features.orientation_deg).toFixed(1)}°</div>
              </div>
            )}

            {features.boundary_distance_px != null && (
              <div className="bg-slate-950 p-2.5 rounded-xl border border-slate-800">
                <div className="text-[10px] uppercase text-slate-400 font-semibold">Boundary Dist</div>
                <div className="text-white font-bold mt-0.5">{Number(features.boundary_distance_px).toFixed(1)} px</div>
              </div>
            )}

            {features.region_density != null && (
              <div className="bg-slate-950 p-2.5 rounded-xl border border-slate-800">
                <div className="text-[10px] uppercase text-slate-400 font-semibold">Region Density</div>
                <div className="text-white font-bold mt-0.5">{Number(features.region_density).toFixed(2)}</div>
              </div>
            )}

            {features.fragmentation != null && (
              <div className="bg-slate-950 p-2.5 rounded-xl border border-slate-800">
                <div className="text-[10px] uppercase text-slate-400 font-semibold">Fragmentation</div>
                <div className="text-white font-bold mt-0.5">{Number(features.fragmentation).toFixed(2)}</div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 5. BINARY CHANGE-DETECTION MASK PREVIEW */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg space-y-4 font-mono">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <div className="flex items-center space-x-2">
              <span className="text-base">🖼️</span>
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                Binary Change Mask Preview
              </h4>
              <span className="px-2 py-0.5 text-[10px] rounded bg-slate-950 text-cyan-300 border border-slate-800">
                GET /api/v1/change-detection/{maskResultId || "{result_id}"}/mask
              </span>
            </div>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Change mask — analytical output
            </p>
          </div>

          <button
            onClick={() => setShowMask((prev) => !prev)}
            className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs transition-colors cursor-pointer"
          >
            {showMask ? "Hide Change Mask" : "View Change Mask"}
          </button>
        </div>

        {showMask && (
          <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-3">
            {maskUrl && !maskError ? (
              <div className="flex flex-col items-center justify-center space-y-2">
                <div className="relative border border-slate-800 rounded-lg overflow-hidden max-w-sm bg-black">
                  <img
                    src={maskUrl}
                    alt={`Analytical change mask for ${maskResultId}`}
                    onError={() => setMaskError(true)}
                    className="max-h-60 w-auto object-contain block mx-auto"
                  />
                </div>
                <div className="text-[11px] text-slate-400 text-center">
                  Artifact: <strong className="text-slate-200">{maskResultId}</strong> • Binary analytical output
                </div>
              </div>
            ) : (
              <div className="py-6 text-center text-xs text-slate-400 space-y-1">
                <div className="text-xl">🖼️</div>
                <div className="text-slate-300 font-bold">Change Mask Image Unavailable</div>
                <p className="text-[11px] text-slate-400">
                  {maskResultId
                    ? "Binary change mask image could not be loaded from active API endpoint."
                    : "No change detection result artifact ID is linked to this investigation."}
                </p>
              </div>
            )}

            <div className="p-2.5 bg-slate-900/60 rounded-lg border border-slate-800/80 text-[10px] text-slate-400">
              Notice: This image is an analytical change mask (binary thresholded mask representing changed pixels), not an RGB satellite picture.
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
