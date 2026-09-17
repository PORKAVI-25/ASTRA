/**
 * ASTRA Backend API Data Contracts (ASTRA-DC-v0.1)
 *
 * Strict TypeScript mirrors of backend Pydantic models.
 * Preserves exact snake_case fields as emitted by FastAPI endpoints.
 * Authoritative reference: docs/dashboard-contract.md
 */

export interface ApiErrorDetail {
  error: string;
  message: string;
  details?: Record<string, unknown>;
  stage?: string;
  stage_result?: Record<string, unknown> | null;
}

export interface GeoBoundingBox {
  min_lon: number;
  min_lat: number;
  max_lon: number;
  max_lat: number;
}

export interface HealthResponse {
  status: string;
  version: string;
  service: string;
  timestamp: string;
  environment: string;
  offline_mode: boolean;
  modules: Record<string, string>;
}

export interface TemporalObservation {
  observation_id: string;
  scene_id: string;
  tile_id?: string | null;
  acquisition_time: string;
  sensor: string;
  platform: string;
  crs: string;
  bounds_wgs84: GeoBoundingBox;
  source_hash?: string;
  file_path?: string | null;
  provenance_reference?: string | null;
  is_synthetic?: boolean;
  spatial_resolution_m?: number;
  cloud_cover_percentage?: number;
  bands?: string[];
  metadata?: Record<string, unknown>;
}

export interface TemporalSeries {
  series_id: string;
  target_id?: string;
  grid_cell_id?: string;
  bounds_wgs84?: GeoBoundingBox;
  tile_col?: number;
  tile_row?: number;
  zoom_level?: number;
  observations: TemporalObservation[];
  observation_count: number;
  earliest_date?: string | null;
  latest_date?: string | null;
  start_time?: string;
  end_time?: string;
  timespan_days?: number;
}

export interface ScenePairCompatibility {
  is_compatible: boolean;
  status?: string;
  reasons?: string[];
  rejection_reasons?: string[];
  is_cross_sensor?: boolean;
  is_cross_platform?: boolean;
  crs_match?: boolean;
  gsd_match?: boolean;
  footprint_overlap_ratio?: number;
  temporal_baseline_days?: number;
}

export interface ScenePair {
  pair_id: string;
  earlier_observation: TemporalObservation;
  later_observation: TemporalObservation;
  temporal_separation_seconds?: number;
  temporal_separation_days?: number;
  spatial_overlap?: Record<string, unknown>;
  compatibility: ScenePairCompatibility;
  pairing_method: string;
  metadata?: Record<string, unknown>;
}

export interface TemporalSeriesPairsResponse {
  series_id: string;
  mode: string;
  valid_pairs: ScenePair[];
  rejected_pairs: ScenePair[];
  total_pairs: number;
}

export interface ChangeRegion {
  region_id: string;
  pixel_count: number;
  area_px: number;
  area_m2?: number;
  bbox_px: [number, number, number, number]; // [min_row, min_col, max_row, max_col]
  bbox_wgs84?: GeoBoundingBox;
  centroid_px: [number, number]; // [row, col]
  centroid_wgs84?: [number, number]; // [lon, lat]
  mean_change_score: number;
  max_change_score: number;
  geometry?: Record<string, unknown>;
}

export interface ChangeMetrics {
  total_pixels: number;
  valid_pixels: number;
  invalid_pixels: number;
  changed_pixels: number;
  changed_fraction: number;
  number_of_regions: number;
  changed_area_px: number;
  changed_area_m2?: number;
  mean_change_score: number;
  max_change_score: number;
  threshold_used: number;
  threshold_method: string;
}

export interface ChangeDetectionResult {
  result_id: string;
  scene_pair_id: string;
  earlier_tile_id: string;
  later_tile_id: string;
  algorithm_id: string;
  algorithm_version: string;
  parameters: Record<string, unknown>;
  metrics: ChangeMetrics;
  regions: ChangeRegion[];
  created_at: string;
  execution_time_ms: number;
  provenance_id: string;
  is_synthetic: boolean;
  is_cached: boolean;
  score_map_path?: string;
  change_mask_path?: string;
}

export interface ChangeDetectionRunRequest {
  earlier_path?: string;
  later_path?: string;
  pair?: ScenePair;
  config?: Record<string, unknown>;
}

export type InvestigationStageStatus =
  | "PENDING"
  | "RUNNING"
  | "COMPLETED"
  | "FAILED"
  | "SKIPPED";

export interface InvestigationStageResult {
  stage: string;
  status: InvestigationStageStatus;
  artifact_id?: string | null;
  provenance_id?: string | null;
  output_path?: string | null;
  error_message?: string | null;
  details: Record<string, unknown>;
  timestamp?: string | null;
}

export interface CandidateCorrespondenceItem {
  reference_candidate_id: string;
  target_pair_id: string;
  status: string;
  relationship: string;
  matched_region_id?: string | null;
  metric_iou?: number;
  centroid_distance_m?: number;
  candidate_scores?: Record<string, number>;
  resolution_notes?: string[];
}

