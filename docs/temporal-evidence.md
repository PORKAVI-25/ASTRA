# ASTRA Phase M4E: Earliest Supporting Observation & Temporal Evidence Chain

## 1. Purpose

The Earliest Supporting Observation and Temporal Evidence Chain module (Phase M4E) provides a deterministic, explainable, offline-first temporal evidence reasoner downstream of False-Alarm Suppression (Phase M4D).

Given a reviewed candidate change region from a multi-temporal satellite observation series, Phase M4E addresses the following core questions:
1. **Earliest Supporting Observation**: What is the chronologically earliest satellite observation in the series that provides valid, verified supporting evidence that the candidate change was physically present?
2. **Pre-Change Absence**: Can absence prior to the change be positively established, bounding when the physical onset occurred?
3. **Temporal Onset Interval**: What is the bounded half-open temporal interval $(T_{\text{pre}}, T_{\text{earliest}}]$ during which the change event began?
4. **Temporal Persistence**: Does supporting evidence persist across subsequent observations ($N_{\text{support}} \ge \text{min\_persistent}$), confirming a true change rather than transient noise?
5. **Category Evolution**: How did the semantic classification (from Phase M4C-B) evolve over time without re-inferring or modifying classification logic?
6. **Immutable Provenance**: What is the complete upstream lineage across all evaluated scene pairs, detection results, and suppression screenings?

M4E is strictly an **orchestration and reasoning layer**. It never accesses raw imagery, recomputes differencing, or runs ML models.

---

## 2. Architecture & Pipeline

```
Phase M4A: TemporalSeries & ScenePairs (O1, O2, O3, ..., On)
    │
    ▼
Phase M4B: ChangeDetectionResult (ChangeRegions, mean_change_score)
    │
    ▼
Phase M4C-A: ChangeEvidence (spatial, spectral, context, temporal)
    │
    ▼
Phase M4C-B: ChangeClassificationResult (category, evidence_score, tier)
    │
    ▼
Phase M4D: SuppressionResult (RETAINED, FLAGGED, SUPPRESSED, INSUFFICIENT_EVIDENCE)
    │
    ▼
════════════════════════════════════════════════════════════════════════
Phase M4E: Temporal Evidence Reasoner
  ├── Chronology Engine (strictly ascending validation, duplicate epoch audit)
  ├── Multi-Pair Lineage Alignment (anchored to candidate discovery pair)
  ├── Observation Node Evaluator (strict M4D authority, positive pre-change absence)
  ├── Metric Spatial Correspondence (WGS84 projected bbox IoU in m²)
  ├── Timeline & Trajectory Reasoner (earliest support gate, persistence, onset interval)
  └── Provenance & Persistence (deterministic content hash, real scene IDs)
════════════════════════════════════════════════════════════════════════
    │
    ▼
TemporalEvidenceResult (JSON) & ProvenanceRecord (JSON)
```

---

## 3. Multi-Pair Upstream Lineage

M4E evaluates observations across an ordered `TemporalSeries`. Every evaluated pair retains its full upstream lineage:
- `scene_pair_id`: Unique identifier of the scene pair.
- `change_detection_result_id`: Upstream M4B change detection result.
- `evidence_id`: Upstream M4C-A feature extraction result.
- `classification_id`: Upstream M4C-B classification result (when available).
- `suppression_id`: Upstream M4D false-alarm screening result.

```python
class PairwiseTemporalEvidenceInput(BaseModel):
    scene_pair_id: str
    change_detection_result_id: str
    evidence_id: str
    classification_id: Optional[str] = None
    suppression_id: str
    suppression_result: Optional[SuppressionResult] = None
    change_detection_result: Optional[ChangeDetectionResult] = None
    evidence: Optional[ChangeEvidence] = None
    classification: Optional[ChangeClassificationResult] = None
```

The discovery pair (`discovery_pair_evidence`) is mandatory and defines the initial detection epoch. Subsequent pairwise inputs (`pairwise_evidence`) capture temporal persistence.

---

## 4. Candidate Anchoring & Discovery Pair Consistency

Candidate regions are identified by `CandidateRegionRef`:
- `scene_pair_id`: Must match `discovery_pair_evidence.scene_pair_id`.
- `change_detection_result_id`: Must match `discovery_pair_evidence.change_detection_result_id`.
- `region_id`: Region identifier scoped to the parent change detection result.

Region IDs are **never** treated as globally unique across different detection runs. If the discovery pair IDs disagree with the candidate reference, the evaluation is immediately rejected with HTTP 422 or `ValueError`.

---

## 5. $S_{\text{chg}}$ — Strict Source of Truth

The change magnitude score $S_{\text{chg}}$ is strictly defined as:
$$S_{\text{chg}} \equiv \text{ChangeRegion.mean\_change\_score}$$

