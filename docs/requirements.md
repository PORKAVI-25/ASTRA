# A.S.T.R.A. System Requirements Specification

**Project:** A.S.T.R.A. (*Automated Semantic Tracking and Retrieval Architecture*)  
**Challenge:** Smart India Hackathon (SIH) 2026  
**Problem Statement:** SIH26227 / PS227  
**Theme:** Semantic Retrieval and Multi-Temporal Change Analysis of Satellite Imagery  
**Stage:** Phase 0 (Foundation)

---

## 1. Problem Statement Context

Satellite remote sensing produces terabytes of multi-sensor, multi-resolution earth observation imagery. Analysts and automated systems face two core challenges:
1. **Semantic Retrieval**: Locating specific geographic features, terrain classifications, human settlements, or environmental conditions across multi-temporal datasets using semantic queries (text descriptions, reference image patches, or attribute filters) without exhaustive manual indexing.
2. **Multi-Temporal Change Analysis**: Detecting, quantifying, and categorizing structural and land-cover changes across repeated observations over time (e.g. deforestation, urban sprawl, disaster damage, water body shrinkage) while maintaining geographic and temporal accuracy.

ASTRA addresses these challenges through a modular, reproducible, and strictly air-gapped / offline-ready architecture.

---

## 2. Functional Requirements (FR)

### FR-1: Satellite Imagery Ingestion & Tiling
- **FR-1.1**: The system shall accept standard geospatial satellite imagery formats (GeoTIFF, COG, NetCDF).
- **FR-1.2**: Ingestion pipelines shall tile large satellite scenes into uniform, georeferenced chips while computing and assigning a deterministic, stable `tile_id` to each tile.
- **FR-1.3**: Every ingested tile must maintain an immutable, bidirectionally queryable link to its parent source scene ID.

### FR-2: Provenance & Geospatial Metadata Preservation
- **FR-2.1**: The system must preserve Coordinate Reference System (CRS) information (EPSG codes / WKT), bounding box coordinates (both projected and WGS84 latitude/longitude), acquisition timestamp (UTC), sensor/platform name, and band configuration.
- **FR-2.2**: Any preprocessing, radiometric calibration, or normalization applied to a tile must be logged in a reproducible provenance record.

### FR-3: Semantic Retrieval (Phase 1+ Specification)
- **FR-3.1**: The system shall generate multi-modal semantic embeddings from image tiles via decoupled model adapters.
- **FR-3.2**: The system shall index tile embeddings in a local vector index (e.g. FAISS) without external vector database dependencies.
- **FR-3.3**: The system shall support semantic query execution via text prompts and query image patches, returning top-k tiles ranked by similarity with confidence scores.

### FR-4: Multi-Temporal Change Analysis (Phase 2+ Specification)
- **FR-4.1**: Given two or more co-registered imagery tiles of identical geographic bounds acquired at timestamps $T_1$ and $T_2$, the system shall detect pixel-level and semantic-level changes.
- **FR-4.2**: Change analysis shall output localized change masks, categorized transition labels (e.g., vegetation to built-up), and summary metrics.

### FR-5: Evaluation & Benchmarking
- **FR-5.1**: The system shall provide automated evaluation pipelines reporting Mean Average Precision (mAP), Precision@K, Recall@K, and Intersection over Union (IoU) for change masks.
- **FR-5.2**: Never fabricate accuracy numbers; all metrics must be calculated against verifiable ground truth benchmark datasets stored locally in `data/benchmark/`.

---

## 3. Non-Functional Requirements (NFR)

### NFR-1: Strict Offline Operation & Zero External Runtime Dependencies
- **NFR-1.1**: The system must operate fully offline once base software, pre-trained model weights, and datasets are staged.
- **NFR-1.2**: Runtime code paths must strictly prohibit outbound network requests to third-party cloud APIs (e.g., OpenAI, Google Earth Engine runtime, external CDN assets).

### NFR-2: Modularity & Anti-Bloat Guardrails
- **NFR-2.1**: Follow the "Ponytail" anti-bloat principle. Avoid microservices, distributed queues (Kafka/RabbitMQ), and orchestration frameworks (Kubernetes) until specifically approved.
- **NFR-2.2**: The system shall be structured as a clean modular monolith where each domain component communicates through typed internal interfaces.

### NFR-3: Model Decoupling & Benchmarking
- **NFR-3.1**: Machine learning models must be accessed exclusively through adapter interfaces (`BaseEmbeddingAdapter`, `BaseChangeDetectorAdapter`).
- **NFR-3.2**: No single foundation model shall be hard-coded as the permanent system default without formal benchmark comparisons across candidate models.

### NFR-4: Data Integrity & Transparency
- **NFR-4.1**: Demo, synthetic, or mock data must be explicitly flagged with `is_synthetic: true` to prevent contamination of production metrics.
- **NFR-4.2**: All operations must be deterministic and verifiable given the same input data, random seed, and staged model weights.

---

## 4. Phase 0 Acceptance Criteria Matrix

| Item | Requirement | Verification Method | Status |
|---|---|---|---|
| REQ-01 | Monorepo layout with clear separation | Directory inspection | Done |
| REQ-02 | FastAPI backend with health monitoring | Pytest + HTTP GET `/api/v1/health` | Phase 0 |
| REQ-03 | React + TypeScript + Tailwind frontend shell | Vite build + UI dev server | Phase 0 |
| REQ-04 | Configuration system with offline enforcement | Pytest on `backend/config.py` | Phase 0 |
| REQ-05 | Formal Data Contracts (Tile, Scene, Provenance) | Pydantic model validation tests | Phase 0 |
| REQ-06 | Offline compliance verification script | Static scanner `scripts/check_offline.py` | Phase 0 |
| REQ-07 | Comprehensive architecture & ADR documentation | Review against design rules | Phase 0 |
