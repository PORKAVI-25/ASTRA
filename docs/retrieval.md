# ASTRA Phase 2B — Local Semantic Retrieval Engine Documentation

- **Project:** A.S.T.R.A. (*Automated Semantic Tracking and Retrieval Architecture*)
- **Challenge:** Smart India Hackathon 2026 — PS 227
- **Stage:** Phase 2B (Production-Shaped Local Semantic Retrieval Engine)
- **Status:** Complete & Verified
- **Date:** 2026-09-16

---

## 1. Executive Summary & Architecture Overview

Phase 2B establishes ASTRA's operational semantic retrieval layer, bridging Phase 1 geospatial ingestion and tiling with the foundation models staged and validated in Phase 2A/2A.1.

The retrieval subsystem operates **100% offline**, requiring zero cloud connections, zero remote inference APIs, and zero external database daemons. It enables defense analysts and disaster response teams to perform natural language text-to-image queries and visual image-to-image similarity searches across multi-spectral satellite imagery using local staged model weights.

### Subsystem Component Architecture

```
+---------------------------------------------------------------------------------------------------------+
|                                        FastAPI REST Retrieval API                                       |
|                  POST /api/v1/retrieval/text    |    POST /api/v1/retrieval/image                        |
|                                GET /api/v1/retrieval/health                                             |
+----------------------------------------------------+----------------------------------------------------+
                                                     |
                                                     v
+---------------------------------------------------------------------------------------------------------+
|                                             RetrievalService                                            |
|   - Coordinates query embedding, metadata pre-filtering, vector similarity search, and ranking          |
+-----------------------------+---------------------------------------+-----------------------------------+
                              |                                       |
                              v                                       v
               +------------------------------+       +-------------------------------+
               |       EmbeddingService       |       |         MetadataStore         |
               |  - embed_image()             |       |  - Persistent SQLite database |
               |  - embed_text()              |       |  - Exact 2D AOI bounding box  |
               |  - wraps RemoteCLIP /        |       |  - Date range & sensor filter |
               |    EmbeddingModelAdapter     |       |  - Provenance reference links |
               +------------------------------+       +---------------+---------------+
                                                                      |
                                                                      v
                                                      +-------------------------------+
                                                      |          VectorIndex          |
                                                      |  - NumpyCosineVectorIndex     |
                                                      |  - Normalized inner product   |
                                                      |  - Deterministic tie-breaking |
                                                      |  - Persistent .npz storage    |
                                                      +-------------------------------+
```

---

## 2. Core Interfaces & Component Design

The retrieval layer is organized cleanly under `backend/ml/retrieval/`:

```
backend/ml/retrieval/
    __init__.py           # Unified public exports
    types.py              # Pydantic data contracts (requests, filters, responses, records)
    embedding_service.py  # Wrapper over Phase 2A foundation model adapters
    vector_index.py       # VectorIndex abstract interface & NumPy exact cosine backend
    metadata_store.py     # SQLite metadata store with spatial AOI & attribute filtering
    retrieval_service.py  # High-level query orchestration and ranking service
```

### A. `EmbeddingService`
- **Role**: Wraps underlying `EmbeddingModelAdapter` instances (RemoteCLIP ViT-B/32, OpenAI CLIP, Reference Baseline).
- **Enforcement**: Strictly offline; validates that local weight checkpoints are present on disk before loading. If missing, raises an explicit `RuntimeError` rather than attempting a network download.
- **Normalization**: Enforces unit L2 norm ($\|v\|_2 = 1.0$) across all output vectors for consistent cosine inner product mathematics.

### B. `VectorIndex` & `NumpyCosineVectorIndex`
- **Role**: High-performance, exact in-memory cosine similarity search with persistent disk serialization.
- **Backend**: Pure NumPy matrix multiplication (`matrix.dot(query)`).
- **Tie-Breaking**: Implements strictly deterministic ranking (`-round(score, 6)`, `tile_id ASC`) ensuring byte-for-byte identical search results across runs and platforms.
- **Pre-Filtering**: Accepts `candidate_ids` to restrict matrix operations exclusively to tiles meeting spatial and temporal metadata filter criteria.

### C. `MetadataStore`
- **Role**: Embedded SQLite database (`data/indices/metadata_store.sqlite3`) storing tile bounding boxes, acquisition timestamps, sensor/platform tags, and embedding lineage records.
- **Spatial AOI Filter**: Exact 2D bounding box intersection:
  $$\text{box}_A \cap \text{box}_B \iff (A.\min_x \le B.\max_x \land A.\max_x \ge B.\min_x \land A.\min_y \le B.\max_y \land A.\max_y \ge B.\min_y)$$
