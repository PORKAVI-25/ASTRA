# ASTRA Analyst Dashboard Implementation Plan (Phase M4F)

## 1. Plan Overview

This plan outlines the systematic implementation of the **ASTRA Analyst Dashboard** across 12 distinct milestones (`D1` through `D12`).

It provides a step-by-step roadmap to transition the current prototype UI into a production-grade, air-gapped analyst workstation that interacts seamlessly with the ASTRA M1–M4F backend.

---

## 2. Milestone Breakdown

```
┌────────────────────────────────────────────────────────────────────────┐
│                   ASTRA ANALYST DASHBOARD ROADMAP                      │
├────────────────────────────────┬───────────────────────────────────────┤
│ D1: API Client Layer           │ Complete typed API client & mappers   │
│ D2: Series Explorer            │ Temporal series & observation browser │
│ D3: Investigation Launcher     │ Interactive pair & candidate launcher │
│ D4: Investigation Dossier View │ Executive summary & trajectory card   │
│ D5: Timeline Ribbon View       │ Multi-epoch chronological trajectory  │
│ D6: Spatial Candidate Panel    │ BBox, IoU & region ID shift tracker   │
│ D7: Evidence & Suppression     │ M4D false-alarm screening breakdown   │
│ D8: Provenance & Lineage       │ Cryptographic audit tree & waterfall  │
│ D9: Analyst Review Workflow    │ Confirm / Reject / Flag triage engine │
│ D10: UI Polish & Layout        │ Dark mode, responsive design, tabs    │
│ D11: Automated Frontend Tests  │ Unit tests for client, mappers & UI   │
│ D12: End-to-End Verification   │ Full pipeline run, offline scanner    │
└────────────────────────────────┴───────────────────────────────────────┘
```

---

### Milestone D1 — API Client Layer & View Model Mappers

- **Goal**: Create comprehensive, type-safe API client functions and contract mappers.
- **Files to Create / Modify**:
  - `frontend/src/types/api.ts` [NEW] — Mirrors raw backend JSON contracts.
  - `frontend/src/types/models.ts` [NEW] — View models defined in `dashboard-data-model.md`.
  - `frontend/src/services/api.ts` [MODIFY] — Add functions:
    - `fetchSeriesList(): Promise<TemporalSeries[]>`
    - `fetchSeriesById(seriesId: string): Promise<TemporalSeries>`
    - `fetchSeriesPairs(seriesId: string, mode?: string): Promise<TemporalSeriesPairsResponse>`
    - `executeInvestigation(request: InvestigationRequest): Promise<InvestigationDossier>`
    - `detectCandidateRegions(pair: ScenePair): Promise<ChangeDetectionResult>`
    - `getChangeDetectionMaskUrl(resultId: string): string`
  - `frontend/src/services/transformers.ts` [NEW] — Pure contract $\to$ view model transformation helpers.
- **Backend Changes**: None.
- **Tests**:
  - Test mapping functions with mocked `InvestigationDossier` and `TemporalSeries` JSON fixtures.
- **Acceptance Criteria**:
  - 100% TypeScript compile pass (`tsc -b`).
  - Zero `any` types in public API interfaces.

---

### Milestone D2 — Temporal Series Explorer

- **Goal**: Allow analysts to browse all cataloged satellite temporal series, inspect observation dates, sensors, and platform metadata.
- **Files to Create / Modify**:
  - `frontend/src/components/series/SeriesList.tsx` [NEW] — Grid/list of registered series with badge metrics.
  - `frontend/src/components/series/SeriesDetail.tsx` [NEW] — Expanded view showing observation calendar, sensors, GSD, and timespan.
  - `frontend/src/components/series/ObservationCard.tsx` [NEW] — Visual card for each acquisition epoch ($T_1, T_2, \dots$).
- **Backend Changes**: None.
- **Tests**:
  - Verify empty catalog state, loading skeleton, and error state when backend is unreachable.