- M4C-A mirrors this value as `ChangeRegionFeatures.change_score["mean"]`.
- M4E **never** loads raster GeoTIFF imagery, runs differencing, inspects pixels, or recalculates spectral deltas.
- **Strict Semantics**: $S_{\text{chg}} = 0.0$ is assigned **only** when a valid upstream M4B `ChangeDetectionResult` was evaluated and explicitly contains no candidate-corresponding `ChangeRegion`.
- If an M4B result is missing, unavailable, or malformed, $S_{\text{chg}}$ is **not** zero; the node transitions to `INSUFFICIENT_DATA`. Missing data is never converted into a zero measurement.

---

## 6. M4D Authority & Gating Semantics

M4E strictly respects the upstream Phase M4D suppression decision without override:

| M4D Decision | Support Multiplier ($G_{\text{M4D}}$) | Eligible for Earliest Support? | Node Status |
| :--- | :---: | :---: | :--- |
| `RETAINED` | $1.00$ | **Yes** (if score $\ge \tau_{\text{support}}$) | `EARLIEST_SUPPORTING` or `PERSISTENT_SUPPORT` |
| `FLAGGED` | $0.40$ (discounted audit) | **No** (never earliest support) | `FLAGGED_SUPPORT` |
| `SUPPRESSED` | $0.00$ | **No** (never earliest support) | `SUPPRESSED_ARTIFACT` |
| `INSUFFICIENT_EVIDENCE` | $0.00$ | **No** (never earliest support) | `INSUFFICIENT_DATA` |

`SUPPRESSED`, `INSUFFICIENT_EVIDENCE`, and `FLAGGED` observations can **never** become the earliest supporting observation.

---

## 7. Heuristic Support Score Formulation

> [!IMPORTANT]
> The temporal support score $S_{\text{support}}$ is an **uncalibrated, non-probabilistic audit index**. It must **NEVER** be interpreted or represented as a probability or likelihood.

The score is calculated deterministically as:
$$S_{\text{raw}} = w_{\text{spatial}} \times L_{\text{sensor}} \times \left(0.40 \times S_{\text{chg}} + 0.60 \times (S_{\text{cls}} \times w_{\text{tier}})\right)$$
$$S_{\text{support}} = G_{\text{M4D}} \times S_{\text{raw}}$$

Where:
- $w_{\text{spatial}} = \text{iou\_wgs84}$ (or $0.50$ for centroid-only matches).
- $L_{\text{sensor}} = 0.85$ for uncalibrated cross-sensor pairings, $1.00$ for same-sensor pairings.
- $w_{\text{tier}} \in \{1.00 \text{ (high)}, 0.70 \text{ (medium)}, 0.40 \text{ (low)}, 0.20 \text{ (uncertain)}\}$.
- Default minimum support threshold: $\tau_{\text{support}} = 0.45$.

---

## 8. Positive Pre-Change Absence Verification

Pre-change absence (`PRE_CHANGE_ABSENCE`) is never assumed from missing detections. It requires explicit positive evidence:
1. **Spatial Coverage**: The candidate bounding box must intersect and be covered by the pre-change observation footprint.
2. **Positively Recorded Cloud Fraction**: Observation metadata must explicitly report cloud cover, with $\text{cloud\_fraction} \le 0.10$ ($10\%$).
3. **Positively Recorded Valid Pixel Ratio**: Observation metadata must explicitly report valid pixel ratio, with $\text{valid\_pixel\_ratio} \ge 0.90$ ($90\%$).
4. **M4D Screening**: Upstream screening provides no obstruction.
5. **Detection Contrast**: Valid upstream pairwise evidence establishes change appearing at the later endpoint.

If quality metadata is missing, the observation becomes `INSUFFICIENT_DATA`—missing metadata is **never** inferred as clear.

---

## 9. Spatial Correspondence & Metric Bounding Box IoU

To prevent spatial distortion, M4E strictly decouples **HOW** geometry was compared from **WHAT** topological relationship was observed:

- **Geometric Comparison Status** (`SpatialCorrespondenceStatus`):
  - `EXACT_PIXEL_GRID`: Requires identical CRS, matching GSD ($\le 1\%$), transform origin, and square pixel geometry.
  - `GEOREFERENCED_BBOX`: Axis-aligned bounding boxes reprojected into a local metric projection (UTM or planar equirectangular) to compute IoU in $m^2$.
  - `GEOREFERENCED_CENTROID_ONLY`: Haversine geodesic distance in meters.
  - `DISJOINT`: Non-overlapping footprints.
  - `INSUFFICIENT_METADATA`: Missing coordinates.

