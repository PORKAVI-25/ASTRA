# ASTRA Analyst Dashboard Data Model (Phase M4F-F)

## 1. Architectural Principles

1. **Clean Separation of Concerns**:
   - The frontend is a **presentation and audit client**. It does NOT execute change detection, spectral math, suppression rules, or temporal reasoning.
   - Domain logic remains strictly in the Python backend.
2. **Contract-Driven Transformations**:
   - The frontend consumes backend responses conforming to `ASTRA-DC-v0.1` and maps them into safe, localized **View Models**.
3. **Type Safety & Immutability**:
   - All models are defined in strict TypeScript with explicit nullability.
4. **Air-Gapped Offline Integrity**:
   - Models represent discrete, local entities without external URLs or third-party cloud references.

---

## 2. Core View Model Definitions

### 2.1 `TemporalSeriesSummary` & `TemporalObservationSummary`

Represents a temporal satellite imagery sequence and its constituent chronological acquisitions for UI selection and filtering.

```typescript
export interface TemporalObservationSummary {
  observationId: string;
  sceneId: string;
  tileId: string;
  acquisitionTime: string; // ISO 8601 UTC
  displayDate: string;     // Formatted (e.g., "Jan 15, 2026")
  sensor: string;          // e.g., "MSI"
  platform: string;        // e.g., "Sentinel-2A"
  cloudCoverPct: number;   // 0.0 - 100.0
  isSynthetic: boolean;
  filePath: string;
}

export interface TemporalSeriesSummary {
  seriesId: string;
  gridCellId: string;
  observationCount: number;
  startDate: string;       // Formatted UTC string
  endDate: string;         // Formatted UTC string
  timespanDays: number;
  sensors: string[];       // Unique sensors present
  observations: TemporalObservationSummary[];
}
```

### 2.2 `ScenePairSummary`

Represents an evaluated or candidate pairing between two temporal observations.

```typescript
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
  pairingMethod: "baseline_t0" | "adjacent" | "all_pairwise" | string;
  isCompatible: boolean;
  rejectionReasons: string[];
}
```

### 2.3 `CandidateChange`

Represents a localized candidate change region discovered in a scene pair (from M4B `ChangeDetectionResult`).

```typescript
export interface CandidateBoundingBox {
  minRow: number;
  minCol: number;
  maxRow: number;
  maxCol: number;
  widthPx: number;
  heightPx: number;
}

export interface GeoCoordinate {
  lon: number;
  lat: number;
}

export interface CandidateChange {
  regionId: string;            // e.g., "reg_0001", "reg_0002"
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
  meanChangeScore: number;     // 0.0 - 1.0
  maxChangeScore: number;      // 0.0 - 1.0
  isTargetCandidate?: boolean; // Highlighted target for demo
}
```

### 2.4 `InvestigationRequest`

Form payload passed from dashboard to backend to initiate multi-temporal orchestration.

```typescript
export interface InvestigationRequest {
  series_id: string;
  discovery_pair_id: string;
  candidate_region_id: string;
  pairing_strategy?: "adjacent" | "baseline";
  output_dir?: string | null;
  change_detection_config?: Record<string, unknown> | null;
  evidence_config?: Record<string, unknown> | null;
  classifier_config?: Record<string, unknown> | null;
  suppression_config?: Record<string, unknown> | null;
  temporal_evidence_config?: Record<string, unknown> | null;
  requested_format?: "json";
}
```

### 2.5 `TemporalTimelineNode`

Presentation model for each chronological epoch evaluated across the candidate's trajectory.

```typescript
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
  status: string;              // "EXACT_PIXEL_GRID", "GEOREFERENCED_BBOX", etc.
  relationship: "MATCHED" | "SPLIT" | "MERGED" | "AMBIGUOUS" | "NONE";
  isCompatible: boolean;
  iouWgs84: number;            // 0.0 - 1.0
  centroidDistanceM?: number;  // Meters
  centroidDistancePx?: number; // Pixels
}

export interface TemporalTimelineNode {
  observationId: string;
  acquisitionTime: string;     // ISO 8601 UTC
  displayDate: string;         // e.g., "Feb 15, 2026"
  sensor: string;
  platform: string;
  status: NodeStatusType;
  statusColor: "emerald" | "blue" | "amber" | "rose" | "slate";
  m4dDecision: "RETAINED" | "FLAGGED" | "SUPPRESSED" | "INSUFFICIENT_EVIDENCE" | null;
  supportScore: number;        // 0.00 - 1.00 (M4E uncalibrated heuristic)
  isEarliestSupportEligible: boolean;
  categoryObserved?: string;   // e.g., "construction", "vegetation_loss"
  categoryConfidence?: "high" | "medium" | "low" | "uncertain";
  spatialAlignment: SpatialAlignmentMetrics;
  isCrossSensor: boolean;
  reasons: string[];
  limitations: string[];
}
```

### 2.6 `SuppressionSummary`

Summarizes false-alarm screening results across the evaluated epochs.

```typescript
export interface EpochSuppressionMetrics {
  pairId: string;
  retainedCount: number;
  flaggedCount: number;
  suppressedCount: number;
  candidateDecision: "RETAINED" | "FLAGGED" | "SUPPRESSED" | "NOT_EVALUATED";
  primaryRiskReason?: string;
}

export interface SuppressionSummary {
  overallScreeningOutcome: "PASS" | "FLAGGED_RISK" | "SUPPRESSED";
  totalEpochsRetained: number;
  totalEpochsFlagged: number;
  totalEpochsSuppressed: number;
  perEpochBreakdown: EpochSuppressionMetrics[];
}
```

### 2.7 `SpatialCorrespondenceSummary`

Tracks topological correspondence and region ID shifts across epochs.

