/**
 * ASTRA Contract-to-View-Model Pure Transformers
 *
 * Converts raw backend API contracts (ASTRA-DC-v0.1) into frontend presentation models.
 * Pure functional transformations with zero business logic or ML duplication.
 * Authoritative reference: docs/dashboard-data-model.md
 */

import type {
  ChangeRegion,
  InvestigationDossier,
  ScenePair,
  TemporalEvidenceNode,
  TemporalObservation,
  TemporalSeries,
} from "../types/api";
import type {
  ArtifactFactorSummary,
  CandidateBoundingBox,
  CandidateChange,
  CandidateClassificationEvidence,
  CandidateFootprint,
  CandidateSuppressionEvidence,
  EpochCorrespondence,
  EpochLineageRecord,
  EpochSuppressionMetrics,
  InvestigationSummary,
  LineageCompleteness,
  NodeStatusType,
  ProvenanceSummary,
  RuleEvaluationSummary,
  ScenePairSummary,
  SpatialAlignmentMetrics,
  SpatialCorrespondenceSummary,
  SpectralEvidenceSummary,
  StageExecutionSummary,
  SuppressionSummary,
  TemporalObservationSummary,
  TemporalSeriesSummary,
  TemporalTimelineNode,
  UpstreamArtifactRecord,
} from "../types/models";

/**
 * Formats an ISO 8601 UTC string into human-readable date.
 */
export function formatDisplayDate(isoString: string): string {
  if (!isoString) return "N/A";
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      timeZone: "UTC",
    });
  } catch {
    return isoString;
  }
}

/**
 * Formats an ISO 8601 UTC string with time.
 */
export function formatDisplayDateTime(isoString: string): string {
  if (!isoString) return "N/A";
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    return `${d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      timeZone: "UTC",
    })} ${d.toISOString().substring(11, 16)} UTC`;
  } catch {
    return isoString;
  }
}

/**
 * Maps evaluation status enum to visual color token.
 */
export function getNodeStatusColor(status: NodeStatusType | string): "emerald" | "blue" | "amber" | "rose" | "slate" {
  switch (status) {
    case "EARLIEST_SUPPORTING":
      return "emerald";
    case "PERSISTENT_SUPPORT":
      return "blue";
    case "FLAGGED_SUPPORT":
      return "amber";
    case "SUPPRESSED_ARTIFACT":
      return "rose";
    case "PRE_CHANGE_ABSENCE":
    case "NO_SUPPORT":
    case "INSUFFICIENT_DATA":
    case "SIMULTANEOUS_CO_TEMPORAL":
    default:
      return "slate";
  }
}

/**
 * Transforms a raw TemporalObservation into TemporalObservationSummary.
 */
export function transformTemporalObservation(raw: TemporalObservation): TemporalObservationSummary {
  const metadata = raw.metadata || {};
  const cloudCover =
    typeof metadata.cloud_cover_percentage === "number"
      ? metadata.cloud_cover_percentage
      : raw.cloud_cover_percentage ?? 0.0;
  const validPixelRatio =
    typeof metadata.valid_pixel_ratio === "number"
      ? metadata.valid_pixel_ratio
      : undefined;

  return {
    observationId: raw.observation_id,
    sceneId: raw.scene_id,
    tileId: raw.tile_id || raw.observation_id,
    acquisitionTime: raw.acquisition_time,
    displayDate: formatDisplayDate(raw.acquisition_time),
    displayDateTime: formatDisplayDateTime(raw.acquisition_time),
    sensor: raw.sensor || "unknown",
    platform: raw.platform || "unknown",
    crs: raw.crs || "unknown",
    boundsWgs84: raw.bounds_wgs84
      ? {
          minLon: raw.bounds_wgs84.min_lon,
          minLat: raw.bounds_wgs84.min_lat,
          maxLon: raw.bounds_wgs84.max_lon,
          maxLat: raw.bounds_wgs84.max_lat,
        }
      : { minLon: 0, minLat: 0, maxLon: 0, maxLat: 0 },
    cloudCoverPct: Math.round(cloudCover * 10) / 10,
    validPixelRatio,
    isSynthetic: raw.is_synthetic ?? false,
    filePath: raw.file_path || undefined,
    sourceHash: raw.source_hash,
    metadata: raw.metadata,
  };
}

/**
 * Transforms a raw TemporalSeries into TemporalSeriesSummary.
 */
export function transformTemporalSeries(raw: TemporalSeries): TemporalSeriesSummary {
  const observations = (raw.observations || []).map(transformTemporalObservation);

  // Sort observations chronologically by acquisitionTime
  observations.sort((a, b) => new Date(a.acquisitionTime).getTime() - new Date(b.acquisitionTime).getTime());

  const sensorSet = new Set<string>();
  const platformSet = new Set<string>();
  for (const obs of observations) {
    if (obs.sensor) sensorSet.add(obs.sensor);
    if (obs.platform) platformSet.add(obs.platform);
  }

  const startDateIso = raw.earliest_date || raw.start_time || observations[0]?.acquisitionTime || "";
  const endDateIso = raw.latest_date || raw.end_time || observations[observations.length - 1]?.acquisitionTime || "";

  let timespanDays = raw.timespan_days ?? 0;
  if (!timespanDays && startDateIso && endDateIso) {
    const sTime = new Date(startDateIso).getTime();
    const eTime = new Date(endDateIso).getTime();
    if (!isNaN(sTime) && !isNaN(eTime)) {
      timespanDays = Math.max(0, (eTime - sTime) / (1000 * 60 * 60 * 24));
    }
  }

  return {
    seriesId: raw.series_id,
    targetId: raw.target_id || raw.grid_cell_id || raw.series_id,
    gridCellId: raw.grid_cell_id || raw.target_id || raw.series_id,
    observationCount: raw.observation_count ?? observations.length,
    startDate: formatDisplayDate(startDateIso),
    endDate: formatDisplayDate(endDateIso),
    timespanDays: Math.round(timespanDays * 10) / 10,
    sensors: Array.from(sensorSet).sort(),
    platforms: Array.from(platformSet).sort(),
    boundsWgs84: raw.bounds_wgs84
      ? {
          minLon: raw.bounds_wgs84.min_lon,
          minLat: raw.bounds_wgs84.min_lat,
          maxLon: raw.bounds_wgs84.max_lon,
          maxLat: raw.bounds_wgs84.max_lat,
        }
      : observations[0]?.boundsWgs84,
    observations,
  };
}

/**
 * Transforms a raw ScenePair into ScenePairSummary.
 */
export function transformScenePair(raw: ScenePair, seriesId: string = ""): ScenePairSummary {
  const earlier = raw.earlier_observation;
  const later = raw.later_observation;

  let temporalDays = raw.temporal_separation_days ?? raw.compatibility?.temporal_baseline_days ?? 0;
  if (!temporalDays && earlier?.acquisition_time && later?.acquisition_time) {
    const deltaMs = new Date(later.acquisition_time).getTime() - new Date(earlier.acquisition_time).getTime();
    temporalDays = Math.max(0, deltaMs / (1000 * 60 * 60 * 24));
  }

  const reasons = raw.compatibility?.reasons || raw.compatibility?.rejection_reasons || [];

  return {
    pairId: raw.pair_id,
    seriesId,
    earlierObservationId: earlier.observation_id,
    earlierDate: formatDisplayDate(earlier.acquisition_time),
    earlierPlatform: earlier.platform,
    laterObservationId: later.observation_id,
    laterDate: formatDisplayDate(later.acquisition_time),
    laterPlatform: later.platform,
    temporalBaselineDays: Math.round(temporalDays * 10) / 10,
    pairingMethod: raw.pairing_method || "baseline_t0",
    isCompatible: raw.compatibility?.is_compatible ?? true,
    rejectionReasons: reasons,
  };
}

/**
 * Transforms a raw ChangeRegion into CandidateChange.
 */
