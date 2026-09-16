# ASTRA Temporal Change Detection Engine (Phase M4B)

## 1. Overview & Architectural Role

Phase M4B introduces the **Reproducible Temporal Change Detection Engine** to ASTRA (Automated Semantic Tracking and Retrieval Architecture for SIH PS 227).

While **Phase M4A** establishes temporal metadata models, spatial overlap calculations, and deterministic scene pairing ($T_1 \le T_2$), **Phase M4B** answers the core question:
> *"Where did the satellite imagery actually change between earlier and later observations?"*

### Scope Boundaries & Roadmap
- **Phase M4A (Complete)**: Temporal observations, chronological ordering, spatial overlap calculation, and valid `ScenePair` formation.
- **Phase M4B (Current)**: Deterministic, reproducible, offline change detection yielding continuous score rasters, binary masks, connected change components, quantitative change metrics, and immutable provenance records.
- **Phase M4C (Future)**: Semantic change-type classification (e.g., vegetation loss, urban construction, water body shrinkage, road development).
- **Phase M4D (Future)**: False-alarm suppression (illumination compensation, cloud/shadow masking, coregistration jitter filtering).

---

## 2. Mathematical Formulation & Processing Pipeline

The change detection pipeline executes deterministically through six sequential stages:

```
+-----------------------------------------------------------------------+
| 1. Dual-Raster Ingestion & Spatial/Band Compatibility Check           |
|    - Verify identical dimensions: (H, W)                              |
|    - Align evaluated spectral bands (1 to C)                          |
+-----------------------------------------------------------------------+
                                  |
                                  v
+-----------------------------------------------------------------------+
| 2. Quality & Nodata Isolation                                         |
|    - Identify NaNs, Infs, and metadata nodata values                  |
|    - Construct valid_mask: bool[H, W]                                 |
+-----------------------------------------------------------------------+
                                  |
                                  v
+-----------------------------------------------------------------------+
| 3. Radiometric Normalization                                          |
|    - Robust Percentile (2%-98%) or Min-Max over valid pixels          |
|    - Map reflectance to normalized float32 in [0.0, 1.0]              |
+-----------------------------------------------------------------------+
                                  |
                                  v
+-----------------------------------------------------------------------+
| 4. Continuous Change Score Raster                                     |
|    - Band-averaged absolute difference:                               |
|      S(x, y) = (1/C) * sum_{c=1}^C |I_later(c, x, y) - I_earlier(c, x, y)| |
+-----------------------------------------------------------------------+
                                  |
                                  v
+-----------------------------------------------------------------------+
| 5. Thresholding & Binary Change Mask                                  |
|    - Statistical (mu + k*sigma), Percentile (p), or Fixed (tau)       |
|    - Raw mask: M_raw(x, y) = (S(x, y) >= tau) AND valid_mask(x, y)    |
+-----------------------------------------------------------------------+
                                  |
                                  v
+-----------------------------------------------------------------------+
| 6. Connected Component Labeling & Metric Extraction                   |
|    - 4- or 8-connectivity BFS clustering                              |
|    - Area filtering: suppress regions < minimum_region_area           |
|    - Compute pixel & WGS84 bounding boxes, centroids, scores          |
+-----------------------------------------------------------------------+
```

### Radiometric Normalization
Sensors, atmospheric transmission, and seasonal cycles produce reflectance variation across acquisitions. ASTRA provides two normalization strategies:
1. **Robust Percentile (`robust_percentile`, Default)**:
   For each spectral band $c$:
   $$p_{\text{low}} = \text{Percentile}(I_c[\text{valid}], 2.0), \quad p_{\text{high}} = \text{Percentile}(I_c[\text{valid}], 98.0)$$
   $$\tilde{I}_c(x, y) = \text{clip}\left(\frac{I_c(x, y) - p_{\text{low}}}{p_{\text{high}} - p_{\text{low}}}, 0.0, 1.0\right)$$
   This mitigates sensor saturation and localized glint artifacts.
2. **Min-Max Scaling (`min_max`)**:
   Linear scaling mapping $[\min(I_c), \max(I_c)]$ to $[0.0, 1.0]$.
3. **None (`none`)**:
   Preserves raw raster values, clipped to $[0.0, 1.0]$.

### Continuous Change Scoring
For an aligned pair with $C$ evaluated bands:
$$S(x, y) = \begin{cases}
\frac{1}{C} \sum_{c=1}^C |\tilde{I}_{\text{later}}(c, x, y) - \tilde{I}_{\text{earlier}}(c, x, y)| & \text{if } \text{valid\_mask}(x, y) = \text{True} \\
0.0 & \text{otherwise}
\end{cases}$$
$S(x, y) \in [0.0, 1.0]$ provides a smooth, unquantized representation of surface alteration.

