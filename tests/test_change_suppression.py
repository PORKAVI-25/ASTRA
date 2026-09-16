"""ASTRA False-Alarm Suppression Test Suite (Phase M4D).

Validates conservative, deterministic false-alarm screening across 15 mandatory scenarios
plus negative protection and safety tests:
1. Cloud patch multi-evidence suppression
2. Bright construction resembling cloud retained
3. Cloud shadow directional ray suppression
4. Dark water expansion not shadow retained
5. Edge shear dipole suppression
6. Narrow road resembling edge shear retained
7. Viewing parallax on highrise flagged (never suppressed)
8. Snow patch NDSI suppression
9. RGB-only cloud ambiguity flagged / insufficient (never suppressed)
10. Scene-wide illumination soft penalty (local contrast retained)
11. Seasonal vegetation drying flagged (no hard suppression)
12. Cross-sensor genuine construction retained
13. Missing solar metadata degradation
14. Filtered change mask encoding (strictly 0, 1, 2)
15. Deterministic repeatability and provenance
16. Zero silent drops (input region count == output region count)
17. Zero regions handling (empty evidence)
18. Composite risk F >= 0.70 alone MUST NEVER hard suppress
19. Small region insufficiency (<10px)
20. API & CLI integration smoke tests
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List, Optional
import numpy as np
import pytest
import rasterio
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
    ChangeCategory,
    ChangeClassificationResult,
    ChangeEvidence,
    ChangeRegionFeatures,
    ConfidenceTier,
    ContextEvidence,
    EvidenceConfig,
    EvidenceFeature,
    RegionClassification,
    SpatialEvidence,
    SpectralEvidence,
    TemporalEvidence,
)
from backend.ml.change_detection import (
    ChangeDetectionConfig,
    ChangeDetectionResult,
    ChangeMetrics,
    ChangeRegion,
)
from backend.ml.change_suppression import (
    ArtifactType,
    ChangeSuppressionService,
    RegionSuppression,
    SuppressionConfig,
    SuppressionDecision,
    SuppressionMetrics,
    SuppressionResult,
    evaluate_region_suppression,
    generate_filtered_change_mask,
)
from geospatial.contracts import GeoBoundingBox


@pytest.fixture
def temp_suppression_dirs(tmp_path: Path):
    """Provides isolated directories for suppression results and provenance."""
    out_dir = tmp_path / "change_suppression"
    prov_dir = tmp_path / "provenance"
    out_dir.mkdir(parents=True, exist_ok=True)
    prov_dir.mkdir(parents=True, exist_ok=True)
    return out_dir, prov_dir


def create_mock_evidence_region(
    region_id: str = "reg_0001",
    area_px: int = 100,
    width_px: int = 10,
    height_px: int = 10,
    aspect_ratio: float = 1.0,
    compactness: float = 0.5,
    rectangularity: float = 0.8,
    linearity_score: float = 0.1,
    minor_axis_length: float = 10.0,
    has_wavelength_metadata: bool = True,
    later_mean_per_band: Optional[Dict[str, float]] = None,
    delta_per_band: Optional[Dict[str, float]] = None,
    brightness_delta: float = 0.1,
    bg_contrast: float = 0.2,
    surrounding_mean: float = 0.1,
    mean_change_score: float = 0.7,
) -> ChangeRegionFeatures:
    """Helper to construct a strongly-typed ChangeRegionFeatures instance."""
    spatial = SpatialEvidence(
        area_px=area_px,
        pixel_count=area_px,
        width_px=width_px,
        height_px=height_px,
        aspect_ratio=aspect_ratio,
        perimeter_px=float(2 * (width_px + height_px)),
        compactness=compactness,
        rectangularity=rectangularity,
        elongation=1.0,
        major_axis_length=float(width_px),
        minor_axis_length=minor_axis_length,
        axis_ratio=1.0,
        linearity_score=linearity_score,
        orientation_degrees=0.0,
        component_density=rectangularity,
        shape_regularity=0.8,
        fragmentation=1.2,
        neighboring_changed_regions_count=0,
    )

    bands = later_mean_per_band or {"Blue": 60.0, "Green": 60.0, "Red": 60.0, "NIR": 120.0}
    deltas = delta_per_band or {"Blue": 10.0, "Green": 10.0, "Red": 10.0, "NIR": 20.0}

    spectral = SpectralEvidence(
        available=True,
        earlier_mean_per_band={"Blue": 50.0, "Green": 50.0, "Red": 50.0, "NIR": 100.0},
        later_mean_per_band=bands,
        delta_per_band=deltas,
        abs_delta_per_band={k: abs(v) for k, v in deltas.items()},
        band_names=list(bands.keys()) if has_wavelength_metadata else ["Red", "Green", "Blue"],
        has_wavelength_metadata=has_wavelength_metadata,
        brightness_delta=EvidenceFeature(
            feature_id=f"feat_{region_id}_brightness_delta",
            feature_name="brightness_delta",
            value=brightness_delta,
            available=True,
            source="spectral",
        ),
    )

    context = ContextEvidence(
        available=True,
        neighborhood_buffer_px=15,
        surrounding_mean_change=surrounding_mean,
        region_to_background_contrast=bg_contrast,
        local_background_mean_per_band={"Red": 40.0, "NIR": 100.0},
    )

    return ChangeRegionFeatures(
        region_id=region_id,
        spatial=spatial,
        spectral=spectral,
        context=context,
        change_score={
            "mean_change_score": mean_change_score,
            "max_change_score": 0.9,
            "score_std": 0.1,
            "changed_fraction": 0.05,
        },
        features={},
    )


def create_mock_evidence_doc(
    regions: List[ChangeRegionFeatures],
    evidence_id: str = "evi_mock_001",
) -> ChangeEvidence:
    """Helper to wrap region features into a ChangeEvidence document."""
    temporal = TemporalEvidence(
        earlier_acquisition_time=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        later_acquisition_time=datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc),
        temporal_separation_seconds=31 * 86400.0,
        temporal_separation_days=31.0,
        temporal_separation_hours=31.0 * 24.0,
        earlier_scene_id="scene_t1",
        later_scene_id="scene_t2",
    )
    return ChangeEvidence(
        evidence_id=evidence_id,
        scene_pair_id="pair_mock_001",
        change_detection_result_id="res_mock_001",
        extractor_id="astra_change_evidence",
        extractor_version="1.0.0",
        temporal=temporal,
        regions=regions,
        config=EvidenceConfig(),
        provenance_id=f"prov_{evidence_id}",
        created_at=datetime.now(timezone.utc),
    )


# ==============================================================================
# 15 MANDATORY TESTS
# ==============================================================================


def test_01_cloud_patch_multi_evidence_suppression():
    """TEST 1: Bright white cloud, flat visible spectrum, high Cirrus -> SUPPRESSED."""
    reg = create_mock_evidence_region(
        region_id="reg_cloud_01",
        area_px=150,
        rectangularity=0.32,  # Non-structural morphology <= 0.50
        later_mean_per_band={
            "Blue": 140.0,
            "Green": 138.0,
            "Red": 142.0,
            "NIR": 135.0,
            "Cirrus": 12.0,  # 12.0 / 255.0 ~ 0.047 >= 0.015
            "SWIR": 50.0,
        },
    )
    aux = {
        "vis_reflectance": 0.55,  # >= 0.35
        "whiteness": 0.04,        # <= 0.15
        "cirrus_reflectance": 0.047,
    }
    sup = evaluate_region_suppression(reg, aux=aux)
    assert sup.decision == SuppressionDecision.SUPPRESSED
    assert sup.hard_triggered is True
    assert sup.primary_attribution == ArtifactType.CLOUD_CONTAMINATION
    assert sup.decision_basis == "CONSERVATIVE_MULTI_EVIDENCE"


def test_02_bright_construction_resembling_cloud_retained():
    """TEST 2: Bright concrete roof with high rectangularity (>0.50) -> RETAINED."""
    reg = create_mock_evidence_region(
        region_id="reg_bldg_01",
        area_px=220,
        rectangularity=0.92,  # Structural rectangularity > 0.50 protects building
        later_mean_per_band={
            "Blue": 110.0,
            "Green": 112.0,
            "Red": 115.0,
            "NIR": 120.0,
            "SWIR": 105.0,  # High SWIR, not absorbing
        },
    )
    aux = {
        "vis_reflectance": 0.44,
        "whiteness": 0.05,
        "swir_reflectance": 0.40,
    }
    sup = evaluate_region_suppression(reg, original_category="construction", aux=aux)
    assert sup.decision == SuppressionDecision.RETAINED
    assert sup.hard_triggered is False
    assert sup.retained_category == "construction"


def test_03_cloud_shadow_directional_ray_suppressed():
    """TEST 3: Dark absorbing patch aligned with solar azimuth ray and cloud -> SUPPRESSED."""
    reg = create_mock_evidence_region(
        region_id="reg_shadow_01",
        area_px=180,
        later_mean_per_band={
            "Blue": 15.0,
            "Green": 18.0,
            "Red": 15.0,
            "NIR": 20.0,
        },
    )
    aux = {
        "vis_reflectance": 0.06,  # <= 0.10
        "nir_reflectance": 0.08,  # <= 0.12
        "solar_azimuth": 145.0,
        "shadow_ray_aligned": True,
        "cloud_candidates": ["reg_cloud_01"],
    }
    sup = evaluate_region_suppression(reg, aux=aux)
    assert sup.decision == SuppressionDecision.SUPPRESSED
    assert sup.hard_triggered is True
    assert sup.primary_attribution == ArtifactType.CLOUD_SHADOW


def test_04_dark_water_expansion_not_shadow_retained():
    """TEST 4: Dark water expansion (low NIR, high NDWI) without cloud along solar ray -> RETAINED."""
    reg = create_mock_evidence_region(
        region_id="reg_water_01",
        area_px=300,
        later_mean_per_band={
            "Blue": 25.0,
            "Green": 30.0,
            "Red": 18.0,
            "NIR": 12.0,  # Low NIR
        },
    )
    aux = {
        "vis_reflectance": 0.07,
        "nir_reflectance": 0.05,
        "solar_azimuth": 145.0,
        "shadow_ray_aligned": False,  # NO cloud candidate along solar ray!
        "cloud_candidates": [],
    }
    sup = evaluate_region_suppression(reg, original_category="water_extent_change", aux=aux)
    assert sup.decision == SuppressionDecision.RETAINED
    assert sup.hard_triggered is False
    assert sup.retained_category == "water_extent_change"


def test_05_edge_shear_dipole_suppression():
    """TEST 5: 1-pixel fringe on static boundary with dipole sign reversal -> SUPPRESSED."""
    reg = create_mock_evidence_region(
        region_id="reg_shear_01",
        area_px=60,
        minor_axis_length=1.2,  # <= 2.0 px
        compactness=0.04,        # <= 0.08
    )
    aux = {
        "edge_overlap_ratio": 0.85,    # >= 0.70
        "dipole_sign_reversal": True,
    }
    sup = evaluate_region_suppression(reg, aux=aux)
    assert sup.decision == SuppressionDecision.SUPPRESSED
    assert sup.hard_triggered is True
    assert sup.primary_attribution == ArtifactType.COREGISTRATION_EDGE_SHEAR


def test_06_narrow_road_resembling_shear_retained():
    """TEST 6: Narrow genuine road with uniform positive delta and no dipole -> RETAINED."""
    reg = create_mock_evidence_region(
        region_id="reg_road_01",
        area_px=180,
        linearity_score=0.92,
        minor_axis_length=1.8,
        compactness=0.05,
    )
    aux = {
        "edge_overlap_ratio": 0.80,
        "dipole_sign_reversal": False,  # No dipole sign reversal; uniform genuine change!
    }
    sup = evaluate_region_suppression(reg, original_category="road_development", aux=aux)
    assert sup.decision == SuppressionDecision.RETAINED
    assert sup.hard_triggered is False
    assert sup.retained_category == "road_development"


def test_07_viewing_parallax_on_highrise_flagged():
    """TEST 7: Tall building viewing geometry parallax -> FLAGGED (NEVER SUPPRESSED)."""
    reg = create_mock_evidence_region(
        region_id="reg_parallax_01",
        area_px=120,
    )
    aux = {
        "parallax_detected": True,
    }
    sup = evaluate_region_suppression(reg, original_category="construction", aux=aux)
    assert sup.decision == SuppressionDecision.FLAGGED
    assert sup.hard_triggered is False
    assert sup.primary_attribution == ArtifactType.VIEWING_GEOMETRY_PARALLAX
    # Parallax must never be suppressed
    assert sup.decision != SuppressionDecision.SUPPRESSED


def test_08_snow_patch_ndsi_suppressed():
    """TEST 8: Snow patch with valid Green + SWIR and NDSI >= 0.40 -> SUPPRESSED."""
    reg = create_mock_evidence_region(
        region_id="reg_snow_01",
        area_px=200,
        has_wavelength_metadata=True,
    )
    aux = {
        "green_reflectance": 0.60,
        "swir_reflectance": 0.15,
        # NDSI = (0.60 - 0.15) / (0.60 + 0.15) = 0.45 / 0.75 = 0.60 >= 0.40
    }
    sup = evaluate_region_suppression(reg, aux=aux)
    assert sup.decision == SuppressionDecision.SUPPRESSED
    assert sup.hard_triggered is True
    assert sup.primary_attribution == ArtifactType.SNOW_ICE


def test_09_rgb_only_cloud_ambiguity_flagged():
    """TEST 9: RGB only bright candidate without SWIR/Cirrus -> FLAGGED or INSUFFICIENT."""
    reg = create_mock_evidence_region(
        region_id="reg_rgb_cloud_01",
        area_px=150,
        has_wavelength_metadata=False,  # RGB only!
        later_mean_per_band={"Blue": 180.0, "Green": 180.0, "Red": 180.0},
    )
    aux = {
        "vis_reflectance": 0.70,
        "whiteness": 0.02,
    }
    sup = evaluate_region_suppression(reg, aux=aux)
    assert sup.decision in (SuppressionDecision.FLAGGED, SuppressionDecision.INSUFFICIENT_EVIDENCE)
    assert sup.hard_triggered is False
    assert sup.decision != SuppressionDecision.SUPPRESSED
    assert any("SWIR/Cirrus bands unavailable" in lim for lim in sup.data_limitations)


def test_10_scene_wide_illumination_soft_penalty():
    """TEST 10: Scene-wide shift but candidate has strong local contrast -> RETAINED."""
    reg = create_mock_evidence_region(
        region_id="reg_illum_01",
        area_px=140,
        bg_contrast=0.35,       # Strong local contrast >= 0.15
        surrounding_mean=0.25,
        mean_change_score=0.85,
    )
    aux = {
        "tile_median_change": 0.30,
    }
    sup = evaluate_region_suppression(reg, aux=aux)
    assert sup.decision == SuppressionDecision.RETAINED
    assert sup.hard_triggered is False


def test_11_seasonal_vegetation_drying_flagged():
    """TEST 11: Broad seasonal vegetation decline where background also changes -> FLAGGED."""
    reg = create_mock_evidence_region(
        region_id="reg_season_01",
        area_px=250,
        bg_contrast=0.04,       # Low local contrast < 0.15
        surrounding_mean=0.30,  # Background also changing
        mean_change_score=0.35, # Highly coupled
    )
    aux = {
        "tile_median_change": 0.28,
    }
    cfg = SuppressionConfig(flag_threshold=0.30)
    sup = evaluate_region_suppression(reg, config=cfg, aux=aux)
    assert sup.decision == SuppressionDecision.FLAGGED
    assert sup.hard_triggered is False


def test_12_cross_sensor_genuine_construction_retained():
    """TEST 12: Sentinel-2 / Landsat-8 pair: building must NOT be suppressed by cross-sensor delta."""
    reg = create_mock_evidence_region(
        region_id="reg_cross_bldg_01",
        area_px=180,
        rectangularity=0.88,
        bg_contrast=0.25,
    )
    aux = {
        "is_cross_sensor": True,
    }
    sup = evaluate_region_suppression(reg, original_category="construction", aux=aux)
    # Must NOT suppress due to cross-sensor differences
    assert sup.decision in (SuppressionDecision.RETAINED, SuppressionDecision.FLAGGED)
    assert sup.decision != SuppressionDecision.SUPPRESSED
    assert any("Cross-sensor pair" in lim for lim in sup.data_limitations)


def test_13_missing_solar_metadata_degradation():
    """TEST 13: Dark patch with missing solar geometry -> FLAGGED or INSUFFICIENT with limitation."""
    reg = create_mock_evidence_region(
        region_id="reg_dark_no_solar_01",
        area_px=160,
    )
    aux = {
        "vis_reflectance": 0.05,
        "nir_reflectance": 0.06,
        "solar_azimuth": None,  # Solar geometry missing!
        "shadow_ray_aligned": False,
    }
    sup = evaluate_region_suppression(reg, aux=aux)
    assert sup.decision in (SuppressionDecision.FLAGGED, SuppressionDecision.INSUFFICIENT_EVIDENCE)
    assert sup.decision != SuppressionDecision.SUPPRESSED
    assert any("Solar geometry missing" in lim for lim in sup.data_limitations)


def test_14_filtered_change_mask_encoding(tmp_path: Path):
    """TEST 14: Mixed scene (1 retained, 1 flagged, 1 suppressed) contains strictly 0, 1, 2."""
    r_ret = RegionSuppression(
        region_id="reg_ret",
        decision=SuppressionDecision.RETAINED,
        artifact_risk_score=0.1,
        artifact_risk_interpretation="Low risk",
        decision_basis="LOW_ARTIFACT_RISK",
        original_category="construction",
        retained_category="construction",
        confidence_tier_adjusted="high",
        hard_triggered=False,
    )
    r_flg = RegionSuppression(
        region_id="reg_flg",
        decision=SuppressionDecision.FLAGGED,
        artifact_risk_score=0.5,
        artifact_risk_interpretation="Flagged",
        decision_basis="MODERATE_ARTIFACT_RISK",
        original_category="road_development",
        retained_category="road_development",
        confidence_tier_adjusted="medium",
        hard_triggered=False,
    )
    r_sup = RegionSuppression(
        region_id="reg_sup",
        decision=SuppressionDecision.SUPPRESSED,
        artifact_risk_score=1.0,
        artifact_risk_interpretation="Suppressed",
        decision_basis="CONSERVATIVE_MULTI_EVIDENCE",
        original_category="unknown",
        retained_category="suppressed",
        confidence_tier_adjusted="suppressed",
        hard_triggered=True,
    )

    regions_suppression = [r_ret, r_flg, r_sup]
    chg_regions = [
        ChangeRegion(
            region_id="reg_ret",
            bbox_px=(10, 10, 30, 30),
            area_px=400,
            pixel_count=400,
            area_m2=400.0,
            centroid_px=(20.0, 20.0),
            mean_change_score=0.8,
            max_change_score=0.9,
        ),
        ChangeRegion(
            region_id="reg_flg",
            bbox_px=(40, 40, 60, 60),
            area_px=400,
            pixel_count=400,
            area_m2=400.0,
            centroid_px=(50.0, 50.0),
            mean_change_score=0.6,
            max_change_score=0.7,
        ),
        ChangeRegion(
            region_id="reg_sup",
            bbox_px=(70, 70, 90, 90),
            area_px=400,
            pixel_count=400,
            area_m2=400.0,
            centroid_px=(80.0, 80.0),
            mean_change_score=0.9,
            max_change_score=1.0,
        ),
    ]

    mask_path = tmp_path / "filtered_change_mask.tif"
    generate_filtered_change_mask(
        regions_suppression=regions_suppression,
        target_path=mask_path,
        change_regions=chg_regions,
        shape=(100, 100),
    )

    assert mask_path.exists()
    with rasterio.open(mask_path) as src:
        arr = src.read(1)
        unique_vals = set(np.unique(arr))
        assert unique_vals.issubset({0, 1, 2})
        assert 0 in unique_vals  # Background and suppressed
        assert 1 in unique_vals  # Retained
        assert 2 in unique_vals  # Flagged


def test_15_deterministic_repeatability_and_provenance(temp_suppression_dirs):
    """TEST 15: Identical inputs produce identical IDs, decisions, and valid prov_sup_{hash}.json."""
    out_dir, prov_dir = temp_suppression_dirs
    service = ChangeSuppressionService(output_dir=out_dir, provenance_dir=prov_dir)

    reg = create_mock_evidence_region(
        region_id="reg_repeat_01",
        area_px=150,
        rectangularity=0.85,
    )
    evi = create_mock_evidence_doc([reg], evidence_id="evi_repeat_test")

    res1 = service.suppress_false_alarms(evi)
    res2 = service.suppress_false_alarms(evi)

    assert res1.suppression_id == res2.suppression_id
    assert res1.provenance_id == res2.provenance_id
    assert res1.metrics.retained_count == res2.metrics.retained_count
    assert res1.regions[0].decision == res2.regions[0].decision
    assert res1.regions[0].artifact_risk_score == res2.regions[0].artifact_risk_score

    # Verify provenance file
    prov_file = prov_dir / f"{res1.provenance_id}.json"
    assert prov_file.exists()
    with open(prov_file, "r", encoding="utf-8") as f:
        prov_data = json.load(f)
        assert prov_data["provenance_id"] == res1.provenance_id
        assert prov_data["processing_stage"] == "false_alarm_suppression"


# ==============================================================================
# ADDITIONAL SAFETY & PROTECTION TESTS
# ==============================================================================


def test_16_zero_silent_drops_input_equals_output(temp_suppression_dirs):
    """Verifies that every input region has exactly one RegionSuppression record."""
    out_dir, prov_dir = temp_suppression_dirs
    service = ChangeSuppressionService(output_dir=out_dir, provenance_dir=prov_dir)

    regions = [
        create_mock_evidence_region(region_id=f"reg_multi_{i}", area_px=50 + i * 20)
        for i in range(5)
    ]
    evi = create_mock_evidence_doc(regions, evidence_id="evi_zero_drop_test")
    res = service.suppress_false_alarms(evi)

    assert len(res.regions) == len(regions)
    assert res.metrics.total_input_regions == len(regions)
    assert [r.region_id for r in res.regions] == [r.region_id for r in regions]


def test_17_zero_regions_handling(temp_suppression_dirs):
    """Verifies that empty evidence (0 candidate regions) is handled gracefully."""
    out_dir, prov_dir = temp_suppression_dirs
    service = ChangeSuppressionService(output_dir=out_dir, provenance_dir=prov_dir)

    evi = create_mock_evidence_doc([], evidence_id="evi_empty_test")
    res = service.suppress_false_alarms(evi)

    assert res.metrics.total_input_regions == 0
    assert res.metrics.suppressed_count == 0
    assert res.metrics.suppression_rate == 0.0
    assert len(res.regions) == 0


def test_18_composite_risk_alone_never_hard_suppresses():
    """CRITICAL SAFETY RULE: F >= 0.70 alone MUST NEVER cause hard suppression (stays FLAGGED)."""
    reg = create_mock_evidence_region(
        region_id="reg_high_f_no_hard_gate",
        area_px=100,
        rectangularity=0.85,  # Structural; cloud hard gate blocked
        bg_contrast=0.05,
        surrounding_mean=0.65,
        mean_change_score=0.70,
    )
    # Inject multiple sub-threshold artifacts so sum(weight * score) >= 0.50
    aux = {
        "vis_reflectance": 0.36,
        "whiteness": 0.14,
        "swir_reflectance": 0.30,
        "tile_median_change": 0.25,
        "radiometric_gain_shift": True,
        "unknown_artifact_detected": True,
        "haze_detected": True,
        "is_cross_sensor": True,
    }
    cfg = SuppressionConfig(suppression_threshold=0.50)
    sup = evaluate_region_suppression(reg, config=cfg, aux=aux)

    # Risk score F should be high
    assert sup.artifact_risk_score >= 0.50
    # BUT decision MUST be FLAGGED, NEVER SUPPRESSED because no hard gate was met!
    assert sup.decision == SuppressionDecision.FLAGGED
    assert sup.hard_triggered is False
    assert sup.decision != SuppressionDecision.SUPPRESSED
    assert sup.decision_basis == "HIGH_ARTIFACT_RISK_UNCONFIRMED"


def test_19_small_region_insufficiency():
    """Regions smaller than min_evaluation_area_px produce INSUFFICIENT_EVIDENCE."""
    reg = create_mock_evidence_region(
        region_id="reg_tiny_01",
        area_px=6,  # < 10 px
    )
    sup = evaluate_region_suppression(reg)
    assert sup.decision == SuppressionDecision.INSUFFICIENT_EVIDENCE
    assert sup.decision_basis == "DATA_LIMITATION"
    assert any("below minimum evaluation threshold" in lim for lim in sup.data_limitations)


def test_20_api_endpoints_integration(temp_suppression_dirs):
    """Smoke test for FastAPI change-suppression endpoints."""
    out_dir, prov_dir = temp_suppression_dirs
    service = ChangeSuppressionService(output_dir=out_dir, provenance_dir=prov_dir)

    from backend.api.v1.endpoints.change_suppression import set_suppression_service
    set_suppression_service(service)

    client = TestClient(app)

    # 1. Health check
    resp_health = client.get("/api/v1/change-suppression/health")
    assert resp_health.status_code == 200
    h_data = resp_health.json()
    assert h_data["status"] == "ready"
    assert h_data["suppressor_id"] == "astra_deterministic_suppressor"

    # 2. Suppress request
    reg = create_mock_evidence_region("reg_api_01", area_px=120)
    evi = create_mock_evidence_doc([reg], evidence_id="evi_api_test")

    payload = {
        "evidence": evi.model_dump(mode="json"),
    }
    resp_sup = client.post("/api/v1/change-suppression/suppress", json=payload)
    assert resp_sup.status_code == 200
    sup_data = resp_sup.json()
    sup_id = sup_data["suppression_id"]
    assert sup_id.startswith("sup_")
    assert len(sup_data["regions"]) == 1

    # 3. Retrieve result by ID
    resp_get = client.get(f"/api/v1/change-suppression/results/{sup_id}")
    assert resp_get.status_code == 200
    assert resp_get.json()["suppression_id"] == sup_id

    # 4. Stream mask
    resp_mask = client.get(f"/api/v1/change-suppression/results/{sup_id}/mask")
    assert resp_mask.status_code == 200
    assert resp_mask.headers["content-type"] == "image/tiff"


def test_21_cli_runner_smoke(temp_suppression_dirs):
    """Smoke test for scripts/run_change_suppression.py CLI."""
    out_dir, prov_dir = temp_suppression_dirs
    reg = create_mock_evidence_region("reg_cli_01", area_px=110)
    evi = create_mock_evidence_doc([reg], evidence_id="evi_cli_test")

    evi_file = out_dir / "evidence_cli.json"
    evi_file.write_text(evi.model_dump_json(indent=2), encoding="utf-8")

    cmd = [
        sys.executable,
        "scripts/run_change_suppression.py",
        "--evidence-file",
        str(evi_file),
        "--output-dir",
        str(out_dir),
        "--provenance-dir",
        str(prov_dir),
        "--json",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"CLI stderr: {res.stderr}"
    data = json.loads(res.stdout)
    assert data["suppression_id"].startswith("sup_")
    assert data["metrics"]["total_input_regions"] == 1