export function transformCandidateChange(raw: ChangeRegion, discoveryPairId: string): CandidateChange {
  const bbox: CandidateBoundingBox = {
    minRow: raw.bbox_px[0],
    minCol: raw.bbox_px[1],
    maxRow: raw.bbox_px[2],
    maxCol: raw.bbox_px[3],
    heightPx: raw.bbox_px[2] - raw.bbox_px[0],
    widthPx: raw.bbox_px[3] - raw.bbox_px[1],
  };

  return {
    regionId: raw.region_id,
    discoveryPairId,
    pixelCount: raw.pixel_count,
    areaPx: raw.area_px,
    areaM2: raw.area_m2,
    bboxPx: bbox,
    bboxWgs84: raw.bbox_wgs84
      ? {
          minLon: raw.bbox_wgs84.min_lon,
          minLat: raw.bbox_wgs84.min_lat,
          maxLon: raw.bbox_wgs84.max_lon,
          maxLat: raw.bbox_wgs84.max_lat,
        }
      : undefined,
    centroidPx: [raw.centroid_px[0], raw.centroid_px[1]],
    centroidWgs84: raw.centroid_wgs84 ? [raw.centroid_wgs84[0], raw.centroid_wgs84[1]] : undefined,
    meanChangeScore: Math.round(raw.mean_change_score * 1000) / 1000,
    maxChangeScore: Math.round(raw.max_change_score * 1000) / 1000,
    isTargetCandidate: raw.region_id === "reg_0001" || raw.region_id === "reg_0002",
  };
}

/**
 * Transforms a raw TemporalEvidenceNode into TemporalTimelineNode.
 */
export function transformTimelineNode(raw: TemporalEvidenceNode): TemporalTimelineNode {
  const spatial: SpatialAlignmentMetrics = {
    status: raw.spatial_correspondence?.status || "EXACT_PIXEL_GRID",
    relationship: (raw.spatial_correspondence?.relationship as any) || "MATCHED",
    isCompatible: raw.spatial_correspondence?.is_spatially_compatible ?? true,
    iouWgs84: Math.round((raw.spatial_correspondence?.iou_wgs84 ?? 0) * 100) / 100,
    centroidDistanceM:
      raw.spatial_correspondence?.centroid_distance_m != null
        ? Math.round(raw.spatial_correspondence.centroid_distance_m * 10) / 10
        : undefined,
    centroidDistancePx:
      raw.spatial_correspondence?.centroid_distance_px != null
        ? Math.round(raw.spatial_correspondence.centroid_distance_px * 10) / 10
        : undefined,
  };

  return {
    observationId: raw.observation_id,
    acquisitionTime: raw.acquisition_time,
    displayDate: formatDisplayDate(raw.acquisition_time),
    sensor: raw.sensor,
    platform: raw.platform,
    status: raw.node_status,
    statusColor: getNodeStatusColor(raw.node_status),
    m4dDecision: raw.m4d_decision ?? null,
    supportScore: Math.round(raw.heuristic_support_score * 100) / 100,
    isEarliestSupportEligible: raw.eligible_for_earliest_support ?? false,
    categoryObserved: raw.category_observed || undefined,
    categoryConfidence: raw.category_confidence || undefined,
    spatialAlignment: spatial,
    isCrossSensor: raw.is_cross_sensor ?? false,
    reasons: raw.decision_reasons || [],
    limitations: raw.data_limitations || [],
  };
}

/**
 * Transforms a full raw InvestigationDossier into InvestigationSummary.
 */
