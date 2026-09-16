# ASTRA Phase M4A — Temporal Data Model & Scene Pairing Specification

- **Project:** A.S.T.R.A. (*Automated Semantic Tracking and Retrieval Architecture*)
- **Challenge:** Smart India Hackathon 2026 — PS 227
- **Stage:** Phase M4A (Temporal Observation Modeling & Deterministic Scene Pairing)
- **Status:** Complete & Verified
- **Date:** 2026-09-16

---

## 1. Executive Summary & Architectural Scope

Phase M4A constructs the temporal foundation for ASTRA, enabling systematic, offline-capable association of multi-temporal satellite imagery over identical geographic footprints.

### Important Scientific Demarcation
> [!IMPORTANT]
> **Temporal Pairing vs. Physical Change Detection**:
> - **Phase M4A (Current)** establishes *observational association*: spatial overlap verification, chronological validation, metadata compatibility, and deterministic pair IDs.
> - **Phase M4A DOES NOT claim that a pair constitutes physical change**. Establishing that two observations cover the same area at different dates ($T_1 < T_2$) is a necessary mathematical prerequisite for change analysis, but not change detection itself.
> - **Phase M4B/M4C/M4D (Deferred)** will introduce pixel difference algorithms, spectral indices (NDVI/NDWI drift), foundation model feature embedding distance, and segmentation mask generation.

---

## 2. Core Temporal Domain Model

The temporal domain models reside under `backend/ml/change/types.py` and are re-exported through `backend.change_analysis`:

```
backend/ml/change/
    __init__.py           # Unified exports
    types.py              # Pydantic data contracts (observations, overlap, pairs, series, config)
    scene_pairing.py      # Exact 2D bounding-box spatial overlap & pairing logic
    temporal_catalog.py   # Ingestion manifest discovery, series grouping, and pair evaluation
```

```
+-----------------------------------------------------------------------------------------------+
|                                      TemporalCatalog                                          |
|  - discover_manifests(tiles_dir, scenes_dir)                                                  |
|  - build_series() -> Dict[str, TemporalSeries]                                                |
|  - generate_pairs(config) -> (valid_pairs, rejected_pairs)                                    |
+---------------------------------------------------+-------------------------------------------+
                                                    |
                         +--------------------------+--------------------------+
                         |                                                     |
                         v                                                     v
+------------------------------------------------+    +-----------------------------------------+
|                 TemporalSeries                 |    |                ScenePair                |
|  - series_id: str                              |    |  - pair_id: str (deterministic)         |
|  - target_id: str (grid anchor)                |    |  - earlier_observation: TemporalObs (T1)|
|  - bounds_wgs84: GeoBoundingBox                |    |  - later_observation: TemporalObs (T2)  |
|  - observations: List[TemporalObservation]     |    |  - temporal_separation_days: float      |
|    (sorted strictly chronologically)           |    |  - spatial_overlap: SpatialOverlap      |
|  - earliest_date, latest_date: datetime        |    |  - compatibility: PairCompatibility     |
+------------------------------------------------+    +-----------------------------------------+
                         |
                         v
+------------------------------------------------+
|              TemporalObservation               |
|  - observation_id: str                         |
|  - scene_id: str, tile_id: Optional[str]       |
|  - acquisition_time: datetime (UTC normalized) |
|  - sensor: str, platform: str, crs: str        |
|  - bounds_wgs84: GeoBoundingBox                |
|  - source_hash: str (SHA-256)                  |
|  - provenance_reference: Optional[str]         |
+------------------------------------------------+
```

---

## 3. Data Contracts

### A. `TemporalObservation`
Encapsulates an ingested satellite chip or scene with verified temporal metadata:
- `observation_id`: Stable identifier derived from `tile_id` (or `scene_id`) and content hash.
- `scene_id`: Root satellite acquisition ID.
- `tile_id`: Optional sub-chip identifier.
- `acquisition_time`: Timezone-aware UTC datetime. **Missing or unparseable timestamps are strictly rejected.**
- `sensor`: Imaging instrument (e.g. `Sentinel-2A MSI`, `Landsat-8 OLI`).
- `platform`: Spacecraft platform (e.g. `Sentinel-2`, `Landsat-8`).
- `crs`: Coordinate reference system (e.g. `EPSG:32643`).
- `bounds_wgs84`: Bounding box in geographic EPSG:4326.
- `source_hash`: Cryptographic SHA-256 of pixel binary.
- `provenance_reference`: Lineage linkage to Phase 1 ingestion record.

### B. `SpatialOverlap`
Exposes comprehensive 2D overlap metrics:
- `intersection_bounds`: Extracted `GeoBoundingBox` of overlapping region (or `None` if disjoint).
- `intersection_area_deg2`: Overlap area in square degrees.
- `overlap_ratio_iou`: Intersection over Union ($\frac{\text{area}_{\cap}}{\text{area}_1 + \text{area}_2 - \text{area}_{\cap}}$).
- `overlap_ratio_earlier`: $\frac{\text{area}_{\cap}}{\text{area}_1}$.
- `overlap_ratio_later`: $\frac{\text{area}_{\cap}}{\text{area}_2}$.
- `overlap_ratio_min`: $\frac{\text{area}_{\cap}}{\min(\text{area}_1, \text{area}_2)}$.
- `is_overlapping`: Boolean indicator ($> 0$).

### C. `ScenePair`
- `pair_id`: Unique deterministic string (`pair_{earlier_id}__{later_id}`).
- `earlier_observation`: Observation at $T_1$.
- `later_observation`: Observation at $T_2$ ($T_2 > T_1$).
- `temporal_separation_seconds`: Exact elapsed time.
- `temporal_separation_days`: Elapsed time in fractional days.
- `spatial_overlap`: Associated `SpatialOverlap` record.
- `compatibility`: `PairCompatibility` object with detailed diagnostic codes.

