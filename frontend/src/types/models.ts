/**
 * ASTRA Frontend Presentation View Models
 *
 * Clean, decoupled presentation models optimized for UI rendering.
 * Does NOT contain ML business logic.
 * Authoritative reference: docs/dashboard-data-model.md
 */

export interface TemporalObservationSummary {
  observationId: string;
  sceneId: string;
  tileId: string;
  acquisitionTime: string; // ISO 8601 UTC
  displayDate: string;     // Formatted (e.g., "Jan 15, 2026")
  displayDateTime: string; // Formatted with time
  sensor: string;          // e.g., "MSI"
  platform: string;        // e.g., "Sentinel-2A"
  crs: string;
  boundsWgs84: {
    minLon: number;
    minLat: number;
    maxLon: number;
    maxLat: number;
  };
  cloudCoverPct: number;   // 0.0 - 100.0
  validPixelRatio?: number; // 0.0 - 1.0
  isSynthetic: boolean;
  filePath?: string;
  sourceHash?: string;
  metadata?: Record<string, unknown>;
}

export interface TemporalSeriesSummary {
  seriesId: string;
  targetId: string;
  gridCellId: string;
  observationCount: number;
  startDate: string;       // Formatted UTC string
  endDate: string;         // Formatted UTC string
  timespanDays: number;
  sensors: string[];       // Unique sensors present
  platforms: string[];     // Unique platforms present
  boundsWgs84?: {
    minLon: number;
    minLat: number;
    maxLon: number;
    maxLat: number;
  };
  observations: TemporalObservationSummary[];
}

export interface ScenePairSummary {
  pairId: string;
  seriesId: string;
  earlierObservationId: string;
  earlierDate: string;
  earlierPlatform: string;
  laterObservationId: string;
  laterDate: string;
  laterPlatform: string;
  temporalBaselineDays: number;
  pairingMethod: string;
  isCompatible: boolean;
  rejectionReasons: string[];
}

export interface CandidateBoundingBox {
  minRow: number;
  minCol: number;
  maxRow: number;
  maxCol: number;
  widthPx: number;
  heightPx: number;
}

export interface CandidateChange {
  regionId: string;
  discoveryPairId: string;
  pixelCount: number;
  areaPx: number;
  areaM2?: number;
  bboxPx: CandidateBoundingBox;
  bboxWgs84?: {
    minLon: number;
    minLat: number;
    maxLon: number;
    maxLat: number;
  };
  centroidPx: [number, number];
  centroidWgs84?: [number, number];
  meanChangeScore: number;
  maxChangeScore: number;
  isTargetCandidate?: boolean;
}

export interface CandidateFootprintFeatures {
  area?: number;
  widthPx?: number;
  heightPx?: number;
  width_px?: number;
  height_px?: number;
  aspectRatio?: number;
  aspect_ratio?: number;
  perimeterPx?: number;
  perimeter_px?: number;
  compactness?: number;
  rectangularity?: number;
  elongation?: number;
  orientationDeg?: number;
  orientation_deg?: number;
  centroid?: [number, number];
  boundaryDistancePx?: number;
  boundary_distance_px?: number;
  regionDensity?: number;
  region_density?: number;
  fragmentation?: number;
  [key: string]: unknown;
}

export interface CandidateFootprint {
  regionId: string;
  discoveryPairId: string;
  pixelCount?: number;
  areaPx?: number;
  areaM2?: number;
  bboxPx?: CandidateBoundingBox;
  bboxWgs84?: {
    minLon: number;
    minLat: number;
    maxLon: number;
    maxLat: number;
  };
  centroidPx?: [number, number];
  centroidWgs84?: [number, number];
  features?: CandidateFootprintFeatures;
  spatialStatus?: string;
  crs?: string;
}

export type NodeStatusType =
  | "PRE_CHANGE_ABSENCE"
  | "EARLIEST_SUPPORTING"
  | "PERSISTENT_SUPPORT"
  | "FLAGGED_SUPPORT"
  | "SUPPRESSED_ARTIFACT"
  | "NO_SUPPORT"
  | "INSUFFICIENT_DATA"
  | "SIMULTANEOUS_CO_TEMPORAL";

export interface SpatialAlignmentMetrics {
  status: string;
  relationship: "MATCHED" | "SPLIT" | "MERGED" | "AMBIGUOUS" | "NONE" | string;
  isCompatible: boolean;
  iouWgs84: number;
  centroidDistanceM?: number;
  centroidDistancePx?: number;
}

export interface TemporalTimelineNode {
  observationId: string;
  acquisitionTime: string;
  displayDate: string;
  sensor: string;
  platform: string;
  status: NodeStatusType;
  statusColor: "emerald" | "blue" | "amber" | "rose" | "slate";
  m4dDecision: "RETAINED" | "FLAGGED" | "SUPPRESSED" | "INSUFFICIENT_EVIDENCE" | null;
  supportScore: number;
  isEarliestSupportEligible: boolean;
  categoryObserved?: string;
  categoryConfidence?: "high" | "medium" | "low" | "uncertain";
  spatialAlignment: SpatialAlignmentMetrics;
  isCrossSensor: boolean;
  reasons: string[];
  limitations: string[];
}

