"""ASTRA Change Evidence Extraction Test Suite (Phase M4C-A).

Validates the deterministic, explainable feature/evidence extraction layer:
Fixture A: Rectangular changed region (area, dimensions, aspect ratio, compactness, rectangularity)
Fixture B: Elongated changed region (linearity proxy, principal axis ratio, orientation)
Fixture C: Multiple discrete regions (per-region evidence, deterministic ordering)
Fixture D: RGB imagery (generic per-band stats, physical indices marked unavailable)
Fixture E: Multispectral with explicit metadata (per-band deltas, NDVI/NDWI calculated)
Fixture F: Multispectral WITHOUT wavelength metadata (physical indices unavailable)
Fixture G: Temporal progression evidence (exact UTC timestamps, seconds/days/hours)
Fixture H: Invalid/nodata handling (exclusion from regional means, unavailable flags)
Fixture I: Deterministic repeat execution (equivalent evidence, hashes, and feature IDs)
Fixture J: Service persistence, artifact generation, and immutable provenance
Fixture K: API endpoints integration
Fixture L: CLI smoke test execution
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
from backend.ml.change_classification import (
    ChangeClassificationEvidenceService,
    ChangeEvidenceExtractor,
    EvidenceConfig,
)
from backend.ml.change_detection import (
    ChangeDetectionConfig,
    ChangeDetectionResult,
    ChangeMetrics,
    ChangeRegion,
)
from geospatial.contracts import GeoBoundingBox


@pytest.fixture
def temp_classification_dirs(tmp_path: Path):
    """Provides isolated temporary directories for classification evidence and provenance."""
    evidence_dir = tmp_path / "change_classification"
    prov_dir = tmp_path / "provenance"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    prov_dir.mkdir(parents=True, exist_ok=True)
    return evidence_dir, prov_dir


def create_mock_scene_pair(
    pair_id: str = "pair_test_001",
    t1: Optional[datetime] = None,
    t2: Optional[datetime] = None,
    band_mapping: Optional[dict] = None,
) -> ScenePair:
    """Constructs a valid M4A ScenePair for evidence extraction tests."""
    time1 = t1 or datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    time2 = t2 or datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc)
    meta1 = {"band_mapping": band_mapping} if band_mapping else {}

    obs1 = TemporalObservation(
        observation_id=f"{pair_id}_obs1",
        scene_id=f"{pair_id}_scene1",
        acquisition_time=time1,
        sensor="Sentinel-2A MSI",
        platform="Sentinel-2",
        crs="EPSG:4326",
        bounds_wgs84=GeoBoundingBox(min_lon=10.0, min_lat=20.0, max_lon=10.1, max_lat=20.1),
        source_hash="1" * 64,
        is_synthetic=True,
        metadata=meta1,
    )
    obs2 = TemporalObservation(
        observation_id=f"{pair_id}_obs2",
        scene_id=f"{pair_id}_scene2",
        acquisition_time=time2,
        sensor="Sentinel-2A MSI",
        platform="Sentinel-2",
        crs="EPSG:4326",
        bounds_wgs84=GeoBoundingBox(min_lon=10.0, min_lat=20.0, max_lon=10.1, max_lat=20.1),
        source_hash="2" * 64,
        is_synthetic=True,
    )

    delta_sec = (time2 - time1).total_seconds()
    return ScenePair(
        pair_id=pair_id,
        earlier_observation=obs1,
        later_observation=obs2,
        temporal_separation_seconds=delta_sec,
        temporal_separation_days=delta_sec / 86400.0,
        spatial_overlap=SpatialOverlap(
            intersection_bounds=None,
            earlier_area_deg2=0.01,
            later_area_deg2=0.01,
            is_overlapping=True,
        ),
        compatibility=PairCompatibility(
            is_compatible=True,
            status=PairCompatibilityStatus.COMPATIBLE,
        ),
    )


def create_mock_change_result(
    result_id: str,
    regions: List[ChangeRegion],
    h: int = 100,
    w: int = 100,
) -> ChangeDetectionResult:
    """Constructs a valid M4B ChangeDetectionResult."""
    total_changed = sum(r.pixel_count for r in regions)
    return ChangeDetectionResult(
        result_id=result_id,
        scene_pair_id="pair_test_001",
        algorithm_id="pixel_difference",
        algorithm_version="1.0.0",
        config=ChangeDetectionConfig(),
        metrics=ChangeMetrics(
            total_pixels=h * w,
            valid_pixels=h * w,
            invalid_pixels=0,
            changed_pixels=total_changed,
            changed_fraction=float(total_changed / (h * w)),
            number_of_regions=len(regions),
            changed_area_px=total_changed,
            threshold_used=0.2,
            threshold_method="statistical",
        ),
        regions=regions,
        provenance_id=f"prov_chg_{result_id}",
    )


# --- FIXTURE A: Rectangular Changed Region ---
def test_fixture_a_rectangular_changed_region():
    """A known rectangular change (20x40 = 800px) must yield exact area, dimensions, rectangularity=1.0."""
    extractor = ChangeEvidenceExtractor()
    pair = create_mock_scene_pair()

    # Region: [20:40, 10:50] -> height=20, width=40, area=800
    reg = ChangeRegion(
        region_id="reg_0001",
        pixel_count=800,
        area_px=800,
        bbox_px=[20, 10, 39, 49],
        centroid_px=[29.5, 29.5],
        mean_change_score=0.8,
        max_change_score=0.9,
    )
    change_res = create_mock_change_result("res_01", [reg], 100, 100)

    # Change mask
    mask = np.zeros((100, 100), dtype=np.uint8)
    mask[20:40, 10:50] = 255

    evidence = extractor.extract(
        scene_pair=pair,
        change_result=change_res,
        change_mask=mask,
    )

    assert len(evidence.regions) == 1
    sp = evidence.regions[0].spatial

    assert sp.area_px == 800
    assert sp.width_px == 40
    assert sp.height_px == 20
    assert np.isclose(sp.aspect_ratio, 2.0, atol=1e-3)
    assert np.isclose(sp.rectangularity, 1.0, atol=1e-3)
    assert sp.perimeter_px == (20 * 2 + 40 * 2 - 4)  # Outer boundary perimeter
    assert 0.0 < sp.compactness < 1.0

    # Scope verification: Confirm M4C-A produces no classification labels or confidences
    assert not hasattr(evidence, "classification")
    assert not hasattr(evidence.regions[0], "classification")
    dump_str = str(evidence.model_dump())
    assert "construction" not in dump_str
    assert "clearance" not in dump_str
    assert "road_development" not in dump_str
    assert "water_extent_change" not in dump_str


# --- FIXTURE B: Elongated Changed Region ---
def test_fixture_b_elongated_changed_region():
    """An elongated narrow change strip (5x80) must exhibit high linearity and elongation."""
    extractor = ChangeEvidenceExtractor()
    pair = create_mock_scene_pair()

    # Region: [10:15, 10:90] -> height=5, width=80, area=400
    reg = ChangeRegion(
        region_id="reg_0001",
        pixel_count=400,
        area_px=400,
        bbox_px=[10, 10, 14, 89],
        centroid_px=[12.0, 49.5],
        mean_change_score=0.75,
        max_change_score=0.95,
    )
    change_res = create_mock_change_result("res_02", [reg], 100, 100)

    mask = np.zeros((100, 100), dtype=np.uint8)
    mask[10:15, 10:90] = 255

    evidence = extractor.extract(
        scene_pair=pair,
        change_result=change_res,
        change_mask=mask,
    )

    sp = evidence.regions[0].spatial
    assert sp.aspect_ratio >= 15.0  # 80 / 5 = 16.0
    assert sp.linearity_score > 0.85  # Strong principal elongation
    assert sp.axis_ratio > 10.0
    # Horizontal strip must have orientation close to 0.0 degrees (East-West)
    assert np.isclose(sp.orientation_degrees, 0.0, atol=1.0)

    # Also test vertical strip to verify row/column axis consistency
    reg_v = ChangeRegion(
        region_id="reg_vert",
        pixel_count=400,
        area_px=400,
        bbox_px=[10, 10, 89, 14],
        centroid_px=[49.5, 12.0],
        mean_change_score=0.75,
        max_change_score=0.95,
    )
    change_res_v = create_mock_change_result("res_02_v", [reg_v], 100, 100)
    mask_v = np.zeros((100, 100), dtype=np.uint8)
    mask_v[10:90, 10:15] = 255
    evi_v = extractor.extract(scene_pair=pair, change_result=change_res_v, change_mask=mask_v)
    sp_v = evi_v.regions[0].spatial
    assert sp_v.linearity_score > 0.85
    # Vertical strip must have orientation close to 90.0 degrees (North-South)
    assert np.isclose(abs(sp_v.orientation_degrees), 90.0, atol=1.0)


# --- FIXTURE C: Multiple Discrete Regions ---
def test_fixture_c_multiple_regions():
    """Multiple regions must maintain independent feature extraction and deterministic ordering."""
    extractor = ChangeEvidenceExtractor()
    pair = create_mock_scene_pair()

    reg1 = ChangeRegion(
        region_id="reg_0001",
        pixel_count=300,
        area_px=300,
        bbox_px=[10, 10, 24, 29],
        centroid_px=[17.0, 19.5],
        mean_change_score=0.8,
        max_change_score=0.9,
    )
    reg2 = ChangeRegion(
        region_id="reg_0002",
        pixel_count=100,
        area_px=100,
        bbox_px=[60, 60, 69, 69],
        centroid_px=[64.5, 64.5],
        mean_change_score=0.6,
        max_change_score=0.7,
    )
    change_res = create_mock_change_result("res_03", [reg1, reg2], 100, 100)

    mask = np.zeros((100, 100), dtype=np.uint8)
    mask[10:25, 10:30] = 255
    mask[60:70, 60:70] = 255

    evidence = extractor.extract(
        scene_pair=pair,
        change_result=change_res,
        change_mask=mask,
    )

    assert len(evidence.regions) == 2
    assert evidence.regions[0].region_id == "reg_0001"
    assert evidence.regions[1].region_id == "reg_0002"
    assert evidence.regions[0].spatial.area_px == 300
    assert evidence.regions[1].spatial.area_px == 100


# --- FIXTURE D: RGB Imagery Without Physical Wavelengths ---
def test_fixture_d_rgb_imagery_no_physical_wavelengths():
    """RGB imagery must yield per-band statistics, but mark physical indices as unavailable."""
    extractor = ChangeEvidenceExtractor()
    pair = create_mock_scene_pair()

    reg = ChangeRegion(
        region_id="reg_0001",
        pixel_count=100,
        area_px=100,
        bbox_px=[10, 10, 19, 19],
        centroid_px=[14.5, 14.5],
        mean_change_score=0.5,
        max_change_score=0.7,
    )
    change_res = create_mock_change_result("res_04", [reg], 50, 50)

    # 3-band RGB imagery
    img_t1 = np.full((3, 50, 50), 50.0, dtype=np.float32)
    img_t2 = np.full((3, 50, 50), 50.0, dtype=np.float32)
    # Brightness increase in region
    img_t2[:, 10:20, 10:20] = 120.0

    mask = np.zeros((50, 50), dtype=np.uint8)
    mask[10:20, 10:20] = 255

    evidence = extractor.extract(
        scene_pair=pair,
        change_result=change_res,
        earlier_image=img_t1,
        later_image=img_t2,
        change_mask=mask,
    )

    spec = evidence.regions[0].spectral
    assert spec.available is True
    assert len(spec.earlier_mean_per_band) == 3
    # delta should be 120 - 50 = 70.0
    for b in spec.delta_per_band.values():
        assert np.isclose(b, 70.0, atol=1e-2)

    # Strict physical index policy: NDVI and NDWI must be marked unavailable
    assert spec.has_wavelength_metadata is False
    assert spec.ndvi_mean is None
    assert spec.ndwi_mean is None
    assert evidence.regions[0].features["ndvi_mean"].available is False
    assert "NIR and Red" in evidence.regions[0].features["ndvi_mean"].unavailability_reason


# --- FIXTURE E: Multispectral with Explicit Metadata ---
def test_fixture_e_multispectral_with_explicit_metadata():
    """4-band raster with explicit band mapping must correctly compute physical NDVI and NDWI."""
    extractor = ChangeEvidenceExtractor()
    # Explicit band mapping: Blue=0, Green=1, Red=2, NIR=3
    mapping = {"blue": 0, "green": 1, "red": 2, "nir": 3}
    pair = create_mock_scene_pair(band_mapping=mapping)

    reg = ChangeRegion(
        region_id="reg_0001",
        pixel_count=100,
        area_px=100,
        bbox_px=[10, 10, 19, 19],
        centroid_px=[14.5, 14.5],
        mean_change_score=0.6,
        max_change_score=0.8,
    )
    change_res = create_mock_change_result("res_05", [reg], 50, 50)

    # Earlier: high vegetation (NIR=200, Red=40) -> NDVI = (200-40)/(240) = 0.667
    img_t1 = np.zeros((4, 50, 50), dtype=np.float32)
    img_t1[2, :, :] = 40.0   # Red
    img_t1[3, :, :] = 200.0  # NIR

    # Later: cleared/bare ground (NIR=80, Red=100) -> NDVI = (80-100)/(180) = -0.111
    img_t2 = np.zeros((4, 50, 50), dtype=np.float32)
    img_t2[2, :, :] = 100.0  # Red
    img_t2[3, :, :] = 80.0   # NIR

    mask = np.zeros((50, 50), dtype=np.uint8)
    mask[10:20, 10:20] = 255

    config = EvidenceConfig(band_mapping=mapping)
    evidence = extractor.extract(
        scene_pair=pair,
        change_result=change_res,
        earlier_image=img_t1,
        later_image=img_t2,
        change_mask=mask,
        config=config,
    )

    spec = evidence.regions[0].spectral
    assert spec.has_wavelength_metadata is True
    assert spec.ndvi_mean is not None
    assert spec.ndvi_mean.available is True
    assert np.isclose(spec.ndvi_mean.value, -0.111, atol=1e-2)
    assert spec.vegetation_proxy_delta is not None
    assert spec.vegetation_proxy_delta.value < 0  # Vegetation loss delta


# --- FIXTURE F: Multispectral WITHOUT Wavelength Metadata ---
def test_fixture_f_multispectral_without_wavelength_metadata():
    """8-band raster without band mapping must mark NDVI as unavailable with explicit reason."""
    extractor = ChangeEvidenceExtractor()
    pair = create_mock_scene_pair(band_mapping=None)

    reg = ChangeRegion(
        region_id="reg_0001",
        pixel_count=100,
        area_px=100,
        bbox_px=[10, 10, 19, 19],
        centroid_px=[14.5, 14.5],
        mean_change_score=0.4,
        max_change_score=0.5,
    )
    change_res = create_mock_change_result("res_06", [reg], 50, 50)

    img_t1 = np.ones((8, 50, 50), dtype=np.float32) * 50
    img_t2 = np.ones((8, 50, 50), dtype=np.float32) * 80

    mask = np.zeros((50, 50), dtype=np.uint8)
    mask[10:20, 10:20] = 255

    evidence = extractor.extract(
        scene_pair=pair,
        change_result=change_res,
        earlier_image=img_t1,
        later_image=img_t2,
        change_mask=mask,
    )

    spec = evidence.regions[0].spectral
    assert len(spec.delta_per_band) == 8
    assert spec.ndvi_mean is None
    assert evidence.regions[0].features["ndvi_mean"].available is False
    assert "not explicitly identified" in evidence.regions[0].features["ndvi_mean"].unavailability_reason


# --- FIXTURE G: Temporal Progression Evidence ---
def test_fixture_g_temporal_progression_evidence():
    """Verifies exact UTC timestamps and temporal separation in seconds, days, and hours."""
    extractor = ChangeEvidenceExtractor()
    t1 = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 11, 12, 0, tzinfo=timezone.utc)  # 10.5 days = 252 hours
    pair = create_mock_scene_pair(t1=t1, t2=t2)

    reg = ChangeRegion(
        region_id="reg_0001",
        pixel_count=50,
        area_px=50,
        bbox_px=[5, 5, 9, 14],
        centroid_px=[7.0, 9.5],
        mean_change_score=0.5,
        max_change_score=0.6,
    )
    change_res = create_mock_change_result("res_07", [reg], 30, 30)

    evidence = extractor.extract(scene_pair=pair, change_result=change_res)

    temp = evidence.temporal
    assert temp.earlier_acquisition_time == t1
    assert temp.later_acquisition_time == t2
    assert temp.temporal_separation_seconds == 10.5 * 86400.0
    assert np.isclose(temp.temporal_separation_days, 10.5, atol=1e-4)
    assert np.isclose(temp.temporal_separation_hours, 252.0, atol=1e-2)


# --- FIXTURE H: Invalid / Nodata Region Handling ---
def test_fixture_h_invalid_nodata_handling():
    """NaNs or infs in regional pixels must be safely isolated without raising errors."""
    extractor = ChangeEvidenceExtractor()
    pair = create_mock_scene_pair()

    reg = ChangeRegion(
        region_id="reg_0001",
        pixel_count=100,
        area_px=100,
        bbox_px=[10, 10, 19, 19],
        centroid_px=[14.5, 14.5],
        mean_change_score=0.5,
        max_change_score=0.6,
    )
    change_res = create_mock_change_result("res_08", [reg], 50, 50)

    # 100% NaN imagery
    img_nan = np.full((3, 50, 50), np.nan, dtype=np.float32)
    mask = np.zeros((50, 50), dtype=np.uint8)
    mask[10:20, 10:20] = 255

    evidence = extractor.extract(
        scene_pair=pair,
        change_result=change_res,
        earlier_image=img_nan,
        later_image=img_nan,
        change_mask=mask,
    )

    spec = evidence.regions[0].spectral
    assert spec.available is False
    assert "NaN, Inf, or nodata" in spec.unavailability_reason or "NaN or Inf" in spec.unavailability_reason

    # Partial NaN imagery: 50 pixels valid (100.0 earlier, 150.0 later), 50 pixels NaN
    img_part_e = np.full((3, 50, 50), 100.0, dtype=np.float32)
    img_part_l = np.full((3, 50, 50), 150.0, dtype=np.float32)
    img_part_e[:, 10:15, 10:20] = np.nan  # Top half of region is NaN

    evi_part = extractor.extract(
        scene_pair=pair,
        change_result=change_res,
        earlier_image=img_part_e,
        later_image=img_part_l,
        change_mask=mask,
    )
    spec_part = evi_part.regions[0].spectral
    assert spec_part.available is True
    # Mean of valid pixels must be exactly 100 earlier and 150 later
    for b_name in spec_part.earlier_mean_per_band.values():
        assert np.isclose(b_name, 100.0)
    for b_name in spec_part.later_mean_per_band.values():
        assert np.isclose(b_name, 150.0)
    for b_name in spec_part.delta_per_band.values():
        assert np.isclose(b_name, 50.0)


# --- FIXTURE I: Deterministic Repeat Execution ---
def test_fixture_i_deterministic_repeat_execution():
    """Repeated extraction on identical inputs must produce bit-for-bit identical outputs and IDs."""
    extractor = ChangeEvidenceExtractor()
    pair = create_mock_scene_pair()

    reg = ChangeRegion(
        region_id="reg_0001",
        pixel_count=120,
        area_px=120,
        bbox_px=[10, 10, 19, 21],
        centroid_px=[14.5, 15.5],
        mean_change_score=0.65,
        max_change_score=0.85,
    )
    change_res = create_mock_change_result("res_09", [reg], 50, 50)
    mask = np.zeros((50, 50), dtype=np.uint8)
    mask[10:20, 10:22] = 255

    evi1 = extractor.extract(scene_pair=pair, change_result=change_res, change_mask=mask)
    evi2 = extractor.extract(scene_pair=pair, change_result=change_res, change_mask=mask)

    assert evi1.evidence_id == evi2.evidence_id
    assert evi1.provenance_id == evi2.provenance_id
    assert evi1.regions[0].spatial.area_px == evi2.regions[0].spatial.area_px
    assert evi1.regions[0].spatial.linearity_score == evi2.regions[0].spatial.linearity_score


# --- FIXTURE J: Service Persistence & Lineage Provenance ---
def test_fixture_j_service_persistence_and_provenance(temp_classification_dirs):
    """Service must persist evidence.json and record prov_evi_*.json matching ASTRA-DC-v0.1."""
    evidence_dir, prov_dir = temp_classification_dirs
    service = ChangeClassificationEvidenceService(output_dir=evidence_dir, provenance_dir=prov_dir)
    pair = create_mock_scene_pair()

    reg = ChangeRegion(
        region_id="reg_0001",
        pixel_count=100,
        area_px=100,
        bbox_px=[10, 10, 19, 19],
        centroid_px=[14.5, 14.5],
        mean_change_score=0.7,
        max_change_score=0.9,
    )
    change_res = create_mock_change_result("res_10", [reg], 50, 50)
    mask = np.zeros((50, 50), dtype=np.uint8)
    mask[10:20, 10:20] = 255

    evidence = service.extract_evidence(
        scene_pair=pair,
        change_result=change_res,
        change_mask=mask,
    )

    # Check persisted files
    target_file = evidence_dir / evidence.evidence_id / "evidence.json"
    assert target_file.exists()
    data = json.loads(target_file.read_text(encoding="utf-8"))
    assert data["evidence_id"] == evidence.evidence_id
    assert len(data["regions"]) == 1

    # Check provenance record
    prov_file = prov_dir / f"{evidence.provenance_id}.json"
    assert prov_file.exists()
    prov_data = json.loads(prov_file.read_text(encoding="utf-8"))
    assert prov_data["provenance_id"] == evidence.provenance_id
    assert prov_data["processing_stage"] == "change_evidence_extraction"
    assert prov_data["executed_by"] == "astra.ml.change_classification"

    # Check lookup helper
    retrieved = service.get_evidence(evidence.evidence_id)
    assert retrieved is not None
    assert retrieved.evidence_id == evidence.evidence_id


# --- FIXTURE K: API Endpoints Integration ---
def test_fixture_k_api_endpoints_integration(temp_classification_dirs):
    """FastAPI endpoints for change evidence extraction must return typed responses."""
    from backend.api.v1.endpoints.change_classification import (
        get_evidence_service,
        set_evidence_service,
    )

    evidence_dir, prov_dir = temp_classification_dirs
    service = ChangeClassificationEvidenceService(output_dir=evidence_dir, provenance_dir=prov_dir)
    set_evidence_service(service)

    client = TestClient(app)

    # 1. Health check
    res_health = client.get("/api/v1/change-classification/health")
    assert res_health.status_code == 200
    data_health = res_health.json()
    assert data_health["status"] == "healthy"
    assert data_health["subsystem"] == "change_evidence_extraction"

    # 2. Extract evidence via POST
    pair = create_mock_scene_pair()
    reg = ChangeRegion(
        region_id="reg_0001",
        pixel_count=80,
        area_px=80,
        bbox_px=[5, 5, 12, 14],
        centroid_px=[8.5, 9.5],
        mean_change_score=0.6,
        max_change_score=0.8,
    )
    change_res = create_mock_change_result("res_api_01", [reg], 40, 40)

    payload = {
        "pair": pair.model_dump(mode="json"),
        "change_result": change_res.model_dump(mode="json"),
    }
    res_post = client.post("/api/v1/change-classification/evidence", json=payload)
    assert res_post.status_code == 200
    data_post = res_post.json()
    assert "evidence_id" in data_post
    evi_id = data_post["evidence_id"]

    # 3. Retrieve via GET /{evidence_id}
    res_get = client.get(f"/api/v1/change-classification/evidence/{evi_id}")
    assert res_get.status_code == 200
    assert res_get.json()["evidence_id"] == evi_id

    # 4. Prohibited remote URL rejection
    res_remote = client.post(
        "/api/v1/change-classification/evidence",
        json={"pair": pair.model_dump(mode="json"), "change_result": change_res.model_dump(mode="json"), "earlier_path": "https://remote.test/t1.tif"},
    )
    assert res_remote.status_code == 400
    assert "strictly forbidden" in res_remote.json()["detail"]

    set_evidence_service(None)


# --- FIXTURE L: CLI Smoke Test ---
def test_fixture_l_cli_smoke_test(tmp_path: Path):
    """CLI extract_change_evidence.py must execute cleanly and output structured summary."""
    # Create mock change result on disk
    from backend.ml.change_detection.service import ChangeDetectionService
    cd_service = ChangeDetectionService(output_dir=tmp_path / "cd_results")

    reg = ChangeRegion(
        region_id="reg_0001",
        pixel_count=100,
        area_px=100,
        bbox_px=[10, 10, 19, 19],
        centroid_px=[14.5, 14.5],
        mean_change_score=0.75,
        max_change_score=0.85,
    )
    change_res = create_mock_change_result("res_cli_test", [reg], 50, 50)
    res_dir = tmp_path / "cd_results" / change_res.result_id
    res_dir.mkdir(parents=True, exist_ok=True)
    (res_dir / "result.json").write_text(change_res.model_dump_json(indent=2), encoding="utf-8")

    cli_out_dir = tmp_path / "cli_evidence"

    cmd = [
        sys.executable,
        "scripts/extract_change_evidence.py",
        "--result-id", change_res.result_id,
        "--change-results-dir", str(tmp_path / "cd_results"),
        "--output-dir", str(cli_out_dir),
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert "ASTRA Change Classification: Evidence Extraction Layer" in proc.stdout
    assert "Feature Families Status:" in proc.stdout
    assert "Regional Morphology & Evidence Summary:" in proc.stdout

    # Run with --json
    cmd_json = cmd + ["--json"]
    proc_json = subprocess.run(cmd_json, capture_output=True, text=True, check=True)
    json_data = json.loads(proc_json.stdout)
    assert "evidence_id" in json_data
    assert json_data["change_detection_result_id"] == change_res.result_id
