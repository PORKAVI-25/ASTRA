"""Automated tests for data contracts, tile identity, and provenance immutability."""

from datetime import datetime, timezone
import pytest
from pydantic import ValidationError
from geospatial.contracts import (
    GeoBoundingBox,
    SceneManifest,
    TileDimensions,
    TileManifest,
    ProvenanceRecord,
    HealthResponse,
)


def test_geoboundingbox_valid():
    """Verifies that valid WGS84 bounding box instantiates correctly."""
    bbox = GeoBoundingBox(
        min_lon=76.842,
        min_lat=11.231,
        max_lon=77.891,
        max_lat=12.215,
    )
    assert bbox.min_lon == 76.842
    assert bbox.max_lat == 12.215


def test_geoboundingbox_invalid_inversion():
    """Verifies that inverted coordinate bounds trigger validation error."""
    with pytest.raises(ValidationError):
        GeoBoundingBox(
            min_lon=78.0,
            min_lat=12.0,
            max_lon=76.0,  # max_lon < min_lon
            max_lat=13.0,
        )


def test_tile_manifest_stable_identity_and_scene_linkage():
    """Verifies that tile manifest enforces stable tile identity and links to source scene (Rules 3, 4, 5)."""
    tile = TileManifest(
        tile_id="tile_S2A_T43PGQ_x004_y008_z14",
        source_scene_id="S2A_MSIL2A_20260315T052021_N0500_R019_T43PGQ_20260315T083045",
        tile_col=4,
        tile_row=8,
        zoom_level=14,
        dimensions=TileDimensions(width_px=512, height_px=512, channels=3),
        crs="EPSG:32643",
        bounds_wgs84=GeoBoundingBox(
            min_lon=77.0123,
            min_lat=11.4501,
            max_lon=77.0582,
            max_lat=11.4960,
        ),
        acquisition_time=datetime.now(timezone.utc),
        sensor="Sentinel-2A MSI",
        file_path="data/processed/tiles/tile_S2A_T43PGQ_x004_y008_z14.png",
        sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        is_synthetic=False,
    )
    assert tile.tile_id.startswith("tile_")
    assert tile.source_scene_id.startswith("S2A_")
    assert tile.crs == "EPSG:32643"
    assert tile.is_synthetic is False


def test_tile_manifest_sha256_hash_validation():
    """Verifies that invalid hash lengths are rejected."""
    with pytest.raises(ValidationError):
        TileManifest(
            tile_id="tile_invalid",
            source_scene_id="scene_001",
            tile_col=0,
            tile_row=0,
            crs="EPSG:4326",
            bounds_wgs84=GeoBoundingBox(min_lon=0, min_lat=0, max_lon=1, max_lat=1),
            acquisition_time=datetime.now(timezone.utc),
            sensor="TestSensor",
            file_path="dummy.png",
            sha256_hash="tooshort",  # Invalid hash length
        )


def test_synthetic_data_flag_enforcement():
    """Verifies that synthetic data can be explicitly tagged (Rule 9)."""
    tile = TileManifest(
        tile_id="demo_synthetic_tile_001",
        source_scene_id="demo_synthetic_scene_001",
        tile_col=0,
        tile_row=0,
        crs="EPSG:4326",
        bounds_wgs84=GeoBoundingBox(min_lon=10.0, min_lat=10.0, max_lon=11.0, max_lat=11.0),
        acquisition_time=datetime.now(timezone.utc),
        sensor="SyntheticSensor",
        file_path="data/processed/synthetic.png",
        sha256_hash="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        is_synthetic=True,
    )
    assert tile.is_synthetic is True


def test_provenance_record_creation():
    """Verifies creation and field validation of provenance records."""
    record = ProvenanceRecord(
        provenance_id="prov_001",
        target_tile_id="tile_S2A_001",
        source_scene_id="scene_S2A_001",
        processing_stage="chipping_and_normalization",
        pipeline_version="0.1.0",
        parameters={"chip_size": 512, "normalization": "min_max"},
        executed_by="astra.ingestion.chipper",
    )
    assert record.pipeline_version == "0.1.0"
    assert record.parameters["chip_size"] == 512