export interface EpochSuppressionMetrics {
  pairId: string;
  retainedCount: number;
  flaggedCount: number;
  suppressedCount: number;
  candidateDecision: "RETAINED" | "FLAGGED" | "SUPPRESSED" | "INSUFFICIENT_EVIDENCE" | "NOT_EVALUATED";
  primaryRiskReason?: string;
}

export interface SuppressionSummary {
  overallScreeningOutcome: "PASS" | "FLAGGED_RISK" | "SUPPRESSED";
  totalEpochsRetained: number;
  totalEpochsFlagged: number;
  totalEpochsSuppressed: number;
  perEpochBreakdown: EpochSuppressionMetrics[];
}

export interface EpochCorrespondence {
  targetPairId: string;
  targetEpochDate: string;
  referenceCandidateId: string;
  matchedRegionId?: string;
  isIdShifted: boolean;
  status: string;
  relationship: "MATCHED" | "SPLIT" | "MERGED" | "AMBIGUOUS" | "NONE" | string;
  metricIou: number;
  centroidDistanceM: number;
  resolutionNotes: string[];
}

export interface SpatialCorrespondenceSummary {
  referenceCandidateId: string;
  epochs: EpochCorrespondence[];
  averageIou: number;
  maxCentroidDriftM: number;
  isStable: boolean;
}

export interface StageExecutionSummary {
  stage: string;
  status: "COMPLETED" | "FAILED" | "SKIPPED" | "RUNNING" | "PENDING";
  artifactId?: string;
  provenanceId?: string;
  details: Record<string, unknown>;
  timestamp?: string;
}

export interface UpstreamArtifactRecord {
  stageId: string; // e.g., "M1", "M4B", "M4C-A", "M4C-B", "M4D", "M4E", "M4F"
  stageName: string;
  artifactId: string;
  artifactType: string;
  provenanceId?: string;
  hash?: string;
  sourcePairId?: string;
  status: string;
  timestamp?: string;
  outputPath?: string;
  details?: Record<string, unknown>;
}

export interface EpochLineageRecord {
  pairId: string;
  earlierSceneId?: string;
  laterSceneId?: string;
  changeDetectionResultId?: string;
  evidenceId?: string;
  classificationId?: string;
  suppressionId?: string;
  matchedRegionId?: string;
  metricIou?: number;
  centroidDistanceM?: number;
  relationship?: string;
  isIdShifted?: boolean;
}

export interface LineageCompleteness {
  status: "COMPLETE" | "PARTIAL" | "INSUFFICIENT";
  label: string;
  description: string;
  missingReferences: string[];
  presentCount: number;
  totalExpected: number;
}

export interface ProvenanceSummary {
  investigationId: string;
  investigationProvenanceId: string;
  temporalEvidenceProvenanceId?: string;
  contentHash: string;
  createdAt: string;
  upstreamHashes: Record<string, string>;
  stages: StageExecutionSummary[];
  isVerified: boolean;
  scenePairIds?: string[];
  changeDetectionResultIds?: string[];
  evidenceIds?: string[];
  classificationIds?: string[];
  suppressionIds?: string[];
  temporalEvidenceId?: string;
  artifacts?: UpstreamArtifactRecord[];
  epochLineage?: EpochLineageRecord[];
  completeness?: LineageCompleteness;
}

export interface RuleEvaluationSummary {
  ruleId: string;
  category: string;
  matched: boolean;
  weight?: number;
  scoreContribution?: number;
  description: string;
  evidenceUsed?: Record<string, unknown>;
}

export interface SpectralEvidenceSummary {
  available: boolean;
  unavailabilityReason?: string;
  hasWavelengthMetadata: boolean;
  ndviMean?: { value?: number; available: boolean; reason?: string };
  ndwiMean?: { value?: number; available: boolean; reason?: string };
  waterSpectralCriterionFraction?: { value?: number; available: boolean };
  vegetationProxyDelta?: { value?: number; available: boolean };
  brightnessDelta?: { value?: number; available: boolean };
  bandNames: string[];
  earlierMeanPerBand: Record<string, number>;
  laterMeanPerBand: Record<string, number>;
  deltaPerBand: Record<string, number>;
}

export interface ArtifactFactorSummary {
  artifactType: string;
  label: string;
  detected: boolean;
  artifactScore: number;
  weight?: number;
  hardTriggered: boolean;
  description: string;
  metricsUsed?: Record<string, unknown>;
  status: "CLEAR" | "RISK_DETECTED" | "HARD_TRIGGERED" | "DATA_LIMITATION" | "UNAVAILABLE";
}