- **Acceptance Criteria**:
  - Displays `series_grid_lon77.33_lat13.08_c0000_r0000_z14` with 4 observations.
  - Displays observation dates (Jan 15, Feb 15, Mar 15, Apr 15, 2026).

---

### Milestone D3 — Investigation Launcher

- **Goal**: Enable analysts to select a series, select an observation pair, discover candidate change regions, and launch an investigation.
- **Files to Create / Modify**:
  - `frontend/src/components/investigation/Launcher.tsx` [NEW] — Multi-step wizard or form:
    1. Series selector.
    2. Discovery pair selector (defaults to $T_1 \to T_2$).
    3. Pairing strategy toggle (`baseline` vs `adjacent`).
    4. Candidate region selector with auto-detection via `POST /api/v1/change-detection/run`.
    5. "Launch Investigation" button with validation gates.
  - `frontend/src/components/investigation/ExecutionProgress.tsx` [NEW] — Step-by-step simulated progress tracker.
- **Backend Changes**: None.
- **Tests**:
  - Form validation tests (empty inputs disabled, invalid pairing modes rejected).
- **Acceptance Criteria**:
  - Submits valid `InvestigationRequest` to `POST /api/v1/pipeline/investigate`.
  - Catches structured HTTP 400 `VALIDATION_ERROR` and displays user-friendly error banners.

---

### Milestone D4 — Investigation Result Dossier (Executive View)

- **Goal**: Present the high-level findings of the investigation dossier conforming to `ASTRA-DC-v0.1`.
- **Files to Create / Modify**:
  - `frontend/src/components/investigation/DossierView.tsx` [NEW] — Top-level tabbed container.
  - `frontend/src/components/investigation/ExecutiveSummaryCard.tsx` [NEW] — Executive summary:
    - Primary category banner (`CONSTRUCTION`).
    - Temporal support status chip (`STRONG_TEMPORAL_SUPPORT`).
    - Confidence tier badge (`HIGH`).
    - Onset interval card with mathematical bounding `(T_pre, T_earliest]`.
    - Sampling limitation caveat.
    - Deterministic ID, timestamp, and content hash badges.
- **Backend Changes**: None.
- **Tests**:
  - Verify correct badge styling across all status enums.
- **Acceptance Criteria**:
  - Renders all executive summary fields from `inv_8c939ce062ed9b8c`.

---

### Milestone D5 — Temporal Timeline Visualization

- **Goal**: Render the multi-epoch chronological timeline ribbon and detailed observation audit cards.
- **Files to Create / Modify**:
  - `frontend/src/components/timeline/TimelineRibbon.tsx` [NEW] — Horizontal visual trajectory bar connecting epochs with status dots.
  - `frontend/src/components/timeline/TimelineNodeCard.tsx` [NEW] — Epoch card displaying:
    - Observation date and sensor platform.
    - Status pill (`PRE_CHANGE_ABSENCE`, `EARLIEST_SUPPORTING`, `PERSISTENT_SUPPORT`, `FLAGGED_SUPPORT`, `SUPPRESSED_ARTIFACT`).
    - Heuristic support score bar (0.00 – 1.00).
    - Earliest support eligibility indicator.
    - M4D screening badge (`RETAINED` vs `FLAGGED`).
    - Audit justification bullets and data limitations.
- **Backend Changes**: None.
- **Tests**:
  - Test chronological ordering and status color tokens.
- **Acceptance Criteria**:
  - T1 rendered as `PRE_CHANGE_ABSENCE`.
  - T2 rendered as `EARLIEST_SUPPORTING` with score ~0.92.
  - T3 & T4 rendered as `PERSISTENT_SUPPORT`.

---

### Milestone D6 — Spatial Candidate & Correspondence Panel