> [!CAUTION]
> IoU is **never calculated in longitude/latitude degree space**, as degree areas vary with latitude ($\cos(\text{lat})$ scaling). Furthermore, metric IoU represents **bounding-box overlap**, not pixel-mask or polygon overlap.

- **Topological Relationship** (`CorrespondenceRelationship`):
  - `NONE`, `MATCHED`, `SPLIT`, `MERGED`, `AMBIGUOUS`.

---

## 10. Temporal Onset Interval Mathematics

Physical change onset is bounded as a **half-open interval**:
$$(T_{\text{pre}}, T_{\text{earliest}}]$$

Because the physical event could have occurred at any moment immediately after the confirmed clear pre-change observation up to and including the earliest supporting observation, the interval is open on the left and closed on the right.

- **Interval Types**:
  - `BOUNDED_HALF_OPEN`: $(T_{\text{pre}}, T_{\text{earliest}}]$ when pre-change absence is verified.
  - `LEFT_UNBOUNDED`: $(-\infty, T_{\text{earliest}}]$ when earliest support exists without verified prior absence.
  - `UNRESOLVED`: When earliest support cannot be established.
- **Display Observation Span**: Reported separately as $[T_{\text{pre}}, T_{\text{earliest}}]$ for user presentation.

---

## 11. Category Authority & Evolution

M4E does not perform change classification. The observed category is taken directly from Phase M4C-B `RegionClassification.category`.

- If M4C-B is omitted: `category_observed = None`.
- M4E audits temporal transitions across supporting nodes:
  - `unknown` $\to$ `construction`: Valid (initial surface clearing before structural features emerge).
  - `clearance` $\to$ `construction`: Valid (vegetation clearance followed by building construction).
  - `water_extent_change` $\leftrightarrow$ `construction`: Incompatible on the same footprint $\implies$ flags `TEMPORALLY_AMBIGUOUS`.

---

## 12. Provenance & Deterministic Hashing

Results are uniquely and deterministically identified via SHA-256 hashing:
- Hash seed components:
  1. `series_id`
  2. Canonical candidate reference (`{scene_pair_id}:{cdr_id}:{region_id}`)
  3. `evaluator_id` & `evaluator_version`
  4. Canonical JSON configuration string
  5. Sorted evaluated `scene_pair_ids`
  6. Sorted evaluated `suppression_ids`
  7. Sorted upstream SHA-256 artifact hashes

- **Geospatial Provenance Integrity**:
  - `source_scene_id`: Guaranteed to be an actual satellite `scene_id` (never a composite pair ID or suppression ID).
  - Full multi-pair parameters are captured in `ProvenanceRecord.parameters`.
  - Stored under `data/manifests/provenance/prov_tem_{hash}.json`.

---

## 13. REST API Reference

Mounted under `/api/v1/temporal-evidence/`:

### `POST /api/v1/temporal-evidence/evaluate`
Evaluates candidate temporal support across a temporal series and pairwise evidence.
- **Request Body**:
  ```json
  {
    "candidate_ref": {
      "change_detection_result_id": "cdr_pair_01",
      "scene_pair_id": "pair_01",
      "region_id": "reg_0001"
    },
    "series": { ... },
    "discovery_pair_evidence": { ... },
    "pairwise_evidence": [ ... ],
    "config_overrides": {
      "min_support_score_threshold": 0.50
    }
  }
  ```
- **Validation**: Unknown fields or invalid config keys return HTTP 422.
- **Response**: `TemporalEvidenceResult` with HTTP 200.

### `GET /api/v1/temporal-evidence/{result_id}`
Retrieves a previously evaluated and persisted result.

### `GET /api/v1/temporal-evidence/health`
Returns health check status and configuration defaults.

---

## 14. CLI Usage

The offline CLI tool is located at `scripts/evaluate_temporal_evidence.py`:

```bash
python scripts/evaluate_temporal_evidence.py \
  --manifest path/to/input_manifest.json \
  --output-dir data/temporal_evidence \
  --provenance-dir data/manifests/provenance \
  --min-support-threshold 0.45
```

The tool operates completely offline and writes both result JSON and provenance records.

---

## 15. Known Limitations

1. **Discrete Satellite Sampling**: Onset intervals reflect satellite overpass dates; exact physical moment of disturbance is unobservable.
2. **Cross-Sensor Spectral Shifts**: Radiometric equivalence between differing sensors (e.g. Sentinel-2 vs Landsat-8) is uncalibrated without physical surface reflectance normalization.
3. **Cloud Gaps**: Extended temporal gaps (> 90 days) increase onset interval uncertainty and cap confidence tiers.
4. **Bounding Box Approximation**: Metric IoU is calculated on axis-aligned bounding boxes, not polygon masks.
