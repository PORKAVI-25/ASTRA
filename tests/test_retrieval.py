"""Comprehensive automated test suite for Phase 2B Semantic Retrieval Engine.

Covers all 18 specified test requirements:
1. Embedding service contract
2. Deterministic normalization
3. Vector add and search
4. Vector persistence and reload
5. Incremental upsert
6. Stale embedding replacement
7. Metadata filtering attributes
8. AOI spatial filtering
9. Date range filtering
10. Sensor filtering
11. Text-to-image retrieval
12. Image-to-image retrieval
13. Deterministic ranking and tie-breaking
14. Provenance linkage
15. Missing local model behavior
16. Offline enforcement
17. API integration
18. Empty-index behavior
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import numpy as np
import pytest
from starlette.testclient import TestClient

from backend.api.v1.endpoints.retrieval import set_retrieval_service
from backend.main import app
from backend.ml.benchmark.candidates import (
    ReferenceSpectralSpatialAdapter,
    RemoteCLIPAdapter,
    registry,
)
from backend.ml.retrieval.embedding_service import EmbeddingService
from backend.ml.retrieval.metadata_store import MetadataStore
from backend.ml.retrieval.retrieval_service import RetrievalService
from backend.ml.retrieval.types import (
    EmbeddingRecord,
    RetrievalFilter,
    TextRetrievalRequest,
)
from backend.ml.retrieval.vector_index import NumpyCosineVectorIndex
from geospatial.contracts import GeoBoundingBox, TileDimensions, TileManifest


@pytest.fixture(scope="module")
def retrieval_test_dir(tmp_path_factory) -> Path:
    """Provides an isolated directory for retrieval tests."""
    temp_dir = tmp_path_factory.mktemp("astra_retrieval_test")
    return temp_dir


@pytest.fixture(scope="module")
def synthetic_tiles(retrieval_test_dir: Path) -> list:
    """Generates synthetic tile images and TileManifest instances."""
    import rasterio
    from rasterio.transform import from_origin

    tiles = []
    tile_dir = retrieval_test_dir / "tiles"
    tile_dir.mkdir(parents=True, exist_ok=True)

    # 4 distinct synthetic tiles across space, time, and sensor
    specs = [
        ("tile_001", "scene_alpha", "Sentinel-2A MSI", "Sentinel-2", "2026-03-01T10:00:00Z", 77.10, 13.10, 77.20, 13.20, 1),
        ("tile_002", "scene_alpha", "Sentinel-2A MSI", "Sentinel-2", "2026-03-01T10:00:00Z", 77.20, 13.10, 77.30, 13.20, 2),
        ("tile_003", "scene_beta",  "Landsat-8 OLI",   "Landsat-8",  "2026-04-15T09:30:00Z", 78.50, 14.50, 78.60, 14.60, 3),
        ("tile_004", "scene_gamma", "Sentinel-2B MSI", "Sentinel-2", "2026-05-20T11:15:00Z", 76.00, 12.00, 76.10, 12.10, 4),
    ]

    for t_id, s_id, sensor, platform, acq_str, min_lon, min_lat, max_lon, max_lat, seed in specs:
        img_path = tile_dir / f"{t_id}.png"
        rng = np.random.RandomState(seed)
        data = rng.randint(50, 240, size=(3, 64, 64), dtype=np.uint8)

        # Write raster
        transform = from_origin(min_lon, max_lat, 0.001, 0.001)
        with rasterio.open(
            img_path,
            "w",
            driver="PNG",
            height=64,
            width=64,
            count=3,
            dtype="uint8",
            crs="EPSG:4326",
            transform=transform,
        ) as dst:
            dst.write(data)

        # Compute hash
        import hashlib
        sha = hashlib.sha256(img_path.read_bytes()).hexdigest()

        tile = TileManifest(
            tile_id=t_id,
            source_scene_id=s_id,
            tile_col=0,
            tile_row=0,
            zoom_level=14,
            dimensions=TileDimensions(width_px=64, height_px=64, channels=3),
            crs="EPSG:4326",
            bounds_wgs84=GeoBoundingBox(min_lon=min_lon, min_lat=min_lat, max_lon=max_lon, max_lat=max_lat),
            acquisition_time=datetime.fromisoformat(acq_str),
            sensor=sensor,
            file_path=str(img_path),
            sha256_hash=sha,
            is_synthetic=True,
        )
        tiles.append((tile, platform))

    return tiles


@pytest.fixture(scope="module")
def reference_embedding_service() -> EmbeddingService:
    """Provides a deterministic EmbeddingService using reference adapter for fast test execution."""
    adapter = ReferenceSpectralSpatialAdapter()
    return EmbeddingService(adapter=adapter)


@pytest.fixture
def isolated_retrieval_system(retrieval_test_dir: Path, reference_embedding_service: EmbeddingService):
    """Provides isolated VectorIndex, MetadataStore, and RetrievalService."""
    vec_path = retrieval_test_dir / f"test_vec_{np.random.randint(10000)}.npz"
    db_path = retrieval_test_dir / f"test_meta_{np.random.randint(10000)}.sqlite3"

    vec_index = NumpyCosineVectorIndex(dimension=512, storage_path=vec_path)
    meta_store = MetadataStore(db_path=db_path)
    service = RetrievalService(reference_embedding_service, vec_index, meta_store)

    return service, vec_index, meta_store


# ==============================================================================
# 1. Embedding Service Contract
# ==============================================================================
def test_01_embedding_service_contract(reference_embedding_service: EmbeddingService):
    """Verifies that EmbeddingService adheres to the required contract."""
    svc = reference_embedding_service
    assert svc.model_id == "reference-spectral-spatial"
    assert svc.embedding_dimension == 512
    assert isinstance(svc.preprocessing_version, str)
    assert len(svc.preprocessing_version) > 0


# ==============================================================================
# 2. Deterministic Normalization
# ==============================================================================
def test_02_deterministic_normalization(reference_embedding_service: EmbeddingService, synthetic_tiles):
    """Verifies that embedding vectors are strictly unit L2 normalized and deterministic."""
    tile, _ = synthetic_tiles[0]
    vec1 = reference_embedding_service.embed_image(tile.file_path)
    vec2 = reference_embedding_service.embed_image(tile.file_path)

    # Unit norm check
    norm = float(np.linalg.norm(vec1))
    assert abs(norm - 1.0) < 1e-6, f"Norm was {norm}, expected 1.0"

    # Determinism check (bit-for-bit identical)
    np.testing.assert_array_almost_equal(vec1, vec2, decimal=6)


# ==============================================================================
# 3. Vector Add and Search
# ==============================================================================
def test_03_vector_index_add_and_search(isolated_retrieval_system):
    """Verifies adding vectors to index and querying returns ranked results."""
    _, vec_index, _ = isolated_retrieval_system

    v1 = np.ones(512, dtype=np.float32) / np.sqrt(512)
    v2 = np.zeros(512, dtype=np.float32)
    v2[0] = 1.0

    vec_index.add("id_1", v1)
    vec_index.add("id_2", v2)

    assert vec_index.size() == 2
    assert vec_index.contains("id_1")

    # Search query identical to v2
    results = vec_index.search(v2, top_k=2)
    assert len(results) == 2
    assert results[0][0] == "id_2"
    assert abs(results[0][1] - 1.0) < 1e-5


# ==============================================================================
# 4. Vector Persistence and Reload
# ==============================================================================
def test_04_vector_index_persistence_and_reload(retrieval_test_dir: Path):
    """Verifies vector index persistence to .npz disk and byte-accurate restoration."""
    save_path = retrieval_test_dir / "persist_test.npz"
    index = NumpyCosineVectorIndex(dimension=512, storage_path=save_path)

    v1 = np.ones(512, dtype=np.float32) / np.sqrt(512)
    index.add("tile_persist_1", v1)
    index.save()

    assert save_path.exists()

    # Reload into fresh index
    reloaded = NumpyCosineVectorIndex(dimension=512, storage_path=save_path)
    assert reloaded.size() == 1
    assert reloaded.contains("tile_persist_1")

    v_stored = reloaded.get_vector("tile_persist_1")
    np.testing.assert_array_almost_equal(v1, v_stored, decimal=6)


# ==============================================================================
# 5. Incremental Upsert
# ==============================================================================
def test_05_incremental_upsert(isolated_retrieval_system):
    """Verifies that upserting an existing ID updates the vector without size inflation."""
    _, vec_index, _ = isolated_retrieval_system

    v1 = np.ones(512, dtype=np.float32) / np.sqrt(512)
    v2 = -v1

    vec_index.upsert("tile_alpha", v1)
    assert vec_index.size() == 1

    # Upsert with new vector
    vec_index.upsert("tile_alpha", v2)
    assert vec_index.size() == 1

    stored = vec_index.get_vector("tile_alpha")
    np.testing.assert_array_almost_equal(stored, v2, decimal=6)


# ==============================================================================
# 6. Stale Embedding Replacement
# ==============================================================================
def test_06_stale_embedding_replacement(isolated_retrieval_system, synthetic_tiles):
    """Verifies that changed image hash or model tags trigger staleness detection."""
    _, _, meta_store = isolated_retrieval_system
    tile, platform = synthetic_tiles[0]

    # Store initial tile and embedding
    meta_store.store_tile(tile, platform=platform)
    emb_rec = EmbeddingRecord(
        tile_id=tile.tile_id,
        scene_id=tile.source_scene_id,
        embedding_model_id="remoteclip-vit-b-32",
        embedding_model_version="1.0.0",
        embedding_dimension=512,
        preprocessing_version="v1.0.0-clip",
        source_sha256=tile.sha256_hash,
        created_at=datetime.now(timezone.utc),
        vector_index_reference=f"idx_{tile.tile_id}",
        provenance_reference="prov_001",
    )
    meta_store.store_embedding_record(emb_rec)

    # 1. Unchanged parameters -> NOT stale
    assert not meta_store.is_tile_stale(
        tile_id=tile.tile_id,
        current_sha256=tile.sha256_hash,
        model_id="remoteclip-vit-b-32",
        preprocessing_version="v1.0.0-clip",
    )

    # 2. Hash changed -> STALE
    assert meta_store.is_tile_stale(
        tile_id=tile.tile_id,
        current_sha256="modified_sha256_hash_9999999",
        model_id="remoteclip-vit-b-32",
        preprocessing_version="v1.0.0-clip",
    )

    # 3. Model changed -> STALE
    assert meta_store.is_tile_stale(
        tile_id=tile.tile_id,
        current_sha256=tile.sha256_hash,
        model_id="clay-foundation-v0.1",
        preprocessing_version="v1.0.0-clip",
    )


# ==============================================================================
# 7. Metadata Filtering Attributes
# ==============================================================================
def test_07_metadata_filtering_attributes(isolated_retrieval_system, synthetic_tiles):
    """Verifies filtering by scene_id and platform."""
    _, _, meta_store = isolated_retrieval_system
    for tile, platform in synthetic_tiles:
        meta_store.store_tile(tile, platform=platform)

    # Filter by scene
    matches_alpha = meta_store.filter_tile_ids(RetrievalFilter(scene_id="scene_alpha"))
    assert matches_alpha == {"tile_001", "tile_002"}

    # Filter by platform
    matches_landsat = meta_store.filter_tile_ids(RetrievalFilter(platform="Landsat-8"))
    assert matches_landsat == {"tile_003"}


# ==============================================================================
# 8. AOI Spatial Filtering
# ==============================================================================
def test_08_aoi_spatial_filtering(isolated_retrieval_system, synthetic_tiles):
    """Verifies exact 2D bounding box intersection filtering."""
    _, _, meta_store = isolated_retrieval_system
    for tile, platform in synthetic_tiles:
        meta_store.store_tile(tile, platform=platform)

    # AOI covering tile_001 and tile_002 (lon 77.0 to 77.4, lat 13.0 to 13.3)
    aoi_hit = GeoBoundingBox(min_lon=77.05, min_lat=13.05, max_lon=77.35, max_lat=13.25)
    hit_ids = meta_store.filter_tile_ids(RetrievalFilter(aoi=aoi_hit))
    assert "tile_001" in hit_ids
    assert "tile_002" in hit_ids
    assert "tile_003" not in hit_ids
    assert "tile_004" not in hit_ids

    # AOI in Atlantic Ocean (disjoint) -> 0 matches
    aoi_miss = GeoBoundingBox(min_lon=-20.0, min_lat=0.0, max_lon=-10.0, max_lat=10.0)
    miss_ids = meta_store.filter_tile_ids(RetrievalFilter(aoi=aoi_miss))
    assert len(miss_ids) == 0


# ==============================================================================
# 9. Date Range Filtering
# ==============================================================================
def test_09_date_range_filtering(isolated_retrieval_system, synthetic_tiles):
    """Verifies date_from and date_to acquisition filtering."""
    _, _, meta_store = isolated_retrieval_system
    for tile, platform in synthetic_tiles:
        meta_store.store_tile(tile, platform=platform)

    # Tiles acquisition dates: tile_001/002: March 2026, tile_003: April 2026, tile_004: May 2026
    filt_march = RetrievalFilter(
        date_from=datetime(2026, 2, 1, tzinfo=timezone.utc),
        date_to=datetime(2026, 3, 31, tzinfo=timezone.utc),
    )
    res_march = meta_store.filter_tile_ids(filt_march)
    assert res_march == {"tile_001", "tile_002"}

    filt_april_may = RetrievalFilter(
        date_from=datetime(2026, 4, 1, tzinfo=timezone.utc),
    )
    res_late = meta_store.filter_tile_ids(filt_april_may)
    assert res_late == {"tile_003", "tile_004"}


# ==============================================================================
# 10. Sensor Filtering
# ==============================================================================
def test_10_sensor_filtering(isolated_retrieval_system, synthetic_tiles):
    """Verifies case-insensitive sensor name filtering."""
    _, _, meta_store = isolated_retrieval_system
    for tile, platform in synthetic_tiles:
        meta_store.store_tile(tile, platform=platform)

    res = meta_store.filter_tile_ids(RetrievalFilter(sensor="sentinel-2a msi"))
    assert res == {"tile_001", "tile_002"}

    res_l8 = meta_store.filter_tile_ids(RetrievalFilter(sensor="LANDSAT-8 OLI"))
    assert res_l8 == {"tile_003"}


# ==============================================================================
# 11. Text-to-Image Retrieval
# ==============================================================================
def test_11_text_to_image_retrieval(isolated_retrieval_system, synthetic_tiles):
    """Verifies end-to-end text query execution, ranking, and response fields."""
    service, vec_index, meta_store = isolated_retrieval_system

    for tile, platform in synthetic_tiles:
        v = service.embedding_service.embed_image(tile.file_path)
        vec_index.add(tile.tile_id, v)
        meta_store.store_tile(tile, platform=platform)
        meta_store.store_embedding_record(
            EmbeddingRecord(
                tile_id=tile.tile_id,
                scene_id=tile.source_scene_id,
                embedding_model_id=service.embedding_service.model_id,
                embedding_model_version="1.0.0",
                embedding_dimension=512,
                preprocessing_version="v1.0",
                source_sha256=tile.sha256_hash,
                created_at=datetime.now(timezone.utc),
                vector_index_reference=f"idx_{tile.tile_id}",
                provenance_reference=f"prov_{tile.tile_id}",
            )
        )

    resp = service.text_to_image("dense vegetation forest", top_k=3)
    assert resp.query == "dense vegetation forest"
    assert resp.query_type == "text"
    assert resp.returned_count == 3
    assert len(resp.results) == 3

    top = resp.results[0]
    assert top.rank == 1
    assert top.provenance_id == f"prov_{top.tile_id}"
    assert top.bounds_wgs84 is not None
    assert top.embedding_model_id == service.embedding_service.model_id


# ==============================================================================
# 12. Image-to-Image Retrieval
# ==============================================================================
def test_12_image_to_image_retrieval(isolated_retrieval_system, synthetic_tiles):
    """Verifies image similarity retrieval matches identical tile with top score."""
    service, vec_index, meta_store = isolated_retrieval_system

    for tile, platform in synthetic_tiles:
        v = service.embedding_service.embed_image(tile.file_path)
        vec_index.add(tile.tile_id, v)
        meta_store.store_tile(tile, platform=platform)

    query_tile, _ = synthetic_tiles[0]
    resp = service.image_to_image(image_input=query_tile.file_path, top_k=2)

    assert resp.query_type == "image"
    assert resp.returned_count == 2
    # First match must be the query tile itself with cosine similarity ~ 1.0
    assert resp.results[0].tile_id == query_tile.tile_id
    assert abs(resp.results[0].score - 1.0) < 1e-4


# ==============================================================================
# 13. Deterministic Ranking and Tie-Breaking
# ==============================================================================
def test_13_deterministic_ranking_and_tie_breaking():
    """Verifies that equal similarity scores break ties deterministically on tile_id ascending."""
    vec_index = NumpyCosineVectorIndex(dimension=4)

    # Identical vectors for three different IDs
    v = np.array([0.5, 0.5, 0.5, 0.5], dtype=np.float32)
    vec_index.add("zebra_tile", v)
    vec_index.add("alpha_tile", v)
    vec_index.add("beta_tile", v)

    results = vec_index.search(v, top_k=3)
    ids = [r[0] for r in results]

    # Must be alphabetically ordered for equal scores
    assert ids == ["alpha_tile", "beta_tile", "zebra_tile"]


# ==============================================================================
# 14. Provenance Linkage
# ==============================================================================
def test_14_provenance_linkage(isolated_retrieval_system, synthetic_tiles):
    """Verifies that retrieval result objects contain valid provenance IDs."""
    service, vec_index, meta_store = isolated_retrieval_system
    tile, platform = synthetic_tiles[0]

    v = service.embedding_service.embed_image(tile.file_path)
    vec_index.add(tile.tile_id, v)
    meta_store.store_tile(tile, platform=platform)
    meta_store.store_embedding_record(
        EmbeddingRecord(
            tile_id=tile.tile_id,
            scene_id=tile.source_scene_id,
            embedding_model_id="remoteclip-vit-b-32",
            embedding_model_version="1.0.0",
            embedding_dimension=512,
            preprocessing_version="v1.0.0-clip",
            source_sha256=tile.sha256_hash,
            created_at=datetime.now(timezone.utc),
            vector_index_reference="idx_001",
            provenance_reference="prov_lineage_test_12345",
        )
    )

    resp = service.image_to_image(tile.file_path, top_k=1)
    assert resp.results[0].provenance_id == "prov_lineage_test_12345"


# ==============================================================================
# 15. Missing Local Model Fails Clearly (Zero Download)
# ==============================================================================
def test_15_missing_local_model_fails_clearly_zero_download():
    """Verifies that requesting an unstaged model raises RuntimeError without downloading."""
    with pytest.raises(RuntimeError) as exc_info:
        # Clay foundation model is registered as NOT STAGED
        EmbeddingService(model_id="clay-v0.1")

    assert "cannot be loaded" in str(exc_info.value)
    assert "staged offline" in str(exc_info.value)


# ==============================================================================
# 16. Offline Enforcement Zero Network Calls
# ==============================================================================
def test_16_offline_enforcement_zero_network_calls(isolated_retrieval_system, synthetic_tiles):
    """Verifies that search execution makes ZERO network connections via socket interception."""
    service, vec_index, meta_store = isolated_retrieval_system
    tile, platform = synthetic_tiles[0]

    v = service.embedding_service.embed_image(tile.file_path)
    vec_index.add(tile.tile_id, v)
    meta_store.store_tile(tile, platform=platform)

    # Intercept socket creation
    original_socket = socket.socket
    network_called = False

    def guard_socket(*args, **kwargs):
        nonlocal network_called
        network_called = True
        raise RuntimeError("Prohibited network socket call detected during retrieval!")

    socket.socket = guard_socket
    try:
        service.text_to_image("urban roads", top_k=1)
        service.image_to_image(tile.file_path, top_k=1)
    finally:
        socket.socket = original_socket

    assert not network_called, "Retrieval triggered unauthorized outbound network socket!"


# ==============================================================================
# 17. API Integration
# ==============================================================================
def test_17_api_endpoints_integration(client: TestClient, isolated_retrieval_system, synthetic_tiles):
    """Verifies /api/v1/retrieval/text, /image, /health REST endpoints."""
    service, vec_index, meta_store = isolated_retrieval_system

    for tile, platform in synthetic_tiles:
        v = service.embedding_service.embed_image(tile.file_path)
        vec_index.add(tile.tile_id, v)
        meta_store.store_tile(tile, platform=platform)

    # Inject isolated test service
    set_retrieval_service(service)

    try:
        # 1. Health check
        h_res = client.get("/api/v1/retrieval/health")
        assert h_res.status_code == 200
        h_data = h_res.json()
        assert h_data["index_size"] == 4
        assert h_data["offline_status"] is True

        # 2. Text retrieval
        t_res = client.post(
            "/api/v1/retrieval/text",
            json={
                "query": "agricultural fields",
                "top_k": 2,
                "filters": {"sensor": "Sentinel-2A MSI"},
            },
        )
        assert t_res.status_code == 200
        t_data = t_res.json()
        assert t_data["query_type"] == "text"
        assert len(t_data["results"]) == 2

        # 3. Image retrieval (local file)
        query_tile, _ = synthetic_tiles[0]
        i_res = client.post(
            "/api/v1/retrieval/image",
            json={"file_path": query_tile.file_path, "top_k": 1},
        )
        assert i_res.status_code == 200
        i_data = i_res.json()
        assert i_data["results"][0]["tile_id"] == query_tile.tile_id

        # 4. Prohibited remote URL rejection
        bad_res = client.post(
            "/api/v1/retrieval/image",
            json={"file_path": "https://example.com/satellite.jpg", "top_k": 1},
        )
        assert bad_res.status_code == 400
        assert "Remote URLs are strictly prohibited" in bad_res.json()["detail"]

    finally:
        # Reset global service
        set_retrieval_service(None)


# ==============================================================================
# 18. Empty Index Graceful Handling
# ==============================================================================
def test_18_empty_index_graceful_handling(isolated_retrieval_system):
    """Verifies that querying an empty index returns empty results without error."""
    service, _, _ = isolated_retrieval_system

    resp_text = service.text_to_image("city center", top_k=5)
    assert resp_text.returned_count == 0
    assert resp_text.results == []
    assert resp_text.total_candidates_searched == 0

    h = service.get_health()
    assert h.index_size == 0