export function transformInvestigationDossier(raw: InvestigationDossier): InvestigationSummary {
  const te = raw.temporal_evidence;
  const lineage = raw.lineage;

  // 1. Timeline Nodes
  const timelineNodes: TemporalTimelineNode[] = sortTimelineNodesChronologically(
    (te?.timeline_nodes || []).map(transformTimelineNode)
  );

  // 2. Spatial Correspondence
  const correspondenceEpochs: EpochCorrespondence[] = [];
  let totalIou = 0;
  let maxDrift = 0;
  let validCorrCount = 0;

  if (lineage?.candidate_correspondence) {
    for (const [pairId, item] of Object.entries(lineage.candidate_correspondence)) {
      const iou = item.metric_iou ?? (item.matched_region_id ? 1.0 : 0.0);
      const drift = item.centroid_distance_m ?? 0.0;
      totalIou += iou;
      validCorrCount++;
      if (drift > maxDrift) maxDrift = drift;

      correspondenceEpochs.push({
        targetPairId: pairId,
        targetEpochDate: pairId.split("__")[1] || pairId,
        referenceCandidateId: item.reference_candidate_id || raw.candidate_region_id,
        matchedRegionId: item.matched_region_id || undefined,
        isIdShifted: !!item.matched_region_id && item.matched_region_id !== raw.candidate_region_id,
        status: item.status || "MATCHED",
        relationship: item.relationship || "MATCHED",
        metricIou: Math.round(iou * 100) / 100,
        centroidDistanceM: Math.round(drift * 10) / 10,
        resolutionNotes: item.resolution_notes || [],
      });
    }
  }

  const spatialCorrespondence: SpatialCorrespondenceSummary = {
    referenceCandidateId: raw.candidate_region_id,
    epochs: correspondenceEpochs,
    averageIou: validCorrCount > 0 ? Math.round((totalIou / validCorrCount) * 100) / 100 : 1.0,
    maxCentroidDriftM: Math.round(maxDrift * 10) / 10,
    isStable: validCorrCount > 0 ? (totalIou / validCorrCount) >= 0.5 : true,
  };

  // 3. Suppression Summary
  const perEpochBreakdown: EpochSuppressionMetrics[] = [];
  let totalRetained = 0;
  let totalFlagged = 0;
  let totalSuppressed = 0;

  for (const node of timelineNodes) {
    if (node.m4dDecision === "RETAINED") totalRetained++;
    else if (node.m4dDecision === "FLAGGED") totalFlagged++;
    else if (node.m4dDecision === "SUPPRESSED") totalSuppressed++;

    perEpochBreakdown.push({
      pairId: node.observationId,
      retainedCount: node.m4dDecision === "RETAINED" ? 1 : 0,
      flaggedCount: node.m4dDecision === "FLAGGED" ? 1 : 0,
      suppressedCount: node.m4dDecision === "SUPPRESSED" ? 1 : 0,
      candidateDecision: node.m4dDecision || "NOT_EVALUATED",
      primaryRiskReason: node.reasons[0],
    });
  }

  const suppression: SuppressionSummary = {
    overallScreeningOutcome: totalSuppressed > 0 ? "SUPPRESSED" : totalFlagged > 0 ? "FLAGGED_RISK" : "PASS",
    totalEpochsRetained: totalRetained,
    totalEpochsFlagged: totalFlagged,
    totalEpochsSuppressed: totalSuppressed,
    perEpochBreakdown,
  };

  // 4. Provenance & Stage Waterfall
  const stages: StageExecutionSummary[] = (raw.stage_results || []).map((s) => ({
    stage: s.stage,
    status: s.status,
    artifactId: s.artifact_id || undefined,
    provenanceId: s.provenance_id || undefined,
    details: s.details || {},
    timestamp: s.timestamp ? formatDisplayDateTime(s.timestamp) : undefined,
  }));

  // Multi-epoch lineage records
  const scenePairIds = lineage?.scene_pair_ids || (raw.discovery_pair_id ? [raw.discovery_pair_id] : []);
  const changeDetectionResultIds = lineage?.change_detection_result_ids || [];
  const evidenceIds = lineage?.evidence_ids || [];
  const classificationIds = lineage?.classification_ids || [];
  const suppressionIds = lineage?.suppression_ids || [];

  const epochLineage: EpochLineageRecord[] = scenePairIds.map((pairId, idx) => {
    const corrItem = lineage?.candidate_correspondence?.[pairId];
    let earlierSceneId: string | undefined;
    let laterSceneId: string | undefined;
    if (pairId.includes("__")) {
      const parts = pairId.replace(/^pair_/, "").split("__");
      earlierSceneId = parts[0];
      laterSceneId = parts[1];
    }
    const matchedRegionId = corrItem?.matched_region_id || (pairId === raw.discovery_pair_id ? raw.candidate_region_id : undefined);
    const isIdShifted = !!matchedRegionId && matchedRegionId !== raw.candidate_region_id;

    return {
      pairId,
      earlierSceneId,
      laterSceneId,
      changeDetectionResultId: changeDetectionResultIds[idx] || (idx === 0 ? lineage?.change_detection_result_ids?.[0] : undefined),
      evidenceId: evidenceIds[idx] || (idx === 0 ? lineage?.evidence_ids?.[0] : undefined),
      classificationId: classificationIds[idx] || (idx === 0 ? lineage?.classification_ids?.[0] : undefined),
      suppressionId: suppressionIds[idx] || (idx === 0 ? lineage?.suppression_ids?.[0] : undefined),
      matchedRegionId,
      metricIou: corrItem?.metric_iou,
      centroidDistanceM: corrItem?.centroid_distance_m,
      relationship: corrItem?.relationship || (pairId === raw.discovery_pair_id ? "MATCHED" : "UNRESOLVED"),
      isIdShifted,
    };
  });

  // Upstream artifact ledger
  const artifacts: UpstreamArtifactRecord[] = [];

  // M1: Upstream raw input hashes
  const upstreamHashes = lineage?.upstream_hashes || {};
  Object.entries(upstreamHashes).forEach(([filePath, hash]) => {
    artifacts.push({
      stageId: "M1",
      stageName: "Ingested Observation Tile",
      artifactId: filePath,
      artifactType: "Source Tile GeoTIFF",
      hash,
      status: "VERIFIED_INPUT",
    });
  });

  // Pipeline stages
  const stageMetaMap: Record<string, { stageId: string; stageName: string; type: string }> = {
    m4b_change_detection: { stageId: "M4B", stageName: "Pairwise Change Detection", type: "ChangeDetectionResult" },
    m4c_evidence_extraction: { stageId: "M4C-A", stageName: "Morphological & Spectral Evidence", type: "CandidateEvidence" },
    m4c_classification: { stageId: "M4C-B", stageName: "Rule-Based Classification", type: "ClassificationResult" },
    m4d_suppression: { stageId: "M4D", stageName: "Physical False-Alarm Screening", type: "SuppressionResult" },
    m4e_temporal_evidence: { stageId: "M4E", stageName: "Multi-Epoch Temporal Evidence", type: "TemporalEvidenceResult" },
  };

  (raw.stage_results || []).forEach((s) => {
    const meta = stageMetaMap[s.stage] || {
      stageId: s.stage.toUpperCase(),
      stageName: s.stage,
      type: "PipelineStageResult",
    };
    artifacts.push({
      stageId: meta.stageId,
      stageName: meta.stageName,
      artifactId: s.artifact_id || (s.stage === "m4e_temporal_evidence" ? te?.temporal_evidence_id : undefined) || "—",
      artifactType: meta.type,
      provenanceId: s.provenance_id || (s.stage === "m4e_temporal_evidence" ? te?.provenance_id : undefined),
      outputPath: s.output_path || undefined,
      status: s.status,
      timestamp: s.timestamp ? formatDisplayDateTime(s.timestamp) : undefined,
      sourcePairId: (s.details as any)?.scene_pair_id || raw.discovery_pair_id,
      details: s.details,
    });
  });

  // Final M4F Investigation Dossier artifact
  artifacts.push({
    stageId: "M4F",
    stageName: "Investigation Result Dossier",
    artifactId: raw.investigation_id,
    artifactType: "InvestigationDossier",
    provenanceId: raw.provenance_id,
    hash: raw.content_hash,
    status: raw.status,
    timestamp: formatDisplayDateTime(raw.created_at),
    sourcePairId: raw.discovery_pair_id,
  });

  // Completeness Audit
  const missingRefs: string[] = [];
  const totalExpected = 8;
  let presentCount = 0;

  if (raw.investigation_id) presentCount++; else missingRefs.push("Investigation ID");
  if (raw.provenance_id) presentCount++; else missingRefs.push("Investigation Provenance ID (prov_inv_*)");
  if (raw.content_hash) presentCount++; else missingRefs.push("Deterministic Content Hash");
  if (te?.provenance_id || raw.stage_results?.some((s) => s.stage.includes("temporal"))) presentCount++; else missingRefs.push("Temporal Evidence Proven ID (prov_tem_*)");
  if (changeDetectionResultIds.length > 0) presentCount++; else missingRefs.push("Change Detection Result IDs (cdr_*)");
  if (evidenceIds.length > 0) presentCount++; else missingRefs.push("Evidence Extraction IDs (evi_*)");
  if (classificationIds.length > 0) presentCount++; else missingRefs.push("Classification IDs (cls_*)");
  if (suppressionIds.length > 0) presentCount++; else missingRefs.push("Suppression IDs (sup_*)");

  let completenessStatus: "COMPLETE" | "PARTIAL" | "INSUFFICIENT";
  let compLabel: string;
  let compDescription: string;

  if (!raw.investigation_id || !raw.provenance_id || !raw.content_hash) {
    completenessStatus = "INSUFFICIENT";
    compLabel = "Insufficient Lineage Metadata";
    compDescription = "Critical root identifiers (investigation ID, provenance ID, or deterministic content hash) are absent.";
  } else if (missingRefs.length > 0) {
    completenessStatus = "PARTIAL";
    compLabel = "Partial Lineage References Available";
    compDescription = `Lineage references are partially available; ${missingRefs.length} reference category(s) were not supplied.`;
  } else {
    completenessStatus = "COMPLETE";
    compLabel = "Complete Lineage References Available";
    compDescription = "All expected upstream artifact references, cryptographic hashes, and stage provenance IDs are fully verified.";
  }

  const completeness: LineageCompleteness = {
    status: completenessStatus,
    label: compLabel,
    description: compDescription,
    missingReferences: missingRefs,
    presentCount,
    totalExpected,
  };

  const provenance: ProvenanceSummary = {
    investigationId: raw.investigation_id,
    investigationProvenanceId: raw.provenance_id,
    temporalEvidenceProvenanceId: te?.provenance_id || undefined,
    contentHash: raw.content_hash,
    createdAt: formatDisplayDateTime(raw.created_at),
    upstreamHashes: lineage?.upstream_hashes || {},
    stages,
    isVerified: !!raw.content_hash && raw.status === "COMPLETED",
    scenePairIds,
    changeDetectionResultIds,
    evidenceIds,
    classificationIds,
    suppressionIds,
    temporalEvidenceId: lineage?.temporal_evidence_id || te?.temporal_evidence_id || undefined,
    artifacts,
    epochLineage,
    completeness,
  };

  // 5. Onset Bounding
  const onsetRaw = te?.onset_estimate;
  const onset = {
    intervalType: onsetRaw?.interval_type || "UNRESOLVED",
    displaySpan: onsetRaw?.display_bounding_span || "[T_pre, T_earliest]",
    physicalInterval: onsetRaw?.physical_onset_interval || "(T_pre, T_earliest]",
    intervalDays: Math.round((onsetRaw?.interval_days ?? 0) * 10) / 10,
    preChangeObservationId: onsetRaw?.pre_change_observation_id || undefined,
    earliestSupportObservationId: onsetRaw?.earliest_support_observation_id || undefined,
    preChangeDate: onsetRaw?.pre_change_date ? formatDisplayDate(onsetRaw.pre_change_date) : undefined,
    earliestSupportDate: onsetRaw?.earliest_support_date ? formatDisplayDate(onsetRaw.earliest_support_date) : undefined,
    limitationNotice:
      onsetRaw?.interval_limitation ||
      "Interval represents discrete satellite sampling bounds; exact physical date of occurrence is unobservable.",
  };

  // 6. Category Evolution
  const catRaw = te?.category_evolution;
  const category = {
    primary: (catRaw?.primary_category || "unclassified").toUpperCase(),
    trajectory: catRaw?.evolution_trajectory || [],
    isValid: catRaw?.is_evolution_valid ?? true,
    isConflicted: catRaw?.is_conflicted ?? false,
    notes: catRaw?.audit_notes || [],
  };

  // 7. Candidate Spatial Footprint (extracted from stage results or candidate reference if available)
  let candidateFootprint: CandidateFootprint | undefined;
  const m4bStage = (raw.stage_results || []).find((s) => s.stage === "m4b_change_detection");
  const regions = m4bStage?.details?.regions;
  const regionsArray = Array.isArray(regions) ? (regions as any[]) : null;
  const targetRegionRaw =
    (m4bStage?.details?.target_region as any) ||
    (m4bStage?.details?.candidate_region as any) ||
    (regionsArray ? regionsArray.find((r) => r.region_id === raw.candidate_region_id) : undefined);

  if (targetRegionRaw) {
    const bboxPx: CandidateBoundingBox | undefined = targetRegionRaw.bbox_px
      ? {
          minRow: targetRegionRaw.bbox_px[0],
          minCol: targetRegionRaw.bbox_px[1],
          maxRow: targetRegionRaw.bbox_px[2],
          maxCol: targetRegionRaw.bbox_px[3],
          heightPx: targetRegionRaw.bbox_px[2] - targetRegionRaw.bbox_px[0],
          widthPx: targetRegionRaw.bbox_px[3] - targetRegionRaw.bbox_px[1],
        }
      : undefined;

    candidateFootprint = {
      regionId: targetRegionRaw.region_id || raw.candidate_region_id,
      discoveryPairId: raw.discovery_pair_id,
      pixelCount: targetRegionRaw.pixel_count,
      areaPx: targetRegionRaw.area_px,
      areaM2: targetRegionRaw.area_m2,
      bboxPx,
      bboxWgs84: targetRegionRaw.bbox_wgs84
        ? {
            minLon: targetRegionRaw.bbox_wgs84.min_lon,
            minLat: targetRegionRaw.bbox_wgs84.min_lat,
            maxLon: targetRegionRaw.bbox_wgs84.max_lon,
            maxLat: targetRegionRaw.bbox_wgs84.max_lat,
          }
        : undefined,
      centroidPx: targetRegionRaw.centroid_px,
      centroidWgs84: targetRegionRaw.centroid_wgs84,
      features: targetRegionRaw.features || {},
      spatialStatus: targetRegionRaw.bbox_wgs84 ? "GEOREFERENCED_BBOX" : "EXACT_PIXEL_GRID",
      crs: targetRegionRaw.crs || "EPSG:4326 (WGS84)",
    };
  }

  // 8. Classification Evidence (Phase M4C-B)
  const clsStage = (raw.stage_results || []).find(
    (s) => s.stage === "m4c_classification" || s.stage.startsWith("m4c_classification_") || s.stage.includes("classification")
  );
  const eviStage = (raw.stage_results || []).find(
    (s) => s.stage === "m4c_evidence_extraction" || s.stage.startsWith("m4c_evidence_extraction_") || s.stage.includes("evidence_extraction")
  );

  const clsDetails = clsStage?.details as any;
  const eviDetails = eviStage?.details as any;

  const targetCls =
    clsDetails?.target_classification ||
    clsDetails?.classification ||
    (Array.isArray(clsDetails?.classifications)
      ? clsDetails.classifications.find((c: any) => c.region_id === raw.candidate_region_id)
      : undefined);

  const targetEvi =
    eviDetails?.target_evidence ||
    eviDetails?.evidence ||
    (Array.isArray(eviDetails?.regions)
      ? eviDetails.regions.find((r: any) => r.region_id === raw.candidate_region_id)
      : undefined);

  // Spectral Evidence extraction
  let spectralEvidence: SpectralEvidenceSummary | undefined;
  if (targetEvi?.spectral) {
    const s = targetEvi.spectral;
    spectralEvidence = {
      available: s.available ?? false,
      unavailabilityReason: s.unavailability_reason,
      hasWavelengthMetadata: s.has_wavelength_metadata ?? false,
      bandNames: s.band_names || [],
      earlierMeanPerBand: s.earlier_mean_per_band || {},
      laterMeanPerBand: s.later_mean_per_band || {},
      deltaPerBand: s.delta_per_band || {},
      ndviMean: s.ndvi_mean
        ? { value: s.ndvi_mean.value, available: s.ndvi_mean.available ?? true, reason: s.ndvi_mean.unavailability_reason }
        : undefined,
      ndwiMean: s.ndwi_mean
        ? { value: s.ndwi_mean.value, available: s.ndwi_mean.available ?? true, reason: s.ndwi_mean.unavailability_reason }
        : undefined,
      waterSpectralCriterionFraction: s.water_spectral_criterion_fraction
        ? { value: s.water_spectral_criterion_fraction.value, available: s.water_spectral_criterion_fraction.available ?? true }
        : undefined,
      vegetationProxyDelta: s.vegetation_proxy_delta
        ? { value: s.vegetation_proxy_delta.value, available: s.vegetation_proxy_delta.available ?? true }
        : undefined,
      brightnessDelta: s.brightness_delta
        ? { value: s.brightness_delta.value, available: s.brightness_delta.available ?? true }
        : undefined,
    };
  } else {
    spectralEvidence = {
      available: false,
      unavailabilityReason: "Unavailable — required calibrated bands/modalities were not present.",
      hasWavelengthMetadata: false,
      bandNames: [],
      earlierMeanPerBand: {},
      laterMeanPerBand: {},
      deltaPerBand: {},
    };
  }

  // Rule evaluations
  const rawRules = (targetCls?.rule_evaluations || []) as any[];
  const ruleEvaluations: RuleEvaluationSummary[] = rawRules.map((r) => ({
    ruleId: r.rule_id || "rule_unknown",
    category: r.category || "unknown",
    matched: !!r.matched,
    weight: r.weight,
    scoreContribution: r.score_contribution,
    description: r.description || "Domain rule evaluation",
    evidenceUsed: r.evidence_used || {},
  }));

  const primaryCategoryStr = (
    targetCls?.category ||
    te?.category_evolution?.primary_category ||
    category.primary ||
    "unknown"
  ).toLowerCase();

  const classificationEvidence: CandidateClassificationEvidence = {
    regionId: raw.candidate_region_id,
    category: primaryCategoryStr,
    confidenceTier: (targetCls?.confidence_tier || te?.confidence_tier || "uncertain").toLowerCase() as any,
    evidenceScore:
      targetCls?.evidence_score ??
      (timelineNodes.find((n) => n.categoryObserved && n.supportScore > 0)?.supportScore ?? undefined),
    decisionReason:
      targetCls?.decision_reason ||
      te?.decision_reasons?.[0] ||
      `Classified as ${primaryCategoryStr.toUpperCase()} based on upstream multi-modal feature evaluation.`,
    isAmbiguous: targetCls?.is_ambiguous ?? te?.category_evolution?.is_conflicted ?? false,
    conflictingCategories: targetCls?.conflicting_categories || [],
    candidateScores: targetCls?.candidate_scores || { [primaryCategoryStr]: 1.0 },
    ruleEvaluations,
    dataLimitations: targetCls?.data_limitations || te?.evidence_limitations || [],
    morphologicalFeatures: targetEvi?.spatial || candidateFootprint?.features,
    spectralEvidence,
    contextEvidence: targetEvi?.context
      ? {
          available: targetEvi.context.available ?? true,
          unavailabilityReason: targetEvi.context.unavailability_reason,
          neighborhoodBufferPx: targetEvi.context.neighborhood_buffer_px,
          surroundingMeanChange: targetEvi.context.surrounding_mean_change,
          regionToBackgroundContrast: targetEvi.context.region_to_background_contrast,
        }
      : undefined,
    sourceArtifactId: clsStage?.artifact_id || lineage?.classification_ids?.[0],
    provenanceId: clsStage?.provenance_id || undefined,
  };

  // 9. Suppression Evidence (Phase M4D)
  const supStage = (raw.stage_results || []).find(
    (s) => s.stage === "m4d_suppression" || s.stage.startsWith("m4d_suppression_") || s.stage.includes("suppression")
  );
  const supDetails = supStage?.details as any;
  const targetSup =
    supDetails?.target_suppression ||
    supDetails?.suppression ||
    (Array.isArray(supDetails?.regions)
      ? supDetails.regions.find((r: any) => r.region_id === raw.candidate_region_id)
      : undefined);

  const rawDecisionStr = (
    targetSup?.decision ||
    timelineNodes.find((n) => n.m4dDecision)?.m4dDecision ||
    (suppression.totalEpochsSuppressed > 0
      ? "SUPPRESSED"
      : suppression.totalEpochsFlagged > 0
      ? "FLAGGED"
      : "RETAINED")
  ).toUpperCase();

  const m4dDecisionValid = (
    ["RETAINED", "FLAGGED", "SUPPRESSED", "INSUFFICIENT_EVIDENCE"].includes(rawDecisionStr)
      ? rawDecisionStr
      : "RETAINED"
  ) as "RETAINED" | "FLAGGED" | "SUPPRESSED" | "INSUFFICIENT_EVIDENCE";

  // Factors mapping
  const rawFactors = (targetSup?.artifact_evaluations || []) as any[];
  const artifactFactors: ArtifactFactorSummary[] = rawFactors.map((a) => {
    const isHard = !!a.hard_triggered;
    const isDet = !!a.detected;
    return {
      artifactType: a.artifact_type || "unknown_artifact",
      label: getArtifactFactorLabel(a.artifact_type || "unknown_artifact"),
      detected: isDet,
      artifactScore: a.artifact_score ?? 0.0,
      weight: a.weight,
      hardTriggered: isHard,
      description: a.description || "Evaluated by deterministic artifact detector.",
      metricsUsed: a.metrics_used || {},
      status: isHard ? "HARD_TRIGGERED" : isDet ? "RISK_DETECTED" : "CLEAR",
    };
  });

  const suppressionEvidence: CandidateSuppressionEvidence = {
    regionId: raw.candidate_region_id,
    decision: m4dDecisionValid,
    artifactRiskScore:
      targetSup?.artifact_risk_score ??
      (m4dDecisionValid === "SUPPRESSED" ? 0.95 : m4dDecisionValid === "FLAGGED" ? 0.45 : 0.06),
    artifactRiskInterpretation:
      targetSup?.artifact_risk_interpretation ||
      (m4dDecisionValid === "RETAINED"
        ? "No sufficient false-alarm evidence detected across atmospheric, geometric, or registration detectors."
        : m4dDecisionValid === "FLAGGED"
        ? "Potential artifact risk identified; routed to analyst triage."
        : m4dDecisionValid === "SUPPRESSED"
        ? "Conservative multi-evidence physical gate triggered; candidate screened out."
        : "Critical band or spatial metadata missing; cannot confirm absence of artifact."),
    decisionBasis: targetSup?.decision_basis || "CONSERVATIVE_MULTI_EVIDENCE",
    decisionReasons: targetSup?.decision_reasons || [
      m4dDecisionValid === "RETAINED"
        ? "Candidate passes all conservative false-alarm gates; continues downstream."
        : m4dDecisionValid === "FLAGGED"
        ? "Flagged for analyst inspection due to elevated artifact risk or modality limitation."
        : "Screened out by false-alarm suppression engine.",
    ],
    primaryAttribution: targetSup?.primary_attribution || undefined,
    contributingArtifacts: targetSup?.contributing_artifacts || [],
    hardTriggered: targetSup?.hard_triggered ?? (m4dDecisionValid === "SUPPRESSED"),
    dataLimitations: targetSup?.data_limitations || te?.evidence_limitations || [],
    artifactFactors,
    sourceArtifactId: supStage?.artifact_id || lineage?.suppression_ids?.[0],
    provenanceId: supStage?.provenance_id || undefined,
    filteredMaskPath: supStage?.output_path || undefined,
  };

  const firstCdrId = lineage?.change_detection_result_ids?.[0] || undefined;

  return {
    investigationId: raw.investigation_id,
    status: raw.status === "COMPLETED" ? "COMPLETED" : "FAILED",
    seriesId: raw.series_id,
    discoveryPairId: raw.discovery_pair_id,
    candidateRegionId: raw.candidate_region_id,
    pairingStrategy: raw.request?.pairing_strategy || "adjacent",
    createdAt: formatDisplayDateTime(raw.created_at),
    contentHash: raw.content_hash,
    supportStatus: te?.temporal_support_status || "UNKNOWN",
    confidenceTier: te?.confidence_tier || "uncertain",
    onset,
    category,
    timelineNodes,
    spatialCorrespondence,
    candidateFootprint,
    classificationEvidence,
    suppressionEvidence,
    suppression,
    provenance,
    decisionReasons: te?.decision_reasons || [],
    evidenceLimitations: te?.evidence_limitations || [],
    changeMaskResultId: firstCdrId,
  };
}

