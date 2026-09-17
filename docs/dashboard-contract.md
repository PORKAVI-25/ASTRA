# ASTRA Analyst Dashboard API Contract (Phase M4F-F)

## 1. Executive Overview

This contract formalizes the integration interface between the **ASTRA Backend API** and the **Analyst Dashboard Frontend** for Phase M4F.

It details:
- All operational REST endpoints available for dashboard consumption today.
- Exact request and response data contracts conforming to `ASTRA-DC-v0.1`.
- Capabilities that can be rendered immediately by the UI without backend changes.
- Backend gaps, missing endpoints, and recommended architectural extensions.
- Strict air-gapped offline constraints governing client-side rendering.

---

## 2. API Endpoints Inventory

### 2.1 Core Operational Endpoints for Dashboard

| Method | Endpoint | Description | Status | Response Model |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/health` | Backend telemetry & offline readiness | **Active** | `HealthResponse` |
| `GET` | `/api/v1/temporal/series` | List all cataloged `TemporalSeries` | **Active** | `List[TemporalSeries]` |
| `GET` | `/api/v1/temporal/series/{series_id}` | Retrieve single `TemporalSeries` | **Active** | `TemporalSeries` |
| `GET` | `/api/v1/temporal/series/{series_id}/pairs` | Generate pairs (`baseline`, `adjacent`, `all_pairwise`) | **Active** | `TemporalSeriesPairsResponse` |
| `POST` | `/api/v1/pipeline/investigate` | Run end-to-end multi-temporal investigation | **Active** | `InvestigationDossier` |
| `POST` | `/api/v1/change-detection/run` | Run M4B change detection on a `ScenePair` | **Active** | `ChangeDetectionResult` |
| `GET` | `/api/v1/change-detection/{result_id}` | Retrieve precomputed change detection result | **Active** | `ChangeDetectionResult` |
| `GET` | `/api/v1/change-detection/{result_id}/mask` | Stream binary change mask PNG | **Active** | `image/png` |
| `GET` | `/api/v1/change-suppression/results/{sup_id}` | Retrieve false-alarm screening result | **Active** | `SuppressionResult` |
| `GET` | `/api/v1/change-suppression/results/{sup_id}/mask` | Stream tri-state filtered change mask GeoTIFF | **Active** | `image/tiff` |
| `GET` | `/api/v1/temporal-evidence/{tem_id}` | Retrieve standalone temporal evidence result | **Active** | `TemporalEvidenceResult` |
| `GET` | `/api/v1/scenes` | List all ingested satellite scenes | **Active** | `List[SceneSummaryResponse]` |
| `GET` | `/api/v1/ingestion/{scene_id}` | Full scene ingestion manifest | **Active** | `SceneManifest` |
| `GET` | `/api/v1/scenes/{scene_id}/tiles` | List tile manifests for a scene | **Active** | `List[TileManifest]` |

---

## 3. Existing Request Schemas

### 3.1 Investigation Execution: `POST /api/v1/pipeline/investigate`

**Request Model:** `backend.orchestrator.types.InvestigationRequest`
**Validation Policy:** Strict Pydantic v2 `ConfigDict(extra="forbid")`.

```json
{
  "series_id": "series_grid_lon77.33_lat13.08_c0000_r0000_z14",
  "discovery_pair_id": "pair_obs_tile_c0000_r0000_z14_01__obs_tile_c0000_r0000_z14_02",
  "candidate_region_id": "reg_0002",
  "pairing_strategy": "baseline",
  "output_dir": null,
  "change_detection_config": null,
  "evidence_config": null,
  "classifier_config": null,
  "suppression_config": null,
  "temporal_evidence_config": null,
  "requested_format": "json"
}
```

#### Field Specifications:
- `series_id` (`string`, required, min length: 3): Target temporal series identifier.
- `discovery_pair_id` (`string`, required, min length: 5): Scene pair where candidate was observed.
- `candidate_region_id` (`string`, required, min length: 3): Local region ID within discovery pair (e.g. `reg_0001`, `reg_0002`).
- `pairing_strategy` (`string`, optional, default: `"adjacent"`): Subsequent pairing mode (`"adjacent"` or `"baseline"`).
- `change_detection_config` (`object`, optional): Hyperparameter overrides for M4B.
- `evidence_config` (`object`, optional): Fallback band mapping. If omitted, the backend injects `band_mapping={"red": 0, "green": 1, "blue": 2}`.
- `classifier_config` (`object`, optional): Hyperparameter overrides for M4C-B.
- `suppression_config` (`object`, optional): Hyperparameter overrides for M4D.
- `temporal_evidence_config` (`object`, optional): Hyperparameter overrides for M4E.

### 3.2 Pairwise Discovery: `GET /api/v1/temporal/series/{series_id}/pairs`

#### Query Parameters:
- `mode` (`string`, optional, default: `"baseline"`):
  - `"baseline"`: All pairs anchored to $T_0$ ($T_0 \to T_1, T_0 \to T_2, \dots, T_0 \to T_n$).
  - `"adjacent"`: Consecutive chronological pairs ($T_0 \to T_1, T_1 \to T_2, \dots$).
  - `"all_pairwise"`: Complete combinatorial pairs.

### 3.3 Candidate Region Discovery: `POST /api/v1/change-detection/run`

Used by the frontend to detect and list candidate change regions for a pair *prior* to launching an investigation:

```json
{
  "pair": {
    "pair_id": "pair_obs_tile_...__obs_tile_...",
    "earlier_observation": { ... },
    "later_observation": { ... },
    "compatibility": { "is_compatible": true, ... },
    "pairing_method": "baseline_t0"
  },
  "config": null
}
```

---

## 4. Existing Response Schemas

### 4.1 Investigation Dossier: `InvestigationDossier`

The response of `POST /api/v1/pipeline/investigate` is a complete, self-contained JSON dossier conforming to `ASTRA-DC-v0.1`:

```json
{
  "investigation_id": "inv_8c939ce062ed9b8c",
  "request": { ... },
  "series_id": "series_grid_lon77.33_lat13.08_c0000_r0000_z14",
  "discovery_pair_id": "pair_obs_tile_c0000_r0000_z14_01__obs_tile_c0000_r0000_z14_02",
  "candidate_region_id": "reg_0002",
  "temporal_evidence_id": "tem_7c8d9e0f1a2b3c4d",
  "stage_results": [
    {
      "stage": "series_resolution",
      "status": "COMPLETED",
      "artifact_id": "series_grid_lon77.33_lat13.08_c0000_r0000_z14",
      "provenance_id": null,
      "output_path": null,
      "error_message": null,
      "details": { "observation_count": 4 },
      "timestamp": "2026-04-15T10:30:00Z"
    },
    ...
  ],
  "lineage": {
    "scene_pair_ids": ["pair_T1__T2", "pair_T1__T3", "pair_T1__T4"],
    "change_detection_result_ids": ["cdr_...", "cdr_...", "cdr_..."],
    "evidence_ids": ["evi_...", "evi_...", "evi_..."],
    "classification_ids": ["cls_...", "cls_...", "cls_..."],
    "suppression_ids": ["sup_...", "sup_...", "sup_..."],
    "temporal_evidence_id": "tem_7c8d9e0f1a2b3c4d",
    "upstream_hashes": {
      "data/processed/tiles/obs_tile_01.tif": "a1b2c3d4e5f6...",
      "cdr_pair_T1__T2": "f8e7d6c5b4a3..."
    },
    "candidate_correspondence": {
      "pair_T1__T2": {
        "reference_candidate_id": "reg_0002",
        "target_pair_id": "pair_T1__T2",
        "status": "EXACT_REFERENCE",
        "relationship": "MATCHED",
        "matched_region_id": "reg_0002",
        "metric_iou": 1.0,
        "centroid_distance_m": 0.0,
        "candidate_scores": { "reg_0002": 1.0 },
        "resolution_notes": ["Discovery candidate reference region."]
      },
      "pair_T1__T3": {
        "reference_candidate_id": "reg_0002",
        "target_pair_id": "pair_T1__T3",
        "status": "GEOREFERENCED_BBOX",
        "relationship": "MATCHED",
        "matched_region_id": "reg_0001",
        "metric_iou": 0.88,
        "centroid_distance_m": 4.2,
        "candidate_scores": { "reg_0001": 0.88 },
        "resolution_notes": ["Matched region reg_0001 via bbox IoU 0.88."]
      }
    }
  },
  "provenance_id": "prov_inv_8c939ce062ed9b8c",
  "created_at": "2026-04-15T10:30:00Z",
  "content_hash": "8c939ce062ed9b8c",
  "temporal_evidence": {
    "temporal_evidence_id": "tem_7c8d9e0f1a2b3c4d",
    "candidate_ref": {
      "change_detection_result_id": "cdr_...",
      "scene_pair_id": "pair_T1__T2",
      "region_id": "reg_0002"
    },
    "series_id": "series_grid_lon77.33_lat13.08_c0000_r0000_z14",
    "evaluator_id": "astra_temporal_evidence_evaluator",
    "evaluator_version": "1.0.0",
    "config": {
      "min_persistent_observations": 2,
      "min_support_score_threshold": 0.45,
      "min_bbox_iou_threshold": 0.30,
      "max_centroid_distance_m": 60.0
    },
    "temporal_support_status": "STRONG_TEMPORAL_SUPPORT",
    "confidence_tier": "high",
    "onset_estimate": {
      "pre_change_observation_id": "obs_tile_01",
      "pre_change_date": "2026-01-15T10:30:00Z",
      "earliest_support_observation_id": "obs_tile_02",
      "earliest_support_date": "2026-02-15T10:30:00Z",
      "interval_days": 31.0,
      "provisional_flagged_observation_id": null,
      "provisional_flagged_date": null,
      "interval_type": "BOUNDED_HALF_OPEN",
      "display_bounding_span": "[2026-01-15, 2026-02-15]",
      "physical_onset_interval": "(2026-01-15, 2026-02-15]",
      "interval_limitation": "Interval represents discrete satellite sampling bounds; exact physical date of occurrence is unobservable."
    },
    "category_evolution": {
      "earliest_observed_category": "construction",
      "latest_observed_category": "construction",
      "primary_category": "construction",
      "is_evolution_valid": true,
      "is_conflicted": false,
      "evolution_trajectory": ["construction", "construction", "construction"],
      "audit_notes": []
    },
    "metrics": {
      "total_observations_in_series": 4,
      "evaluated_nodes_count": 4,
      "supporting_nodes_count": 3,
      "flagged_nodes_count": 0,
      "suppressed_nodes_count": 0,
      "absence_nodes_count": 1,
      "insufficient_data_nodes_count": 0,
      "simultaneous_nodes_count": 0,
      "cross_sensor_nodes_count": 0
    },
    "timeline_nodes": [
      {
        "observation_id": "obs_tile_01",
        "acquisition_time": "2026-01-15T10:30:00Z",
        "sensor": "MSI",
        "platform": "Sentinel-2A",
        "node_status": "PRE_CHANGE_ABSENCE",
        "m4d_decision": null,
        "heuristic_support_score": 0.0,
        "eligible_for_earliest_support": false,
        "spatial_correspondence": {
          "status": "EXACT_PIXEL_GRID",
          "relationship": "MATCHED",
          "is_spatially_compatible": true,
          "iou_wgs84": 1.0,
          "centroid_distance_m": 0.0,
          "centroid_distance_px": 0.0,
          "crs_match": true,
          "gsd_match": true
        },
        "category_observed": null,
        "category_confidence": null,
        "evidence_score_m4c": null,
        "is_cross_sensor": false,
        "decision_reasons": ["Pre-change observation confirmed clear baseline absence."],
        "data_limitations": []
      },
      {
        "observation_id": "obs_tile_02",
        "acquisition_time": "2026-02-15T10:30:00Z",
        "sensor": "MSI",
        "platform": "Sentinel-2B",
        "node_status": "EARLIEST_SUPPORTING",
        "m4d_decision": "RETAINED",
        "heuristic_support_score": 0.92,
        "eligible_for_earliest_support": true,
        "spatial_correspondence": {
          "status": "EXACT_PIXEL_GRID",
          "relationship": "MATCHED",
          "is_spatially_compatible": true,
          "iou_wgs84": 1.0,
          "centroid_distance_m": 0.0,
          "centroid_distance_px": 0.0,
          "crs_match": true,
          "gsd_match": true
        },
        "category_observed": "construction",
        "category_confidence": "high",
        "evidence_score_m4c": 0.95,
        "is_cross_sensor": false,
        "decision_reasons": [
          "Satisfies M4D RETAINED screening without cloud/edge artifacts.",
          "Earliest chronological epoch showing affirmative change signal."
        ],
        "data_limitations": []
      }
    ],
    "decision_reasons": [
      "Earliest supporting observation established at 2026-02-15T10:30:00Z.",
      "Pre-change absence confirmed at 2026-01-15T10:30:00Z.",
      "Persistent support confirmed across 2 subsequent observations."
    ],
    "evidence_limitations": [
      "Interval represents discrete satellite sampling bounds."
    ],
    "provenance_id": "prov_tem_7c8d9e0f1a2b3c4d",
    "created_at": "2026-04-15T10:30:00Z"
  },
  "status": "COMPLETED",
  "dossier_path": "data/processed/investigations/inv_8c939ce062ed9b8c/dossier.json"
}
```

---

## 5. Exact Fields the Dashboard Can Consume TODAY

| UI Component | Dossier / Endpoint Field | Source | Rendering Representation |
| :--- | :--- | :--- | :--- |
| **Executive Header** | `investigation_id` | `dossier` | Monospace badge, copy button |
| | `content_hash` | `dossier` | Verification hash badge |
| | `created_at` | `dossier` | Formatted UTC timestamp |
| | `status` | `dossier` | Status pill (`COMPLETED` = emerald) |
| | `series_id` | `dossier` | Clickable series badge |
| | `discovery_pair_id` | `dossier` | Discovery pair label |
| | `candidate_region_id`| `dossier` | Target region label (`reg_0002`) |
| **Temporal Onset Card** | `onset_estimate.interval_type` | `temporal_evidence` | Interval type tag (`BOUNDED_HALF_OPEN`) |
| | `onset_estimate.display_bounding_span` | `temporal_evidence` | Primary large badge: `[T_pre, T_earliest]` |
| | `onset_estimate.physical_onset_interval` | `temporal_evidence` | Mathematical interval notation: `(T_pre, T_earliest]` |
| | `onset_estimate.interval_days` | `temporal_evidence` | Duration pill: `31.0 days` |
| | `onset_estimate.pre_change_date` | `temporal_evidence` | Sub-label: Pre-change absence date |
| | `onset_estimate.earliest_support_date` | `temporal_evidence` | Sub-label: Earliest supporting date |
| | `onset_estimate.interval_limitation` | `temporal_evidence` | Warning notice / callout box |
| **Support & Confidence**| `temporal_support_status` | `temporal_evidence` | Large chip: `STRONG_TEMPORAL_SUPPORT` |
| | `confidence_tier` | `temporal_evidence` | Tier badge (`HIGH` = green, `MEDIUM` = amber, `LOW` = orange, `UNCERTAIN` = red) |
| **Category Evolution** | `category_evolution.primary_category` | `temporal_evidence` | Primary category banner (`CONSTRUCTION`) |
| | `category_evolution.evolution_trajectory` | `temporal_evidence` | Trajectory chips: `T1 -> T2 -> T3` |
| | `category_evolution.is_evolution_valid` | `temporal_evidence` | Checkmark or conflict alert |
| **Timeline Nodes** | `timeline_nodes[].acquisition_time` | `temporal_evidence` | Chronological column headers |
| | `timeline_nodes[].node_status` | `temporal_evidence` | Colored status pills: `PRE_CHANGE_ABSENCE`, `EARLIEST_SUPPORTING`, `PERSISTENT_SUPPORT`, etc. |
| | `timeline_nodes[].heuristic_support_score` | `temporal_evidence` | Support score progress bar (0.00 – 1.00) |
| | `timeline_nodes[].m4d_decision` | `temporal_evidence` | M4D badge: `RETAINED`, `FLAGGED`, `SUPPRESSED` |
| | `timeline_nodes[].decision_reasons` | `temporal_evidence` | Bulleted expandable list |
| | `timeline_nodes[].data_limitations` | `temporal_evidence` | Caveat warning items |
| **Spatial Tracking** | `lineage.candidate_correspondence` | `dossier.lineage` | Per-epoch correspondence table: Target Pair, Matched Region ID, IoU, Centroid Drift |
| **Lineage & Hashes** | `lineage.upstream_hashes` | `dossier.lineage` | Upstream cryptographic table |
| **Stage Waterfall** | `stage_results[]` | `dossier` | Step-by-step stage status, artifact IDs, execution times |
| **Change Mask Image**| `GET /api/v1/change-detection/{result_id}/mask` | M4B endpoint | Interactive PNG change mask display |

---

## 6. Fields Missing for an Ideal Analyst UI

The following capabilities are needed for a first-class spatial-temporal analyst workflow:

1. **Candidate Spatial Geometry in Dossier**:
   - The dossier specifies `candidate_region_id: "reg_0002"`, but does NOT directly embed `bbox_wgs84`, `bbox_px`, `centroid_wgs84`, or GeoJSON `geometry`.
   - *Current Workaround*: Frontend calls `GET /api/v1/change-detection/{cdr_id}` where `cdr_id = lineage.change_detection_result_ids[0]` and reads the matching `ChangeRegion`.
2. **Multi-Epoch Matched Region Geometries**:
   - `lineage.candidate_correspondence` gives `matched_region_id: "reg_0001"`, `metric_iou: 0.88`, and `centroid_distance_m: 4.2`. It does not embed the matched region's polygon coordinates in the dossier.
   - *Current Workaround*: Fetch respective `ChangeDetectionResult` for each evaluated pair.
3. **RGB Tile Thumbnails / Previews**:
   - Tile rasters are multi-band GeoTIFFs on disk (`.tif`). Browsers cannot render GeoTIFFs in an `<img>` tag.
   - *Current Workaround*: Render SVG/Canvas footprint outlines and bounding box overlays; use PNG change masks from `/api/v1/change-detection/{result_id}/mask`.
4. **Candidate Region Pre-Investigation Discovery**:
   - When an analyst selects a `ScenePair`, they need to see candidate regions (`reg_0001`, `reg_0002`) to choose one.
   - *Current Workaround*: Frontend calls `POST /api/v1/change-detection/run` with the selected pair to inspect `regions[]`.
5. **Provenance Record REST Resolution**:
   - Dossier references `prov_inv_{hash}`, `prov_tem_{hash}`, etc., but there is no `GET /api/v1/provenance/{id}` endpoint to inspect raw provenance records.
   - *Current Workaround*: Lineage and upstream hashes in `InvestigationDossier` already provide all necessary cryptographic verification data.
6. **Analyst Review Persistence**:
   - The analyst's triage decision (`Confirm`, `Reject`, `Flag/Needs Review`, comments) is not saved in backend storage.
   - *Current Workaround*: Store reviews in browser `localStorage` and provide JSON export.

---

## 7. Backend Work vs. Immediate Frontend Work

### What Requires Backend Enhancements (Phase M4F-G or Future):
- [ ] Dedicated `GET /api/v1/temporal/pairs/{pair_id}/candidates` endpoint to list candidate regions without passing full `ScenePair` payloads.
- [ ] Dedicated `GET /api/v1/tiles/{tile_id}/preview.png` endpoint to convert multi-band GeoTIFFs into browser-viewable RGB PNGs.
- [ ] Dedicated `POST /api/v1/investigations/{investigation_id}/reviews` and `GET .../reviews` for persistent team-wide analyst audit trails.
- [ ] Dedicated `GET /api/v1/provenance/{provenance_id}` endpoint.

### What Can Be Implemented IMMEDIATELY in Frontend:
- [x] Full Series Explorer (`/api/v1/temporal/series`, `/api/v1/temporal/series/{id}`).
- [x] Pair Discovery Browser (`/api/v1/temporal/series/{id}/pairs?mode=...`).
- [x] Candidate Discovery via `POST /api/v1/change-detection/run`.
- [x] Investigation Launcher with full parameter validation (`POST /api/v1/pipeline/investigate`).
- [x] Full Dossier Presentation: Executive Summary, Trajectory, Onset Interval, Metrics, Limitations.
- [x] Multi-Epoch Chronological Timeline Ribbon with interactive status inspection.
- [x] Multi-Epoch Spatial Correspondence Tracker showing region ID shifts and metric IoU.
- [x] High-resolution Binary Change Mask viewer (`GET /api/v1/change-detection/{result_id}/mask`).
- [x] Upstream Cryptographic Lineage & Stage Waterfall view.
- [x] Local Analyst Review workflow (`Confirm`, `Reject`, `Flag/Needs Review`) backed by `localStorage` and audit trail export.

---

## 8. Error States & Validation Handling

| Status Code | Error Code | Example Condition | UI Handling |
| :--- | :--- | :--- | :--- |
| **400 Bad Request** | `VALIDATION_ERROR` | Unknown `series_id` or invalid `candidate_region_id` | Highlight form field with server message; prevent submission. |
| **400 Bad Request** | `PIPELINE_ERROR` | Detection, evidence, or suppression failure on a pair | Display Stage Failure card showing exact failing stage and diagnostics. |
| **404 Not Found** | `NOT_FOUND` | Missing temporal series or result ID | Render empty state card with retry / back navigation. |
| **422 Unprocessable** | `UNPROCESSABLE_ENTITY` | Pydantic schema violation (e.g. unknown field) | Form validation banner; client contract error. |
| **500 Server Error** | `INTERNAL_SERVER_ERROR`| Unhandled server exception | Safe error message with log inspection prompt. |

---

## 9. Loading & Processing States

- Investigation execution is **synchronous**: typical runtime on 4-epoch synthetic dataset is **1.2s – 2.5s**.
- The frontend must display an animated pipeline execution tracker simulating the 8 orchestration steps:
  1. Resolving temporal series
  2. Validating discovery pair
  3. Running M4B change detection
  4. Grounding candidate region
  5. Generating pairwise sequence
  6. Extracting evidence & classifying
  7. Screening false alarms
  8. Computing temporal evidence & onset interval
- On completion, smooth transition to the `InvestigationDossier` view.

---

## 10. Demo Dataset Assumptions

- **Series Identifier**: `series_grid_lon77.33_lat13.08_c0000_r0000_z14` (4 epochs: Jan 15, Feb 15, Mar 15, Apr 15, 2026).
- **Target Candidate**: `reg_0002` (in T1 $\to$ T2 discovery pair, representing a genuine construction onset).
- **Spatial Correspondence**:
  - T1 $\to$ T2: `reg_0002` (exact reference, IoU 1.0)
  - T1 $\to$ T3: `reg_0001` (matched region ID shift, IoU ~0.88)
  - T1 $\to$ T4: `reg_0003` (matched region ID shift, IoU ~0.87)
- **Outcome**: `STRONG_TEMPORAL_SUPPORT`, `HIGH` confidence, Onset Interval `(2026-01-15, 2026-02-15]`.
- **Default Band Mapping**: RGB `{"red": 0, "green": 1, "blue": 2}`.

---

## 11. Air-Gapped Offline Constraints

1. **Zero External CDN Dependencies**:
   - No Google Fonts, CDN scripts, or external CSS links.
   - All fonts must use system font stacks (`ui-sans-serif, system-ui, -apple-system, sans-serif`) or locally bundled fonts.
2. **Zero Remote Tile Servers**:
   - Do NOT embed Leaflet or Mapbox instances requesting external tiles (`tile.openstreetmap.org`, `mapbox.com`, etc.).
   - Visualizations must use HTML5 Canvas, SVG vectors, and locally served mask PNGs (`/api/v1/change-detection/{result_id}/mask`).
3. **Local Backend Communication Only**:
   - Requests target `http://127.0.0.1:8000` (or `import.meta.env.VITE_API_URL`).
4. **Verification**:
   - All frontend code must pass `python scripts/check_offline.py` (0 remote URLs, 0 unauthorized outbound calls).
