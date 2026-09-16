"""ASTRA Temporal Change Detection Test Suite (Phase M4B).

Validates the deterministic offline change detection engine, covering:
1. Identical rasters (zero change)
2. Synthetic single known change region
3. Multiple discrete change regions (CCL)
4. Noise filtering below minimum region area
5. Nodata and NaN/Inf isolation
6. Thresholding methods (fixed, statistical, percentile)
7. Multispectral band averaging and selection
8. Spatial dimension mismatch failure
9. Deterministic repeatability
10. Incompatible ScenePair & negative temporal separation rejection
11. Service persistence, artifact generation, and immutable provenance
12. FastAPI endpoints integration
13. CLI smoke test execution
"""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
import pytest
from PIL import Image
from fastapi.testclient import TestClient

from backend.main import app
from backend.ml.change.types import (
    PairCompatibility,
    PairCompatibilityStatus,
    ScenePair,
    SpatialOverlap,
    TemporalObservation,
)
from backend.ml.change_detection import (
    ASTRAPixelDifferenceDetector,
    ChangeDetectionConfig,
    ChangeDetectionService,
    NormalizationMethod,
    ThresholdMethod,
)
from geospatial.contracts import GeoBoundingBox


@pytest.fixture
def temp_change_dirs(tmp_path: Path):
    """Provides isolated temporary directories for results and provenance."""
    results_dir = tmp_path / "change_results"
    prov_dir = tmp_path / "provenance"
    results_dir.mkdir(parents=True, exist_ok=True)
    prov_dir.mkdir(parents=True, exist_ok=True)
    return results_dir, prov_dir


def create_test_observation(
    obs_id: str,
    timestamp: datetime,
    file_path: str,
    scene_id: str = "scene_test",
    tile_id: str = "tile_test",
) -> TemporalObservation:
    """Helper to construct a valid TemporalObservation."""
    return TemporalObservation(
        observation_id=obs_id,
        scene_id=scene_id,
        tile_id=tile_id,
        acquisition_time=timestamp,
        sensor="Sentinel-2A MSI",
        platform="Sentinel-2",
        crs="EPSG:4326",
        bounds_wgs84=GeoBoundingBox(min_lon=10.0, min_lat=20.0, max_lon=10.1, max_lat=20.1),
        source_hash="a" * 64,
        file_path=file_path,
        is_synthetic=True,
        metadata={"spatial_resolution_m": 10.0},
    )


def test_01_identical_rasters_zero_change():
    """Identical rasters must yield 0 changed pixels, 0 regions, and zero change score."""
    detector = ASTRAPixelDifferenceDetector()
    data = np.full((3, 64, 64), 100.0, dtype=np.float32)

    # 1. Fixed threshold
    config_fixed = ChangeDetectionConfig(
        threshold_method=ThresholdMethod.FIXED,
        fixed_threshold=0.1,
        minimum_region_area=1,
    )
    result_fixed, score_map_fixed, mask_fixed = detector.detect(data, data, config=config_fixed)

    assert result_fixed.metrics.total_pixels == 64 * 64
    assert result_fixed.metrics.valid_pixels == 64 * 64
    assert result_fixed.metrics.changed_pixels == 0
    assert result_fixed.metrics.changed_fraction == 0.0
    assert result_fixed.metrics.number_of_regions == 0
    assert result_fixed.metrics.mean_change_score == 0.0
    assert np.all(score_map_fixed == 0.0)
    assert np.all(mask_fixed == 0)

    # 2. Statistical threshold (must not flag zero-variance zero-change as changed)
    config_stat = ChangeDetectionConfig(
        threshold_method=ThresholdMethod.STATISTICAL,
        threshold_std_multiplier=2.0,
        minimum_region_area=1,
    )
    result_stat, _, mask_stat = detector.detect(data, data, config=config_stat)
    assert result_stat.metrics.changed_pixels == 0
    assert result_stat.metrics.number_of_regions == 0
    assert np.all(mask_stat == 0)

    # 3. Percentile threshold (must not flag zero-variance zero-change as changed)
    config_perc = ChangeDetectionConfig(
        threshold_method=ThresholdMethod.PERCENTILE,
        threshold_percentile=95.0,
        minimum_region_area=1,
    )
    result_perc, _, mask_perc = detector.detect(data, data, config=config_perc)
    assert result_perc.metrics.changed_pixels == 0
    assert result_perc.metrics.number_of_regions == 0
    assert np.all(mask_perc == 0)