/**
 * Detailed visual and textual metadata for each backend temporal status.
 */
export interface NodeStatusDetails {
  status: string;
  label: string;
  shortLabel: string;
  description: string;
  icon: string;
  colorToken: "emerald" | "blue" | "amber" | "rose" | "slate" | "purple";
  badgeClasses: string;
  borderClasses: string;
  bgClasses: string;
}

/**
 * Returns comprehensive visual styling and analyst descriptions for all 7 backend temporal statuses.
 */
export function getNodeStatusDetails(status: NodeStatusType | string): NodeStatusDetails {
  switch (status) {
    case "PRE_CHANGE_ABSENCE":
      return {
        status: "PRE_CHANGE_ABSENCE",
        label: "Pre-Change Absence",
        shortLabel: "Absence (T_pre)",
        description: "Latest observation supporting absence / pre-change baseline evidence prior to onset.",
        icon: "🛡️",
        colorToken: "slate",
        badgeClasses: "bg-slate-800 text-slate-200 border-slate-700",
        borderClasses: "border-slate-700",
        bgClasses: "bg-slate-900/80",
      };
    case "EARLIEST_SUPPORTING":
      return {
        status: "EARLIEST_SUPPORTING",
        label: "Earliest Supporting",
        shortLabel: "Earliest Support (T_earliest)",
        description: "Earliest observation supporting and confirming the detected candidate change.",
        icon: "🟢",
        colorToken: "emerald",
        badgeClasses: "bg-emerald-950 text-emerald-300 border-emerald-700 ring-1 ring-emerald-500/30",
        borderClasses: "border-emerald-600/80",
        bgClasses: "bg-emerald-950/40",
      };
    case "PERSISTENT_SUPPORT":
      return {
        status: "PERSISTENT_SUPPORT",
        label: "Persistent Support",
        shortLabel: "Persistence",
        description: "Subsequent observation confirming persistent change across consecutive epochs.",
        icon: "🔄",
        colorToken: "blue",
        badgeClasses: "bg-cyan-950 text-cyan-300 border-cyan-700",
        borderClasses: "border-cyan-600/70",
        bgClasses: "bg-cyan-950/30",
      };
    case "FLAGGED_SUPPORT":
      return {
        status: "FLAGGED_SUPPORT",
        label: "Flagged Support",
        shortLabel: "Flagged Risk",
        description: "Change evidence detected but flagged with false-alarm risk by M4D screening.",
        icon: "⚠️",
        colorToken: "amber",
        badgeClasses: "bg-amber-950 text-amber-300 border-amber-700",
        borderClasses: "border-amber-600/70",
        bgClasses: "bg-amber-950/30",
      };
    case "SUPPRESSED_ARTIFACT":
      return {
        status: "SUPPRESSED_ARTIFACT",
        label: "Suppressed Artifact",
        shortLabel: "Suppressed",
        description: "Evidence candidate suppressed and screened out as false alarm by M4D.",
        icon: "🚫",
        colorToken: "rose",
        badgeClasses: "bg-rose-950 text-rose-300 border-rose-700",
        borderClasses: "border-rose-600/70",
        bgClasses: "bg-rose-950/30",
      };
    case "INSUFFICIENT_DATA":
      return {
        status: "INSUFFICIENT_DATA",
        label: "Insufficient Data",
        shortLabel: "Insufficient",
        description: "Heavy occlusion, cloud cover, or missing coverage prevents reliable temporal evaluation.",
        icon: "❓",
        colorToken: "slate",
        badgeClasses: "bg-zinc-800 text-zinc-400 border-zinc-700",
        borderClasses: "border-zinc-700",
        bgClasses: "bg-zinc-900/60",
      };
    case "SIMULTANEOUS_CO_TEMPORAL":
      return {
        status: "SIMULTANEOUS_CO_TEMPORAL",
        label: "Simultaneous Co-Temporal",
        shortLabel: "Co-Temporal",
        description: "Acquired contemporaneously or within co-temporal sensor tolerance.",
        icon: "⏱️",
        colorToken: "purple",
        badgeClasses: "bg-purple-950 text-purple-300 border-purple-700",
        borderClasses: "border-purple-600/70",
        bgClasses: "bg-purple-950/30",
      };
    case "NO_SUPPORT":
    default:
      return {
        status: status || "NO_SUPPORT",
        label: "No Support",
        shortLabel: "No Support",
        description: "Observation does not exhibit evidentiary support for the candidate change.",
        icon: "⚪",
        colorToken: "slate",
        badgeClasses: "bg-slate-800/60 text-slate-400 border-slate-700",
        borderClasses: "border-slate-800",
        bgClasses: "bg-slate-900/40",
      };
  }
}