- **Incremental Staleness**: Detects whether a tile's pixel hash (`sha256_hash`), model ID, or preprocessing version has changed, preventing redundant re-embedding.

### D. `RetrievalService`
- **Role**: Orchestrates end-to-end user queries (`text_to_image`, `image_to_image`).
- **Workflow**:
  1. Vectorizes query (text prompt or local image tile).
  2. Queries `MetadataStore` for candidate tile IDs matching filters (AOI, date range, sensor, platform).
  3. Executes similarity search in `VectorIndex` restricted to candidate IDs.
  4. Enriches ranked matches with spatial coordinates, acquisition date, sensor metadata, and provenance IDs.

---

## 3. Storage Layout & Data Flow

All persistent retrieval assets reside locally under `data/indices/`:

```
data/
  manifests/
    scenes/*.json            # Phase 1 SceneManifest records
    tiles/*.json             # Phase 1 TileManifest records
    provenance/prov_*.json   # Immutable ASTRA Provenance records
  indices/
    metadata_store.sqlite3   # Persistent SQLite metadata & spatial index
    vector_index.npz         # Compressed NumPy vector store (IDs and float32 matrix)
```

### SQLite Schema

```sql
CREATE TABLE tiles (
    tile_id TEXT PRIMARY KEY,
    source_scene_id TEXT NOT NULL,
    sensor TEXT NOT NULL,
    platform TEXT NOT NULL,
    acquisition_time TEXT,
    crs TEXT NOT NULL,
    min_lon REAL NOT NULL,
    min_lat REAL NOT NULL,
    max_lon REAL NOT NULL,
    max_lat REAL NOT NULL,
    file_path TEXT NOT NULL,
    sha256_hash TEXT NOT NULL,
    is_synthetic INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE embeddings (
    tile_id TEXT PRIMARY KEY,
    scene_id TEXT NOT NULL,
    embedding_model_id TEXT NOT NULL,
    embedding_model_version TEXT NOT NULL,
    embedding_dimension INTEGER NOT NULL,
    preprocessing_version TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    vector_index_reference TEXT NOT NULL,
    provenance_reference TEXT NOT NULL,
    FOREIGN KEY (tile_id) REFERENCES tiles (tile_id) ON DELETE CASCADE
);
```

---

## 4. Embedding Lifecycle & Incremental Indexing

```
  [Source GeoTIFF / Tile]
             |
             v
   Compute SHA-256 Hash
             |
             v
   Check MetadataStore:
   - Does tile_id exist?
   - Does source_sha256 match?
   - Does model_id match?
   - Does preprocessing_version match?
             |
     +-------+-------+
     |               |
   [MATCH]       [MISMATCH / NEW]
     |               |
   SKIP (0 ms)       v
               Run EmbeddingService
                     |
                     v
               Record Provenance
                     |
                     v
               Upsert VectorIndex & MetadataStore
```

- **Unchanged Tiles**: Skipped immediately without model invocation.
- **Modified Rasters**: When a tile's content changes, the old vector is updated in-place via `VectorIndex.upsert()` and the new lineage is saved.

---

## 5. Metadata & Spatial Filtering

Filtering is applied **before** or during vector distance evaluation:

1. **Spatial Area of Interest (AOI)**: Takes a WGS84 `GeoBoundingBox` (`min_lon`, `min_lat`, `max_lon`, `max_lat`). Only tiles geometrically overlapping the AOI are evaluated.
2. **Temporal Window**: `date_from` and `date_to` constrain search to specific acquisition timeframes.
3. **Sensor & Platform**: Case-insensitive filtering on sensor (`Sentinel-2A MSI`, `Landsat-8 OLI`) or platform (`Sentinel-2`, `Landsat-8`).
4. **Scene Isolation**: `scene_id` limits search to a single satellite acquisition.

---

## 6. Provenance Tracking

Conforming to ASTRA-DC-v0.1, every generated embedding generates an immutable `ProvenanceRecord`:

- **Lineage Chain**:
  $$\text{Source Scene} \longrightarrow \text{Tiled Chip} \longrightarrow \text{Embedding Generation} \longrightarrow \text{Vector Index Entry}$$
- **Provenance Attributes**:
  - `provenance_id`: Unique identifier (e.g. `prov_emb_...`).
  - `target_tile_id`: Targeted tile chip ID.
  - `source_scene_id`: Root satellite acquisition ID.
  - `processing_stage`: `"semantic_embedding_generation"`.
  - `pipeline_version`: `"0.2.0"`.
  - `parameters`: Model ID, version, dimension, preprocessing tag, and source tile SHA-256 hash.
  - `executed_by`: `"astra.retrieval.indexer"`.
  - `timestamp`: UTC execution time.

