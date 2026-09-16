# ASTRA Change Classification: Semantic Rule Engine (Phase M4C-B)

## 1. Purpose & Pipeline Role

Phase **M4C-B** is ASTRA's deterministic, explainable **Change-Type Classification Layer**. It translates low-level multi-modal features extracted by Phase M4C-A into five operational semantic change categories:

1. `construction`
2. `clearance`
3. `water_extent_change`
4. `road_development`
5. `unknown`

```
+-----------------------------------------------------------------------------------+
| Phase M4A: Temporal Observation Ingestion & Scene Pairing                         |
+-----------------------------------------------------------------------------------+
                                         │
                                         ▼
+-----------------------------------------------------------------------------------+
| Phase M4B: Continuous Pixel Differencing & ChangeRegion Extraction                |
+-----------------------------------------------------------------------------------+
                                         │
                                         ▼
+-----------------------------------------------------------------------------------+
| Phase M4C-A: Deterministic Feature/Evidence Extraction (Morphology, Spectral, Ctx)|
+-----------------------------------------------------------------------------------+
                                         │
                                         ▼
+-----------------------------------------------------------------------------------+
| Phase M4C-B: [CURRENT SUBPHASE] Deterministic Semantic Classification             |
+-----------------------------------------------------------------------------------+
                                         │
                                         ▼
+-----------------------------------------------------------------------------------+
| Phase M4D: [FUTURE SUBPHASE] False-Alarm Suppression (Cloud, Shadow, Haze, Jitter)|
+-----------------------------------------------------------------------------------+
```

> [!IMPORTANT]
> **M4C-B ARCHITECTURAL BOUNDARIES**:
> - M4C-B evaluates **what the change looks like** based strictly on observable geometry, spectral reflectance, and context contrast.
> - It does **NOT** attempt to filter false alarms caused by illumination changes, seasonal grass drying, or cloud shadows (strictly reserved for **Phase M4D**).
> - It does **NOT** query external foundation models or black-box neural networks.
> - "Unknown" is a primary, first-class category, not a fallback failure.

---

## 2. Three-Stage Evidentiary Decision Network

The classifier implements an auditable three-stage evidentiary pipeline:

```
                  ChangeRegionFeatures (from M4C-A)
                                  │
                                  ▼
        ┌───────────────────────────────────────────────────┐
        │ Stage 1: Eligibility & Physical Band Gating       │
        │ - Check minimum region size (area_px >= 10)       │
        │ - Identify calibrated multispectral vs. RGB       │
        └─────────────────────────┬─────────────────────────┘
                                  │
                                  ▼
        ┌───────────────────────────────────────────────────┐
        │ Stage 2: Multi-Modal Category Evidentiary Scoring │
        │ For each candidate c in [CONSTRUCTION, CLEARANCE, │
        │                          WATER, ROAD]:            │
        │   - Evaluate domain rules (Geometry, Spectral,    │
        │     Context)                                      │
        │   - Compute normalized evidence score S(c) in[0,1]│
        │   - Apply negative disqualifiers                  │
        └─────────────────────────┬─────────────────────────┘
                                  │
                                  ▼
        ┌───────────────────────────────────────────────────┐
        │ Stage 3: Arbitration, Conflict & Confidence       │
        │ - Select top candidate c* = argmax S(c)           │
        │ - Verify minimum threshold S(c*) >= 0.45          │
        │ - Verify ambiguity margin S(c*) - S(runner_up)    │
        │   >= 0.15                                         │
        │ - If margin fails -> UNKNOWN (is_ambiguous=True)  │
        │ - Assign ConfidenceTier: HIGH / MEDIUM / LOW      │
        └───────────────────────────────────────────────────┘
```

---

## 3. Semantic Category Rules & Formulations