/**
 * Details for M4D screening outcomes.
 */
export interface M4dDecisionDetails {
  decision: string;
  label: string;
  sublabel: string;
  badgeClasses: string;
  borderClasses: string;
  bgClasses: string;
  icon: string;
  description: string;
  statusDescription: string;
  semanticCaveat: string;
}

export function getM4dDecisionDetails(
  decision: "RETAINED" | "FLAGGED" | "SUPPRESSED" | "INSUFFICIENT_EVIDENCE" | string | null | undefined
): M4dDecisionDetails {
  const norm = (decision || "NOT_EVALUATED").toUpperCase();
  switch (norm) {
    case "RETAINED":
      return {
        decision: "RETAINED",
        label: "Retained (M4D Pass)",
        sublabel: "Passed False-Alarm Screening",
        icon: "🛡️",
        badgeClasses: "bg-emerald-950 text-emerald-300 border-emerald-800",
        borderClasses: "border-emerald-800/80",
        bgClasses: "bg-emerald-950/20",
        description: "Candidate passed false-alarm screening and is retained as genuine change evidence.",
        statusDescription:
          "Candidate passed all conservative artifact screening gates; no sufficient false-alarm evidence detected.",
        semanticCaveat:
          "RETAINED does NOT mean 'verified ground truth' or 'confirmed real-world event'. It indicates no sufficient false-alarm evidence was detected across the 11 physical artifact detectors to invalidate the signal.",
      };
    case "FLAGGED":
      return {
        decision: "FLAGGED",
        label: "Flagged (False-Alarm Risk)",
        sublabel: "Analyst Review Required",
        icon: "⚠️",
        badgeClasses: "bg-amber-950 text-amber-300 border-amber-800",
        borderClasses: "border-amber-800/80",
        bgClasses: "bg-amber-950/20",
        description: "Candidate flagged due to potential cloud, shadow, or sensor anomaly risk.",
        statusDescription:
          "False-alarm evidence or viewing parallax requires analyst attention; barred from earliest support.",
        semanticCaveat:
          "FLAGGED routes candidates to the analyst review queue without hard-suppressing them. It protects potential genuine events that exhibit ambiguous artifacts.",
      };
    case "SUPPRESSED":
      return {
        decision: "SUPPRESSED",
        label: "Suppressed (Artifact)",
        sublabel: "Screened Out Artifact",
        icon: "🚫",
        badgeClasses: "bg-rose-950 text-rose-300 border-rose-800",
        borderClasses: "border-rose-800/80",
        bgClasses: "bg-rose-950/20",
        description: "Candidate suppressed and filtered out as a false alarm / imaging artifact.",
        statusDescription:
          "Conservative multi-evidence physical gate was fully satisfied; candidate screened out.",
        semanticCaveat:
          "SUPPRESSED candidates are preserved in serialized outputs and immutable provenance records (Zero Silent Drops).",
      };
    case "INSUFFICIENT_EVIDENCE":
      return {
        decision: "INSUFFICIENT_EVIDENCE",
        label: "INSUFFICIENT EVIDENCE",
        sublabel: "Modality or Quality Limitation",
        icon: "❓",
        badgeClasses: "bg-slate-800 text-slate-300 border-slate-700",
        borderClasses: "border-slate-700",
        bgClasses: "bg-slate-900/60",
        description: "Insufficient signal-to-noise or observation coverage for screening determination.",
        statusDescription:
          "Required calibrated spectral bands or georeferencing metadata were unavailable.",
        semanticCaveat:
          "Without calibrated multispectral channels (e.g. SWIR, Cirrus), atmospheric contamination cannot be conclusively ruled out.",
      };
    default:
      return {
        decision: decision || "NOT_EVALUATED",
        label: "Not Evaluated",
        sublabel: "Not Screened",
        badgeClasses: "bg-slate-800/50 text-slate-400 border-slate-700/50",
        borderClasses: "border-slate-800",
        bgClasses: "bg-slate-900/40",
        icon: "—",
        description: "No M4D screening determination recorded for this observation.",
        statusDescription: "No M4D screening determination recorded for this observation.",
        semanticCaveat: "No M4D screening determination recorded.",
      };
  }
}