def test_02_synthetic_known_change_region():
    """A single known rectangular alteration must be accurately detected and bounded."""
    detector = ASTRAPixelDifferenceDetector()
    earlier = np.zeros((1, 100, 100), dtype=np.float32)
    later = np.zeros((1, 100, 100), dtype=np.float32)

    # Insert a 20x20 patch of changed pixels in center [40:60, 40:60]
    later[0, 40:60, 40:60] = 1.0

    config = ChangeDetectionConfig(
        threshold_method=ThresholdMethod.FIXED,
        fixed_threshold=0.5,
        minimum_region_area=20,
        normalization_method=NormalizationMethod.NONE,
    )

    result, score_map, mask = detector.detect(earlier, later, config=config)

    assert result.metrics.changed_pixels == 400
    assert result.metrics.number_of_regions == 1
    region = result.regions[0]
    assert region.region_id == "reg_0001"
    assert region.pixel_count == 400
    assert region.bbox_px == [40, 40, 59, 59]
    assert region.centroid_px == [49.5, 49.5]
    assert region.mean_change_score == 1.0
    assert region.max_change_score == 1.0
    assert np.sum(mask == 255) == 400


def test_03_multiple_discrete_change_regions():
    """Multiple spatially separated change patches must be extracted as discrete regions."""
    detector = ASTRAPixelDifferenceDetector()
    earlier = np.zeros((1, 100, 100), dtype=np.float32)
    later = np.zeros((1, 100, 100), dtype=np.float32)

    # Region 1: 10x10 = 100 px at [10:20, 10:20]
    later[0, 10:20, 10:20] = 1.0
    # Region 2: 15x15 = 225 px at [60:75, 60:75]
    later[0, 60:75, 60:75] = 1.0

    config = ChangeDetectionConfig(
        threshold_method=ThresholdMethod.FIXED,
        fixed_threshold=0.5,
        minimum_region_area=25,
        connectivity=8,
        normalization_method=NormalizationMethod.NONE,
    )

    result, _, mask = detector.detect(earlier, later, config=config)

    assert result.metrics.number_of_regions == 2
    assert result.metrics.changed_pixels == 325

    # Regions should be ordered descending by area
    assert result.regions[0].pixel_count == 225
    assert result.regions[0].bbox_px == [60, 60, 74, 74]
    assert result.regions[1].pixel_count == 100
    assert result.regions[1].bbox_px == [10, 10, 19, 19]


def test_04_noise_filtering_below_minimum_area():
    """Scattered noise pixels below minimum_region_area must be filtered out."""
    detector = ASTRAPixelDifferenceDetector()
    earlier = np.zeros((1, 50, 50), dtype=np.float32)
    later = np.zeros((1, 50, 50), dtype=np.float32)

    # Scattered small patches (3 px and 5 px)
    later[0, 5:8, 5] = 1.0    # 3 px
    later[0, 20:25, 20] = 1.0  # 5 px

    config = ChangeDetectionConfig(
        threshold_method=ThresholdMethod.FIXED,
        fixed_threshold=0.5,
        minimum_region_area=10,  # larger than both patches
        normalization_method=NormalizationMethod.NONE,
    )

    result, score_map, mask = detector.detect(earlier, later, config=config)

    # Both patches exceed threshold in raw score, but must be suppressed by CCL area filter
    assert result.metrics.number_of_regions == 0
    assert result.metrics.changed_pixels == 0
    assert np.all(mask == 0)


def test_05_nodata_and_invalid_pixel_handling():
    """Nodata values and NaNs must be isolated and excluded from valid calculations."""
    detector = ASTRAPixelDifferenceDetector()
    earlier = np.full((1, 40, 40), 10.0, dtype=np.float32)
    later = np.full((1, 40, 40), 10.0, dtype=np.float32)

    # Set 10x10 corner to NaN in earlier
    earlier[0, :10, :10] = np.nan
    # Set another 10x10 corner to explicit nodata (999.0) in later
    later[0, 30:, 30:] = 999.0

    config = ChangeDetectionConfig(
        threshold_method=ThresholdMethod.FIXED,
        fixed_threshold=0.1,
        nodata_value=999.0,
        normalization_method=NormalizationMethod.NONE,
    )

    result, score_map, mask = detector.detect(earlier, later, config=config)

    assert result.metrics.total_pixels == 1600
    assert result.metrics.invalid_pixels == 200
    assert result.metrics.valid_pixels == 1400
    # In invalid regions, scores and mask must remain strictly 0
    assert np.all(score_map[:10, :10] == 0.0)
    assert np.all(score_map[30:, 30:] == 0.0)
    assert np.all(mask[:10, :10] == 0)
    assert np.all(mask[30:, 30:] == 0)