### A. Construction (`construction`)
- **Intent**: Man-made structures, foundation pouring, building development, industrial installations.
- **Rules Evaluated**:
  1. `rule_const_geom_rectangularity` (weight: 30): $\text{rectangularity} \ge 0.60$.
  2. `rule_const_geom_compactness` (weight: 15): $\text{compactness} \ge 0.20$.
  3. `rule_const_geom_non_linear` (weight: 15): $\text{linearity\_score} \le 0.65$ and $\text{aspect\_ratio} \le 4.0$.
  4. `rule_const_spec_brightness_increase` (weight: 25): $\text{brightness\_delta} > 0.05$ (concrete/metal/roof reflectance).
  5. `rule_const_ctx_contrast` (weight: 15): $\text{region\_to\_background\_contrast} \ge 0.15$.
- **Disqualifiers**:
  - `disqual_const_water_presence` (-50): $\text{water\_spectral\_criterion\_fraction} > 0.30$.
  - `disqual_const_extreme_elongation` (-40): $\text{linearity\_score} > 0.85$ and $\text{aspect\_ratio} > 6.0$.
  - `disqual_const_no_brightness_increase` (-35): $\text{brightness\_delta} \le 0.0$ or unavailable (absence of positive reflectance increase disqualifies building construction).

### B. Clearance (`clearance`)
- **Intent**: Tree clearing, deforestation, vegetation removal, topsoil exposure.
- **Rules Evaluated**:
  1. `rule_clear_spec_ndvi_decline` (weight: 45): $\Delta \text{NDVI} \le -0.15$ (when multispectral).
  2. `rule_clear_spec_post_ndvi_low` (weight: 15): $\text{post\_ndvi} \le 0.25$ (bare ground).
  3. `rule_clear_spec_rgb_brightness_proxy` (weight: 35): $\text{brightness\_delta} > 0.05$ (RGB bare soil proxy).
  4. `rule_clear_geom_non_linear` (weight: 20): $\text{linearity\_score} \le 0.70$.
  5. `rule_clear_geom_organic_shape` (weight: 10): $\text{rectangularity} \le 0.85$.
  6. `rule_clear_ctx_isolated` (weight: 10): $\text{surrounding\_mean\_change} \le 0.30$.
- **Disqualifiers**:
  - `disqual_clear_vegetation_gain` (-60): $\Delta \text{NDVI} > 0.05$ (re-greening strictly violates clearance).
  - `disqual_clear_water_presence` (-50): $\text{water\_spectral\_criterion\_fraction} > 0.35$.
  - `disqual_clear_linear_corridor` (-40): $\text{linearity\_score} > 0.80$ and $\text{aspect\_ratio} > 5.0$ (corridor morphology disqualifies broad areal clearance).

### C. Water Extent Change (`water_extent_change`)
- **Strict Physical Policy**: Water extent change **strictly requires calibrated Green and NIR bands**.
- If wavelength metadata is missing (e.g. RGB imagery), water scoring yields $0.0$, preventing dark asphalt or shadow hallucination.
- **Rules Evaluated (When Bands Available)**:
  1. `rule_water_spec_criterion_fraction` (weight: 55): $\text{water\_spectral\_criterion\_fraction} \ge 0.40$.
  2. `rule_water_spec_mean_ndwi` (weight: 25): $\text{ndwi\_mean} \ge 0.10$.
  3. `rule_water_uniformity` (weight: 20): $\text{score\_std} \le 0.25$.
- **Disqualifiers**:
  - `disqual_water_high_vegetation` (-50): $\text{post\_ndvi} > 0.30$.

### D. Road Development (`road_development`)
- **Intent**: Linear transportation corridors, access tracks, highway grading.
- **Rules Evaluated**:
  1. `rule_road_geom_linearity` (weight: 35): $\text{linearity\_score} \ge 0.75$.
  2. `rule_road_geom_elongation` (weight: 25): $\text{aspect\_ratio} \ge 5.0$ or $\text{axis\_ratio} \ge 5.0$.
  3. `rule_road_geom_corridor_length` (weight: 15): $\text{major\_axis\_length} \ge 40.0\text{ px}$.
  4. `rule_road_geom_corridor_width_bounded` (weight: 15): $\text{minor\_axis\_length} \le 30.0\text{ px}$.
  5. `rule_road_ctx_contrast` (weight: 10): $\text{region\_to\_background\_contrast} \ge 0.10$.