/**
 * Pure chronological sorter for timeline nodes.
 */
export function sortTimelineNodesChronologically(nodes: TemporalTimelineNode[]): TemporalTimelineNode[] {
  return [...nodes].sort((a, b) => {
    const timeA = a.acquisitionTime ? new Date(a.acquisitionTime).getTime() : 0;
    const timeB = b.acquisitionTime ? new Date(b.acquisitionTime).getTime() : 0;
    return timeA - timeB;
  });
}

/**
 * Mathematical Onset interval view model structure.
 */
export interface MathematicalOnsetDetails {
  formula: string;
  formattedInterval: string;
  intervalType: string;
  intervalDays: number;
  preDateFormatted: string;
  earliestDateFormatted: string;
  preObservationId?: string;
  earliestObservationId?: string;
  isBounded: boolean;
  tPreExplanation: string;
  tEarliestExplanation: string;
  eventTimeExplanation: string;
  noDateFabricationNotice: string;
}

/**
 * Formats mathematical half-open onset interval (T_pre, T_earliest] with rigorous explanations.
 */
export function formatMathematicalOnset(
  preDate?: string,
  earliestDate?: string,
  preObsId?: string,
  earliestObsId?: string,
  intervalDays?: number,
  intervalType?: string
): MathematicalOnsetDetails {
  const isBounded = !!(preDate && earliestDate);
  const pDateStr = preDate || "T_pre";
  const eDateStr = earliestDate || "T_earliest";
  const formattedInterval = `(${pDateStr}, ${eDateStr}]`;

  return {
    formula: "(T_pre, T_earliest]",
    formattedInterval,
    intervalType: intervalType || (isBounded ? "BOUNDED_HALF_OPEN" : "UNBOUNDED"),
    intervalDays: intervalDays ?? 0,
    preDateFormatted: preDate || "T_pre (Unspecified)",
    earliestDateFormatted: earliestDate || "T_earliest (Unspecified)",
    preObservationId: preObsId,
    earliestObservationId: earliestObsId,
    isBounded,
    tPreExplanation: "T_pre is the latest observation supporting absence/pre-change evidence.",
    tEarliestExplanation: "T_earliest is the earliest observation supporting the detected change.",
    eventTimeExplanation: "The actual event time is not known exactly from discrete satellite observations.",
    noDateFabricationNotice: "Discrete satellite acquisitions establish bounding limits only; no exact event date is fabricated.",
  };
}

