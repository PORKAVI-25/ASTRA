# ASTRA Pipeline Orchestrator (Phase M4F)

## 1. Purpose

The `ASTRAPipelineOrchestrator` (`backend/orchestrator/service.py`) provides end-to-end deterministic coordination across all operational satellite change analysis modules in ASTRA:
- **Phase M4A**: Temporal Series & Scene Pairing
- **Phase M4B**: Pixel-Difference Change Detection
- **Phase M4C-A**: Multi-Modal Change Evidence Extraction
- **Phase M4C-B**: Deterministic Change-Type Classification
- **Phase M4D**: Conservative False-Alarm Suppression
- **Phase M4E**: Earliest Supporting Observation & Temporal Evidence Reasoning

The orchestrator operates as a modular monolith coordinator. It takes an explicit candidate change discovery reference on a multi-temporal satellite series and produces a fully populated, cryptographically ground-truth verifiable `InvestigationDossier` (`inv_{hash}`) and `ProvenanceRecord` (`prov_inv_{hash}`).

---

## 2. Architecture

```
                                InvestigationRequest
                                        │
                                        ▼
                   ┌─────────────────────────────────────────┐
                   │       ASTRAPipelineOrchestrator         │
                   └─────────────────────────────────────────┘
                                        │
                   1. Resolve Series (M4A TemporalCatalog)
                   2. Validate Discovery Pair
                   3. M4B Detection on Discovery Pair
                   4. Validate Candidate Region ID
                   5. Sequence Chronological Subsequent Pairs
                                        │
             ┌──────────────────────────┴──────────────────────────┐
             ▼                                                     ▼
     Discovery Pair                                      Subsequent Pairs (T3..TN)
   ┌─────────────────┐                                   ┌─────────────────────────┐
   │ M4B (Pre-run)   │                                   │ M4B Change Detection    │
   │ M4C-A Evidence  │                                   │ M4C-A Evidence          │
   │ M4C-B Classify  │                                   │ M4C-B Classify          │
   │ M4D Suppress    │                                   │ M4D Suppress            │
   └────────┬────────┘                                   └────────────┬────────────┘
            │                                                         │
            └──────────────────────────┬──────────────────────────────┘
                                       │
                                       ▼
                       PairwiseTemporalEvidenceInputs
                                       │
                                       ▼
                     Phase M4E TemporalEvidenceService
                    (Chronology, Absence, Onset, Nodes)
                                       │
                                       ▼
                             InvestigationDossier
                    (Dossier JSON, Lineage, Provenance)
```

---

## 3. Exact Execution Sequence

1. **Series Resolution**:
   - Matches `request.series_id` against the in-memory or discovered `TemporalCatalog`.
   - Halts with `InvestigationPipelineError` if `series_id` is missing.
2. **Discovery Pair Resolution & Validation**:
   - Resolves `request.discovery_pair_id` from registered known pairs or generates from series observations.
   - Verifies both earlier ($T_1$) and later ($T_2$) observation IDs belong to the requested series.
   - Rejects pairs belonging to another series or nonexistent pair IDs.
3. **Discovery Pair Change Detection**:
   - Delegates to `ChangeDetectionService.run_detection(pair=discovery_pair)`.
   - Emits `ChangeDetectionResult`, `score_map.npy`, and `change_mask.png`.
4. **Candidate Region Validation**:
   - Validates that `request.candidate_region_id` is present in `discovery_cdr.regions`.
   - Halts immediately if the candidate region is invalid.
5. **Chronological Pair Sequencing**:
   - Sorts series observations strictly by `(acquisition_time, observation_id)`.
   - Locates discovery epoch index $j$.
   - For all subsequent observations $k > j$, pairs them either adjacently ($O_{k-1} \to O_k$) or baseline-referenced ($O_{\text{base}} \to O_k$) according to `request.pairing_strategy`.
6. **Pairwise Upstream Execution**:
   - For discovery pair and every subsequent pair, sequentially runs:
     1. M4B: `ChangeDetectionService`
     2. M4C-A: `ChangeClassificationEvidenceService.extract_evidence`
     3. M4C-B: `ChangeClassificationEvidenceService.classify_evidence`
     4. M4D: `ChangeSuppressionService.suppress_false_alarms`
   - Preserves actual artifact IDs: `scene_pair_id`, `change_detection_result_id`, `evidence_id`, `classification_id`, `suppression_id`.
   - Aggregates upstream hashes into `lineage.upstream_hashes`.
7. **Temporal Evidence Reasoning (M4E)**:
   - Constructs `CandidateRegionRef(discovery_cdr_id, discovery_pair_id, candidate_region_id)`.
   - Invokes `TemporalEvidenceService.evaluate_temporal_evidence` with the discovery bundle and subsequent pairwise inputs.
   - Preserves onset interval $(T_{\text{pre}}, T_{\text{earliest}}]$, temporal support status, and trajectory nodes.