- **Disqualifiers & Penalties**:
  - `disqual_road_missing_context` (-50): Flanking terrain context unavailable; elongated geometry alone is insufficient for road classification.
  - `penalty_road_negligible_contrast` (-20): Corridor lacks visible contrast with flanking terrain ($< 0.05$).
  - `disqual_road_water_canal` (-60): $\text{water\_spectral\_criterion\_fraction} > 0.35$ (canal/ditch, not roadway).
  - `disqual_road_excessive_width` (-40): $\text{minor\_axis\_length} > 45.0\text{ px}$ (massive clearing, not corridor).
  - `disqual_road_compact_blob` (-50): $\text{compactness} > 0.50$ and $\text{aspect\_ratio} < 2.5$.

### E. Unknown (`unknown`)
- **Assigned When**:
  1. Size is insufficient: $\text{area\_px} < 10\text{ px}$.
  2. Required spectral modality is unavailable: $\text{spectral.available} = \text{False}$.
  3. Top evidence score is insufficient: $S(c^*) < 0.45$.
  4. Evidence is ambiguous: $S(c^*) - S(c_{\text{runner-up}}) < 0.15$, with both candidates $\ge 0.45$.

---

## 4. Construction vs. Clearance Arbitration

| Characteristic | Construction | Clearance |
|---|---|---|
| **Dominant Signal** | Geometric rectangularity & structural brightness | Spectral vegetation loss & soil exposure |
| **Rectangularity** | $\ge 0.60$ (typically $\ge 0.75$) | Variable or organic ($< 0.60$) |
| **Edges** | Straight, sharp corners, cohesive footprint | Irregular, dendritic, or parcel-shaped |
| **Context** | Distinct contrast against surrounding terrain | Moderate contrast |

**Arbitration Rule**: If vegetation is removed over an area that exhibits high rectangularity ($\ge 0.75$) and sharp structural brightness, it is classified as `construction` (building site prep / foundation). If rectangularity is lower or boundaries are natural/organic, it is classified as `clearance`.

---

## 5. Confidence Tiers & Evidence Scores

Evidence scores $S(c) \in [0.0, 1.0]$ are **uncalibrated evidence alignment metrics**, calculated as normalized rule weights minus penalties. They are explicitly **heuristics** and **not** Bayesian posterior probabilities or empirical statistical certainties.

> [!NOTE]
> All threshold values in `ClassifierConfig` are documented engineering heuristics intended to provide a deterministic, auditable baseline for satellite change interpretation. They have not been empirically fitted against labelled ground-truth distributions.

Downstream consumers rely on stratified **Confidence Tiers**:
- **`HIGH`**: Calibrated multispectral imagery + $S(c) \ge 0.75$ + margin $\ge 0.30$ + region size $\ge 25\text{ px}$.
- **`MEDIUM`**: $S(c) \ge 0.55$ + margin $\ge 0.18$.
- **`LOW`**: Uncalibrated RGB imagery only, or marginal score ($0.45 \le S(c) < 0.55$).
- **`UNCERTAIN`**: Standard for all `unknown` decisions.

---

## 6. Provenance & Reproducibility (ASTRA-DC-v0.1)

Every classification execution persists an immutable provenance record at:
`data/manifests/provenance/prov_cls_{hash}.json`

Recording:
- `provenance_id`: Deterministic hash ID
- `processing_stage`: `"change_type_classification"`
- `executed_by`: `"astra.ml.change_classification.classifier"`
- `parameters`:
  - `evidence_id`, `scene_pair_id`, `change_detection_result_id`
  - Complete classifier configuration and threshold dictionary
  - Input hashes from evidence document
  - Region count and category distribution
  - Artifact path: `data/change_classification/{id}/classification.json`