def test_06_thresholding_methods():
    """Validates statistical, percentile, and fixed threshold calculations."""
    detector = ASTRAPixelDifferenceDetector()
    earlier = np.zeros((1, 100, 100), dtype=np.float32)
    later = np.zeros((1, 100, 100), dtype=np.float32)

    # Background has slight variation: 0.1
    later[0, :, :] = 0.1
    # True change patch: 0.8 on 500 pixels
    later[0, 10:35, 10:30] = 0.8

    # 1. Fixed threshold
    cfg_fixed = ChangeDetectionConfig(
        threshold_method=ThresholdMethod.FIXED,
        fixed_threshold=0.5,
        minimum_region_area=20,
        normalization_method=NormalizationMethod.NONE,
    )
    res_fixed, _, _ = detector.detect(earlier, later, config=cfg_fixed)
    assert res_fixed.metrics.threshold_used == 0.5
    assert res_fixed.metrics.changed_pixels == 500

    # 2. Statistical threshold (mean + 2*std)
    cfg_stat = ChangeDetectionConfig(
        threshold_method=ThresholdMethod.STATISTICAL,
        threshold_std_multiplier=2.0,
        minimum_region_area=20,
        normalization_method=NormalizationMethod.NONE,
    )
    res_stat, _, _ = detector.detect(earlier, later, config=cfg_stat)
    assert res_stat.metrics.threshold_used > 0.1
    assert res_stat.metrics.changed_pixels == 500

    # 3. Percentile threshold (95th percentile)
    cfg_perc = ChangeDetectionConfig(
        threshold_method=ThresholdMethod.PERCENTILE,
        threshold_percentile=96.0,
        minimum_region_area=20,
        normalization_method=NormalizationMethod.NONE,
    )
    res_perc, _, _ = detector.detect(earlier, later, config=cfg_perc)
    assert res_perc.metrics.threshold_used > 0.1


def test_07_multispectral_band_averaging():
    """Multi-band rasters must correctly average differences and support band selection."""
    detector = ASTRAPixelDifferenceDetector()
    earlier = np.zeros((4, 50, 50), dtype=np.float32)
    later = np.zeros((4, 50, 50), dtype=np.float32)

    # Change only in Band 0: magnitude 1.0
    later[0, 10:30, 10:30] = 1.0
    # Other bands remain 0.0

    # Across 4 bands, average difference is 1.0 / 4 = 0.25
    cfg_all = ChangeDetectionConfig(
        threshold_method=ThresholdMethod.FIXED,
        fixed_threshold=0.20,
        minimum_region_area=20,
        normalization_method=NormalizationMethod.NONE,
    )
    res_all, score_all, _ = detector.detect(earlier, later, config=cfg_all)
    assert np.isclose(score_all[15, 15], 0.25, atol=1e-5)
    assert res_all.metrics.changed_pixels == 400

    # If evaluating only Band 0, score should be 1.0
    cfg_b0 = ChangeDetectionConfig(
        bands=[0],
        threshold_method=ThresholdMethod.FIXED,
        fixed_threshold=0.50,
        minimum_region_area=20,
        normalization_method=NormalizationMethod.NONE,
    )
    res_b0, score_b0, _ = detector.detect(earlier, later, config=cfg_b0)
    assert np.isclose(score_b0[15, 15], 1.0, atol=1e-5)
    assert res_b0.metrics.changed_pixels == 400


def test_08_spatial_dimension_mismatch_failure():
    """Rasters with incompatible spatial dimensions must immediately raise ValueError."""
    detector = ASTRAPixelDifferenceDetector()
    earlier = np.zeros((1, 50, 50), dtype=np.float32)
    later = np.zeros((1, 60, 60), dtype=np.float32)

    with pytest.raises(ValueError, match="Spatial dimension mismatch"):
        detector.detect(earlier, later)


