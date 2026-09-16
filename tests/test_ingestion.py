"""Automated comprehensive test suite for Phase 1 Ingestion Vertical Slice."""

from pathlib import Path
import pytest
from starlette.testclient import TestClient
from backend.ingestion.service import IngestionService
from backend.ingestion.validator import validate_raster
from backend.ingestion.extractor import extract_scene_metadata
from backend.ingestion.tiler import generate_tiles_for_scene
from backend.provenance.service import ProvenanceService
from tests.create_test_raster import create_synthetic_geotiff, create_synthetic_cog


@pytest.fixture(scope="module")
def test_data_dir(tmp_path_factory) -> Path:
    """Fixture providing temporary test directory with synthetic rasters."""
    temp_dir = tmp_path_factory.mktemp("astra_ingestion_test")
    return temp_dir


@pytest.fixture(scope="module")
def sample_geotiff(test_data_dir: Path) -> Path:
    """Generates synthetic UTM GeoTIFF."""
    return create_synthetic_geotiff(test_data_dir / "synthetic_test_utm.tif", width=1024, height=1024)


@pytest.fixture(scope="module")
def sample_cog(test_data_dir: Path) -> Path:
    """Generates synthetic COG raster."""
    return create_synthetic_cog(test_data_dir / "synthetic_test_cog.tif", width=512, height=512)


@pytest.fixture
def isolated_service(test_data_dir: Path) -> IngestionService:
    """Provides an IngestionService isolated to a temporary directory."""
    manifest_dir = test_data_dir / "manifests"
    return IngestionService(manifests_dir=manifest_dir)


def test_01_valid_geotiff_validation(sample_geotiff: Path):
    """Verifies that a valid GeoTIFF is successfully recognized by validator."""
    res = validate_raster(sample_geotiff)
    assert res.is_valid is True
    assert res.driver == "GTiff"
    assert res.format_name == "Standard GeoTIFF"
    assert res.error_message is None


def test_02_cog_recognition(sample_cog: Path):
    """Verifies that a Cloud Optimized GeoTIFF (COG) is recognized with is_cog=True."""
    res = validate_raster(sample_cog)
    assert res.is_valid is True
    assert res.driver == "GTiff"
    assert res.is_cog is True
    assert res.format_name == "Cloud Optimized GeoTIFF (COG)"


def test_03_invalid_file_handling(test_data_dir: Path):
    """Verifies that non-existent, empty, and non-geospatial files are safely handled without crash."""
    # 1. Non-existent file
    res_missing = validate_raster(test_data_dir / "non_existent.tif")
    assert res_missing.is_valid is False
    assert "File not found" in res_missing.error_message

    # 2. Corrupt / non-geospatial text file
    dummy_file = test_data_dir / "corrupted.tif"
    dummy_file.write_text("NOT A GEOSPATIAL RASTER")
    res_corrupt = validate_raster(dummy_file)
    assert res_corrupt.is_valid is False
    assert "Corrupt or invalid geospatial raster" in res_corrupt.error_message


def test_04_crs_and_bounds_preservation(sample_geotiff: Path):
    """Verifies that CRS and geographic bounding boxes are correctly preserved (Rule 5)."""
    meta = extract_scene_metadata(sample_geotiff, is_cog=False)
    assert "32643" in meta.crs or "EPSG:32643" in meta.crs
    assert meta.bounds_wgs84.min_lon < meta.bounds_wgs84.max_lon
    assert meta.bounds_wgs84.min_lat < meta.bounds_wgs84.max_lat
    # Check geographic range for UTM zone 43N
    assert 70.0 <= meta.bounds_wgs84.min_lon <= 80.0
    assert 10.0 <= meta.bounds_wgs84.min_lat <= 20.0


def test_05_metadata_extraction_integrity(sample_geotiff: Path):
    """Verifies metadata fields: bands, acquisition time, sensor, synthetic flag."""
    meta = extract_scene_metadata(sample_geotiff, is_cog=False)
    assert meta.sensor == "Sentinel-2A MSI"
    assert meta.platform == "Sentinel-2"
    assert meta.acquisition_time is not None
    assert meta.acquisition_time.year == 2026
    assert meta.acquisition_time.month == 3
    assert len(meta.bands) == 3
    assert meta.is_synthetic is True