- **Goal**: Track spatial candidate alignment and multi-epoch local region ID shifts across epochs.
- **Files to Create / Modify**:
  - `frontend/src/components/spatial/CandidatePanel.tsx` [NEW] — Spatial correspondence container.
  - `frontend/src/components/spatial/CorrespondenceTable.tsx` [NEW] — Table listing:
    - Evaluated scene pair.
    - Target epoch date.
    - Reference candidate ID (`reg_0002`).
    - Matched local region ID (`reg_0002` at T2, `reg_0001` at T3, `reg_0003` at T4).
    - Metric-projected BBox IoU (e.g., 1.0, 0.88, 0.87).
    - Geodesic centroid drift in meters.
    - Geometric comparison status.
  - `frontend/src/components/spatial/ChangeMaskViewer.tsx` [NEW] — Embedded viewer for binary change mask PNG (`GET /api/v1/change-detection/{result_id}/mask`).
- **Backend Changes**: None.
- **Tests**:
  - Verify correspondence row highlighting when region IDs differ.
- **Acceptance Criteria**:
  - Clearly highlights region ID shifts across epochs.
  - Successfully displays the binary change mask image.

---

### Milestone D7 — Evidence & False-Alarm Suppression Panel

- **Goal**: Present explainable feature evidence (M4C-A/B) and false-alarm screening metrics (M4D).
- **Files to Create / Modify**:
  - `frontend/src/components/evidence/SuppressionPanel.tsx` [NEW] — Screening summary cards (Retained, Flagged, Suppressed).
  - `frontend/src/components/evidence/CategoryEvolutionCard.tsx` [NEW] — Sequence of category classifications across epochs and conflict audit notes.
- **Backend Changes**: None.
- **Tests**:
  - Verify counts and badges match `metrics` in dossier.
- **Acceptance Criteria**:
  - Displays breakdown of screened false alarms and validates category trajectory consistency.

---

### Milestone D8 — Provenance & Cryptographic Lineage Panel

- **Goal**: Render immutable upstream artifact hashes and stage execution waterfall.
- **Files to Create / Modify**:
  - `frontend/src/components/provenance/ProvenanceTree.tsx` [NEW] — Cryptographic SHA-256 hash inspection table.
  - `frontend/src/components/provenance/StageWaterfall.tsx` [NEW] — Ordered execution stages with status icons, artifact IDs, and execution timestamps.
- **Backend Changes**: None.
- **Tests**:
  - Verify copy-to-clipboard functionality for SHA-256 hashes and artifact IDs.
- **Acceptance Criteria**:
  - Renders all upstream artifact IDs (`cdr_...`, `evi_...`, `cls_...`, `sup_...`, `tem_...`) and SHA-256 hashes.

---

### Milestone D9 — Analyst Review & Audit Trail Workflow

- **Goal**: Enable analysts to review, triage, and annotate investigation dossiers with immutable local audit logging.
- **Files to Create / Modify**:
  - `frontend/src/components/review/ReviewControls.tsx` [NEW] — Action buttons:
    - **Confirm**: Validates change emergence and category.
    - **Reject**: Marks candidate as false alarm / analyst disagreement.
    - **Flag / Needs Review**: Escalates to senior analyst.
    - Comment box and category override dropdown.
  - `frontend/src/components/review/ReviewAuditLog.tsx` [NEW] — Chronological table of submitted reviews.
  - `frontend/src/services/reviewStore.ts` [NEW] — `localStorage` repository with SHA-256 review record hashing and JSON export capability.
- **Backend Changes**:
  - *Future Enhancement*: `POST /api/v1/investigations/{id}/reviews` for multi-analyst server-side persistence.
- **Tests**:
  - Unit tests for review creation, validation, `localStorage` persistence, and hash generation.
- **Acceptance Criteria**:
  - Analyst can confirm/reject/flag dossier, append notes, and export review audit records as JSON.

---

### Milestone D10 — Dashboard Polish, Layout & Navigation