---

## 4. Spatial Overlap Mathematics

Spatial intersection is computed on axis-aligned bounding boxes in WGS84:

$$\text{int\_min\_lon} = \max(A.\min_x, B.\min_x)$$
$$\text{int\_max\_lon} = \min(A.\max_x, B.\max_x)$$
$$\text{int\_min\_lat} = \max(A.\min_y, B.\min_y)$$
$$\text{int\_max\_lat} = \min(A.\max_y, B.\max_y)$$

### Overlap Condition
An intersection exists if and only if:
$$\text{int\_min\_lon} < \text{int\_max\_lon} \quad \land \quad \text{int\_min\_lat} < \text{int\_max\_lat}$$

If this condition fails, `intersection_bounds` is `None` and all overlap ratios are set to $0.0$.

### Known Limitation: Bounding Box Approximation
> [!NOTE]
> Bounding-box intersection provides an efficient, exact mathematical overlap for rectangular tile chips in EPSG:4326. However, it does not account for scene rotational skew (non-north-up swaths) or sensor nodata margins. Polygon-level geometry and pixel mask intersection are planned for Phase M4B co-registration.

---

## 5. Pairing Rules & Compatibility Evaluation

The pairing engine evaluates candidate observations against configurable constraints defined in `PairingConfig`:

| Constraint | Evaluation Rule | Failure Status |
|---|---|---|
| **Chronological Order** | $T_{\text{later}} > T_{\text{earlier}}$ | `INVALID_TEMPORAL_ORDER` |
| **Separation Non-Zero** | $T_{\text{later}} \ne T_{\text{earlier}}$ | `IDENTICAL_TIMESTAMPS` |
| **Minimum Separation** | $\Delta t \ge \Delta t_{\min}$ | `BELOW_MIN_INTERVAL` |
| **Maximum Separation** | $\Delta t \le \Delta t_{\max}$ (if configured) | `EXCEEDS_MAX_INTERVAL` |
| **Spatial Overlap Ratio** | $\text{Ratio}_{\text{overlap}} \ge \text{Threshold}_{\min}$ | `INSUFFICIENT_OVERLAP` |
| **Sensor Match** | $\text{Sensor}_1 == \text{Sensor}_2$ (if required) | `INCOMPATIBLE_SENSOR` |
| **Platform Match** | $\text{Platform}_1 == \text{Platform}_2$ (if required) | `INCOMPATIBLE_PLATFORM` |

### Temporal Separation Semantics (Strict Positivity & Min Gap)

> [!IMPORTANT]
> 1. **Strict Positivity ($T_{\text{later}} > T_{\text{earlier}}$)**:
>    - Observations with identical acquisition timestamps ($T_{\text{later}} = T_{\text{earlier}}$) can **never** form a valid temporal before/after pair.
>    - A temporal pair models a physical transition across time; zero-second separation is explicitly rejected with status `IDENTICAL_TIMESTAMPS`.
> 2. **Semantics of `min_temporal_separation_seconds = 0.0`**:
>    - Setting minimum separation to `0.0` (or `--min-days 0.0`) denotes *no additional minimum gap* beyond strict chronological progression ($T_{\text{later}} > T_{\text{earlier}}$).
>    - It does **not** permit zero-duration pairs. Any pair where $T_{\text{later}} = T_{\text{earlier}}$ is immediately rejected.
> 3. **Contractual & Model Validation Guarantee**:
>    - The `ScenePair` Pydantic model enforces via class validation that any pair with `compatibility.is_compatible = True` must have strictly positive temporal separation ($T_{\text{later}} > T_{\text{earlier}}$).

### Cross-Sensor Compatibility
Cross-sensor pairs (e.g. Sentinel-2 MSI at $T_1$ and Landsat-8 OLI at $T_2$) are permitted by default with `is_cross_sensor = True` and explicit explanatory diagnostic notes, unless `require_same_sensor = True` is passed.

---

## 6. Deterministic Pair IDs

ASTRA prohibits random UUIDs for temporal pairs. All pair IDs are generated deterministically:

$$\text{pair\_id} = \text{"pair\_"} + \text{obs\_earlier.observation\_id} + \text{"\_\_"} + \text{obs\_later.observation\_id}$$

Given identical input manifests and configuration, the pair IDs, pair ordering, and validation statuses are guaranteed to be bit-identical across runs and operating systems.

---

## 7. CLI Usage

Index scanning and pair evaluation can be executed via `scripts/build_temporal_catalog.py`:

```bash
# Basic catalog discovery and pairing with default 0.5 IoU threshold
.\.venv\Scripts\python.exe scripts/build_temporal_catalog.py

# Require minimum 30 days separation and same sensor
.\.venv\Scripts\python.exe scripts/build_temporal_catalog.py --min-days 30 --require-same-sensor

# Verbose mode with diagnostic details
.\.venv\Scripts\python.exe scripts/build_temporal_catalog.py -v
```

---

## 8. Deferred Capabilities (M4B, M4C, M4D)

The following capabilities are intentionally out of scope for M4A:
- **Pixel-Level Co-Registration & Resampling**: Adjusting spatial offsets or differing grid pixel scales across sensors (deferred to M4B).
- **Difference Algorithms**: NDVI delta, spectral angle mapper, deep visual feature cosine distance (deferred to M4B).
- **Change Segmentation**: Generating polygon boundaries or rasters of detected physical modifications (deferred to M4C).
- **Interactive UI**: Time-slider before/after swipe controls on the dashboard (deferred to UI phase).