def test_06_deterministic_tiling_and_stable_ids(sample_geotiff: Path, test_data_dir: Path):
    """Verifies that windowed tiling produces deterministic tile IDs and links to scene (Rules 3 & 4)."""
    meta = extract_scene_metadata(sample_geotiff, is_cog=False)
    tiles_1 = generate_tiles_for_scene(meta, tile_size=512, output_dir=test_data_dir / "tiles1")
    tiles_2 = generate_tiles_for_scene(meta, tile_size=512, output_dir=test_data_dir / "tiles2")

    assert len(tiles_1) == 4  # 1024x1024 tiled into 512x512 produces 4 tiles
    assert len(tiles_2) == 4

    for t1, t2 in zip(tiles_1, tiles_2):
        # Strict deterministic identity
        assert t1.tile_id == t2.tile_id
        assert t1.sha256_hash == t2.sha256_hash
        # Strict parent scene linkage
        assert t1.source_scene_id == meta.scene_id
        assert t2.source_scene_id == meta.scene_id
        # Georeferencing
        assert t1.crs == meta.crs
        assert t1.bounds_wgs84.min_lon < t1.bounds_wgs84.max_lon
        assert t1.is_synthetic is True


def test_07_full_ingestion_slice_and_provenance(isolated_service: IngestionService, sample_geotiff: Path):
    """Verifies complete ingestion pipeline execution and provenance recording."""
    resp = isolated_service.ingest_raster(str(sample_geotiff), tile_size=512)
    assert resp.status == "ingested"
    assert resp.tile_count == 4
    assert resp.scene is not None
    assert resp.provenance_id is not None

    # Check that scene manifest is saved
    saved_scene = isolated_service.get_scene(resp.scene.scene_id)
    assert saved_scene is not None
    assert saved_scene.scene_id == resp.scene.scene_id
    assert saved_scene.tile_count == 4

    # Check tile manifests
    saved_tiles = isolated_service.get_scene_tiles(resp.scene.scene_id)
    assert len(saved_tiles) == 4
    for t in saved_tiles:
        assert t.source_scene_id == resp.scene.scene_id


def test_08_duplicate_ingestion_detection(isolated_service: IngestionService, sample_geotiff: Path):
    """Verifies duplicate ingestion returns already_ingested and skips re-computation (Incremental Ingestion)."""
    # Second submission of same raster
    resp_dup = isolated_service.ingest_raster(str(sample_geotiff), tile_size=512)
    assert resp_dup.status == "already_ingested"
    assert resp_dup.tile_count == 4
    assert "already been ingested" in resp_dup.message


def test_09_incremental_ingestion_isolation(isolated_service: IngestionService, sample_geotiff: Path, sample_cog: Path):
    """Verifies ingesting a second distinct raster processes incrementally without affecting the first."""
    resp_cog = isolated_service.ingest_raster(str(sample_cog), tile_size=512)
    assert resp_cog.status == "ingested"
    assert resp_cog.tile_count == 1  # 512x512 with 512 tile_size is 1 tile
    assert resp_cog.scene.is_cog is True

    # Check catalog listing
    scenes = isolated_service.list_scenes()
    scene_ids = [s.scene_id for s in scenes]
    assert len(scenes) == 2
    assert resp_cog.scene.scene_id in scene_ids


def test_10_api_endpoints_integration(client: TestClient, sample_geotiff: Path):
    """Verifies REST API endpoints: POST /api/v1/ingestion, GET /api/v1/scenes, GET /api/v1/scenes/{id}/tiles."""
    # 1. Ingest via API
    post_res = client.post(
        "/api/v1/ingestion",
        json={"file_path": str(sample_geotiff), "tile_size": 512, "force_reprocess": True},
    )
    assert post_res.status_code == 201
    data = post_res.json()
    assert data["status"] == "ingested"
    scene_id = data["scene"]["scene_id"]
    assert data["tile_count"] == 4

    # 2. Get scene manifest
    scene_res = client.get(f"/api/v1/ingestion/{scene_id}")
    assert scene_res.status_code == 200
    scene_data = scene_res.json()
    assert scene_data["scene_id"] == scene_id

    # 3. List scenes
    list_res = client.get("/api/v1/scenes")
    assert list_res.status_code == 200
    scenes_list = list_res.json()
    assert any(s["scene_id"] == scene_id for s in scenes_list)

    # 4. List scene tiles
    tiles_res = client.get(f"/api/v1/scenes/{scene_id}/tiles")
    assert tiles_res.status_code == 200
    tiles_list = tiles_res.json()
    assert len(tiles_list) == 4
    for tile in tiles_list:
        assert tile["source_scene_id"] == scene_id


def test_11_api_invalid_file_rejection(client: TestClient, test_data_dir: Path):
    """Verifies that API returns HTTP 400 Bad Request when attempting to ingest an invalid file."""
    bad_file = test_data_dir / "invalid.tif"
    bad_file.write_text("corrupted content")

    res = client.post(
        "/api/v1/ingestion",
        json={"file_path": str(bad_file)},
    )
    assert res.status_code == 400
    assert "Validation failed" in res.json()["detail"]