```typescript
export interface EpochCorrespondence {
  targetPairId: string;
  targetEpochDate: string;
  referenceCandidateId: string; // Discovery candidate ID (e.g. "reg_0002")
  matchedRegionId?: string;     // Resolved region ID in this epoch (e.g. "reg_0001")
  isIdShifted: boolean;         // True if matchedRegionId !== referenceCandidateId
  status: string;               // "EXACT_REFERENCE", "GEOREFERENCED_BBOX"
  relationship: "MATCHED" | "SPLIT" | "MERGED" | "AMBIGUOUS" | "NONE";
  metricIou: number;            // Bounding box IoU
  centroidDistanceM: number;    // Distance in meters
  resolutionNotes: string[];
}

export interface SpatialCorrespondenceSummary {
  referenceCandidateId: string;
  epochs: EpochCorrespondence[];
  averageIou: number;
  maxCentroidDriftM: number;
  isStable: boolean;
}
```

### 2.8 `ProvenanceSummary`

Cryptographic lineage and chain-of-custody model.

```typescript
export interface StageExecutionSummary {
  stage: string;
  status: "COMPLETED" | "FAILED" | "SKIPPED" | "RUNNING";
  artifactId?: string;
  provenanceId?: string;
  durationMs?: number;
  details: Record<string, unknown>;
}

export interface ProvenanceSummary {
  investigationId: string;
  investigationProvenanceId: string;
  temporalEvidenceProvenanceId?: string;
  contentHash: string;
  createdAt: string;
  upstreamHashes: Record<string, string>; // path/artifact -> SHA-256
  stages: StageExecutionSummary[];
  isVerified: boolean;
}
```

### 2.9 `InvestigationSummary` (Complete View Model)

Root aggregation model for the Investigation Dossier presentation.

```typescript
export interface InvestigationSummary {
  investigationId: string;
  status: "COMPLETED" | "FAILED";
  seriesId: string;
  discoveryPairId: string;
  candidateRegionId: string;
  pairingStrategy: string;
  createdAt: string;
  contentHash: string;

  // Executive Trajectory
  supportStatus: string;       // "STRONG_TEMPORAL_SUPPORT", etc.
  confidenceTier: "high" | "medium" | "low" | "uncertain";

  // Onset Bounding
  onset: {
    intervalType: string;      // "BOUNDED_HALF_OPEN", etc.
    displaySpan: string;       // "[2026-01-15, 2026-02-15]"
    physicalInterval: string;  // "(2026-01-15, 2026-02-15]"
    intervalDays: number;
    preChangeDate?: string;
    earliestSupportDate?: string;
    limitationNotice: string;
  };

  // Semantic Progression
  category: {
    primary: string;           // "construction"
    trajectory: string[];      // ["construction", "construction"]
    isValid: boolean;
    isConflicted: boolean;
    notes: string[];
  };

  // Detailed Panels
  timelineNodes: TemporalTimelineNode[];
  spatialCorrespondence: SpatialCorrespondenceSummary;
  suppression: SuppressionSummary;
  provenance: ProvenanceSummary;
  decisionReasons: string[];
  evidenceLimitations: string[];
  changeMaskResultId?: string; // CDR ID for loading /mask PNG
}
```

### 2.10 `AnalystReview`

Audit trail record capturing human analyst review and triage decisions.

```typescript
export type ReviewDecision = "CONFIRM" | "REJECT" | "FLAG_NEEDS_REVIEW";

export interface AnalystReview {
  reviewId: string;
  investigationId: string;
  candidateRegionId: string;
  decision: ReviewDecision;
  analystId: string;           // e.g., "analyst_porkavi" or "current_user"
  timestamp: string;           // ISO 8601 UTC
  comments: string;
  categoryOverride?: string;   // Optional manual override
  confidenceRating?: number;   // 1 - 5 stars
  auditHash: string;           // SHA-256 of review content
}
```

### 2.11 `DashboardState`

Root state container for the single-page application.

```typescript
export interface DashboardState {
  // Navigation & Telemetry
  isConnected: boolean;
  offlineMode: boolean;
  version: string;
  activeTab: "explore" | "investigate" | "dossier" | "reviews";

  // Catalog & Selection State
  seriesList: TemporalSeriesSummary[];
  selectedSeries: TemporalSeriesSummary | null;
  availablePairs: ScenePairSummary[];
  selectedPair: ScenePairSummary | null;
  candidateRegions: CandidateChange[];
  selectedCandidate: CandidateChange | null;

  // Pipeline Execution State
  isInvestigating: boolean;
  investigationStage: string;  // Simulated stage during run
  investigationError: string | null;

  // Active Dossier
  activeDossier: InvestigationSummary | null;

  // Analyst Reviews Store
  reviews: AnalystReview[];

  // UI Preferences
  showRawJson: boolean;
  activeNodeId: string | null; // For timeline inspection
}
```

---

## 3. Transformation Functions Blueprint

Transforming backend contracts into view models is localized in `frontend/src/services/transformers.ts`:

```typescript
/**
 * Maps raw TemporalSeries API contract into frontend TemporalSeriesSummary.
 */
export function transformTemporalSeries(raw: any): TemporalSeriesSummary {
  // Pure mapping without business logic re-execution
}

/**
 * Maps raw InvestigationDossier API response into frontend InvestigationSummary.
 */
export function transformInvestigationDossier(raw: any): InvestigationSummary {
  // Flattens nested temporal evidence, spatial correspondence, and lineage
}

/**
 * Computes client-side review audit hash for an AnalystReview.
 */
export function createAnalystReviewRecord(
  investigationId: string,
  candidateRegionId: string,
  decision: ReviewDecision,
  comments: string,
  analystId: string = "analyst_local"
): AnalystReview {
  // Generates unique reviewId and timestamp
}
```
