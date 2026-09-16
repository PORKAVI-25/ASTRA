/**
 * ASTRA Frontend Type Definitions
 * Directly mirrors backend geospatial data contracts (ASTRA-DC-v0.1).
 */

export interface HealthResponse {
  status: string;
  version: string;
  service: string;
  timestamp: string;
  environment: string;
  offline_mode: boolean;
  modules: Record<string, string>;
}

export interface GeoBoundingBox {
  min_lon: number;
  min_lat: number;
  max_lon: number;
  max_lat: number;
}

export interface TileDimensions {
  width_px: number;
  height_px: number;
  channels: number;
}

export interface TileManifest {
  tile_id: string;
  source_scene_id: string;
  tile_col: number;
  tile_row: number;
  zoom_level: number;
  dimensions: TileDimensions;
  crs: string;
  bounds_wgs84: GeoBoundingBox;
  acquisition_time: string;
  sensor: string;
  file_path: string;
  sha256_hash: string;
  is_synthetic: boolean;
}

export interface SceneManifest {
  scene_id: string;
  sensor: string;
  platform: string;
  acquisition_time: string;
  crs: string;
  bounds_wgs84: GeoBoundingBox;
  spatial_resolution_m: number;
  cloud_cover_percentage?: number;
  bands: string[];
  source_file_path: string;
  is_synthetic: boolean;
  created_at: string;
}

export interface ProvenanceRecord {
  provenance_id: string;
  target_tile_id: string;
  source_scene_id: string;
  processing_stage: string;
  pipeline_version: string;
  parameters: Record<string, unknown>;
  executed_by: string;
  timestamp: string;
}
