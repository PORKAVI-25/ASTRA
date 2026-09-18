# A.S.T.R.A. (Automated Semantic Tracking and Retrieval Architecture)

> **SIH 2026 Problem Statement:** SIH26227 / PS227  
> **Topic:** Semantic Retrieval and Multi-Temporal Change Analysis of Satellite Imagery  
> **Status:** Phase M4F & Analyst Workstation (Milestones D1–D10) Complete

---

## 1. Overview & Problem Statement

**A.S.T.R.A.** (*Automated Semantic Tracking and Retrieval Architecture*) is a modular, offline-first earth observation intelligence platform and analyst workstation engineered for SIH 2026 PS227.

Satellite remote sensing archives capture rapid planetary dynamics across large geographic extents. Traditional catalog search relying on manual tagging or simple bounding box queries cannot locate specific semantic concepts (*e.g., “rapid clearing adjacent to river crossings”* or *“infrastructure expansion along marshlands”*). Furthermore, observing how those regions evolve over time requires co-registered, multi-temporal change detection that preserves spatial, radiometric, and temporal ground truth.

ASTRA delivers:
1. **Multi-Temporal Change Analysis:** Deterministic, pixel-accurate change quantification across registered temporal observations ($T_1 \rightarrow T_2$).
2. **Temporal Evidence Reasoning:** Multi-epoch trajectory analysis tracking emergence, earliest supporting observation passes, persistent support, and suppression of transient false alarms.
3. **Analyst Workstation (D1–D10):** A unified single-page interface for temporal-series exploration, investigation launcher orchestration, multi-epoch dossier review, cryptographic provenance verification, and analyst audit logging.
4. **Strict Offline & Air-Gapped Operation:** Full functionality designed for secure, disconnected, or field-deployed environments without external cloud API dependencies.
5. **Immutable Geospatial Provenance:** Preserving Coordinate Reference Systems (CRS), WGS84 bounding extents, timestamps, sensor channels, and cryptographic SHA-256 artifact hashes across every processing stage.

---

## 2. Completed Analyst Dashboard (Milestones D1–D10)

The ASTRA frontend is structured as an interactive analyst workstation designed for investigative situational awareness. The completed dashboard scope spans Milestones D1 through D10:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   ASTRA ANALYST DASHBOARD SCOPE                        │
├────────────────────────────────┬───────────────────────────────────────┤
│ D1: API Client Layer           │ Fully typed API client & mappers      │
│ D2: Temporal Series Explorer   │ Catalog browser & epoch inspection    │
│ D3: Investigation Launcher     │ Interactive pair & candidate runner   │
│ D4: Investigation Dossier View │ Executive summary & onset interval    │
│ D5: Temporal Timeline Ribbon   │ Multi-epoch chronological trajectory  │
│ D6: Spatial Candidate Panel    │ BBox, IoU & region ID shift tracker   │
│ D7: Evidence & Suppression     │ M4D false-alarm screening breakdown   │
│ D8: Provenance & Lineage       │ Cryptographic SHA-256 audit waterfall │
│ D9: Analyst Review Workflow    │ Confirm / Reject / Flag triage engine │
│ D10: UI Polish & Shell         │ Cyber-geospatial theme & tab navigation│
└────────────────────────────────┴───────────────────────────────────────┘
```

### Implemented Functional Areas

- **Temporal Series Explorer (D2):**
  - Displays cataloged satellite series with observation count, spatial bounding box (WGS84), and acquisition timespan.
  - Interactive multi-epoch filtering and detail panel showing individual pass dates, platform identifiers (*e.g., Sentinel-2A MSI*), sensor quality metrics, and Coordinate Reference Systems (*e.g., EPSG:32643*).
- **Investigation Launcher (D3):**
  - Guided orchestration wizard allowing analysts to select a target multi-epoch series.
  - Automatic selection of compatible discovery scene pairs ($T_1 \to T_2$) with pairing strategy selection (`baseline` vs `adjacent`).
  - Candidate region identification with interactive bounding box selection and validation gates.
  - Submits structured investigation requests to the backend orchestration pipeline (`POST /api/v1/pipeline/investigate`).
- **Analytical Result Dossier (D4–D9):**
  - **Executive Summary Card (D4):** Highlights primary change category (*e.g., CONSTRUCTION*), confidence tier (*e.g., HIGH*), temporal support status (*e.g., STRONG_TEMPORAL_SUPPORT*), and mathematical onset interval `(T_pre, T_earliest]` with sampling caveats.
  - **Temporal Timeline Ribbon (D5):** Chronological multi-epoch trajectory bar rendering discrete satellite observation passes (`PRE_CHANGE_ABSENCE`, `EARLIEST_SUPPORTING`, `PERSISTENT_SUPPORT`, `FLAGGED_SUPPORT`, `SUPPRESSED_ARTIFACT`).
  - **Spatial Candidate Panel (D6):** Evaluates geographic footprints in WGS84 coordinates, computes local SVG vector footprints without external map tiles, embeds binary change mask images (`/api/v1/change-detection/{id}/mask`), and tracks candidate region ID shifts across epochs (*e.g., reg_0002 → reg_0001*), IoU overlap, and centroid drift.
  - **Evidence & False-Alarm Suppression Panel (D7):** Displays multi-modal feature evidence, category evolution trajectories across time, and conservative false-alarm screening metrics (retained, flagged, and suppressed candidates).
  - **Provenance & Cryptographic Lineage Panel (D8):** Visualizes the end-to-end execution waterfall (`cdr_...`, `evi_...`, `cls_...`, `sup_...`, `tem_...`, `inv_...`) with immutable SHA-256 content hashes and one-click copy utilities.
  - **Analyst Review & Audit Trail (D9):** Provides operational triage controls (**Confirm**, **Reject**, **Flag / Needs Review**), category override selection, attribution notes, deterministic SHA-256 audit hash calculation, local revision persistence, and JSON audit log export.
- **Workstation Shell & Telemetry (D10):**
  - Persistent cyber-geospatial sidebar navigation across **Launcher**, **Explorer**, **Dossier**, and **Foundation** diagnostics.
  - Real-time backend connectivity telemetry with dynamic status badges (`AIR-GAPPED (ONLINE)` when connected, `AIR-GAPPED (STANDALONE)` when offline).

---

## 3. Architecture & Data Flow

ASTRA follows a modular monolith architecture designed for predictability, strict data isolation, and portable execution across developer machines and cloud development containers:

```text
Browser Client
      │
      ▼