8. **Dossier & Provenance Assembly**:
   - Computes deterministic content hash: `inv_{16-hex}`.
   - Records deterministic `created_at` timestamp from latest observation.
   - Persists `dossier.json` to `data/investigations/inv_{hash}/dossier.json`.
   - Persists `prov_inv_{hash}.json` conforming to ASTRA-DC-v0.1.

---

## 4. Integration Boundaries & Contracts

| Upstream Module | Orchestrator Invocations | Outputs Handled |
| :--- | :--- | :--- |
| **M4A** | `catalog.get_series()`, `pair_observations()` | `TemporalSeries`, `ScenePair` |
| **M4B** | `ChangeDetectionService.run_detection()` | `ChangeDetectionResult` (`cdr_...`) |
| **M4C-A** | `evidence_service.extract_evidence()` | `ChangeEvidence` (`evi_...`) |
| **M4C-B** | `evidence_service.classify_evidence()` | `ChangeClassificationResult` (`cls_...`) |
| **M4D** | `suppression_service.suppress_false_alarms()` | `SuppressionResult` (`sup_...`) |
| **M4E** | `temporal_evidence_service.evaluate_temporal_evidence()` | `TemporalEvidenceResult` (`tem_...`) |

All domain boundaries use strict Pydantic v2 models (`ConfigDict(extra="forbid")`). No arbitrary dictionaries or unvalidated parameters cross boundaries.

---

## 5. Artifact Lineage

Every generated `InvestigationDossier` includes an immutable `lineage` payload:
- `scene_pair_ids`: `[pair_O1__O2, pair_O2__O3, ...]`
- `change_detection_result_ids`: `[cdr_pair_O1__O2, ...]`
- `evidence_ids`: `[evi_pair_O1__O2, ...]`
- `classification_ids`: `[cls_evi_pair_O1__O2, ...]`
- `suppression_ids`: `[sup_evi_pair_O1__O2, ...]`
- `temporal_evidence_id`: `tem_{hash}`
- `upstream_hashes`: complete cryptographic SHA-256 hashes of all input rasters, masks, and metadata.

---

## 6. Error Handling

Pipeline execution halts immediately on the first error:
- Missing series $\to$ HTTP 400 (`stage="series_resolution"`)
- Missing discovery pair $\to$ HTTP 400 (`stage="discovery_pair_resolution"`)
- Pair not in series $\to$ HTTP 400 (`stage="discovery_pair_resolution"`)
- Invalid candidate region $\to$ HTTP 400 (`stage="candidate_region_validation"`)
- Upstream service error $\to$ HTTP 400 (`stage="m4b_change_detection_..."`, `stage="m4c_..."`, etc.)

Errors are never swallowed, and missing data is never substituted with fabricated zero scores. Structured stage execution records are returned in `stage_results`.

---

## 7. Determinism

- **Zero Wall-Clock Entropy**: The dossier content hash (`content_hash`) is derived exclusively from canonical representations of:
  - Validated request fields
  - Sorted evaluated scene pair IDs
  - Upstream artifact IDs
  - Upstream cryptographic hashes
  - Hyperparameter configurations
- **Deterministic Timestamp**: Dossier `created_at` timestamp is derived from the latest satellite observation acquisition timestamp in the series.
- **Bit-for-Bit Reproducibility**: Multiple executions on identical inputs yield bit-for-bit identical `investigation_id`, `provenance_id`, and `dossier.json` output.

---

## 8. Offline Operation

- Zero runtime external network calls or cloud API calls.
- Enforces strict compliance with ASTRA Offline Rule 1 & Rule 2.
- Verified with `scripts/check_offline.py` (0 external network calls).

---

## 9. Explicit Discovery Pair Requirement

The orchestrator requires an **explicit `discovery_pair_id`** in `InvestigationRequest`. It does not automatically choose or guess a discovery pair. This guarantees:
- Analyst intent is strictly respected.
- Candidate change regions are grounded to a specific discovery epoch.
- Upstream M4B discovery results are verifiable without ambiguity.

---

## 10. What the Orchestrator Does NOT Do

To maintain strict modular boundaries and prevent duplicate algorithmic drift:
- The orchestrator **does NOT read or write raster rasters directly** (no `rasterio`, `PIL`, or OpenCV imports).
- The orchestrator **does NOT calculate pixel differencing or thresholds** (delegated to M4B).
- The orchestrator **does NOT generate spectral indices or extract context** (delegated to M4C-A).
- The orchestrator **does NOT classify changes or assign category labels** (delegated to M4C-B).
- The orchestrator **does NOT evaluate false-alarm suppression rules** (delegated to M4D).
- The orchestrator **does NOT determine earliest observations or onset intervals** (delegated to M4E).
- The orchestrator **does NOT introduce microservices or remote network boundaries**.