- **Goal**: Integrate all panels into a unified, responsive single-page analyst workspace.
- **Files to Create / Modify**:
  - `frontend/src/App.tsx` [MODIFY] — Reorganize navigation into clean workspace tabs:
    - **Explorer**: Series & observation catalog.
    - **Launcher**: Investigation setup & runner.
    - **Dossier**: Active investigation results.
    - **Audit Log**: Analyst review records.
  - `frontend/src/components/Header.tsx` [MODIFY] — Add tab navigation, system telemetry badges, and quick-status indicators.
  - `frontend/src/index.css` [MODIFY] — Clean utility classes, theme variables, and custom scrollbars.
- **Backend Changes**: None.
- **Tests**:
  - Responsive layout checks across desktop (1920x1080), laptop (1366x768), and tablet viewports.
- **Acceptance Criteria**:
  - Seamless navigation between tabs without state loss.
  - High aesthetic quality: dark slate palette, cyber-geospatial typography, clear visual hierarchy.

---

### Milestone D11 — Automated Frontend Tests

- **Goal**: Implement automated frontend unit and integration test coverage.
- **Files to Create / Modify**:
  - `frontend/src/__tests__/transformers.test.ts` [NEW] — Tests view model transformations with synthetic fixtures.
  - `frontend/src/__tests__/reviewStore.test.ts` [NEW] — Tests local storage persistence and audit hash generation.
  - `frontend/package.json` [MODIFY] — Add test script if test runner is added.
- **Backend Changes**: None.
- **Tests**:
  - Run frontend tests and linter (`npm --prefix frontend run lint` / `npx oxlint`).
- **Acceptance Criteria**:
  - Zero linting errors, 100% typecheck pass, robust transformer coverage.

---

### Milestone D12 — Final Integration Verification

- **Goal**: End-to-end operational verification of backend + frontend in an air-gapped environment.
- **Verification Protocol**:
  1. `python -m pytest -q tests/test_api_investigation.py` (all 15 API tests pass).
  2. `python -m pytest -q` (all 291 full repo tests pass).
  3. `python scripts/check_offline.py` (air-gapped scanner passes, 0 remote calls).
  4. `npm --prefix frontend run build` (production Vite build succeeds).
  5. `git diff --check` (clean formatting).
- **Acceptance Criteria**:
  - Zero regression on existing ML and orchestration capabilities.
  - Clean build output ready for deployment.

---

## 3. Backend Gap Audit Summary

| Identified Area | Current State | Impact on Dashboard | Recommended Action |
| :--- | :--- | :--- | :--- |
| **Candidate Geometry** | Stored in M4B `ChangeDetectionResult`, omitted from `InvestigationDossier` top level. | Extra API call required if UI renders vector polygon. | Frontend fetches CDR via existing `/api/v1/change-detection/{id}`. In future, embed summary bbox in dossier. |
| **Matched Region Geometry** | Dossier lineage provides matched region ID, IoU, and centroid distance, but no polygon coordinates. | UI displays tabular correspondence metrics rather than overlapping vectors. | Fully sufficient for tabular tracking. Full polygon overlays can fetch CDRs if required. |
| **Raster Previews** | Raw scenes are GeoTIFF `.tif` on disk. Binary change mask is served as PNG. | Browser cannot display raw `.tif` tiles without conversion. | UI uses PNG change masks and SVG footprint bounding boxes. Add PNG thumbnail endpoint in future. |
| **Provenance Navigation** | Lineage and upstream SHA-256 hashes are embedded in dossier, but no REST `/provenance/{id}` endpoint exists. | UI cannot fetch standalone raw `prov_...json` files via HTTP. | UI renders embedded lineage and hashes directly from dossier. Add REST provenance endpoint in future. |
| **Analyst Review Persistence**| No review models or endpoints exist in backend. | Review actions cannot be saved to server database. | Implement client-side `localStorage` review store with audit hashing and JSON export. Add server API later. |
| **Offline Operation** | Fully air-gapped backend, offline scanner passing, 0 external network dependencies. | Frontend must avoid remote map tile CDNs (OSM, Mapbox, Google). | Use HTML5 Canvas, SVG vectors, and local `/mask` PNGs to guarantee 100% offline compliance. |