def test_09_deterministic_repeatability():
    """Two executions with identical parameters must yield identical results and hashes."""
    detector = ASTRAPixelDifferenceDetector()
    earlier = np.random.RandomState(42).rand(3, 64, 64).astype(np.float32)
    later = np.random.RandomState(42).rand(3, 64, 64).astype(np.float32)
    later[:, 20:35, 20:35] += 0.8

    config = ChangeDetectionConfig(
        threshold_method=ThresholdMethod.STATISTICAL,
        threshold_std_multiplier=2.0,
        minimum_region_area=15,
    )

    res1, score1, mask1 = detector.detect(earlier, later, config=config, pair_id="pair_repeat_test")
    res2, score2, mask2 = detector.detect(earlier, later, config=config, pair_id="pair_repeat_test")

    assert res1.result_id == res2.result_id
    assert res1.metrics.changed_pixels == res2.metrics.changed_pixels
    assert res1.metrics.threshold_used == res2.metrics.threshold_used
    np.testing.assert_array_equal(score1, score2)
    np.testing.assert_array_equal(mask1, mask2)


def test_10_incompatible_scene_pair_rejection(tmp_path: Path, temp_change_dirs):
    """Incompatible ScenePairs or negative temporal separation must be rejected."""
    results_dir, prov_dir = temp_change_dirs
    service = ChangeDetectionService(output_dir=results_dir, provenance_dir=prov_dir)

    t1 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc)

    p1 = tmp_path / "t1.png"
    p2 = tmp_path / "t2.png"
    Image.fromarray(np.zeros((64, 64), dtype=np.uint8)).save(p1)
    Image.fromarray(np.zeros((64, 64), dtype=np.uint8)).save(p2)

    obs1 = create_test_observation("obs_01", t1, str(p1))
    obs2 = create_test_observation("obs_02", t2, str(p2))

    # 1. Incompatible pair
    incompatible_pair = ScenePair(
        pair_id="pair_incompat_01",
        earlier_observation=obs1,
        later_observation=obs2,
        temporal_separation_seconds=31 * 86400.0,
        temporal_separation_days=31.0,
        spatial_overlap=SpatialOverlap(
            intersection_bounds=None,
            earlier_area_deg2=0.01,
            later_area_deg2=0.01,
            is_overlapping=False,
        ),
        compatibility=PairCompatibility(
            is_compatible=False,
            status=PairCompatibilityStatus.INSUFFICIENT_OVERLAP,
            reasons=["Overlap 0.0 below minimum 0.5"],
        ),
    )

    with pytest.raises(ValueError, match="Cannot run change detection on incompatible ScenePair"):
        service.run_detection(pair=incompatible_pair)

    # 2. Inverted chronological order (T2 <= T1)
    with pytest.raises(ValueError, match="Temporal separation must be strictly positive"):
        service.run_detection(earlier_obs=obs2, later_obs=obs1, earlier_input=str(p2), later_input=str(p1))


def test_11_service_artifact_persistence_and_provenance(tmp_path: Path, temp_change_dirs):
    """Service must save score_map.npy, change_mask.png, result.json, and provenance record."""
    results_dir, prov_dir = temp_change_dirs
    service = ChangeDetectionService(output_dir=results_dir, provenance_dir=prov_dir)

    p1 = tmp_path / "t1.png"
    p2 = tmp_path / "t2.png"
    arr1 = np.zeros((80, 80), dtype=np.uint8)
    arr2 = np.zeros((80, 80), dtype=np.uint8)
    arr2[20:45, 20:45] = 255
    Image.fromarray(arr1).save(p1)
    Image.fromarray(arr2).save(p2)

    obs1 = create_test_observation("obs_11a", datetime(2026, 1, 1, tzinfo=timezone.utc), str(p1))
    obs2 = create_test_observation("obs_11b", datetime(2026, 2, 1, tzinfo=timezone.utc), str(p2))

    config = ChangeDetectionConfig(
        threshold_method=ThresholdMethod.FIXED,
        fixed_threshold=0.3,
        minimum_region_area=20,
    )

    result = service.run_detection(
        earlier_input=p1,
        later_input=p2,
        earlier_obs=obs1,
        later_obs=obs2,
        config=config,
    )

    # Verify generated directory and files
    res_dir = results_dir / result.result_id
    assert res_dir.exists()
    assert (res_dir / "score_map.npy").exists()
    assert (res_dir / "change_mask.png").exists()
    assert (res_dir / "result.json").exists()

    # Verify provenance record
    prov_file = prov_dir / f"{result.provenance_id}.json"
    assert prov_file.exists()
    prov_data = json.loads(prov_file.read_text(encoding="utf-8"))
    assert prov_data["provenance_id"] == result.provenance_id
    assert prov_data["processing_stage"] == "temporal_change_detection"
    assert prov_data["executed_by"] == "astra.ml.change_detection"

    # Verify retrieval methods
    retrieved = service.get_result(result.result_id)
    assert retrieved is not None
    assert retrieved.result_id == result.result_id
    assert retrieved.metrics.changed_pixels == result.metrics.changed_pixels

    mask_path = service.get_mask_path(result.result_id)
    assert mask_path is not None and mask_path.exists()

    score_arr = service.get_score_map(result.result_id)
    assert score_arr is not None
    assert score_arr.shape == (80, 80)


