# A.S.T.R.A. Data Contracts & Metadata Specifications

**Standard:** ASTRA-DC-v0.1  
**Status:** Approved for Phase 0  
**Enforcement:** Pydantic v2 Models & JSON Schema Validation

---

## 1. Overview & Architectural Rules

To satisfy **Critical Architectural Rules 3, 4, 5, and 9**:
1. **Rule 3:** Every imagery tile must possess a deterministic, stable identity (`tile_id`).
2. **Rule 4:** Every tile must remain permanently linked to its parent source scene (`source_scene_id`).
3. **Rule 5:** The system must preserve:
   - Coordinate Reference System (CRS)
   - Geographic Bounding Box (projected and WGS84 coordinates)
   - Acquisition Timestamp (UTC ISO-8601)
   - Sensor & Platform name
   - Source Scene ID
   - Processing lineage (radiometric calibration, chip dimensions, normalization)
4. **Rule 9:** Demo and synthetic data must be explicitly marked (`is_synthetic: true`).

---

## 2. Satellite Scene Manifest Contract (`SceneManifest`)

Represents a full earth observation scene (e.g. Sentinel-2 L2A tile, Landsat-8/9 scene) ingested into the local catalog.

```json
{
  "scene_id": "S2A_MSIL2A_20260315T052021_N0500_R019_T43PGQ_20260315T083045",
  "sensor": "Sentinel-2A MSI",
  "platform": "Sentinel-2",
  "acquisition_time": "2026-03-15T05:20:21Z",
  "crs": "EPSG:32643",
  "bounds_wgs84": {
    "min_lon": 76.842,
    "min_lat": 11.231,
    "max_lon": 77.891,
    "max_lat": 12.215
  },
  "spatial_resolution_m": 10.0,
  "cloud_cover_percentage": 2.4,
  "bands": ["B02", "B03", "B04", "B08"],
  "source_file_path": "data/raw/S2A_20260315_T43PGQ.tif",
  "is_synthetic": false,
  "created_at": "2026-09-16T10:00:00Z"
}
```

---

## 3. Imagery Tile Manifest Contract (`TileManifest`)

Represents an individual chipped sub-tile ready for embedding generation and change detection.

```json
{
  "tile_id": "tile_S2A_T43PGQ_x004_y008_z14",
  "source_scene_id": "S2A_MSIL2A_20260315T052021_N0500_R019_T43PGQ_20260315T083045",
  "tile_col": 4,
  "tile_row": 8,
  "zoom_level": 14,
  "dimensions": {
    "width_px": 512,
    "height_px": 512,
    "channels": 3
  },
  "crs": "EPSG:32643",
  "bounds_wgs84": {
    "min_lon": 77.0123,
    "min_lat": 11.4501,
    "max_lon": 77.0582,
    "max_lat": 11.4960
  },
  "acquisition_time": "2026-03-15T05:20:21Z",
  "sensor": "Sentinel-2A MSI",
  "file_path": "data/processed/tiles/tile_S2A_T43PGQ_x004_y008_z14.png",
  "sha256_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "is_synthetic": false
}
```

---

## 4. Provenance Record Contract (`ProvenanceRecord`)

Records the processing history and cryptographic hash of every transformation.

```json
{
  "provenance_id": "prov_9d8e7f6a5b4c3d2e",
  "target_tile_id": "tile_S2A_T43PGQ_x004_y008_z14",
  "source_scene_id": "S2A_MSIL2A_20260315T052021_N0500_R019_T43PGQ_20260315T083045",
  "processing_stage": "chipping_and_normalization",
  "pipeline_version": "0.1.0",
  "parameters": {
    "chip_size": 512,
    "stride": 512,
    "resampling_method": "bilinear",
    "normalization": "min_max_percentile_2_98"
  },
  "executed_by": "astra.ingestion.chipper",
  "timestamp": "2026-09-16T10:02:00Z"
}
```

---

## 5. System Health Response Contract (`HealthResponse`)

Contract implemented by `GET /health` and `GET /api/v1/health`.

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "service": "ASTRA Backend API",
  "timestamp": "2026-09-16T10:05:00Z",
  "environment": "development",
  "offline_mode": true,
  "modules": {
    "api": "healthy",
    "ingestion": "ready",
    "retrieval": "ready",
    "change_analysis": "ready",
    "provenance": "ready",
    "evaluation": "ready"
  }
}
```
