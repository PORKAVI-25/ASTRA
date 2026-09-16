# ASTRA Change Classification: Evidence Extraction Layer (Phase M4C-A)

## 1. Purpose & Core Objective

Phase M4C-A establishes ASTRA's deterministic, explainable **Feature/Evidence Extraction Layer**.

Upstream in the pipeline:
- **Phase M4A** forms valid, chronologically ordered `ScenePair` instances ($T_1 \le T_2$).
- **Phase M4B** detects pixel differences and segments them into coherent `ChangeRegion` objects.

Phase M4C-A consumes this pair and change detection output along with the underlying satellite imagery, extracting objective, measurable evidence across multiple feature families (spatial morphology, geometry, temporal progression, spectral response, and surrounding context).

> [!IMPORTANT]
> **M4C-A EXTRACTS EVIDENCE ONLY; IT DOES NOT CLASSIFY CHANGE TYPES.**
> - It does **NOT** assign semantic labels (`construction`, `clearance`, `water_extent_change`, `road_development`, `unknown`).
> - It does **NOT** generate classification confidence scores.
> - It does **NOT** train or evaluate machine learning models.
> - Interpretation and fusion of this evidence into semantic decisions is strictly reserved for **Phase M4C-B**.

---

## 2. Evidence Architecture & Families

The evidence extraction system decomposes evidence into five decoupled, explainable families:

```
+-----------------------------------------------------------------------------------+
|                            M4C-A ChangeEvidence Document                          |
+-----------------------------------------------------------------------------------+
  |
  +---> 1. Temporal Progression Evidence
  |     - Earlier and later UTC timestamps
  |     - Exact temporal delta (seconds, hours, days)
  |     - Sensor, platform, and cross-sensor status
  |
  +---> 2. Spatial Geometry & Morphology Evidence (Per Region)
  |     - Area, width, height, aspect ratio, perimeter
  |     - Compactness (isoperimetric quotient), rectangularity
  |     - Linearity proxy & axis ratio via 2D spatial image moments
  |     - Orientation angle [-90°, 90°], component density, shape regularity
  |     - Geospatial coordinates (centroid, WGS84 bbox, metric area)
  |
  +---> 3. Change Magnitude Evidence (Per Region)
  |     - Mean change score, peak change score, score standard deviation
  |     - Fraction of overall scene change accounted for by this region
  |
  +---> 4. Spectral & Radiometric Evidence (Per Region)
  |     - Earlier and later regional mean values per spectral band
  |     - Per-band deltas (later - earlier) and absolute deltas
  |     - Physical indices (NDVI, NDWI) *only if band metadata is explicitly established*
  |     - Measurable water spectral criterion fraction
  |
  +---> 5. Local Neighborhood Context Evidence (Per Region)
        - Surrounding buffer ring around region (excluding changed pixels)
        - Background reflectance and contrast with immediate neighborhood
```

---

## 3. Spatial Morphology & Geometry Features

For every discrete `ChangeRegion`, morphology and geometry features are calculated analytically:

1. **Aspect Ratio**:
   $$\text{aspect\_ratio} = \frac{\max(\text{width}, \text{height})}{\max(1, \min(\text{width}, \text{height}))} \ge 1.0$$
2. **Boundary Perimeter**:
   Exact count of discrete 4-connected boundary pixels (pixels in the region having at least one 4-neighbor outside the component or at the image border).
3. **Compactness**:
   $$\text{compactness} = \min\left(1.0, \frac{4 \pi \cdot \text{area}}{\text{perimeter}^2}\right) \in [0.0, 1.0]$$
   For continuous planar domains, the isoperimetric inequality guarantees $4\pi A / P^2 \le 1.0$. On a discrete pixel grid where perimeter is measured by boundary pixel count, corners are counted once ($P < 2(W+H)$ for rectangles), so the raw discrete ratio can exceed $1.0$ for small components (e.g., an isolated $1\times 1$ pixel has $A=1, P=1 \implies 4\pi \approx 12.57$). The extractor clamps the returned value to $[0.0, 1.0]$.
4. **Rectangularity**:
   $$\text{rectangularity} = \frac{\text{area}}{\text{width} \times \text{height}} \in (0.0, 1.0]$$
   Measures how completely the change component fills its minimum bounding box.
5. **Linearity Proxy & Principal Axes via 2D Spatial Moments**:
   From pixel coordinates $(r_i, c_i)$, Cartesian relative offsets $x_i = c_i - \bar{c}$ (horizontal, pointing East) and $y_i = -(r_i - \bar{r})$ (vertical, pointing North) are used to compute central moments $\mu_{xx}, \mu_{yy}, \mu_{xy}$.
   Eigenvalues $\lambda_1 \ge \lambda_2 \ge 0$ of the spatial covariance tensor yield:
   - Major axis length: $4 \sqrt{\lambda_1}$
   - Minor axis length: $4 \sqrt{\lambda_2}$
   - Axis ratio: $\lambda_1 / \max(10^{-6}, \lambda_2)$
   - **Linearity Score**:
     $$\text{linearity} = \frac{\lambda_1 - \lambda_2}{\lambda_1 + \lambda_2} \in [0.0, 1.0]$$
   - **Orientation**:
     $$\theta = \frac{1}{2} \text{atan2}(2\mu_{xy}, \mu_{xx} - \mu_{yy}) \times \frac{180}{\pi} \in [-90^\circ, 90^\circ]$$
     Angle of the principal major axis relative to the horizontal axis ($0.0^\circ$ for horizontal East-West, $90.0^\circ$ for vertical North-South, $+45.0^\circ$ for SW-NE diagonal, $-45.0^\circ$ for NW-SE diagonal).