def test_12_api_endpoints_integration(tmp_path: Path, temp_change_dirs):
    """FastAPI change detection endpoints must run correctly and return typed responses."""
    from backend.api.v1.endpoints.change_detection import (
        get_change_detection_service,
        set_change_detection_service,
    )

    results_dir, prov_dir = temp_change_dirs
    service = ChangeDetectionService(output_dir=results_dir, provenance_dir=prov_dir)
    set_change_detection_service(service)

    client = TestClient(app)

    # 1. Health check
    res_health = client.get("/api/v1/change-detection/health")
    assert res_health.status_code == 200
    data_health = res_health.json()
    assert data_health["status"] == "healthy"
    assert data_health["algorithm_id"] == "pixel_difference"

    # Create dummy images
    p1 = tmp_path / "api_t1.png"
    p2 = tmp_path / "api_t2.png"
    arr1 = np.zeros((64, 64), dtype=np.uint8)
    arr2 = np.zeros((64, 64), dtype=np.uint8)
    arr2[10:30, 10:30] = 255
    Image.fromarray(arr1).save(p1)
    Image.fromarray(arr2).save(p2)

    # 2. Run change detection via POST
    payload = {
        "earlier_path": str(p1),
        "later_path": str(p2),
        "config": {
            "threshold_method": "fixed",
            "fixed_threshold": 0.2,
            "minimum_region_area": 10,
        },
    }
    res_run = client.post("/api/v1/change-detection/run", json=payload)
    assert res_run.status_code == 200
    data_run = res_run.json()
    assert "result_id" in data_run
    assert data_run["metrics"]["changed_pixels"] == 400
    assert len(data_run["regions"]) == 1

    result_id = data_run["result_id"]

    # 3. Retrieve result via GET /{id}
    res_get = client.get(f"/api/v1/change-detection/{result_id}")
    assert res_get.status_code == 200
    assert res_get.json()["result_id"] == result_id

    # 4. Stream mask image via GET /{id}/mask
    res_mask = client.get(f"/api/v1/change-detection/{result_id}/mask")
    assert res_mask.status_code == 200
    assert res_mask.headers["content-type"] == "image/png"
    assert len(res_mask.content) > 0

    # 5. Prohibited remote URL rejection
    res_remote = client.post(
        "/api/v1/change-detection/run",
        json={"earlier_path": "https://remote.example/t1.tif", "later_path": str(p2)},
    )
    assert res_remote.status_code == 400
    assert "strictly forbidden" in res_remote.json()["detail"]

    # Reset service override
    set_change_detection_service(None)


def test_13_cli_smoke_test(tmp_path: Path):
    """CLI run_change_detection.py script must execute cleanly and generate output."""
    p1 = tmp_path / "cli_t1.png"
    p2 = tmp_path / "cli_t2.png"
    arr1 = np.zeros((64, 64), dtype=np.uint8)
    arr2 = np.zeros((64, 64), dtype=np.uint8)
    arr2[15:35, 15:35] = 255
    Image.fromarray(arr1).save(p1)
    Image.fromarray(arr2).save(p2)

    cli_out_dir = tmp_path / "cli_results"

    cmd = [
        sys.executable,
        "scripts/run_change_detection.py",
        "--earlier", str(p1),
        "--later", str(p2),
        "--threshold-method", "fixed",
        "--fixed-threshold", "0.2",
        "--min-region-area", "15",
        "--output-dir", str(cli_out_dir),
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert "ASTRA Temporal Change Detection Engine" in proc.stdout
    assert "Quantitative Change Summary:" in proc.stdout
    assert "Top Detected Change Regions:" in proc.stdout

    # Run again with --json
    cmd_json = cmd + ["--json"]
    proc_json = subprocess.run(cmd_json, capture_output=True, text=True, check=True)
    json_result = json.loads(proc_json.stdout)
    assert "result_id" in json_result
    assert json_result["metrics"]["changed_pixels"] == 400
