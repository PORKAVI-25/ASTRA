"""ASTRA Change Classification Test Suite (Phase M4C-B).

Validates deterministic, explainable change-type classification across 15 targeted tests:
1. Construction clear-cut (high rectangularity, compactness, brightness)
2. Clearance clear-cut (severe NDVI loss, irregular parcel)
3. Water extent change clear-cut (multispectral with high NDWI fraction)
4. Water without spectral bands rejection (graceful fallback, zero water hallucination)
5. Road development corridor (elongated, narrow, high linearity)
6. Wide clearing not a road (disqualified by minor axis width limit)
7. Canal / linear water (linear shape with high NDWI routes to water, not road)
8. Small region insufficiency (<10px yields UNKNOWN)
9. Conflicting evidence arbitration (rectangular site clearing)
10. Unresolvable conflict -> UNKNOWN with is_ambiguous=True
11. RGB only graceful degradation (confidence tier downgraded to LOW)
12. Zero regions handling (empty change detection result)
13. Deterministic repeatability (identical outputs and IDs across runs)
14. Service persistence & lineage (classification.json and prov_cls_*.json)
15. API & CLI integration smoke tests
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
import pytest
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
    ChangeClassificationEvidenceService,
    ChangeEvidence,
    ChangeRegionFeatures,
    ClassifierConfig,
    ConfidenceTier,
    ContextEvidence,
    DeterministicChangeClassifier,
    EvidenceConfig,
    EvidenceFeature,
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
from geospatial.contracts import GeoBoundingBox


@pytest.fixture
def temp_cls_dirs(tmp_path: Path):
    """Provides isolated directories for evidence, classification, and provenance."""
    out_dir = tmp_path / "change_classification"
    prov_dir = tmp_path / "provenance"
    out_dir.mkdir(parents=True, exist_ok=True)
    prov_dir.mkdir(parents=True, exist_ok=True)
    return out_dir, prov_dir


def create_mock_evidence(
    region_id: str = "reg_0001",
    area_px: int = 100,
    width_px: int = 10,
    height_px: int = 10,
    aspect_ratio: float = 1.0,
    compactness: float = 0.5,
    rectangularity: float = 0.8,
    linearity_score: float = 0.1,
    major_axis_length: float = 12.0,
    minor_axis_length: float = 10.0,
    axis_ratio: float = 1.2,
    has_wavelength_metadata: bool = True,
    veg_delta: Optional[float] = None,
    post_ndvi: Optional[float] = None,
    brightness_delta: float = 0.1,
    water_fraction: float = 0.0,
    ndwi_mean: Optional[float] = None,
    bg_contrast: float = 0.2,
    surrounding_mean: float = 0.1,
) -> ChangeEvidence:
    """Helper to build a strongly-typed mock ChangeEvidence document."""
    spatial = SpatialEvidence(
        area_px=area_px,
        pixel_count=area_px,
        width_px=width_px,
        height_px=height_px,
        aspect_ratio=aspect_ratio,
        perimeter_px=float(2 * (width_px + height_px)),
        compactness=compactness,
        rectangularity=rectangularity,
        elongation=axis_ratio,
        major_axis_length=major_axis_length,
        minor_axis_length=minor_axis_length,
        axis_ratio=axis_ratio,
        linearity_score=linearity_score,
        orientation_degrees=0.0,
        component_density=rectangularity,
        shape_regularity=0.8,
        fragmentation=1.2,
        neighboring_changed_regions_count=0,
    )

    spectral = SpectralEvidence(
        available=True,
        earlier_mean_per_band={"Red": 50.0, "NIR": 150.0},
        later_mean_per_band={"Red": 80.0, "NIR": 90.0},
        delta_per_band={"Red": 30.0, "NIR": -60.0},
        abs_delta_per_band={"Red": 30.0, "NIR": 60.0},
        band_names=["Blue", "Green", "Red", "NIR"] if has_wavelength_metadata else ["Red", "Green", "Blue"],
        has_wavelength_metadata=has_wavelength_metadata,
        ndvi_mean=EvidenceFeature(
            feature_id=f"feat_{region_id}_ndvi_mean",
            feature_name="ndvi_mean",
            value=post_ndvi,
            available=has_wavelength_metadata and post_ndvi is not None,
            source="spectral",
        ) if has_wavelength_metadata and post_ndvi is not None else None,
        ndwi_mean=EvidenceFeature(
            feature_id=f"feat_{region_id}_ndwi_mean",
            feature_name="ndwi_mean",
            value=ndwi_mean,
            available=has_wavelength_metadata and ndwi_mean is not None,
            source="spectral",
        ) if has_wavelength_metadata and ndwi_mean is not None else None,
        water_spectral_criterion_fraction=EvidenceFeature(
            feature_id=f"feat_{region_id}_water_spectral_criterion_fraction",
            feature_name="water_spectral_criterion_fraction",
            value=water_fraction,
            available=has_wavelength_metadata,
            source="spectral",
        ) if has_wavelength_metadata else None,
        vegetation_proxy_delta=EvidenceFeature(
            feature_id=f"feat_{region_id}_vegetation_proxy_delta",
            feature_name="vegetation_proxy_delta",
            value=veg_delta,
            available=has_wavelength_metadata and veg_delta is not None,
            source="spectral",
        ) if has_wavelength_metadata and veg_delta is not None else None,
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
        local_background_mean_per_band={"Red": 40.0, "NIR": 140.0},
    )

    reg_features = ChangeRegionFeatures(
        region_id=region_id,
        spatial=spatial,
        spectral=spectral,
        context=context,
        change_score={"mean_change_score": 0.7, "max_change_score": 0.9, "score_std": 0.1, "changed_fraction": 0.05},
        features={},
    )

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
        evidence_id=f"evi_mock_{region_id}",
        scene_pair_id="pair_mock_001",
        change_detection_result_id="res_mock_001",
        extractor_id="astra_change_evidence",
        extractor_version="1.0.0",
        temporal=temporal,
        regions=[reg_features],
        config=EvidenceConfig(),
        provenance_id=f"prov_evi_mock_{region_id}",
        created_at=datetime.now(timezone.utc),
    )


# --- TEST 1: Construction Clear-Cut ---
def test_01_construction_clear_cut():
    """A building footprint with high rectangularity, solid compactness, and high brightness -> CONSTRUCTION."""
    classifier = DeterministicChangeClassifier()
    evi = create_mock_evidence(
        area_px=200,
        width_px=14,
        height_px=14,
        aspect_ratio=1.0,
        rectangularity=0.92,
        compactness=0.65,
        linearity_score=0.10,
        brightness_delta=0.22,
        bg_contrast=0.30,
        veg_delta=-0.05,
    )
    result = classifier.classify(evi)
    assert len(result.classifications) == 1
    c = result.classifications[0]
    assert c.category == ChangeCategory.CONSTRUCTION
    assert c.confidence_tier in (ConfidenceTier.HIGH, ConfidenceTier.MEDIUM)
    assert c.evidence_score >= 0.70
    assert "rectangularity" in c.decision_reason.lower()


# --- TEST 2: Clearance Clear-Cut ---
def test_02_clearance_clear_cut():
    """Organic vegetation clearing with severe negative NDVI delta -> CLEARANCE."""
    classifier = DeterministicChangeClassifier()
    evi = create_mock_evidence(
        area_px=350,
        width_px=25,
        height_px=20,
        aspect_ratio=1.25,
        rectangularity=0.55,
        compactness=0.35,
        linearity_score=0.20,
        veg_delta=-0.35,
        post_ndvi=0.10,
        brightness_delta=0.12,
        bg_contrast=0.18,
    )
    result = classifier.classify(evi)
    c = result.classifications[0]
    assert c.category == ChangeCategory.CLEARANCE
    assert c.confidence_tier == ConfidenceTier.HIGH
    assert c.evidence_score >= 0.70
    assert "vegetation" in c.decision_reason.lower() or "ndvi" in c.decision_reason.lower()


# --- TEST 3: Water Extent Clear-Cut ---
def test_03_water_extent_clear_cut():
    """Multispectral observation with high NDWI and high water criterion fraction -> WATER_EXTENT_CHANGE."""
    classifier = DeterministicChangeClassifier()
    evi = create_mock_evidence(
        area_px=400,
        water_fraction=0.85,
        ndwi_mean=0.35,
        brightness_delta=-0.15,
        bg_contrast=0.25,
    )
    result = classifier.classify(evi)
    c = result.classifications[0]
    assert c.category == ChangeCategory.WATER_EXTENT_CHANGE
    assert c.confidence_tier == ConfidenceTier.HIGH
    assert c.evidence_score >= 0.75
    assert "water" in c.decision_reason.lower()


# --- TEST 4: Water Without Bands Rejection ---
def test_04_water_without_bands_rejection():
    """In uncalibrated RGB imagery, water must NOT be asserted; falls back gracefully."""
    classifier = DeterministicChangeClassifier()
    evi = create_mock_evidence(
        has_wavelength_metadata=False,
        water_fraction=0.0,
        ndwi_mean=None,
        brightness_delta=-0.10,
    )
    result = classifier.classify(evi)
    c = result.classifications[0]
    # Water must be strictly 0.0
    assert c.candidate_scores.get(ChangeCategory.WATER_EXTENT_CHANGE.value) == 0.0
    assert c.category != ChangeCategory.WATER_EXTENT_CHANGE
    assert any("indices unavailable" in lim for lim in c.data_limitations)


# --- TEST 5: Road Development Corridor ---
def test_05_road_development_corridor():
    """Elongated strip with high linearity and bounded width -> ROAD_DEVELOPMENT."""
    classifier = DeterministicChangeClassifier()
    evi = create_mock_evidence(
        area_px=500,
        width_px=80,
        height_px=8,
        aspect_ratio=10.0,
        axis_ratio=10.0,
        linearity_score=0.92,
        major_axis_length=80.0,
        minor_axis_length=8.0,
        compactness=0.15,
        brightness_delta=0.15,
        bg_contrast=0.20,
    )
    result = classifier.classify(evi)
    c = result.classifications[0]
    assert c.category == ChangeCategory.ROAD_DEVELOPMENT
    assert c.confidence_tier in (ConfidenceTier.HIGH, ConfidenceTier.MEDIUM)
    assert "linearity" in c.decision_reason.lower()


# --- TEST 6: Wide Clearing Not a Road ---
def test_06_wide_clearing_not_road():
    """High linearity on an excessively wide area (minor axis > 45px) must be rejected from road."""
    classifier = DeterministicChangeClassifier()
    evi = create_mock_evidence(
        area_px=3000,
        width_px=100,
        height_px=60,
        aspect_ratio=1.67,
        axis_ratio=2.5,
        rectangularity=0.55,
        linearity_score=0.80,
        major_axis_length=120.0,
        minor_axis_length=55.0,  # Far exceeds road width limit of 30px
        veg_delta=-0.25,
        post_ndvi=0.15,
        brightness_delta=0.04,
    )
    result = classifier.classify(evi)
    c = result.classifications[0]
    assert c.category != ChangeCategory.ROAD_DEVELOPMENT
    assert c.category == ChangeCategory.CLEARANCE


# --- TEST 7: Canal / Linear Water Exclusion from Road ---
def test_07_canal_linear_water_disqualifies_road():
    """A linear water canal must be classified as water_extent_change or unknown, never road."""
    classifier = DeterministicChangeClassifier()
    evi = create_mock_evidence(
        area_px=400,
        width_px=70,
        height_px=6,
        aspect_ratio=11.6,
        linearity_score=0.90,
        major_axis_length=70.0,
        minor_axis_length=6.0,
        water_fraction=0.70,
        ndwi_mean=0.25,
    )
    result = classifier.classify(evi)
    c = result.classifications[0]
    assert c.category == ChangeCategory.WATER_EXTENT_CHANGE
    assert c.category != ChangeCategory.ROAD_DEVELOPMENT


# --- TEST 8: Small Region Insufficiency (<10px yields UNKNOWN) ---
def test_08_small_region_insufficiency():
    """Regions with <10 pixels lack geometric resolution and must be classified as UNKNOWN."""
    classifier = DeterministicChangeClassifier()
    evi = create_mock_evidence(area_px=6, width_px=3, height_px=2)
    result = classifier.classify(evi)
    c = result.classifications[0]
    assert c.category == ChangeCategory.UNKNOWN
    assert c.confidence_tier == ConfidenceTier.UNCERTAIN
    assert "insufficient region size" in c.decision_reason.lower()


# --- TEST 9: Conflicting Evidence Arbitration ---
def test_09_conflicting_evidence_arbitration():
    """A rectangular site clearing with high rectangularity and vegetation decline is arbitrated cleanly."""
    classifier = DeterministicChangeClassifier()
    evi = create_mock_evidence(
        area_px=250,
        rectangularity=0.88,
        compactness=0.55,
        linearity_score=0.15,
        brightness_delta=0.25,
        veg_delta=-0.20,
        bg_contrast=0.30,
    )
    result = classifier.classify(evi)
    c = result.classifications[0]
    assert c.category == ChangeCategory.CONSTRUCTION
    assert c.evidence_score >= 0.70


# --- TEST 10: Unresolvable Conflict -> UNKNOWN ---
def test_10_unresolvable_conflict_unknown():
    """When top candidates have nearly identical evidence scores within margin, UNKNOWN is assigned."""
    classifier = DeterministicChangeClassifier()
    # Configure tight margin
    cfg = ClassifierConfig(ambiguity_margin_threshold=0.30)
    # Balanced evidence: moderate rectangularity, moderate clearing
    evi = create_mock_evidence(
        area_px=150,
        rectangularity=0.62,
        compactness=0.30,
        linearity_score=0.30,
        brightness_delta=0.08,
        veg_delta=-0.16,
        post_ndvi=0.22,
        bg_contrast=0.16,
    )
    result = classifier.classify(evi, config=cfg)
    c = result.classifications[0]
    assert c.category == ChangeCategory.UNKNOWN
    assert c.is_ambiguous is True
    assert len(c.conflicting_categories) >= 2


# --- TEST 11: RGB Only Graceful Degradation ---
def test_11_rgb_only_graceful_degradation():
    """In uncalibrated RGB imagery, valid classification succeeds but confidence is capped at LOW."""
    classifier = DeterministicChangeClassifier()
    evi = create_mock_evidence(
        has_wavelength_metadata=False,
        rectangularity=0.90,
        compactness=0.60,
        brightness_delta=0.20,
        bg_contrast=0.25,
    )
    result = classifier.classify(evi)
    c = result.classifications[0]
    assert c.category == ChangeCategory.CONSTRUCTION
    assert c.confidence_tier == ConfidenceTier.LOW


# --- TEST 12: Zero Regions Handling ---
def test_12_zero_regions_handling():
    """Empty ChangeEvidence produces a valid empty ChangeClassificationResult without errors."""
    classifier = DeterministicChangeClassifier()
    temporal = TemporalEvidence(
        earlier_acquisition_time=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        later_acquisition_time=datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc),
        temporal_separation_seconds=31 * 86400.0,
        temporal_separation_days=31.0,
        temporal_separation_hours=31.0 * 24.0,
        earlier_scene_id="scene_t1",
        later_scene_id="scene_t2",
    )
    empty_evi = ChangeEvidence(
        evidence_id="evi_empty_test",
        scene_pair_id="pair_empty",
        change_detection_result_id="res_empty",
        extractor_id="astra_change_evidence",
        extractor_version="1.0.0",
        temporal=temporal,
        regions=[],
        config=EvidenceConfig(),
        provenance_id="prov_evi_empty",
        created_at=datetime.now(timezone.utc),
    )
    result = classifier.classify(empty_evi)
    assert result.metrics.total_regions == 0
    assert len(result.classifications) == 0
    assert result.metrics.unclassified_unknown_fraction == 0.0


# --- TEST 13: Deterministic Repeatability ---
def test_13_deterministic_repeatability():
    """Repeated classification of the same evidence produces bit-for-bit identical outputs and IDs."""
    classifier = DeterministicChangeClassifier()
    evi = create_mock_evidence(area_px=200, rectangularity=0.85, brightness_delta=0.18)
    res1 = classifier.classify(evi)
    res2 = classifier.classify(evi)

    assert res1.classification_id == res2.classification_id
    assert res1.provenance_id == res2.provenance_id
    assert res1.classifications[0].category == res2.classifications[0].category
    assert res1.classifications[0].evidence_score == res2.classifications[0].evidence_score


# --- TEST 14: Service Persistence & Lineage ---
def test_14_service_persistence_and_provenance(temp_cls_dirs):
    """Service must persist classification.json and record prov_cls_*.json conforming to ASTRA-DC-v0.1."""
    out_dir, prov_dir = temp_cls_dirs
    service = ChangeClassificationEvidenceService(output_dir=out_dir, provenance_dir=prov_dir)
    evi = create_mock_evidence(area_px=300, rectangularity=0.88, brightness_delta=0.20)

    classification = service.classify_evidence(evi)

    # Check persisted classification document
    cls_file = out_dir / classification.classification_id / "classification.json"
    assert cls_file.exists()
    data = json.loads(cls_file.read_text(encoding="utf-8"))
    assert data["classification_id"] == classification.classification_id
    assert len(data["classifications"]) == 1

    # Check provenance manifest
    prov_file = prov_dir / f"{classification.provenance_id}.json"
    assert prov_file.exists()
    prov_data = json.loads(prov_file.read_text(encoding="utf-8"))
    assert prov_data["provenance_id"] == classification.provenance_id
    assert prov_data["source_scene_id"] == evi.temporal.earlier_scene_id
    assert not prov_data["source_scene_id"].startswith("pair_")
    assert prov_data["parameters"]["scene_pair_id"] == evi.scene_pair_id
    assert prov_data["parameters"]["earlier_scene_id"] == evi.temporal.earlier_scene_id
    assert prov_data["parameters"]["later_scene_id"] == evi.temporal.later_scene_id
    assert prov_data["processing_stage"] == "change_type_classification"
    assert prov_data["executed_by"] == "astra.ml.change_classification.classifier"
    assert "input_hashes" in prov_data["parameters"]

    # Check service lookup
    retrieved = service.get_classification(classification.classification_id)
    assert retrieved is not None
    assert retrieved.classification_id == classification.classification_id


# --- TEST 15: API and CLI Smoke Tests ---
def test_15_api_and_cli_smoke_tests(temp_cls_dirs, tmp_path: Path):
    """API endpoints and CLI script must execute cleanly and return typed results."""
    from backend.api.v1.endpoints.change_classification import (
        get_evidence_service,
        set_evidence_service,
    )

    out_dir, prov_dir = temp_cls_dirs
    service = ChangeClassificationEvidenceService(output_dir=out_dir, provenance_dir=prov_dir)
    set_evidence_service(service)

    client = TestClient(app)

    # 1. Health check includes classification telemetry
    res_health = client.get("/api/v1/change-classification/health")
    assert res_health.status_code == 200
    data_h = res_health.json()
    assert "classifier_id" in data_h
    assert data_h["classifier_id"] == "astra_deterministic_rule_classifier"
    assert "classifications_stored" in data_h

    # 2. Classify via POST
    evi = create_mock_evidence(area_px=220, rectangularity=0.90, brightness_delta=0.18)
    # Save evidence first
    evi_dir = out_dir / evi.evidence_id
    evi_dir.mkdir(parents=True, exist_ok=True)
    (evi_dir / "evidence.json").write_text(evi.model_dump_json(indent=2), encoding="utf-8")

    payload = {"evidence_id": evi.evidence_id}
    res_post = client.post("/api/v1/change-classification/classify", json=payload)
    assert res_post.status_code == 200
    data_post = res_post.json()
    assert "classification_id" in data_post
    cls_id = data_post["classification_id"]

    # 3. Retrieve via GET /{classification_id}
    res_get = client.get(f"/api/v1/change-classification/classifications/{cls_id}")
    assert res_get.status_code == 200
    assert res_get.json()["classification_id"] == cls_id

    # 4. CLI Smoke Test
    cli_out_dir = tmp_path / "cli_classification"
    cmd = [
        sys.executable,
        "scripts/classify_changes.py",
        "--evidence-id", evi.evidence_id,
        "--output-dir", str(out_dir),
        "--provenance-dir", str(prov_dir),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert "ASTRA Change-Type Classification: Semantic Decision Layer" in proc.stdout
    assert "Category Distribution:" in proc.stdout
    assert "Regional Semantic Classifications:" in proc.stdout

    # CLI with --json
    cmd_json = cmd + ["--json"]
    proc_json = subprocess.run(cmd_json, capture_output=True, text=True, check=True)
    json_data = json.loads(proc_json.stdout)
    assert "classification_id" in json_data
    assert json_data["evidence_id"] == evi.evidence_id

    set_evidence_service(None)


# --- TEST 16: Unavailable Spectral Modality Yields UNKNOWN ---
def test_16_unavailable_spectral_modality_yields_unknown():
    """When spectral imagery is completely unavailable, region must degrade to UNKNOWN."""
    classifier = DeterministicChangeClassifier()
    evi = create_mock_evidence(area_px=200, rectangularity=0.95, brightness_delta=0.20)
    evi.regions[0].spectral.available = False

    result = classifier.classify(evi)
    c = result.classifications[0]
    assert c.category == ChangeCategory.UNKNOWN
    assert c.confidence_tier == ConfidenceTier.UNCERTAIN
    assert "spectral imagery modality is unavailable" in c.decision_reason.lower()
    assert any("spectral imagery modality unavailable" in lim.lower() for lim in c.data_limitations)


# --- TEST 17: Dark Rectangle Disqualified From Construction ---
def test_17_dark_rectangle_cannot_be_construction():
    """A rectangular patch with negative or zero brightness delta must NOT become construction."""
    classifier = DeterministicChangeClassifier()
    evi = create_mock_evidence(
        area_px=200,
        width_px=14,
        height_px=14,
        rectangularity=0.95,
        compactness=0.70,
        linearity_score=0.10,
        brightness_delta=-0.08,
        bg_contrast=0.20,
    )
    result = classifier.classify(evi)
    c = result.classifications[0]
    assert c.category != ChangeCategory.CONSTRUCTION
    assert c.candidate_scores[ChangeCategory.CONSTRUCTION.value] < 0.45
    assert any(r.rule_id == "disqual_const_no_brightness_increase" for r in c.rule_evaluations)


# --- TEST 18: Linear Corridor Without Context Degrades to UNKNOWN ---
def test_18_linear_corridor_without_flanking_context_degrades_to_unknown():
    """Elongated linear geometry alone must not classify as road if flanking context is unavailable."""
    classifier = DeterministicChangeClassifier()
    evi = create_mock_evidence(
        area_px=500,
        width_px=80,
        height_px=8,
        aspect_ratio=10.0,
        axis_ratio=10.0,
        linearity_score=0.95,
        major_axis_length=80.0,
        minor_axis_length=8.0,
        brightness_delta=0.15,
        bg_contrast=0.20,
    )
    # Context unavailable
    evi.regions[0].context.available = False
    result = classifier.classify(evi)
    c = result.classifications[0]
    assert c.category == ChangeCategory.UNKNOWN
    assert c.candidate_scores[ChangeCategory.ROAD_DEVELOPMENT.value] < 0.45
    assert any(r.rule_id == "disqual_road_missing_context" for r in c.rule_evaluations)


# --- TEST 19: Negligible Flanking Contrast Penalizes Road ---
def test_19_negligible_flanking_contrast_penalizes_road():
    """Corridor with near-zero contrast (< 0.05) against flanking terrain is penalized."""
    classifier = DeterministicChangeClassifier()
    evi = create_mock_evidence(
        area_px=500,
        width_px=80,
        height_px=8,
        aspect_ratio=10.0,
        axis_ratio=10.0,
        linearity_score=0.95,
        major_axis_length=80.0,
        minor_axis_length=8.0,
        brightness_delta=0.02,
        bg_contrast=0.02,
    )
    result = classifier.classify(evi)
    c = result.classifications[0]
    assert any(r.rule_id == "penalty_road_negligible_contrast" for r in c.rule_evaluations)


# --- TEST 20: Mathematical Score Boundedness Across Extremes ---
def test_20_score_bounds_across_extremes():
    """All candidate scores and evidence scores must be provably bounded within [0.0, 1.0]."""
    classifier = DeterministicChangeClassifier()

    extreme_cases = [
        # Massive negative values
        {"brightness_delta": -1.0, "veg_delta": -1.0, "water_fraction": 1.0, "bg_contrast": -0.5},
        # Massive positive values
        {"brightness_delta": 2.0, "veg_delta": 1.0, "water_fraction": 1.0, "bg_contrast": 1.0},
        # All zeros
        {"brightness_delta": 0.0, "veg_delta": 0.0, "water_fraction": 0.0, "bg_contrast": 0.0},
    ]

    for ec in extreme_cases:
        evi = create_mock_evidence(
            area_px=200,
            brightness_delta=ec["brightness_delta"],
            veg_delta=ec["veg_delta"],
            water_fraction=ec["water_fraction"],
            bg_contrast=ec["bg_contrast"],
        )
        result = classifier.classify(evi)
        for reg in result.classifications:
            assert 0.0 <= reg.evidence_score <= 1.0
            for cat_name, score in reg.candidate_scores.items():
                assert 0.0 <= score <= 1.0, f"Score for {cat_name} was {score}, outside [0, 1]"


# --- TEST 21: Ambiguity Margin Boundary Behavior ---
def test_21_ambiguity_margin_boundary_behavior():
    """Verifies that score differences strictly below ambiguity margin yield UNKNOWN."""
    classifier = DeterministicChangeClassifier()
    cfg = ClassifierConfig(
        min_evidence_score_threshold=0.45,
        ambiguity_margin_threshold=0.15,
    )

    # Balanced candidate scores near margin
    evi = create_mock_evidence(
        area_px=250,
        rectangularity=0.72,
        compactness=0.35,
        linearity_score=0.25,
        brightness_delta=0.08,
        veg_delta=-0.18,
        post_ndvi=0.20,
        bg_contrast=0.18,
    )
    result = classifier.classify(evi, config=cfg)
    c = result.classifications[0]

    # Inspect the top two scores
    scores = sorted(c.candidate_scores.values(), reverse=True)
    top, runner = scores[0], scores[1]
    diff = round(top - runner, 4)

    if diff < cfg.ambiguity_margin_threshold and runner >= cfg.min_evidence_score_threshold:
        assert c.category == ChangeCategory.UNKNOWN
        assert c.is_ambiguous is True
    elif top >= cfg.min_evidence_score_threshold:
        assert c.category != ChangeCategory.UNKNOWN
        assert c.is_ambiguous is False