React 19 + TypeScript Frontend
      │  (relative /api/v1/* requests)
      ▼
Vite Development Server (Host: 0.0.0.0, Port: 5173)
      │  (built-in /api proxy forwarding)
      ▼
FastAPI REST API Backend (Host: 127.0.0.1, Port: 8000)
      │
      ├─► Temporal Catalog & Scene Pairing (M4A)
      ├─► Pixel-Difference Change Detection (M4B)
      ├─► Multi-Modal Evidence Extraction (M4C-A)
      ├─► Change-Type Classification Rules (M4C-B)
      ├─► False-Alarm Screening & Suppression (M4D)
      ├─► Earliest Supporting Observation Reasoning (M4E)
      └─► Pipeline Orchestration Service (M4F)
```

### Portable API Routing
- **Relative Client Requests:** The frontend API client (`frontend/src/services/api.ts`) defaults to empty base URL `""`, dispatching relative requests (*e.g., `/api/v1/health`*, *`/api/v1/temporal/series`*). Explicit configuration via `VITE_API_URL` remains supported.
- **Vite Development Proxy:** Vite binds to `0.0.0.0:5173` and proxies all `/api` requests to `http://127.0.0.1:8000`. This enables identical execution in both native local environments and remote port-forwarded environments (*e.g., GitHub Codespaces*) without hardcoding external hostnames or exposing backend CORS.
- *Note:* The Vite development proxy is intended solely for development environments; production deployments typically front both static assets and API services with an enterprise gateway or dedicated web server.

---

## 4. Strict Offline & Air-Gapped Operating Model

ASTRA is engineered under strict air-gapped guidelines:

> **Runtime code must not depend on external APIs, remote CDNs, or live internet connections.**

1. **Self-Contained Data & Assets:** Frontend dependencies and fonts are statically bundled. The UI avoids external tile providers (*e.g., Mapbox, Google Maps, OpenStreetMap*) and instead renders vector geometries via native SVG and raster change masks directly from backend endpoints.
2. **Local Vector Storage:** Retrieval indexing operates entirely in-process using local NumPy/SQLite metadata indexes without external hosted vector databases.
3. **Pre-Staged Weights:** Model adapters reference local disk storage (`models/staged/`). No online downloads (*e.g., `torch.hub` or Hugging Face hub pulls*) are permitted at runtime.
4. **Automated Compliance Verification:** Run `python scripts/check_offline.py` to statically verify that zero prohibited external network calls or remote model imports exist in runtime paths.

---

## 5. Current Implementation Status

| Component | Status | Implementation Details |
|---|---|---|
| **Analyst Workstation (D1–D10)** | ✅ Complete | Full React 19 single-page console: Explorer, Launcher, Dossier, Lineage, Audit Log |
| **FastAPI REST API** | ✅ Complete | Health diagnostics, temporal series catalog, scene pairing, and investigation orchestration |
| **Temporal Scene Pairing (M4A)** | ✅ Complete | Deterministic pair creation, spatial intersection validation, and chronologically ordered acquisition dates |
| **Change Detection Engine (M4B)**| ✅ Complete | Dual-raster alignment, continuous score calculation, thresholding, connected component clustering |
| **Multi-Modal Evidence (M4C-A)** | ✅ Complete | Feature extraction, spectral index analysis, morphological metric profiling |
| **Change Classification (M4C-B)**| ✅ Complete | Deterministic decision-tree and heuristic rules classifying change categories |
| **False-Alarm Suppression (M4D)**| ✅ Complete | Cloud, illumination, and coregistration jitter screening filters |
| **Temporal Reasoning (M4E)**     | ✅ Complete | Earliest supporting observation identification, absence verification, persistence tracking |
| **Pipeline Orchestration (M4F)**| ✅ Complete | End-to-end multi-stage pipeline coordinator producing cryptographically ground-truth dossiers |
| **Automated Test Coverage**      | ✅ Complete | 294 backend pytest tests, 150 frontend node tests, clean linting and builds |
| **Portable Dev Runtime**         | ✅ Complete | Verified on Windows PowerShell and GitHub Codespaces via Vite proxy |
| **Multi-Analyst Server Review**  | ⏳ Phase 2/3 | *Client-side localStorage audit store with SHA-256 hashing is implemented; server database persistence deferred* |
| **Live Satellite Streaming**     | ⏳ Phased | *Continuous real-time satellite scraping deferred; operates strictly on local staged rasters* |
| **Distributed Inference Cluster**| ⏳ Phased | *Multi-node GPU clustering deferred; optimized for standalone single-node analyst workstation* |

---

## 6. Repository Structure

```text
ASTRA/
├── backend/                  # Modular FastAPI backend
│   ├── api/v1/               # REST endpoints (health, temporal, change-detection, pipeline)
│   ├── config.py             # Pydantic Settings with air-gapped enforcement
│   ├── ingestion/            # Satellite raster ingestion, tiling, and metadata extraction
│   ├── ml/                   # Domain ML packages (change, retrieval, suppression)
│   ├── orchestrator/         # End-to-end investigation pipeline coordinator
│   └── main.py               # Application entrypoint
├── frontend/                 # React 19 + TypeScript + Tailwind CSS (Vite)
│   ├── src/
│   │   ├── components/       # Workstation UI panels (series, investigation, layout)
│   │   ├── services/         # Centralized API client, transformers, and reviewStore
│   │   ├── types/            # API contracts and frontend view models
│   │   └── __tests__/        # Automated frontend test suites
│   ├── package.json          # Node scripts and dependencies
│   └── vite.config.ts        # Server configuration and /api proxy routing
├── data/                     # Staged satellite rasters, processed tiles, and manifests
├── docs/                     # Architectural specifications, contracts, and milestone plans
├── geospatial/               # Coordinate Reference Systems and WGS84 bounding utilities
├── ml/                       # Decoupled model adapter interfaces
├── models/                   # Staged offline model weights
├── scripts/                  # Offline compliance scanner and validation utilities
├── tests/                    # Backend pytest automated test suite
└── README.md
```

---

## 7. Run Locally (Windows)

### Prerequisites
- **Python:** 3.11+ (Python 3.14 verified)
- **Node.js:** v18+ (Node v24 verified)
- **PowerShell**

### Step 1: Start the Backend
In a PowerShell terminal:
```powershell
cd C:\Users\<username>\OneDrive\Documents\ASTRA
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```
- API root: `http://127.0.0.1:8000`
- Interactive API Docs: `http://127.0.0.1:8000/docs`

### Step 2: Start the Frontend
In a second PowerShell terminal:
```powershell
cd C:\Users\<username>\OneDrive\Documents\ASTRA\frontend
npm install
npm run dev
```
- Open `http://localhost:5173` (or the next available port displayed in the Vite console output).

---

## 8. Run in GitHub Codespaces

ASTRA is fully configured to operate seamlessly in cloud containers like GitHub Codespaces.

### Step 1: Set Up Backend
In the first Codespaces terminal:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### Step 2: Set Up Frontend
In a second Codespaces terminal:
```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0
```

### Step 3: Access the Workstation
1. Open the **Ports** panel in VS Code / GitHub Codespaces.
2. Locate port **`5173`** and click the **Open in Browser** icon (ensure the protocol is set to HTTP).
3. The frontend communicates with the backend via same-origin relative `/api/v1/*` requests, which Vite proxies internally to `http://127.0.0.1:8000`.

---

## 9. Demonstration & Smoke Test Workflow

A verified demonstration dataset is included in `data/processed/tiles/`:

- **Demo Series Identifier:** `series_grid_lon77.33_lat13.08_c0000_r0000_z14`
- **Characteristics:** Contains 4 chronological observation epochs (Jan 15, Feb 15, Mar 15, and Apr 15, 2026) and 3 valid baseline scene pairs.
- *Single-Observation Series:* Series with only 1 observation epoch (*e.g., `series_grid_lon76.86_lat12.59_c0000_r0001_z14`*) will report zero compatible scene pairs, as multi-temporal pairing mathematically requires at least two distinct epochs ($T_1 < T_2$).

### Step-by-Step Walkthrough

1. **Verify Backend Connection:** Open the dashboard and check that the top-right status badge reads `AIR-GAPPED (ONLINE)`.
2. **Browse Series Catalog:** Navigate to the **Explorer** tab to review cataloged spatial grids, acquisition dates, and sensor channels.
3. **Launch Investigation:**
   - Switch to the **Launcher** tab.
   - Select `series_grid_lon77.33_lat13.08_c0000_r0000_z14`.
   - Select discovery scene pair `T1 (2026-01-15) -> T2 (2026-02-15)`.
   - Select the detected candidate region (`reg_0002`).
   - Click **Launch Automated Investigation**.
4. **Review Analytical Dossier:**
   - Review the **Executive Summary** for the primary classification (*CONSTRUCTION*), confidence tier, and onset bounds `(2026-01-15, 2026-02-15]`.
   - Inspect the **Temporal Timeline Ribbon** to observe the trajectory progression from baseline absence ($T_1$) to earliest emergence ($T_2$) and persistent support ($T_3, T_4$).
   - Inspect the **Spatial Candidate Panel** to inspect the local SVG footprint, change mask image, and track the cross-epoch region ID shifts (*reg_0002 → reg_0001 → reg_0003*).
   - Inspect the **Provenance & Cryptographic Lineage** table to verify upstream SHA-256 hashes.
5. **Analyst Review Action:**
   - Under the **Analyst Review** panel, select a triage decision (**Confirm**, **Reject**, or **Flag**).
   - Enter an analyst note and click **Record Analyst Review**.
   - Confirm that a new immutable revision is created with a deterministic SHA-256 audit hash and export the audit trail as JSON.

---

## 10. Verification & Test Coverage

All core services and UI components are continuously validated against strict automated quality gates:

### Backend Test Suite
```powershell
python -m pytest -q
```
- **Result:** **294 passed** across 18 test modules covering data contracts, coordinate reference systems, change detection, classification, false-alarm suppression, temporal evidence reasoning, pipeline orchestration, and health endpoints.

### Offline Security Scanner
```powershell
python scripts/check_offline.py
```
- **Result:** **PASSED** (126 source files scanned; 0 external runtime APIs, CDN links, or unauthorized remote download hooks detected).

### Frontend Quality Gates
In `frontend/`:
```bash
# 1. TypeScript Strict Typecheck
npx tsc -b --force --noEmit --pretty false

# 2. Automated Unit & Integration Tests
npm test

# 3. Static Code Analysis / Linter
npm run lint

# 4. Production Bundle Compilation
npm run build
```
- **TypeScript:** Passed with 0 errors.
- **Frontend Tests:** **150 passed / 0 failed** across 13 suites validating API handling, view model transformations, SVG geometry calculations, false-alarm screening representation, and analyst review audit trail persistence.
- **Linter (OxLint):** 0 warnings, 0 errors across 51 files.
- **Production Build:** Succeeded in under 2 seconds.

---

## 11. Engineering Principles

- **Modular Monolith:** Co-located domain packages with clean separation of concerns and zero unnecessary microservice overhead.
- **Offline First:** Zero reliance on remote internet connectivity, external CDN links, or cloud inference services.
- **Type Safety & Contracts:** End-to-end typing via Pydantic v2 on the backend and TypeScript strict mode on the frontend.
- **Auditability & Provenance:** Every intermediate output is bound to an immutable SHA-256 hash ensuring end-to-end scientific traceability.
- **Defensive UI Engineering:** Resilient client state management with graceful fallback handling when services are disconnected.

---

## 12. Phased Roadmap & Planned Enhancements

| Phase | Capability | Planned Scope |
|---|---|---|
| **Phase 1** | Foundation & Offline Baseline | Core tiling, data contracts, and foundation diagnostics *(Completed)* |
| **Phase 2** | Change Analysis & Orchestration | Multi-epoch change detection, evidence screening, and orchestrator *(Completed)* |
| **Phase M4F / D1-D10** | Analyst Workstation | Complete interactive single-page analyst console *(Completed)* |
| **Future Phase** | Server-Side Review Persistence | Multi-analyst centralized PostgreSQL/SQLite review record synchronization |
| **Future Phase** | Raster Previews & COG Tiling | Server-side Cloud Optimized GeoTIFF (COG) dynamic windowing and RGB rendering |
| **Future Phase** | Multi-Spectral Sensor Expansion | Pre-configured ingestion pipelines for PlanetScope, Landsat-9, and SAR (Sentinel-1) |
