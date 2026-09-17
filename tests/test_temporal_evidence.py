"""ASTRA Temporal Evidence Reasoner Test Suite (Phase M4E).

Comprehensive verification covering:
- Contract strictness (extra="forbid", validation)
- Strict chronological ordering and simultaneous observation handling
- Multi-pair upstream lineage preservation
- S_chg source of truth strictly from M4B
- Absolute M4D decision authority (RETAINED, FLAGGED, SUPPRESSED, INSUFFICIENT_EVIDENCE)
- Pairwise-based pre-change absence verification
- Spatial correspondence and metric-projected bbox IoU
- Bounded half-open onset interval mathematics (T_pre, T_earliest]
- Earliest supporting observation gating and persistence semantics
- Category evolution vs conflict discrimination
- Cross-sensor confidence capping
- Provenance and deterministic hashing
- REST API safety and CLI offline execution
- 14 adversarial scenarios
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List, Optional
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.config import settings
from geospatial.contracts import GeoBoundingBox, ProvenanceRecord
from backend.ml.change.types import TemporalObservation, TemporalSeries
from backend.ml.change_classification.types import (
    ChangeCategory,
    ChangeClassificationMetrics,
    ChangeClassificationResult,
    ChangeEvidence,
    ChangeRegionFeatures,
    ClassifierConfig,
    ConfidenceTier,
    ContextEvidence,
    EvidenceConfig,
    RegionClassification,
    SpatialEvidence,
    SpectralEvidence,
    TemporalEvidence,
)
from backend.ml.change_detection.types import (
    ChangeDetectionConfig,
    ChangeDetectionResult,
    ChangeMetrics,
    ChangeRegion,
)
from backend.ml.change_suppression.types import (
    ArtifactType,
    RegionSuppression,
    SuppressionConfig,
    SuppressionDecision,
    SuppressionMetrics,
    SuppressionResult,
)
from backend.ml.temporal_evidence import (
    CandidateRegionRef,
    CorrespondenceRelationship,
    PairwiseTemporalEvidenceInput,
    SpatialCorrespondence,
    SpatialCorrespondenceStatus,
    TemporalCategoryEvolution,
    TemporalConfidenceTier,
    TemporalEvidenceConfig,
    TemporalEvidenceMetrics,
    TemporalEvidenceNode,
    TemporalEvidenceResult,
    TemporalEvidenceService,
    TemporalIntervalType,
    TemporalNodeStatus,
    TemporalOnsetEstimate,
    TemporalSupportStatus,
)
from backend.ml.temporal_evidence.correspondence import (
    compute_geodesic_distance_m,
    compute_metric_bbox_iou,
    evaluate_spatial_correspondence,
    project_wgs84_bbox_to_metric,
    verify_pixel_grid_compatibility,
)
from backend.ml.temporal_evidence.chronology import (
    align_pairwise_evidence_to_observations,
    check_temporal_gaps,
    order_and_validate_observations,
)


# ==============================================================================
# Test Helpers and Fixtures
# ==============================================================================

def make_observation(
    obs_id: str,
    dt_str: str,
    sensor: str = "Sentinel-2A MSI",
    platform: str = "Sentinel-2",
    crs: str = "EPSG:32643",
    cloud_frac: Optional[float] = 0.05,
    valid_pixel_ratio: Optional[float] = 0.98,
    min_lon: float = 77.10,
    min_lat: float = 12.10,
    max_lon: float = 77.20,
    max_lat: float = 12.20,
    scene_id: Optional[str] = None,
) -> TemporalObservation:
    # Ensure obs_id has at least 3 chars
    clean_obs_id = obs_id if len(obs_id) >= 3 else f"obs_{obs_id}"
    dt = datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc)
    meta = {}
    if cloud_frac is not None:
        meta["cloud_fraction"] = cloud_frac
    if valid_pixel_ratio is not None:
        meta["valid_pixel_ratio"] = valid_pixel_ratio

    return TemporalObservation(
        observation_id=clean_obs_id,
        scene_id=scene_id or f"S2A_{clean_obs_id}",
        acquisition_time=dt,
        sensor=sensor,
        platform=platform,
        crs=crs,
        bounds_wgs84=GeoBoundingBox(min_lon=min_lon, min_lat=min_lat, max_lon=max_lon, max_lat=max_lat),
        source_hash=f"hash_{clean_obs_id}_12345678",
        metadata=meta,
    )


def make_change_region(
    region_id: str = "reg_0001",
    mean_score: float = 0.75,
    min_lon: float = 77.12,
    min_lat: float = 12.12,
    max_lon: float = 77.13,
    max_lat: float = 12.13,
) -> ChangeRegion:
    clean_reg_id = region_id if len(region_id) >= 3 else f"reg_{region_id}"
    return ChangeRegion(
        region_id=clean_reg_id,
        pixel_count=100,
        area_px=100,
        area_m2=10000.0,
        bbox_px=[10, 10, 30, 30],
        bbox_wgs84=GeoBoundingBox(min_lon=min_lon, min_lat=min_lat, max_lon=max_lon, max_lat=max_lat),
        centroid_px=[20.0, 20.0],
        centroid_wgs84=[(min_lon + max_lon) / 2.0, (min_lat + max_lat) / 2.0],
        mean_change_score=mean_score,
        max_change_score=min(1.0, mean_score + 0.1),
    )


def make_pairwise_evidence(
    pair_id: str,
    region_id: str = "reg_0001",
    decision: SuppressionDecision = SuppressionDecision.RETAINED,
    mean_change_score: float = 0.75,
    category: ChangeCategory = ChangeCategory.CONSTRUCTION,
    confidence_tier: ConfidenceTier = ConfidenceTier.HIGH,
    evidence_score: float = 0.85,
) -> PairwiseTemporalEvidenceInput:
    clean_pair_id = pair_id if len(pair_id) >= 5 else f"pair_{pair_id}"
    clean_reg_id = region_id if len(region_id) >= 3 else f"reg_{region_id}"

    chg_reg = make_change_region(region_id=clean_reg_id, mean_score=mean_change_score)
    cdr_id = f"cdr_{clean_pair_id}"
    evi_id = f"evi_{clean_pair_id}"
    cls_id = f"cls_{clean_pair_id}"
    sup_id = f"sup_{clean_pair_id}"

    cdr = ChangeDetectionResult(
        result_id=cdr_id,
        scene_pair_id=clean_pair_id,
        algorithm_id="pixel_diff",
        algorithm_version="1.0.0",
        config=ChangeDetectionConfig(),
        metrics=ChangeMetrics(
            total_pixels=1000,
            valid_pixels=1000,
            invalid_pixels=0,
            changed_pixels=100,
            changed_fraction=0.1,
            number_of_regions=1,
            changed_area_px=100,
            threshold_used=0.2,
            threshold_method="otsu",
        ),
        regions=[chg_reg],
        provenance_id=f"prov_{cdr_id}",
    )

    reg_supp = RegionSuppression(
        region_id=clean_reg_id,
        decision=decision,
        artifact_risk_score=0.10 if decision == SuppressionDecision.RETAINED else 0.80,
        artifact_risk_interpretation="Low risk" if decision == SuppressionDecision.RETAINED else "Artifact risk",
        decision_basis="MULTI_EVIDENCE",
        decision_reasons=["Test reasons"],
        original_category=category.value,
        retained_category=category.value if decision == SuppressionDecision.RETAINED else "suppressed",
        confidence_tier_adjusted=confidence_tier.value,
    )

    sup = SuppressionResult(
        suppression_id=sup_id,
        scene_pair_id=clean_pair_id,
        change_detection_result_id=cdr_id,
        evidence_id=evi_id,
        classification_id=cls_id,
        suppressor_id="test_suppressor",
        suppressor_version="1.0.0",
        config=SuppressionConfig(),
        metrics=SuppressionMetrics(
            total_input_regions=1,
            retained_count=1 if decision == SuppressionDecision.RETAINED else 0,
            flagged_count=1 if decision == SuppressionDecision.FLAGGED else 0,
            suppressed_count=1 if decision == SuppressionDecision.SUPPRESSED else 0,
            insufficient_evidence_count=1 if decision == SuppressionDecision.INSUFFICIENT_EVIDENCE else 0,
            suppression_rate=0.0,
            total_area_px=100,
            retained_area_px=100 if decision == SuppressionDecision.RETAINED else 0,
            flagged_area_px=100 if decision == SuppressionDecision.FLAGGED else 0,
            suppressed_area_px=100 if decision == SuppressionDecision.SUPPRESSED else 0,
        ),
        regions=[reg_supp],
        provenance_id=f"prov_{sup_id}",
    )

    reg_cls = RegionClassification(
        region_id=clean_reg_id,
        category=category,
        evidence_score=evidence_score,
        confidence_tier=confidence_tier,
        decision_reason="Test classification",
    )

    cls_res = ChangeClassificationResult(
        classification_id=cls_id,
        evidence_id=evi_id,
        scene_pair_id=clean_pair_id,
        change_detection_result_id=cdr_id,
        classifier_id="test_classifier",
        classifier_version="1.0.0",
        config=ClassifierConfig(),
        metrics=ChangeClassificationMetrics(
            total_regions=1,
            high_confidence_count=1,
            ambiguous_count=0,
            unclassified_unknown_fraction=0.0,
        ),
        classifications=[reg_cls],
        provenance_id=f"prov_{cls_id}",
    )

    t_earlier = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t_later = datetime(2026, 1, 15, tzinfo=timezone.utc)
    if "02" in clean_pair_id:
        t_earlier = datetime(2026, 1, 15, tzinfo=timezone.utc)
        t_later = datetime(2026, 2, 1, tzinfo=timezone.utc)
    elif "03" in clean_pair_id:
        t_earlier = datetime(2026, 2, 1, tzinfo=timezone.utc)
        t_later = datetime(2026, 2, 15, tzinfo=timezone.utc)

    dt_sec = (t_later - t_earlier).total_seconds()
    dt_days = dt_sec / 86400.0
    dt_hours = dt_sec / 3600.0

    evi = ChangeEvidence(
        evidence_id=evi_id,
        scene_pair_id=clean_pair_id,
        change_detection_result_id=cdr_id,
        extractor_id="test_extractor",
        extractor_version="1.0.0",
        temporal=TemporalEvidence(
            earlier_acquisition_time=t_earlier,
            later_acquisition_time=t_later,
            temporal_separation_seconds=dt_sec,
            temporal_separation_hours=dt_hours,
            temporal_separation_days=dt_days,
            earlier_scene_id=f"scene_{clean_pair_id}_01",
            later_scene_id=f"scene_{clean_pair_id}_02",
        ),
        regions=[],
        config=EvidenceConfig(),
        source_hashes={"pair_hash": f"sha_{clean_pair_id}"},
        provenance_id=f"prov_{evi_id}",
    )

    return PairwiseTemporalEvidenceInput(
        scene_pair_id=clean_pair_id,
        change_detection_result_id=cdr_id,
        evidence_id=evi_id,
        classification_id=cls_id,
        suppression_id=sup_id,
        suppression_result=sup,
        change_detection_result=cdr,
        evidence=evi,
        classification=cls_res,
    )


# ==============================================================================
# Group A: Contracts & Validation Strictness
# ==============================================================================

def test_candidate_ref_extra_forbid():
    with pytest.raises(Exception):
        CandidateRegionRef(
            change_detection_result_id="res_0001",
            scene_pair_id="pair_0001",
            region_id="reg_0001",
            unknown_field="fail",
        )


def test_pairwise_input_extra_forbid():
    with pytest.raises(Exception):
        PairwiseTemporalEvidenceInput(
            scene_pair_id="pair_0001",
            change_detection_result_id="res_0001",
            evidence_id="evi_0001",
            suppression_id="sup_0001",
            extra_param=123,
        )


def test_config_extra_forbid():
    with pytest.raises(Exception):
        TemporalEvidenceConfig(unknown_hyperparameter=42)


def test_spatial_correspondence_extra_forbid():
    with pytest.raises(Exception):
        SpatialCorrespondence(
            status=SpatialCorrespondenceStatus.GEOREFERENCED_BBOX,
            is_spatially_compatible=True,
            extra_attr=True,
        )


def test_temporal_evidence_result_extra_forbid():
    with pytest.raises(Exception):
        TemporalEvidenceResult.model_validate({"extra_key": 999})


def test_invalid_enum_values_rejected():
    with pytest.raises(Exception):
        TemporalNodeStatus("INVALID_STATUS_CODE")


# ==============================================================================
# Group B: Chronology & Simultaneous Observations
# ==============================================================================

def test_chronology_strictly_ascending():
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    obs3 = make_observation("obs_03", "2026-02-01T00:00:00")
    sorted_obs, simul_ids, warnings = order_and_validate_observations([obs3, obs1, obs2])
    assert [o.observation_id for o in sorted_obs] == ["obs_01", "obs_02", "obs_03"]
    assert len(simul_ids) == 0


def test_chronology_duplicate_timestamps_identified():
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-01T00:00:00")  # Simultaneous
    obs3 = make_observation("obs_03", "2026-01-15T00:00:00")
    sorted_obs, simul_ids, warnings = order_and_validate_observations([obs1, obs2, obs3])
    assert "obs_02" in simul_ids
    assert len(warnings) >= 1
    assert "SIMULTANEOUS_CO_TEMPORAL" in warnings[0]


def test_chronology_simultaneous_excluded_from_ordered_interval(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-01T00:00:00")  # Simultaneous with obs1
    obs3 = make_observation("obs_03", "2026-01-15T00:00:00")
    obs4 = make_observation("obs_04", "2026-02-01T00:00:00")

    series = TemporalSeries(
        series_id="series_simul",
        target_id="tile_0001",
        bounds_wgs84=obs1.bounds_wgs84,
        observations=[obs1, obs2, obs3, obs4],
    )
    cand_ref = CandidateRegionRef(
        change_detection_result_id="cdr_pair_01_03",
        scene_pair_id="pair_01_03",
        region_id="reg_0001",
    )
    disc_pair = make_pairwise_evidence("pair_01_03", region_id="reg_0001")
    sub_pair = make_pairwise_evidence("pair_03_04", region_id="reg_0001")

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    result = service.evaluate_temporal_evidence(
        candidate_ref=cand_ref,
        series=series,
        discovery_pair_evidence=disc_pair,
        pairwise_evidence=[sub_pair],
    )
    simul_nodes = [n for n in result.timeline_nodes if n.node_status == TemporalNodeStatus.SIMULTANEOUS_CO_TEMPORAL]
    assert len(simul_nodes) == 1
    assert simul_nodes[0].eligible_for_earliest_support is False


def test_chronology_empty_series_rejected(tmp_path):
    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    cand_ref = CandidateRegionRef(
        change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001"
    )
    empty_series = TemporalSeries(
        series_id="empty_series", target_id="tile_01", bounds_wgs84=GeoBoundingBox(min_lon=0, min_lat=0, max_lon=1, max_lat=1), observations=[]
    )
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001")
    with pytest.raises(ValueError, match="zero observations"):
        service.evaluate_temporal_evidence(cand_ref, empty_series, disc)


def test_chronology_wide_temporal_gap_warning():
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-05-01T00:00:00")  # 120 days gap
    warnings = check_temporal_gaps([obs1, obs2], max_gap_days=90.0)
    assert len(warnings) == 1
    assert "Wide temporal gap" in warnings[0]


# ==============================================================================
# Group C: Multi-Pair Lineage
# ==============================================================================

def test_multi_pair_discovery_and_subsequent(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    obs3 = make_observation("obs_03", "2026-02-01T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2, obs3])

    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    p1 = make_pairwise_evidence("pair_01", region_id="reg_0001")
    p2 = make_pairwise_evidence("pair_02", region_id="reg_0001")

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, p1, [p2])
    assert res.discovery_scene_pair_id == "pair_01"
    assert "pair_01" in res.evaluated_scene_pair_ids
    assert "pair_02" in res.evaluated_scene_pair_ids
    assert "sup_pair_01" in res.upstream_suppression_ids
    assert "sup_pair_02" in res.upstream_suppression_ids


def test_multi_pair_scene_pair_id_mismatch_rejected(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_OTHER", region_id="reg_0001")

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    with pytest.raises(ValueError, match="Discovery pair ID mismatch"):
        service.evaluate_temporal_evidence(cand, series, disc)


def test_multi_pair_change_detection_id_mismatch_rejected(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1])
    cand = CandidateRegionRef(change_detection_result_id="cdr_MISMATCH", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001")

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    with pytest.raises(ValueError, match="Discovery change detection result ID mismatch"):
        service.evaluate_temporal_evidence(cand, series, disc)


def test_multi_pair_duplicate_scene_pair_id_rejected(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001")
    dup_p1 = make_pairwise_evidence("pair_01", region_id="reg_0001")

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    with pytest.raises(ValueError, match="Duplicate scene_pair_id"):
        service.evaluate_temporal_evidence(cand, series, disc, [dup_p1])


def test_multi_pair_complete_lineage_preserved(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001")

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc)
    assert len(res.evaluated_change_detection_result_ids) == 1
    assert len(res.evaluated_evidence_ids) == 1
    assert len(res.evaluated_classification_ids) == 1
    assert len(res.upstream_suppression_ids) == 1


# ==============================================================================
# Group D: Change Score Source of Truth
# ==============================================================================

def test_s_chg_from_upstream_change_region(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001", mean_change_score=0.88)

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc)
    node_o2 = [n for n in res.timeline_nodes if n.observation_id == "obs_02"][0]
    assert node_o2.heuristic_support_score > 0.50


def test_s_chg_zero_when_valid_m4b_has_no_candidate(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001")
    # Empty CDR regions
    disc.change_detection_result.regions = []

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc)
    node_o2 = [n for n in res.timeline_nodes if n.observation_id == "obs_02"][0]
    # S_chg is zero; support score reflects that
    assert node_o2.heuristic_support_score <= 0.45


def test_s_chg_not_zero_when_m4b_missing(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001")
    disc.change_detection_result = None  # Missing M4B result

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc)
    node_o2 = [n for n in res.timeline_nodes if n.observation_id == "obs_02"][0]
    assert any("M4B ChangeDetectionResult is missing" in lim for lim in node_o2.data_limitations)


def test_s_chg_mirrored_in_change_evidence():
    reg = make_change_region("reg_0001", mean_score=0.72)
    assert reg.mean_change_score == 0.72


def test_m4e_never_recomputes_raster_differencing(monkeypatch, tmp_path):
    import rasterio
    def guarded_open(*args, **kwargs):
        raise RuntimeError("M4E must NEVER open raster imagery for change detection!")
    monkeypatch.setattr(rasterio, "open", guarded_open)

    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001")

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc)
    assert res.temporal_evidence_id.startswith("tem_")


# ==============================================================================
# Group E: M4D Authority
# ==============================================================================

def test_m4d_retained_eligible_for_earliest_support(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001", decision=SuppressionDecision.RETAINED)

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc)
    node_o2 = [n for n in res.timeline_nodes if n.observation_id == "obs_02"][0]
    assert node_o2.eligible_for_earliest_support is True
    assert node_o2.node_status == TemporalNodeStatus.EARLIEST_SUPPORTING


def test_m4d_suppressed_never_earliest_support(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001", decision=SuppressionDecision.SUPPRESSED)

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc)
    node_o2 = [n for n in res.timeline_nodes if n.observation_id == "obs_02"][0]
    assert node_o2.eligible_for_earliest_support is False
    assert node_o2.heuristic_support_score == 0.0
    assert node_o2.node_status == TemporalNodeStatus.SUPPRESSED_ARTIFACT


def test_m4d_insufficient_evidence_never_earliest_support(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001", decision=SuppressionDecision.INSUFFICIENT_EVIDENCE)

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc)
    node_o2 = [n for n in res.timeline_nodes if n.observation_id == "obs_02"][0]
    assert node_o2.eligible_for_earliest_support is False
    assert node_o2.heuristic_support_score == 0.0
    assert node_o2.node_status == TemporalNodeStatus.INSUFFICIENT_DATA


def test_m4d_flagged_discounted_and_never_earliest_support(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001", decision=SuppressionDecision.FLAGGED)

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc)
    node_o2 = [n for n in res.timeline_nodes if n.observation_id == "obs_02"][0]
    assert node_o2.eligible_for_earliest_support is False
    assert node_o2.node_status == TemporalNodeStatus.FLAGGED_SUPPORT
    assert node_o2.heuristic_support_score > 0.0  # Discounted by 0.40


def test_m4d_suppressed_zero_contribution_to_persistence(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    obs3 = make_observation("obs_03", "2026-02-01T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2, obs3])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001", decision=SuppressionDecision.RETAINED)
    sub = make_pairwise_evidence("pair_02", region_id="reg_0001", decision=SuppressionDecision.SUPPRESSED)

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc, [sub])
    assert res.metrics.supporting_nodes_count == 1
    assert res.temporal_support_status == TemporalSupportStatus.SINGLE_OBSERVATION_SUPPORT


def test_m4d_insufficient_zero_contribution_to_persistence(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    obs3 = make_observation("obs_03", "2026-02-01T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2, obs3])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001", decision=SuppressionDecision.RETAINED)
    sub = make_pairwise_evidence("pair_02", region_id="reg_0001", decision=SuppressionDecision.INSUFFICIENT_EVIDENCE)

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc, [sub])
    assert res.metrics.supporting_nodes_count == 1


# ==============================================================================
# Group F: Pre-Change Absence
# ==============================================================================

def test_pre_change_absence_valid_discovery_basis(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00", cloud_frac=0.04, valid_pixel_ratio=0.99)
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001")

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc)
    node_o1 = [n for n in res.timeline_nodes if n.observation_id == "obs_01"][0]
    assert node_o1.node_status == TemporalNodeStatus.PRE_CHANGE_ABSENCE


def test_pre_change_absence_missing_cloud_metadata_fails(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00", cloud_frac=None, valid_pixel_ratio=0.99)
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001")

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc)
    node_o1 = [n for n in res.timeline_nodes if n.observation_id == "obs_01"][0]
    assert node_o1.node_status == TemporalNodeStatus.INSUFFICIENT_DATA


def test_pre_change_absence_missing_valid_pixels_fails(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00", cloud_frac=0.02, valid_pixel_ratio=None)
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001")

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc)
    node_o1 = [n for n in res.timeline_nodes if n.observation_id == "obs_01"][0]
    assert node_o1.node_status == TemporalNodeStatus.INSUFFICIENT_DATA


def test_pre_change_absence_exceeds_cloud_threshold(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00", cloud_frac=0.35, valid_pixel_ratio=0.99)
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001")

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc)
    node_o1 = [n for n in res.timeline_nodes if n.observation_id == "obs_01"][0]
    assert node_o1.node_status == TemporalNodeStatus.INSUFFICIENT_DATA


def test_pre_change_absence_fails_valid_pixel_ratio(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00", cloud_frac=0.02, valid_pixel_ratio=0.60)
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001")

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc)
    node_o1 = [n for n in res.timeline_nodes if n.observation_id == "obs_01"][0]
    assert node_o1.node_status == TemporalNodeStatus.INSUFFICIENT_DATA


def test_pre_change_absence_prior_pair_basis(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    obs3 = make_observation("obs_03", "2026-02-01T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2, obs3])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_02", scene_pair_id="pair_02", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_02", region_id="reg_0001")  # Discovery pair is pair_02 (obs_02 -> obs_03)

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc)
    node_o2 = [n for n in res.timeline_nodes if n.observation_id == "obs_02"][0]
    assert node_o2.node_status == TemporalNodeStatus.PRE_CHANGE_ABSENCE


# ==============================================================================
# Group G: Spatial Correspondence & Metric IoU
# ==============================================================================

def test_spatial_exact_pixel_grid_compatibility():
    is_grid, crs_m, gsd_m = verify_pixel_grid_compatibility(
        cand_crs="EPSG:32643",
        obs_crs="EPSG:32643",
        cand_gsd_m=10.0,
        obs_gsd_m=10.0,
        cand_transform=(500000.0, 10.0, 0.0, 1400000.0, 0.0, -10.0),
        obs_transform=(500000.0, 10.0, 0.0, 1400000.0, 0.0, -10.0),
    )
    assert is_grid is True
    assert crs_m is True
    assert gsd_m is True


def test_spatial_differing_crs_pixel_distance_none():
    corr = evaluate_spatial_correspondence(
        candidate_bbox_wgs84=GeoBoundingBox(min_lon=77.1, min_lat=12.1, max_lon=77.2, max_lat=12.2),
        candidate_centroid_wgs84=[77.15, 12.15],
        candidate_bbox_px=[0, 0, 10, 10],
        candidate_centroid_px=[5.0, 5.0],
        candidate_crs="EPSG:32643",
        target_bbox_wgs84=GeoBoundingBox(min_lon=77.1, min_lat=12.1, max_lon=77.2, max_lat=12.2),
        target_centroid_wgs84=[77.15, 12.15],
        target_bbox_px=[0, 0, 10, 10],
        target_centroid_px=[5.0, 5.0],
        target_crs="EPSG:32644",  # Different CRS
    )
    assert corr.status != SpatialCorrespondenceStatus.EXACT_PIXEL_GRID
    assert corr.centroid_distance_px is None


def test_spatial_differing_gsd_pixel_distance_none():
    corr = evaluate_spatial_correspondence(
        candidate_bbox_wgs84=GeoBoundingBox(min_lon=77.1, min_lat=12.1, max_lon=77.2, max_lat=12.2),
        candidate_centroid_wgs84=[77.15, 12.15],
        candidate_bbox_px=[0, 0, 10, 10],
        candidate_centroid_px=[5.0, 5.0],
        candidate_crs="EPSG:32643",
        target_bbox_wgs84=GeoBoundingBox(min_lon=77.1, min_lat=12.1, max_lon=77.2, max_lat=12.2),
        target_centroid_wgs84=[77.15, 12.15],
        target_bbox_px=[0, 0, 10, 10],
        target_centroid_px=[5.0, 5.0],
        target_crs="EPSG:32643",
        cand_gsd_m=10.0,
        target_gsd_m=30.0,  # 3x resolution difference
    )
    assert corr.centroid_distance_px is None


def test_spatial_metric_bbox_iou_not_degree_space():
    box_a = GeoBoundingBox(min_lon=77.10, min_lat=12.10, max_lon=77.12, max_lat=12.12)
    box_b = GeoBoundingBox(min_lon=77.11, min_lat=12.11, max_lon=77.13, max_lat=12.13)
    iou = compute_metric_bbox_iou(box_a, box_b)
    assert 0.10 < iou < 0.50


def test_spatial_geodesic_centroid_distance():
    d = compute_geodesic_distance_m(77.0, 12.0, 77.0, 12.001)
    assert 100.0 < d < 125.0


def test_spatial_disjoint_footprints():
    corr = evaluate_spatial_correspondence(
        candidate_bbox_wgs84=GeoBoundingBox(min_lon=77.0, min_lat=12.0, max_lon=77.01, max_lat=12.01),
        candidate_centroid_wgs84=[77.005, 12.005],
        candidate_bbox_px=None,
        candidate_centroid_px=None,
        candidate_crs="EPSG:32643",
        target_bbox_wgs84=GeoBoundingBox(min_lon=78.0, min_lat=13.0, max_lon=78.01, max_lat=13.01),
        target_centroid_wgs84=[78.005, 13.005],
        target_bbox_px=None,
        target_centroid_px=None,
        target_crs="EPSG:32643",
    )
    assert corr.status == SpatialCorrespondenceStatus.DISJOINT
    assert corr.is_spatially_compatible is False


def test_spatial_topological_relationship_matched_split_merged():
    corr = SpatialCorrespondence(
        status=SpatialCorrespondenceStatus.GEOREFERENCED_BBOX,
        relationship=CorrespondenceRelationship.SPLIT,
        is_spatially_compatible=True,
        iou_wgs84=0.65,
    )
    assert corr.relationship == CorrespondenceRelationship.SPLIT


# ==============================================================================
# Group H: Onset Interval Mathematics
# ==============================================================================

def test_onset_interval_bounded_half_open(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001")

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc)
    assert res.onset_estimate.interval_type == TemporalIntervalType.BOUNDED_HALF_OPEN
    assert res.onset_estimate.physical_onset_interval.startswith("(")
    assert res.onset_estimate.physical_onset_interval.endswith("]")


def test_onset_interval_left_unbounded(tmp_path):
    # Discovery observation is first in series (no prior observation)
    obs1 = make_observation("obs_01", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001")

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc)
    assert res.onset_estimate.interval_type == TemporalIntervalType.LEFT_UNBOUNDED
    assert "(-infinity" in res.onset_estimate.physical_onset_interval


def test_onset_interval_unresolved(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001", decision=SuppressionDecision.SUPPRESSED)

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc)
    assert res.onset_estimate.interval_type == TemporalIntervalType.UNRESOLVED


def test_onset_interval_display_bounding_span_formatted(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001")

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc)
    assert res.onset_estimate.display_bounding_span == "[2026-01-01, 2026-01-15]"


def test_onset_interval_days_calculation(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-11T00:00:00")  # Exactly 10 days
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001")

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc)
    assert res.onset_estimate.interval_days == 10.0


# ==============================================================================
# Group I: Earliest Support & Persistence Semantics
# ==============================================================================

def test_earliest_support_chronologically_first_eligible(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    obs3 = make_observation("obs_03", "2026-02-01T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2, obs3])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001")
    sub = make_pairwise_evidence("pair_02", region_id="reg_0001")

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc, [sub])
    assert res.onset_estimate.earliest_support_observation_id == "obs_02"


def test_earliest_support_later_retained_after_flagged(tmp_path):
    # obs_01 pre -> obs_02 FLAGGED -> obs_03 RETAINED
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    obs3 = make_observation("obs_03", "2026-02-01T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2, obs3])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001", decision=SuppressionDecision.FLAGGED)
    sub = make_pairwise_evidence("pair_02", region_id="reg_0001", decision=SuppressionDecision.RETAINED)

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc, [sub])
    assert res.onset_estimate.earliest_support_observation_id == "obs_03"
    assert res.onset_estimate.provisional_flagged_observation_id == "obs_02"


def test_persistence_min_observations_satisfied(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    obs3 = make_observation("obs_03", "2026-02-01T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2, obs3])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001")
    sub = make_pairwise_evidence("pair_02", region_id="reg_0001")

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc, [sub])
    assert res.metrics.supporting_nodes_count == 2
    assert res.temporal_support_status == TemporalSupportStatus.STRONG_TEMPORAL_SUPPORT


def test_persistence_single_observation_support(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001")

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc)
    assert res.metrics.supporting_nodes_count == 1
    assert res.temporal_support_status == TemporalSupportStatus.SINGLE_OBSERVATION_SUPPORT


def test_persistence_no_support_when_zero_supporting(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001", decision=SuppressionDecision.SUPPRESSED)

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc)
    assert res.temporal_support_status == TemporalSupportStatus.NO_SUPPORT


def test_persistence_flagged_pending_review(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001", decision=SuppressionDecision.FLAGGED)

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc)
    assert res.temporal_support_status == TemporalSupportStatus.FLAGGED_PENDING_REVIEW


# ==============================================================================
# Group J: Category Authority & Evolution
# ==============================================================================

def test_category_comes_directly_from_m4c(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001", category=ChangeCategory.CONSTRUCTION)

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc)
    assert res.category_evolution.primary_category == ChangeCategory.CONSTRUCTION


def test_category_missing_m4c_is_none(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001")
    disc.classification = None

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc)
    node_o2 = [n for n in res.timeline_nodes if n.observation_id == "obs_02"][0]
    assert node_o2.category_observed is None


def test_category_evolution_unknown_to_construction(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    obs3 = make_observation("obs_03", "2026-02-01T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2, obs3])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    p1 = make_pairwise_evidence("pair_01", region_id="reg_0001", category=ChangeCategory.UNKNOWN)
    p2 = make_pairwise_evidence("pair_02", region_id="reg_0001", category=ChangeCategory.CONSTRUCTION)

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, p1, [p2])
    assert res.category_evolution.is_evolution_valid is True
    assert res.category_evolution.is_conflicted is False


def test_category_evolution_clearance_to_construction(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    obs3 = make_observation("obs_03", "2026-02-01T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2, obs3])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    p1 = make_pairwise_evidence("pair_01", region_id="reg_0001", category=ChangeCategory.CLEARANCE)
    p2 = make_pairwise_evidence("pair_02", region_id="reg_0001", category=ChangeCategory.CONSTRUCTION)

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, p1, [p2])
    assert res.category_evolution.is_evolution_valid is True
    assert res.category_evolution.is_conflicted is False


def test_category_evolution_conflicting_categories(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    obs3 = make_observation("obs_03", "2026-02-01T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2, obs3])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    p1 = make_pairwise_evidence("pair_01", region_id="reg_0001", category=ChangeCategory.WATER_EXTENT_CHANGE)
    p2 = make_pairwise_evidence("pair_02", region_id="reg_0001", category=ChangeCategory.ROAD_DEVELOPMENT)

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, p1, [p2])
    assert res.category_evolution.is_conflicted is True
    assert res.temporal_support_status == TemporalSupportStatus.TEMPORALLY_AMBIGUOUS


# ==============================================================================
# Group K: Cross-Sensor Handling
# ==============================================================================

def test_cross_sensor_same_sensor_high_confidence(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00", sensor="Sentinel-2A MSI")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00", sensor="Sentinel-2A MSI")
    obs3 = make_observation("obs_03", "2026-02-01T00:00:00", sensor="Sentinel-2A MSI")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2, obs3])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    p1 = make_pairwise_evidence("pair_01", region_id="reg_0001")
    p2 = make_pairwise_evidence("pair_02", region_id="reg_0001")

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, p1, [p2])
    assert res.confidence_tier == TemporalConfidenceTier.HIGH


def test_cross_sensor_different_sensor_capped_medium(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00", sensor="Sentinel-2A MSI")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00", sensor="Sentinel-2A MSI")
    obs3 = make_observation("obs_03", "2026-02-01T00:00:00", sensor="Landsat-8 OLI")  # Cross-sensor!
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2, obs3])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    p1 = make_pairwise_evidence("pair_01", region_id="reg_0001")
    p2 = make_pairwise_evidence("pair_02", region_id="reg_0001")

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, p1, [p2])
    assert res.confidence_tier == TemporalConfidenceTier.MEDIUM


def test_cross_sensor_limitation_notice_recorded(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00", sensor="Sentinel-2A MSI")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00", sensor="Landsat-8 OLI")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    p1 = make_pairwise_evidence("pair_01", region_id="reg_0001")

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, p1)
    node_o2 = [n for n in res.timeline_nodes if n.observation_id == "obs_02"][0]
    assert any("cross-sensor" in lim for lim in node_o2.data_limitations)


# ==============================================================================
# Group L: Provenance & Deterministic Serialization
# ==============================================================================

def test_provenance_real_scene_id_not_pair_id(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00", scene_id="S2A_MSIL2A_REAL_SCENE_01")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00", scene_id="S2A_MSIL2A_REAL_SCENE_02")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001")

    prov_dir = tmp_path / "prov"
    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=prov_dir)
    res = service.evaluate_temporal_evidence(cand, series, disc)

    prov_file = prov_dir / f"{res.provenance_id}.json"
    assert prov_file.exists()
    prov_data = json.loads(prov_file.read_text(encoding="utf-8"))
    assert prov_data["source_scene_id"].startswith("S2A_MSIL2A_REAL_SCENE")
    assert not prov_data["source_scene_id"].startswith("pair_")


def test_provenance_complete_parameters_lineage(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001")

    prov_dir = tmp_path / "prov"
    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=prov_dir)
    res = service.evaluate_temporal_evidence(cand, series, disc)

    prov_file = prov_dir / f"{res.provenance_id}.json"
    prov_data = json.loads(prov_file.read_text(encoding="utf-8"))
    params = prov_data["parameters"]
    assert "discovery_scene_pair_id" in params
    assert "evaluated_scene_pair_ids" in params
    assert "upstream_suppression_ids" in params


def test_provenance_deterministic_hash_repeatability(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001")

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res1 = service.evaluate_temporal_evidence(cand, series, disc)
    res2 = service.evaluate_temporal_evidence(cand, series, disc)
    assert res1.temporal_evidence_id == res2.temporal_evidence_id
    assert res1.provenance_id == res2.provenance_id


def test_provenance_deterministic_created_at(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001")

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc)
    assert res.created_at == obs2.acquisition_time


def test_provenance_file_persisted(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001")

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc)
    loaded = service.get_temporal_evidence(res.temporal_evidence_id)
    assert loaded is not None
    assert loaded.temporal_evidence_id == res.temporal_evidence_id


# ==============================================================================
# Group M: REST API Endpoints
# ==============================================================================

def test_api_health_check():
    client = TestClient(app)
    resp = client.get("/api/v1/temporal-evidence/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "ASTRA Temporal Evidence Reasoner" in data["service"]


def test_api_evaluate_valid_request(tmp_path):
    client = TestClient(app)
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001")

    payload = {
        "candidate_ref": cand.model_dump(),
        "series": series.model_dump(mode="json"),
        "discovery_pair_evidence": disc.model_dump(mode="json"),
        "pairwise_evidence": [],
    }
    resp = client.post("/api/v1/temporal-evidence/evaluate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["temporal_evidence_id"].startswith("tem_")


def test_api_evaluate_unknown_config_rejected():
    client = TestClient(app)
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001")

    payload = {
        "candidate_ref": cand.model_dump(),
        "discovery_pair_evidence": disc.model_dump(mode="json"),
        "config_overrides": {"misspelled_threshold": 0.5},
    }
    resp = client.post("/api/v1/temporal-evidence/evaluate", json=payload)
    assert resp.status_code == 422


def test_api_evaluate_discovery_mismatch_rejected():
    client = TestClient(app)
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_DIFFERENT", region_id="reg_0001")

    payload = {
        "candidate_ref": cand.model_dump(),
        "series": series.model_dump(mode="json"),
        "discovery_pair_evidence": disc.model_dump(mode="json"),
    }
    resp = client.post("/api/v1/temporal-evidence/evaluate", json=payload)
    assert resp.status_code == 400


def test_api_get_result_by_id(tmp_path):
    client = TestClient(app)
    resp = client.get("/api/v1/temporal-evidence/tem_nonexistent_id")
    assert resp.status_code == 404


# ==============================================================================
# Group N: CLI Runner
# ==============================================================================

def test_cli_help_flag():
    cmd = [sys.executable, "scripts/evaluate_temporal_evidence.py", "--help"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0
    assert "ASTRA Temporal Evidence Reasoner Engine" in res.stdout


def test_cli_valid_execution_with_manifest(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001")

    manifest = {
        "candidate_ref": cand.model_dump(),
        "series": series.model_dump(mode="json"),
        "discovery_pair_evidence": disc.model_dump(mode="json"),
        "pairwise_evidence": [],
    }
    m_file = tmp_path / "manifest.json"
    m_file.write_text(json.dumps(manifest), encoding="utf-8")

    cmd = [
        sys.executable,
        "scripts/evaluate_temporal_evidence.py",
        "--manifest", str(m_file),
        "--output-dir", str(tmp_path / "cli_out"),
        "--provenance-dir", str(tmp_path / "cli_prov"),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0
    assert "TemporalEvidenceResult persisted" in res.stdout


def test_cli_missing_required_args_fails():
    cmd = [sys.executable, "scripts/evaluate_temporal_evidence.py"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode != 0


# ==============================================================================
# Group O: Adversarial Test Scenarios (14 Scenarios)
# ==============================================================================

def test_adv_01_bright_construction_resembling_cloud(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    obs3 = make_observation("obs_03", "2026-02-01T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2, obs3])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    # Concrete roof retained in M4D
    p1 = make_pairwise_evidence("pair_01", region_id="reg_0001", decision=SuppressionDecision.RETAINED, category=ChangeCategory.CONSTRUCTION)
    p2 = make_pairwise_evidence("pair_02", region_id="reg_0001", decision=SuppressionDecision.RETAINED, category=ChangeCategory.CONSTRUCTION)

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, p1, [p2])
    assert res.temporal_support_status == TemporalSupportStatus.STRONG_TEMPORAL_SUPPORT
    assert res.category_evolution.primary_category == ChangeCategory.CONSTRUCTION


def test_adv_02_road_like_change_near_registration_fringe(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    # Edge-shear false alarm suppressed by M4D
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001", decision=SuppressionDecision.SUPPRESSED, category=ChangeCategory.ROAD_DEVELOPMENT)

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc)
    assert res.temporal_support_status == TemporalSupportStatus.NO_SUPPORT
    assert res.metrics.supporting_nodes_count == 0


def test_adv_03_water_extent_under_illumination(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    obs3 = make_observation("obs_03", "2026-02-01T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2, obs3])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    # Water extent change retained despite illumination shift
    p1 = make_pairwise_evidence("pair_01", region_id="reg_0001", decision=SuppressionDecision.RETAINED, category=ChangeCategory.WATER_EXTENT_CHANGE)
    p2 = make_pairwise_evidence("pair_02", region_id="reg_0001", decision=SuppressionDecision.RETAINED, category=ChangeCategory.WATER_EXTENT_CHANGE)

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, p1, [p2])
    assert res.temporal_support_status == TemporalSupportStatus.STRONG_TEMPORAL_SUPPORT
    assert res.category_evolution.primary_category == ChangeCategory.WATER_EXTENT_CHANGE


def test_adv_04_clearance_seasonal_vegetation(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    # Clearance confirmed by high contrast
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001", decision=SuppressionDecision.RETAINED, category=ChangeCategory.CLEARANCE)

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, disc)
    assert res.category_evolution.primary_category == ChangeCategory.CLEARANCE


def test_adv_05_early_flagged_later_retained(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    obs3 = make_observation("obs_03", "2026-02-01T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2, obs3])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    # p1 FLAGGED, p2 RETAINED
    p1 = make_pairwise_evidence("pair_01", region_id="reg_0001", decision=SuppressionDecision.FLAGGED)
    p2 = make_pairwise_evidence("pair_02", region_id="reg_0001", decision=SuppressionDecision.RETAINED)

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, p1, [p2])
    assert res.onset_estimate.earliest_support_observation_id == "obs_03"
    assert res.onset_estimate.provisional_flagged_observation_id == "obs_02"


def test_adv_06_unknown_to_construction_valid(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    obs3 = make_observation("obs_03", "2026-02-01T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2, obs3])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    p1 = make_pairwise_evidence("pair_01", region_id="reg_0001", category=ChangeCategory.UNKNOWN)
    p2 = make_pairwise_evidence("pair_02", region_id="reg_0001", category=ChangeCategory.CONSTRUCTION)

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, p1, [p2])
    assert res.category_evolution.is_evolution_valid is True


def test_adv_07_clearance_to_construction_valid(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    obs3 = make_observation("obs_03", "2026-02-01T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2, obs3])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    p1 = make_pairwise_evidence("pair_01", region_id="reg_0001", category=ChangeCategory.CLEARANCE)
    p2 = make_pairwise_evidence("pair_02", region_id="reg_0001", category=ChangeCategory.CONSTRUCTION)

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, p1, [p2])
    assert res.category_evolution.is_evolution_valid is True


def test_adv_08_conflicting_incompatible_categories(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    obs3 = make_observation("obs_03", "2026-02-01T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2, obs3])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    p1 = make_pairwise_evidence("pair_01", region_id="reg_0001", category=ChangeCategory.WATER_EXTENT_CHANGE)
    p2 = make_pairwise_evidence("pair_02", region_id="reg_0001", category=ChangeCategory.CONSTRUCTION)

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, p1, [p2])
    assert res.category_evolution.is_conflicted is True
    assert res.temporal_support_status == TemporalSupportStatus.TEMPORALLY_AMBIGUOUS


def test_adv_09_candidate_region_ids_reused_across_parents(tmp_path):
    # Two candidates both have local region_id = "reg_0001", but different CDR parents
    cand1 = CandidateRegionRef(change_detection_result_id="cdr_parent_A", scene_pair_id="pair_A01", region_id="reg_0001")
    cand2 = CandidateRegionRef(change_detection_result_id="cdr_parent_B", scene_pair_id="pair_B01", region_id="reg_0001")
    assert cand1.canonical_id != cand2.canonical_id


def test_adv_10_different_grids_same_target_id():
    corr = evaluate_spatial_correspondence(
        candidate_bbox_wgs84=GeoBoundingBox(min_lon=77.1, min_lat=12.1, max_lon=77.2, max_lat=12.2),
        candidate_centroid_wgs84=[77.15, 12.15],
        candidate_bbox_px=[0, 0, 10, 10],
        candidate_centroid_px=[5.0, 5.0],
        candidate_crs="EPSG:32643",
        target_bbox_wgs84=GeoBoundingBox(min_lon=77.1, min_lat=12.1, max_lon=77.2, max_lat=12.2),
        target_centroid_wgs84=[77.15, 12.15],
        target_bbox_px=[0, 0, 10, 10],
        target_centroid_px=[5.0, 5.0],
        target_crs="EPSG:32644",  # Different CRS
    )
    assert corr.centroid_distance_px is None


def test_adv_11_cross_resolution_confidence_cap(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00", sensor="Sentinel-2A MSI")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00", sensor="Sentinel-2A MSI")
    obs3 = make_observation("obs_03", "2026-02-01T00:00:00", sensor="Landsat-8 OLI")  # 30m
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2, obs3])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    p1 = make_pairwise_evidence("pair_01", region_id="reg_0001")
    p2 = make_pairwise_evidence("pair_02", region_id="reg_0001")

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res = service.evaluate_temporal_evidence(cand, series, p1, [p2])
    assert res.confidence_tier == TemporalConfidenceTier.MEDIUM


def test_adv_12_missing_georeferencing_graceful():
    corr = evaluate_spatial_correspondence(
        candidate_bbox_wgs84=None,
        candidate_centroid_wgs84=None,
        candidate_bbox_px=None,
        candidate_centroid_px=None,
        candidate_crs="EPSG:32643",
        target_bbox_wgs84=None,
        target_centroid_wgs84=None,
        target_bbox_px=None,
        target_centroid_px=None,
        target_crs="EPSG:32643",
    )
    assert corr.status == SpatialCorrespondenceStatus.INSUFFICIENT_METADATA


def test_adv_13_deterministic_serialization(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")
    disc = make_pairwise_evidence("pair_01", region_id="reg_0001")

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res1 = service.evaluate_temporal_evidence(cand, series, disc)
    res2 = service.evaluate_temporal_evidence(cand, series, disc)
    assert res1.model_dump_json() == res2.model_dump_json()


def test_adv_14_changed_upstream_hash_changes_identity(tmp_path):
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-15T00:00:00")
    series = TemporalSeries(series_id="series_01", target_id="tile_01", bounds_wgs84=obs1.bounds_wgs84, observations=[obs1, obs2])
    cand = CandidateRegionRef(change_detection_result_id="cdr_pair_01", scene_pair_id="pair_01", region_id="reg_0001")

    p1_a = make_pairwise_evidence("pair_01", region_id="reg_0001")
    p1_a.evidence.source_hashes = {"pair_hash": "sha_A"}

    p1_b = make_pairwise_evidence("pair_01", region_id="reg_0001")
    p1_b.evidence.source_hashes = {"pair_hash": "sha_B"}

    service = TemporalEvidenceService(output_dir=tmp_path / "out", provenance_dir=tmp_path / "prov")
    res_a = service.evaluate_temporal_evidence(cand, series, p1_a)
    res_b = service.evaluate_temporal_evidence(cand, series, p1_b)
    assert res_a.temporal_evidence_id != res_b.temporal_evidence_id