### Threshold Selection
- **Statistical (`statistical`, Default)**:
  $$\tau = \mu_{\text{valid}} + k \cdot \sigma_{\text{valid}}$$
  Where $\mu_{\text{valid}}$ is the mean score of valid pixels, $\sigma_{\text{valid}}$ is the standard deviation, and $k$ is the configured multiplier (`threshold_std_multiplier`, default: 2.0).
- **Percentile (`percentile`)**:
  $\tau = \text{Percentile}(S_{\text{valid}}, P)$ (default $P = 95.0$).
- **Fixed (`fixed`)**:
  $\tau = \tau_{\text{fixed}}$ (default $\tau = 0.20$).

### Connected Component Analysis (CCL)
To distinguish real geographic alterations from isolated single-pixel sensor noise:
1. Pure-Python/NumPy deterministic BFS traverses pixels where $S(x, y) \ge \tau$.
2. Groups adjacent pixels via 4- or 8-connectivity.
3. Suppresses components whose pixel count $< A_{\min}$ (`minimum_region_area`, default: 20 pixels).
4. Retains valid components, assigning stable identifiers (`reg_0001`, `reg_0002`, ...), calculating:
   - Pixel count & estimated surface area ($m^2$)
   - Pixel bounding box $[r_{\min}, c_{\min}, r_{\max}, c_{\max}]$
   - Pixel centroid $[r_c, c_c]$
   - WGS84 bounding box and geographic centroid
   - GeoJSON polygon boundary
   - Mean and peak change score within the component.

---

## 3. Artifacts & Persistence Layout

Each change detection run creates a deterministic result bundle under `data/change_results/{result_id}/`:

```
data/
  change_results/
    res_chg_1a2b3c4d5e6f7a8b/
      result.json       # Complete ChangeDetectionResult contract
      score_map.npy     # Float32 continuous change score map [H, W]
      change_mask.png   # Uint8 binary mask (0 = unchanged, 255 = changed)
  manifests/
    provenance/
      prov_chg_1a2b3c4d5e6f7a8b.json  # ASTRA-DC-v0.1 Provenance Record
```

### Immutable Provenance Record
Conforming to `ASTRA-DC-v0.1`, every execution records:
- `provenance_id`: Deterministic hash (`prov_chg_...`)
- `processing_stage`: `"temporal_change_detection"`
- `executed_by`: `"astra.ml.change_detection"`
- `parameters`:
  - Algorithm name and version (`pixel_difference`, `1.0.0`)
  - Hyperparameters (`config`)
  - Summary metrics (`metrics`)
  - Input file cryptographic SHA-256 hashes
  - Output artifact references

---

## 4. API & CLI Interface

### REST API Endpoints

| Method | Route | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/change-detection/health` | Subsystem status, active algorithm version, count of stored results |
| `POST` | `/api/v1/change-detection/run` | Execute change detection on raw paths or a `ScenePair` |
| `GET` | `/api/v1/change-detection/{result_id}` | Retrieve JSON metrics and extracted regions |
| `GET` | `/api/v1/change-detection/{result_id}/mask` | Stream binary change mask PNG image |

#### Example Request: `POST /api/v1/change-detection/run`
```json
{
  "earlier_path": "data/tiles/t1_chip.tif",
  "later_path": "data/tiles/t2_chip.tif",
  "config": {
    "threshold_method": "statistical",
    "threshold_std_multiplier": 2.0,
    "minimum_region_area": 25,
    "connectivity": 8,
    "normalization_method": "robust_percentile"
  }
}
```

### CLI Tool: `scripts/run_change_detection.py`

```bash
python scripts/run_change_detection.py \
  --earlier data/scenes/t1.tif \
  --later data/scenes/t2.tif \
  --threshold-method statistical \
  --threshold-std 2.0 \
  --min-region-area 20 \
  --connectivity 8
```

---

## 5. Environmental Limitations & Caveats

The baseline pixel-difference engine is intentionally simple, deterministic, and fast, but exhibits known physical sensitivities:

1. **Illumination & Sun Angle**:
   Differences in solar elevation or azimuth between seasons cause differential building and topographic shadows.
2. **Atmospheric & Cloud Interference**:
   Translucent cirrus clouds, localized smoke, or haze can register as elevated change scores if not masked.
3. **Coregistration Jitter**:
   Sub-pixel spatial misalignments create thin linear boundary false alarms along high-contrast edges (e.g. coastlines, runways, highways).
4. **Phenological Cycles**:
   Natural seasonal greening/browning of vegetation generates radiometric change that does not represent structural land-use alteration.

> **Mitigation Note**: These limitations are explicitly addressed in subsequent phases:
> - **Phase M4C**: Semantic change classification disentangles phenological shifts from urban construction or deforestation.
> - **Phase M4D**: False-alarm suppression eliminates cloud, shadow, and illumination artifacts prior to downstream alerting.