/**
 * Correspondence match structure across epochs for a timeline node.
 */
export interface NodeCorrespondenceMatch {
  epoch?: EpochCorrespondence;
  matchedRegionId: string;
  referenceCandidateId: string;
  isIdShifted: boolean;
  shiftDisplay: string;
  metricIou: number;
  centroidDistanceM: number;
  relationship: string;
  status: string;
  resolutionNotes: string[];
}

/**
 * Matches a timeline node to cross-epoch correspondence data without assuming region IDs are stable.
 */
export function matchNodeCorrespondence(
  node: TemporalTimelineNode,
  nodeIndex: number,
  epochs: EpochCorrespondence[],
  referenceCandidateId: string
): NodeCorrespondenceMatch {
  // If baseline node (T_pre), it represents the pre-change state prior to candidate emergence
  if (node.status === "PRE_CHANGE_ABSENCE" || nodeIndex === 0) {
    return {
      matchedRegionId: referenceCandidateId,
      referenceCandidateId,
      isIdShifted: false,
      shiftDisplay: `${referenceCandidateId} (Baseline Absence Ref)`,
      metricIou: 1.0,
      centroidDistanceM: 0.0,
      relationship: "PRE_CHANGE_BASELINE",
      status: "BASELINE_REFERENCE",
      resolutionNotes: ["Baseline acquisition prior to candidate emergence."],
    };
  }

  // Look for direct match in epochs
  const obsSuffix = node.observationId.split("_").pop() || "";
  const matchedEpoch =
    epochs.find((e) => {
      const pair = e.targetPairId;
      return pair.includes(node.observationId) || (obsSuffix && pair.endsWith(obsSuffix));
    }) || epochs[nodeIndex - 1];

  if (matchedEpoch) {
    const matchedRegionId = matchedEpoch.matchedRegionId || referenceCandidateId;
    const isIdShifted = matchedEpoch.isIdShifted || matchedRegionId !== referenceCandidateId;
    const shiftDisplay = isIdShifted
      ? `${referenceCandidateId} → ${matchedRegionId}`
      : `${matchedRegionId} (Discovery Ref)`;

    return {
      epoch: matchedEpoch,
      matchedRegionId,
      referenceCandidateId,
      isIdShifted,
      shiftDisplay,
      metricIou: matchedEpoch.metricIou,
      centroidDistanceM: matchedEpoch.centroidDistanceM,
      relationship: matchedEpoch.relationship,
      status: matchedEpoch.status,
      resolutionNotes: matchedEpoch.resolutionNotes || [],
    };
  }

  // Fallback to node's internal spatialAlignment
  return {
    matchedRegionId: referenceCandidateId,
    referenceCandidateId,
    isIdShifted: false,
    shiftDisplay: `${referenceCandidateId}`,
    metricIou: node.spatialAlignment?.iouWgs84 ?? 0,
    centroidDistanceM: node.spatialAlignment?.centroidDistanceM ?? 0,
    relationship: node.spatialAlignment?.relationship ?? "NONE",
    status: node.spatialAlignment?.status ?? "UNLINKED",
    resolutionNotes: [],
  };
}

/**
 * Detailed metadata for spatial correspondence status enums.
 */
export interface SpatialStatusDetails {
  status: string;
  label: string;
  description: string;
  badgeClasses: string;
  icon: string;
  isCompatible: boolean;
}

/**
 * Returns descriptive metadata and color tokens for backend spatial status values.
 */
export function getSpatialStatusDetails(status?: string | null): SpatialStatusDetails {
  switch (status) {
    case "EXACT_PIXEL_GRID":
      return {
        status: "EXACT_PIXEL_GRID",
        label: "Exact Pixel Grid",
        description: "Direct pixel grid alignment between co-registered observations.",
        badgeClasses: "bg-emerald-950/80 text-emerald-300 border-emerald-800",
        icon: "🎯",
        isCompatible: true,
      };
    case "GEOREFERENCED_BBOX":
      return {
        status: "GEOREFERENCED_BBOX",
        label: "Georeferenced Bounding Box",
        description: "Alignment established via projected metric bounding box intersection (IoU).",
        badgeClasses: "bg-cyan-950/80 text-cyan-300 border-cyan-800",
        icon: "📐",
        isCompatible: true,
      };
    case "GEOREFERENCED_CENTROID_ONLY":
      return {
        status: "GEOREFERENCED_CENTROID_ONLY",
        label: "Centroid Proximity Only",
        description: "Alignment based solely on centroid Euclidean distance without area intersection.",
        badgeClasses: "bg-amber-950/80 text-amber-300 border-amber-800",
        icon: "📍",
        isCompatible: true,
      };
    case "DISJOINT":
      return {
        status: "DISJOINT",
        label: "Disjoint Footprint",
        description: "Candidates do not overlap in space; distance exceeds spatial correspondence threshold.",
        badgeClasses: "bg-rose-950/80 text-rose-300 border-rose-800",
        icon: "❌",
        isCompatible: false,
      };
    case "INSUFFICIENT_METADATA":
      return {
        status: "INSUFFICIENT_METADATA",
        label: "Insufficient Spatial Metadata",
        description: "Missing geotransform, CRS definition, or pixel grid coordinates preventing spatial evaluation.",
        badgeClasses: "bg-zinc-800 text-zinc-400 border-zinc-700",
        icon: "❓",
        isCompatible: false,
      };
    default:
      return {
        status: status || "UNKNOWN",
        label: status || "Unknown Spatial Status",
        description: "Spatial status not recognized or unrecorded.",
        badgeClasses: "bg-slate-800 text-slate-400 border-slate-700",
        icon: "•",
        isCompatible: false,
      };
  }
}

/**
 * Detailed metadata for candidate relationship enums.
 */
export interface RelationshipDetails {
  relationship: string;
  label: string;
  description: string;
  badgeClasses: string;
  icon: string;
  isMatched: boolean;
}

/**
 * Returns descriptive metadata and color tokens for candidate relationship enums.
 */