export interface CandidateClassificationEvidence {
  regionId: string;
  category: string;
  confidenceTier: "high" | "medium" | "low" | "uncertain";
  evidenceScore?: number;
  decisionReason: string;
  isAmbiguous: boolean;
  conflictingCategories: string[];
  candidateScores: Record<string, number>;
  ruleEvaluations: RuleEvaluationSummary[];
  dataLimitations: string[];
  morphologicalFeatures?: CandidateFootprintFeatures;
  spectralEvidence?: SpectralEvidenceSummary;
  contextEvidence?: {
    available: boolean;
    unavailabilityReason?: string;
    neighborhoodBufferPx?: number;
    surroundingMeanChange?: number;
    regionToBackgroundContrast?: number;
  };
  sourceArtifactId?: string;
  provenanceId?: string;
}

export interface CandidateSuppressionEvidence {
  regionId: string;
  decision: "RETAINED" | "FLAGGED" | "SUPPRESSED" | "INSUFFICIENT_EVIDENCE";
  artifactRiskScore: number;
  artifactRiskInterpretation: string;
  decisionBasis: string;
  decisionReasons: string[];
  primaryAttribution?: string;
  contributingArtifacts: string[];
  hardTriggered: boolean;
  dataLimitations: string[];
  artifactFactors: ArtifactFactorSummary[];
  sourceArtifactId?: string;
  provenanceId?: string;
  filteredMaskPath?: string;
}

export interface InvestigationSummary {
  investigationId: string;
  status: "COMPLETED" | "FAILED";
  seriesId: string;
  discoveryPairId: string;
  candidateRegionId: string;
  pairingStrategy: string;
  createdAt: string;
  contentHash: string;

  supportStatus: string;
  confidenceTier: "high" | "medium" | "low" | "uncertain";

  onset: {
    intervalType: string;
    displaySpan: string;
    physicalInterval: string;
    intervalDays: number;
    preChangeObservationId?: string;
    earliestSupportObservationId?: string;
    preChangeDate?: string;
    earliestSupportDate?: string;
    limitationNotice: string;
  };

  category: {
    primary: string;
    trajectory: string[];
    isValid: boolean;
    isConflicted: boolean;
    notes: string[];
  };

  timelineNodes: TemporalTimelineNode[];
  spatialCorrespondence: SpatialCorrespondenceSummary;
  candidateFootprint?: CandidateFootprint;
  classificationEvidence?: CandidateClassificationEvidence;
  suppressionEvidence?: CandidateSuppressionEvidence;
  suppression: SuppressionSummary;
  provenance: ProvenanceSummary;
  decisionReasons: string[];
  evidenceLimitations: string[];
  changeMaskResultId?: string;
  analystReview?: AnalystReviewRecord;
}

export type ReviewDecision =
  | "PENDING"
  | "CONFIRMED"
  | "REJECTED"
  | "CONFIRM"
  | "REJECT"
  | "FLAG_NEEDS_REVIEW";

export interface AnalystReviewRecord {
  reviewId: string;
  investigationId: string;
  candidateRegionId: string;
  seriesId: string;
  discoveryPairId: string;
  createdAt: string;
  updatedAt: string;
  decision: ReviewDecision;
  analystId: string;
  analystNote: string;
  selectedReason: string;
  reasonCode: string;
  previousDecision?: string;
  revisionNumber: number;
  auditHash: string;
  // Compatibility fields for D4
  comments?: string;
  timestamp?: string;
  categoryOverride?: string;
  confidenceRating?: number;
}

export type AnalystReview = AnalystReviewRecord;

export interface ReviewHistoryExport {
  schemaVersion: "astra_review_v2";
  exportedAt: string;
  investigationId: string;
  candidateRegionId: string;
  seriesId?: string;
  discoveryPairId?: string;
  currentDecision: ReviewDecision;
  latestRevisionNumber: number;
  totalRevisions: number;
  currentAuditHash: string;
  revisions: AnalystReviewRecord[];
}

export type AsyncStatus = "idle" | "loading" | "success" | "error";

export interface AsyncState<T> {
  status: AsyncStatus;
  data: T | null;
  error: string | null;
  errorCode?: string;
}

export interface DashboardState {
  isConnected: boolean;
  offlineMode: boolean;
  version: string;
  activeTab: "explore" | "investigate" | "dossier" | "reviews";

  seriesList: TemporalSeriesSummary[];
  selectedSeries: TemporalSeriesSummary | null;
  availablePairs: ScenePairSummary[];
  selectedPair: ScenePairSummary | null;
  candidateRegions: CandidateChange[];
  selectedCandidate: CandidateChange | null;

  isInvestigating: boolean;
  investigationStage: string;
  investigationError: string | null;

  activeDossier: InvestigationSummary | null;
  reviews: AnalystReview[];

  showRawJson: boolean;
  activeNodeId: string | null;
}
