# A.S.T.R.A. Architecture Decision Records (ADR)

This document records the architectural and design decisions made for project **A.S.T.R.A.**, including the rationale, context, and consequences.

---

## ADR-001: Modular Monolith Architecture over Microservices

### Status: Accepted
### Date: 2026-09-16
### Deciders: ASTRA Engineering Team

### Context
Problem Statement SIH26227 requires semantic retrieval and multi-temporal change analysis of satellite imagery. It is common to prematurely decompose such systems into distributed microservices, message queues (Kafka, RabbitMQ), and container orchestrators (Kubernetes). However, distributed systems introduce network latency, serialization overhead, deployment complexity, and debugging friction.

### Decision
ASTRA will be implemented as a **modular monolith** in Python (FastAPI backend) with clear logical boundaries (`ingestion`, `retrieval`, `change_analysis`, `provenance`, `evaluation`) and a single React frontend shell.

### Consequences
- **Positive:** Zero inter-service network overhead; simplified single-step local testing; frictionless refactoring; low operational overhead.
- **Negative:** Subsystems share the same Python runtime process during Phase 0; long-running computations must eventually be managed via worker processes (multiprocessing / Celery) if needed later.

---

## ADR-002: Strict Offline-First Operation and Asset Pre-Staging

### Status: Accepted
### Date: 2026-09-16
### Deciders: ASTRA Engineering Team

### Context
Satellite data processing systems in defense, emergency response, and secure government contexts frequently operate in air-gapped or disconnected environments. Relying on live remote APIs (OpenAI, HuggingFace Hub downloads at runtime, Google Earth Engine API, cloud CDNs) renders the system vulnerable to network failures and security policy violations.

### Decision
ASTRA must operate completely offline once staged:
1. No runtime code path may issue outbound HTTP/HTTPS requests to external cloud services.
2. All model weights, vocabulary files, geospatial reference datasets, and frontend packages must be pre-staged locally.
3. An explicit configuration flag `ASTRA_OFFLINE_MODE=true` is enabled by default.

### Consequences
- **Positive:** Full air-gap readiness; immunity to network outages; strict data privacy; deterministic execution.
- **Negative:** Initial staging phase required before first execution; local disk footprint is larger.

---

## ADR-003: Model Adapter Pattern for Foundation Models

### Status: Accepted
### Date: 2026-09-16
### Deciders: ASTRA Engineering Team

### Context
Earth Observation foundation models are in rapid development (RemoteCLIP, SatMAE, Prithvi, Clay, etc.). Hardcoding a single model into retrieval and change detection pipelines locks the architecture to one vendor or model architecture and prevents empirical benchmarking.

### Decision
Define explicit abstract adapter classes:
- `BaseEmbeddingAdapter` in `ml/embeddings/base.py`
- `BaseChangeDetectorAdapter` in `ml/change_detection/base.py`
All internal services interact exclusively with these adapter interfaces. Concrete models are plugged in as interchangeable adapters.

### Consequences
- **Positive:** Zero lock-in; straightforward benchmarking and ablation studies; candidate models can be swapped via configuration.
- **Negative:** Minimal layer of interface indirection.

---

## ADR-004: Stable Tile Identity & Immutable Scene Provenance Linkage

### Status: Accepted
### Date: 2026-09-16
### Deciders: ASTRA Engineering Team

### Context
When satellite scenes are tiled into chips, losing connection to the original scene, CRS, or acquisition metadata leads to non-reproducible predictions and errors in change detection. Furthermore, non-deterministic tile identifiers make caching and cross-temporal pairing brittle.

### Decision
1. Every imagery tile is assigned a deterministic, content- or coordinate-derived `tile_id` (e.g., `{scene_id}_{x}_{y}_{zoom}`).
2. Every tile manifest explicitly embeds `source_scene_id`, EPSG CRS, bounding box coordinates, acquisition timestamp (UTC), sensor/platform name, and band specifications.
3. Synthetic and demo tiles must be tagged with `is_synthetic: true`.

### Consequences
- **Positive:** Full auditability, reproducible spatial joins, reliable temporal pairing between $T_1$ and $T_2$ tiles.
- **Negative:** Slightly larger manifest metadata payloads.

---

## ADR-005: Local Vector Retrieval Strategy (FAISS / Local Vector Index)

### Status: Accepted
### Date: 2026-09-16
### Deciders: ASTRA Engineering Team

### Context
Cloud-native vector databases (Pinecone, Weaviate Cloud, Qdrant Cloud) violate the strict offline requirement. Heavy self-hosted databases (e.g., distributed Milvus) add excessive bloat to a hackathon / edge-deployable prototype.

### Decision
ASTRA will use a locally embeddable vector index (such as FAISS or an in-memory cosine similarity index for initial small-scale benchmarks) that reads directly from local storage and operates in-process without daemon dependencies.

### Consequences
- **Positive:** Zero external server dependencies; extremely fast vector lookups; fully offline.
- **Negative:** Sharding across multiple physical machines is deferred until datasets exceed single-machine memory capacity.

---

## ADR-006: Technology Stack Selection

### Status: Accepted
### Date: 2026-09-16
### Deciders: ASTRA Engineering Team

### Context
Selecting technologies that align with fast iteration, strong typing, maintainability, and geospatial ecosystem compatibility.

### Decision
- **Backend:** Python 3.14 + FastAPI + Pydantic v2 + Uvicorn.
- **Frontend:** React 19 + TypeScript + Vite + Tailwind CSS.
- **Testing:** Pytest for backend, TypeScript type-checking and Vite build for frontend.
- **Geospatial & ML:** PyTorch, NumPy, Pillow, Shapely (staged locally).

### Consequences
- **Positive:** Excellent performance, automatic OpenAPI documentation, type safety from frontend to backend data contracts.
- **Negative:** Multi-language monorepo requires coordinating Python and Node.js toolchains.