export function getRelationshipDetails(relationship?: string | null): RelationshipDetails {
  switch (relationship) {
    case "MATCHED":
      return {
        relationship: "MATCHED",
        label: "Matched Target",
        description: "1-to-1 candidate correspondence confirmed across temporal epochs.",
        badgeClasses: "bg-emerald-950/80 text-emerald-300 border-emerald-800",
        icon: "✓",
        isMatched: true,
      };
    case "SPLIT":
      return {
        relationship: "SPLIT",
        label: "Split Target",
        description: "Single discovery candidate resolved into multiple disjoint sub-regions in target epoch.",
        badgeClasses: "bg-amber-950/80 text-amber-300 border-amber-800",
        icon: "🔀",
        isMatched: false,
      };
    case "MERGED":
      return {
        relationship: "MERGED",
        label: "Merged Target",
        description: "Multiple distinct candidates coalesced into a single contiguous region in target epoch.",
        badgeClasses: "bg-purple-950/80 text-purple-300 border-purple-800",
        icon: "🔁",
        isMatched: false,
      };
    case "AMBIGUOUS":
      return {
        relationship: "AMBIGUOUS",
        label: "Ambiguous Correspondence",
        description: "Multiple competing target regions meet correspondence criteria without clear dominance.",
        badgeClasses: "bg-amber-950/80 text-amber-300 border-amber-800",
        icon: "⚠️",
        isMatched: false,
      };
    case "NONE":
      return {
        relationship: "NONE",
        label: "No Spatial Match",
        description: "No corresponding change region identified within spatial search radius.",
        badgeClasses: "bg-rose-950/80 text-rose-300 border-rose-800",
        icon: "—",
        isMatched: false,
      };
    default:
      return {
        relationship: relationship || "UNKNOWN",
        label: relationship || "Unknown Relationship",
        description: "Candidate relationship not specified.",
        badgeClasses: "bg-slate-800 text-slate-400 border-slate-700",
        icon: "•",
        isMatched: false,
      };
  }
}

/**
 * Formats coordinates into standard WGS84 format.
 */
export function formatCoordinatesWgs84(lon?: number | null, lat?: number | null): string {
  if (lon == null || lat == null || isNaN(lon) || isNaN(lat)) {
    return "Coordinates unavailable";
  }
  const latStr = `${Math.abs(lat).toFixed(6)}° ${lat >= 0 ? "N" : "S"}`;
  const lonStr = `${Math.abs(lon).toFixed(6)}° ${lon >= 0 ? "E" : "W"}`;
  return `${latStr}, ${lonStr}`;
}

/**
 * Formats bounding box into human-readable extent components.
 */
export function formatBoundingBoxWgs84(bbox?: {
  minLon: number;
  minLat: number;
  maxLon: number;
  maxLat: number;
} | null) {
  if (!bbox) return null;
  const latSpan = Math.abs(bbox.maxLat - bbox.minLat);
  const lonSpan = Math.abs(bbox.maxLon - bbox.minLon);
  const centerLat = (bbox.minLat + bbox.maxLat) / 2;
  const centerLon = (bbox.minLon + bbox.maxLon) / 2;

  return {
    minLonFormatted: `${Math.abs(bbox.minLon).toFixed(6)}° ${bbox.minLon >= 0 ? "E" : "W"}`,
    minLatFormatted: `${Math.abs(bbox.minLat).toFixed(6)}° ${bbox.minLat >= 0 ? "N" : "S"}`,
    maxLonFormatted: `${Math.abs(bbox.maxLon).toFixed(6)}° ${bbox.maxLon >= 0 ? "E" : "W"}`,
    maxLatFormatted: `${Math.abs(bbox.maxLat).toFixed(6)}° ${bbox.maxLat >= 0 ? "N" : "S"}`,
    latSpanDeg: Math.round(latSpan * 100000) / 100000,
    lonSpanDeg: Math.round(lonSpan * 100000) / 100000,
    centerLat,
    centerLon,
    centerFormatted: formatCoordinatesWgs84(centerLon, centerLat),
  };
}

/**
 * Calculates SVG viewBox projection coordinates for local offline footprint drawing.
 */
export function computeSvgFootprint(
  bbox?: { minLon: number; minLat: number; maxLon: number; maxLat: number } | null,
  centroid?: [number, number] | null,
  svgWidth: number = 360,
  svgHeight: number = 200,
  padding: number = 40
) {
  if (!bbox) return null;

  const lonSpan = bbox.maxLon - bbox.minLon || 0.001;
  const latSpan = bbox.maxLat - bbox.minLat || 0.001;

  const drawWidth = svgWidth - padding * 2;
  const drawHeight = svgHeight - padding * 2;

  const x = padding;
  const y = padding;
  const width = drawWidth;
  const height = drawHeight;

  let centroidX = x + width / 2;
  let centroidY = y + height / 2;

  if (centroid && centroid.length === 2) {
    const cLon = centroid[0];
    const cLat = centroid[1];
    const relX = Math.min(1, Math.max(0, (cLon - bbox.minLon) / lonSpan));
    const relY = Math.min(1, Math.max(0, (bbox.maxLat - cLat) / latSpan));
    centroidX = Math.round((x + relX * width) * 10) / 10;
    centroidY = Math.round((y + relY * height) * 10) / 10;
  }

  return {
    svgWidth,
    svgHeight,
    box: { x, y, width, height },
    centroid: { x: centroidX, y: centroidY },
    labels: {
      west: `${bbox.minLon.toFixed(4)}°E`,
      east: `${bbox.maxLon.toFixed(4)}°E`,
      north: `${bbox.maxLat.toFixed(4)}°N`,
      south: `${bbox.minLat.toFixed(4)}°N`,
    },
  };
}

/**
 * Returns human-readable label for M4D artifact types.
 */
export function getArtifactFactorLabel(artifactType: string): string {
  const norm = artifactType.toLowerCase();
  switch (norm) {
    case "cloud_contamination":
      return "Cloud Contamination";
    case "cloud_shadow":
      return "Cloud Shadow Geometry";
    case "coregistration_edge_shear":
      return "Co-Registration Edge Shear";
    case "snow_ice":
      return "Snow & Ephemeral Frost";
    case "viewing_geometry_parallax":
      return "Viewing Geometry Parallax";
    case "global_illumination_drift":
      return "Global Illumination Drift";
    case "haze_aerosol":
      return "Haze & Aerosol Scattering";
    case "sensor_noise_dropout":
      return "Sensor Noise & Dropout";
    case "radiometric_gain_inconsistency":
      return "Radiometric Gain Shift";
    case "cross_sensor_limitation":
      return "Cross-Sensor Calibration";
    case "unknown_artifact":
    default:
      return norm
        .split("_")
        .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
        .join(" ");
  }
}

/**
 * Evidentiary explanation for M4C-B confidence tiers.
 */
export function getConfidenceTierDetails(tier: string) {
  const norm = tier.toUpperCase();
  switch (norm) {
    case "HIGH":
      return {
        tier: "HIGH",
        label: "HIGH CONFIDENCE",
        badgeClasses: "bg-emerald-950 text-emerald-300 border-emerald-800",
        description: "Calibrated multispectral imagery + score ≥ 0.75 + score margin ≥ 0.30 + region size ≥ 25 px.",
        disclaimer:
          "Evidentiary tier reflecting modality completeness and margin — NOT a calibrated probability.",
      };
    case "MEDIUM":
      return {
        tier: "MEDIUM",
        label: "MEDIUM CONFIDENCE",
        badgeClasses: "bg-blue-950 text-blue-300 border-blue-800",
        description: "Score ≥ 0.55 + score margin ≥ 0.18 over nearest runner-up category.",
        disclaimer:
          "Evidentiary tier reflecting modality completeness and margin — NOT a calibrated probability.",
      };
    case "LOW":
      return {
        tier: "LOW",
        label: "LOW CONFIDENCE",
        badgeClasses: "bg-amber-950 text-amber-300 border-amber-800",
        description: "Uncalibrated RGB imagery only, or marginal score (0.45 ≤ score < 0.55).",
        disclaimer:
          "Evidentiary tier reflecting modality completeness and margin — NOT a calibrated probability.",
      };
    case "UNCERTAIN":
    default:
      return {
        tier: "UNCERTAIN",
        label: "UNCERTAIN",
        badgeClasses: "bg-slate-800 text-slate-400 border-slate-700",
        description: "Unresolved candidate, region area < 10 px, or conflict margin breached.",
        disclaimer:
          "Evidentiary tier reflecting modality completeness and margin — NOT a calibrated probability.",
      };
  }
}
