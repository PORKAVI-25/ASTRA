# A.S.T.R.A. (Automated Semantic Tracking and Retrieval Architecture)

> **SIH 2026 Problem Statement:** SIH26227 / PS227  
> **Topic:** Semantic Retrieval and Multi-Temporal Change Analysis of Satellite Imagery  
> **Status:** Phase 0 — Foundation Complete

---

## 1. Overview

**A.S.T.R.A.** (*Automated Semantic Tracking and Retrieval Architecture*) is a modular, high-performance earth observation intelligence platform engineered for SIH 2026.

Satellite remote sensing archives capture rapid planetary dynamics across vast geographic extents. Traditional catalog search relying on manual tagging or simple bounding box metadata is insufficient for analysts needing to locate specific semantic concepts (e.g. *“rapid deforestation adjacent to newly constructed river crossings”* or *“informal settlements expanding along marshlands”*). Furthermore, observing how those regions evolve over time requires co-registered, multi-temporal change detection that preserves spatial and radiometric truth.

ASTRA delivers:
1. **Semantic Multi-Modal Retrieval:** Querying large-scale satellite imagery collections using natural language prompts or visual exemplars without relying on external cloud APIs.
2. **Multi-Temporal Change Analysis:** Automated, pixel-accurate and semantic-level change quantification across registered temporal observations ($T_1 \rightarrow T_2$).
3. **Strict Offline & Air-Gapped Operation:** Full offline capabilities designed for secure, disconnected, or field-deployed environments.
4. **Immutable Geospatial Provenance:** Preserving CRS, geographic bounding boxes, timestamps, sensor channels, and source scene linkage across every chipped tile.

---

## 2. Architecture Overview

ASTRA is built as a **modular monolith** following strict anti-bloat guardrails:
- **No unnecessary microservices**
- **No Kubernetes or cloud-only infrastructure**
- **No runtime reliance on external cloud APIs or online model weight downloads**

```text
ASTRA/
├── frontend/             # React 19 + TypeScript + Tailwind CSS (Vite)
├── backend/              # FastAPI modular backend
│   ├── api/              # REST endpoints (v1 router, health diagnostics)
│   ├── ingestion/        # Imagery ingestion & chipping pipelines
│   ├── retrieval/        # Local vector retrieval (FAISS/in-memory)
│   ├── change_analysis/  # Multi-temporal change detection service
│   ├── provenance/       # Metadata preservation & scene-tile linkage
│   └── evaluation/       # Benchmark evaluation (mAP, IoU, Recall@K)
├── ml/                   # Model adapter interfaces (decoupled foundation models)
│   ├── embeddings/       # Embedding model adapter (BaseEmbeddingAdapter)
│   ├── change_detection/ # Change detection model adapter (BaseChangeDetectorAdapter)
│   ├── quality/          # Cloud/noise screening
│   └── clustering/       # Semantic clustering
├── geospatial/           # Geospatial coordinate systems & CRS validation
├── data/                 # Staged datasets & metadata stores (strictly local)
│   ├── raw/              # Staged raw satellite scenes (GeoTIFF/COG)
│   ├── processed/        # Processed chips and feature representations
│   ├── manifests/        # JSON scene & tile manifests
│   └── benchmark/        # Ground-truth evaluation benchmarks
├── tests/                # Automated pytest suite (backend, contracts, health)
├── scripts/              # Development, build, and offline verification scripts
├── docs/                 # Architectural specifications, requirements, ADRs
└── README.md
```

For in-depth design details, refer to:
- [System Requirements](file:///docs/requirements.md)
- [Architecture Blueprint](file:///docs/architecture.md)
- [Architecture Decision Records (ADRs)](file:///docs/decisions.md)
- [Offline Operation Policy](file:///docs/offline-policy.md)
- [Data Contract Specifications](file:///docs/data-contract.md)

---

## 3. Strict Offline Design Principle

ASTRA adheres to a fundamental architectural mandate:
> **Runtime code must not depend on external APIs or live internet connections.**

1. **Pre-Staged Weights:** All model weights (PyTorch/Safetensors) are pre-loaded into `models/staged/`.
2. **Local Bundles:** Frontend assets are statically bundled; no external fonts or CDN scripts are fetched at runtime.
3. **Local Vector Storage:** FAISS / local indexing operates entirely in-process.
4. **Compliance Verification:** Run `python scripts/check_offline.py` to statically verify zero runtime network egress dependencies.

---

## 4. Current Implementation Status (Phase 0)

In accordance with the controlled engineering workflow, **Phase 0 is restricted to foundation only**:

| Capability | Phase 0 Status | Description |
|---|---|---|
| **Repository Layout** | ✅ Complete | Clean modular monolith structure established |
| **FastAPI Backend** | ✅ Complete | Modular app, configuration management, health endpoints |
| **Health Monitoring** | ✅ Complete | `/health` & `/api/v1/health` returning system & module states |
| **Configuration System** | ✅ Complete | Pydantic Settings with strict offline flag enforcement |
| **Data Contracts** | ✅ Complete | Pydantic v2 schemas for `SceneManifest`, `TileManifest`, etc. |
| **ML Adapter Interfaces** | ✅ Complete | `BaseEmbeddingAdapter` & `BaseChangeDetectorAdapter` |
| **React + TS Frontend** | ✅ Complete | Modern dashboard shell with real-time backend telemetry |
| **Automated Tests** | ✅ Complete | Pytest test suite for health, configuration, data contracts |
| **Development Scripts** | ✅ Complete | Offline scanner (`check_offline.py`), dev and test runners |
| **Semantic Retrieval** | ⏳ Phase 1 | *Deferred by specification to Phase 1* |
| **Change Detection** | ⏳ Phase 2 | *Deferred by specification to Phase 2* |
| **Model Weight Inference**| ⏳ Phase 1/2 | *Deferred by specification to candidate model benchmarking*|

---

## 5. Development Setup

### Prerequisites
- **Python:** 3.11+ (Python 3.14 verified)
- **Node.js:** v18+ (Node v24 verified)
- **PowerShell** or Bash

### Backend Setup
1. Create and activate a virtual environment:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
2. Install dependencies:
   ```powershell
   pip install -r backend/requirements.txt
   ```
3. Run backend tests:
   ```powershell
   python -m pytest tests/ -v
   ```
4. Start the FastAPI development server:
   ```powershell
   python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
   ```
   API will be available at `http://127.0.0.1:8000`  
   API Documentation (Swagger): `http://127.0.0.1:8000/docs`

### Frontend Setup
1. Navigate to the `frontend/` directory and install packages:
   ```powershell
   cd frontend
   npm install
   ```
2. Start the Vite development server:
   ```powershell
   npm run dev
   ```
   Frontend shell will be available at `http://localhost:5173`

### Offline Compliance Check
Run the static security scanner to verify no external URLs or cloud APIs are introduced:
```powershell
python scripts/check_offline.py
```