---

## 7. REST API Endpoints

All endpoints are mounted under `/api/v1/retrieval`:

### 1. Text-to-Image Search: `POST /api/v1/retrieval/text`
- **Request Body**:
  ```json
  {
    "query": "urban residential settlement and highway network",
    "top_k": 5,
    "filters": {
      "sensor": "Sentinel-2A MSI",
      "date_from": "2026-01-01T00:00:00Z",
      "date_to": "2026-12-31T23:59:59Z",
      "aoi": {
        "min_lon": 76.8,
        "min_lat": 12.5,
        "max_lon": 77.0,
        "max_lat": 12.7
      }
    }
  }
  ```
- **Response**:
  ```json
  {
    "query": "urban residential settlement and highway network",
    "query_type": "text",
    "total_indexed_tiles": 4,
    "filtered_candidates_count": 4,
    "scored_candidates_count": 4,
    "total_candidates_searched": 4,
    "returned_count": 4,
    "results": [
      {
        "tile_id": "tile_synthetic_test_utm_545f364d_c0000_r0000_z14",
        "scene_id": "synthetic_test_utm_545f364d",
        "score": 0.8421,
        "rank": 1,
        "acquisition_time": "2026-03-15T05:20:21Z",
        "sensor": "Sentinel-2A MSI",
        "platform": "Sentinel-2",
        "bounds_wgs84": {
          "min_lon": 76.841204,
          "min_lat": 12.611212,
          "max_lon": 76.888661,
          "max_lat": 12.657817
        },
        "provenance_id": "prov_emb_...",
        "embedding_model_id": "remoteclip-vit-b-32",
        "embedding_model_version": "1.0.0"
      }
    ],
    "execution_time_ms": 84.5
  }
  ```

### Candidate Count Semantics
- `total_indexed_tiles`: Total number of active tile vectors registered in the vector index.
- `filtered_candidates_count`: Number of tiles that passed metadata/AOI/temporal pre-filters and were eligible for scoring.
- `scored_candidates_count`: Exact number of candidate tile vectors actually evaluated by vector similarity scoring.
- `total_candidates_searched`: Backward-compatible alias for `scored_candidates_count`.
- `returned_count`: Number of top-k ranked results returned in the `results` list.

### 2. Image-to-Image Search: `POST /api/v1/retrieval/image`
- Accepts a local filesystem path (`file_path`) or an existing indexed tile identifier (`tile_id`).
- Supports optional `exclude_query_tile` (boolean, defaults to `true` when querying by `tile_id`) to omit the query tile itself from results and ensure similarity retrieval against all other candidates.
- **Security Check**: Rejects remote URLs (`http://`, `https://`, `s3://`) with HTTP 400 Bad Request to maintain strict air-gap compliance.

### 3. Health & Telemetry: `GET /api/v1/retrieval/health`
- Returns index size, active embedding model ID, dimension, offline status, and indexed scenes count.

---

## 8. CLI Index Construction Utility

Index generation is performed via `scripts/build_retrieval_index.py`:

```bash
# Build index using default RemoteCLIP model (CPU)
.\.venv\Scripts\python.exe scripts/build_retrieval_index.py

# Force re-indexing of all tiles
.\.venv\Scripts\python.exe scripts/build_retrieval_index.py --force-reindex

# Build index using reference baseline model (deterministic CI mode)
.\.venv\Scripts\python.exe scripts/build_retrieval_index.py --model reference-spectral-spatial
```

---

## 9. Clarifications & Architectural Distinctions

> [!IMPORTANT]
> - **Benchmark vs. Retrieval Engine**:
>   - *Phase 2A Benchmark*: A controlled model-selection evaluation gate measuring Top-1 accuracy, MRR, and latency on small deterministic fixtures (15 real EuroSAT tiles, 15 synthetic tiles).
>   - *Phase 2B Retrieval Engine*: The production-shaped operational retrieval architecture supporting incremental tile ingestion, spatial/attribute pre-filtering, and zero-shot search across arbitrary ingested scenes.
> - **Vector Index Scalability**:
>   - The current exact NumPy cosine index serves as the initial exact backend; scale threshold and latency trade-offs require empirical benchmarking on larger corpuses before making capacity claims.
>   - For large-scale multi-million tile deployments, the `VectorIndex` abstract interface allows drop-in adoption of an approximate nearest neighbor (ANN) backend (e.g. HNSW or IVF-PQ) without altering the `RetrievalService` or REST API contracts.