export interface InvestigationLineage {
  scene_pair_ids: string[];
  change_detection_result_ids: string[];
  evidence_ids: string[];
  classification_ids: string[];
  suppression_ids: string[];
  temporal_evidence_id?: string | null;
  upstream_hashes: Record<string, string>;
  candidate_correspondence: Record<string, CandidateCorrespondenceItem>;
}

export interface SpatialCorrespondence {
  status: string;
  relationship: string;
  is_spatially_compatible: boolean;
  iou_wgs84: number;
  centroid_distance_m?: number | null;
  centroid_distance_px?: number | null;
  crs_match: boolean;
  gsd_match: boolean;
}

export type NodeStatus =
  | "PRE_CHANGE_ABSENCE"
  | "EARLIEST_SUPPORTING"
  | "PERSISTENT_SUPPORT"
  | "FLAGGED_SUPPORT"
  | "SUPPRESSED_ARTIFACT"
  | "NO_SUPPORT"
  | "INSUFFICIENT_DATA"
  | "SIMULTANEOUS_CO_TEMPORAL";

export interface TemporalEvidenceNode {
  observation_id: string;
  acquisition_time: string;
  sensor: string;
  platform: string;
  node_status: NodeStatus;
  m4d_decision?: "RETAINED" | "FLAGGED" | "SUPPRESSED" | "INSUFFICIENT_EVIDENCE" | null;
  heuristic_support_score: number;
  eligible_for_earliest_support: boolean;
  spatial_correspondence: SpatialCorrespondence;
  category_observed?: string | null;
  category_confidence?: "high" | "medium" | "low" | "uncertain" | null;
  evidence_score_m4c?: number | null;
  is_cross_sensor: boolean;
  decision_reasons: string[];
  data_limitations: string[];
}

export interface TemporalCategoryEvolution {
  earliest_observed_category?: string | null;
  latest_observed_category?: string | null;
  primary_category: string;
  is_evolution_valid: boolean;
  is_conflicted: boolean;
  evolution_trajectory: string[];
  audit_notes: string[];
}

export interface TemporalOnsetEstimate {
  pre_change_observation_id?: string | null;
  pre_change_date?: string | null;
  earliest_support_observation_id?: string | null;
  earliest_support_date?: string | null;
  interval_days?: number | null;
  provisional_flagged_observation_id?: string | null;
  provisional_flagged_date?: string | null;
  interval_type: string;
  display_bounding_span?: string | null;
  physical_onset_interval?: string | null;
  interval_limitation?: string | null;
}

export interface TemporalEvidenceConfig {
  evaluator_id: string;
  evaluator_version: string;
  min_persistent_observations: number;
  min_support_score_threshold: number;
  min_bbox_iou_threshold: number;
  max_centroid_distance_m: number;
  max_pre_change_cloud_fraction: number;
  min_pre_change_valid_pixel_ratio: number;
  max_temporal_gap_days: number;
}

export interface TemporalEvidenceMetrics {
  total_observations_in_series: number;
  evaluated_nodes_count: number;
  supporting_nodes_count: number;
  flagged_nodes_count: number;
  suppressed_nodes_count: number;
  absence_nodes_count: number;
  insufficient_data_nodes_count: number;
  simultaneous_nodes_count: number;
  cross_sensor_nodes_count: number;
}

export interface CandidateRegionRef {
  change_detection_result_id: string;
  scene_pair_id: string;
  region_id: string;
}

export interface TemporalEvidenceResult {
  temporal_evidence_id: string;
  candidate_ref: CandidateRegionRef;
  series_id: string;
  evaluator_id: string;
  evaluator_version: string;
  config: TemporalEvidenceConfig;
  temporal_support_status: string;
  confidence_tier: "high" | "medium" | "low" | "uncertain";
  onset_estimate: TemporalOnsetEstimate;
  category_evolution: TemporalCategoryEvolution;
  metrics: TemporalEvidenceMetrics;
  timeline_nodes: TemporalEvidenceNode[];
  decision_reasons: string[];
  evidence_limitations: string[];
  discovery_scene_pair_id: string;
  evaluated_scene_pair_ids: string[];
  evaluated_change_detection_result_ids: string[];
  evaluated_evidence_ids: string[];
  evaluated_classification_ids: string[];
  upstream_suppression_ids: string[];
  upstream_hashes: Record<string, string>;
  provenance_id: string;
  created_at: string;
}

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
  requested_format?: string;
}

export interface InvestigationDossier {
  investigation_id: string;
  request: InvestigationRequest;
  series_id: string;
  discovery_pair_id: string;
  candidate_region_id: string;
  temporal_evidence_id?: string | null;
  stage_results: InvestigationStageResult[];
  lineage: InvestigationLineage;
  provenance_id: string;
  created_at: string;
  content_hash: string;
  temporal_evidence?: TemporalEvidenceResult | null;
  status: string;
  dossier_path?: string | null;
}