> [!CAUTION]
> **Morphology Alone Cannot Establish Road Development**:
> An elongated geometry ($\text{linearity} \approx 0.95$) may represent a newly constructed highway, a runway, a drainage canal, an agricultural boundary hedge, or a building shadow artifact. M4C-A reports the numerical linearity proxy; M4C-B will combine it with spectral, temporal, and context evidence before drawing conclusions.

---

## 4. Temporal Progression Rigor

Temporal evidence preserves exact chronological definitions established in Phase M4A:
- Timestamps are normalized UTC representations.
- Temporal separation is strictly positive ($T_{\text{later}} > T_{\text{earlier}}$).
- Both fractional days and fractional hours are exposed without reinterpretation or heuristic truncation.

---

## 5. Spectral Features & Band Metadata Policy

Physical reflectance indices are strictly guarded:
- **Generic Band Statistics**: In all cases, per-band means, deltas ($\bar{I}_{\text{later}} - \bar{I}_{\text{earlier}}$), and absolute deltas are computed.
- **Strict Physical Index Policy**:
  - `ndvi_mean` is computed **only** when NIR and Red bands are explicitly mapped (via metadata or explicit configuration).
  - `ndwi_mean` is computed **only** when Green and NIR bands are explicitly mapped.
  - **Index Calculation Semantics**: Indices are computed as the mean of per-pixel index scores ($\frac{1}{N}\sum_{i=1}^N \text{Index}_i$) across all mutually valid regional pixels with guarded denominators ($\epsilon = 10^{-6}$), preserving local pixel contrast across heterogeneous change patches.
  - **Nodata & Invalid Pixel Exclusion**: Any pixel with NaN, Inf, or metadata-defined nodata value in either the earlier or later observation is strictly excluded prior to calculating band statistics or spectral indices.
  - If bands are arbitrary or uncalibrated RGB, indices are marked `available = False` with `unavailability_reason = "NIR and Red bands not explicitly identified in metadata or configuration"`.
  - Under no circumstances does ASTRA fabricate a physical index from arbitrary RGB channels.

---

## 6. Water-Related Measurable Evidence

When Green and NIR bands are established:
- Calculates the measurable fraction of region pixels where $\text{NDWI} > \tau_{\text{water}}$ (`water_criterion_threshold`, default: 0.0).
- Exposes criterion, cutoff threshold, input bands, and configuration version.
- Does **not** classify whether the region is water; provides the numerical fraction for M4C-B to evaluate.

---

## 7. Local Neighborhood Context Evidence

To determine whether a change stands out from its local surroundings:
- Evaluates a configurable outer buffer ring (default: 15 pixels) around the region.
- Strictly masks out all changed pixels to isolate the **unchanged local background**.
- Calculates:
  - `surrounding_mean_change`: Background score map intensity.
  - `region_to_background_contrast`: $|\text{region\_mean\_score} - \text{surrounding\_mean\_score}|$.
  - Local background reflectance per band.
- If fewer than `min_valid_context_pixels` (default: 10) unchanged background pixels exist, marks the context as `available = False`.

---

## 8. Determinism & Provenance

- **Feature IDs**: Every atomic feature has a deterministic identifier: `feat_{region_id}_{feature_name}`.
- **Evidence Document ID**: Derived from SHA-256 hashing of `scene_pair_id`, `change_detection_result_id`, extractor ID/version, and region count.
- **Immutable Provenance**: Persists `data/manifests/provenance/prov_evi_{hash}.json` tracking input image hashes, configuration parameters, region counts, and artifact paths adhering to `ASTRA-DC-v0.1`.

---

## 9. API & CLI Interface

### REST API Endpoints
- `GET /api/v1/change-classification/health`: Subsystem health and count of stored evidence documents.
- `POST /api/v1/change-classification/evidence`: Execute evidence extraction and persist structured JSON.
- `GET /api/v1/change-classification/evidence/{evidence_id}`: Retrieve stored evidence document.

### CLI Tool
```bash
python scripts/extract_change_evidence.py \
  --result-id res_chg_1a2b3c4d5e6f \
  --earlier data/scenes/t1.tif \
  --later data/scenes/t2.tif
```

---

## 10. Roadmap: Relation to M4C-B & M4D

```
+---------------------------+
| Phase M4A: Scene Pairing  |
+---------------------------+
              |
              v
+---------------------------+
| Phase M4B: Change Detect  |
+---------------------------+
              |
              v
+---------------------------+
| Phase M4C-A: Evidence     | <--- [CURRENT SUBPHASE]
| (Extracts metrics only)   |
+---------------------------+
              |
              v
+---------------------------+
| Phase M4C-B: Classifier   | <--- [NEXT SUBPHASE: Fuses evidence into semantic labels]
| (Construction, Clearance, |
|  Road, Water, Unknown)    |
+---------------------------+
              |
              v
+---------------------------+
| Phase M4D: False-Alarm    | <--- [FUTURE: Illumination, cloud, and shadow filtering]
| Suppression               |
+---------------------------+
```
