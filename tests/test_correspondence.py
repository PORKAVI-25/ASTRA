"""Tests for Phase M4F-A/B Candidate-Region Temporal Correspondence & Integration Fixes.

Verifies:
1. Single subsequent region matching candidate.
2. Candidate is reg_0001 in discovery but reg_0003 later.
3. Multiple later regions where candidate is NOT regions[0].
4. Unrelated region with larger sequence position must not be selected merely by ID.
5. No spatial overlap -> explicit no-match/insufficient outcome.
6. Two plausible regions -> deterministic ambiguous outcome unless one clearly valid.
7. Exact/strong bbox overlap.
8. Partial overlap.
9. WGS84 geographic coordinates requiring metric-aware comparison.
10. Correspondence remains deterministic across repeated runs.
11. Original discovery candidate identity remains unchanged.
12. Later region IDs remain their actual local M4B region IDs.
13. M4E receives the resolved correspondence rather than defaulting to regions[0].
14. No classification logic is introduced in correspondence adapter.
15. No raster access or raster imports in orchestrator correspondence adapter.
"""

import ast
from datetime import datetime, timezone
import math
from typing import List, Optional
import pytest

from geospatial.contracts import GeoBoundingBox
from backend.ml.change.types import TemporalObservation, TemporalSeries
from backend.ml.change_classification.types import (
    ChangeCategory,
    ChangeClassificationResult,
    ChangeEvidence,
    ConfidenceTier,
    EvidenceConfig,
    RegionClassification,
    TemporalEvidence,
)
from backend.ml.change_detection.types import (
    ChangeDetectionConfig,
    ChangeDetectionResult,
    ChangeMetrics,
    ChangeRegion,
)
from backend.ml.change_suppression.types import (
    RegionSuppression,
    SuppressionConfig,
    SuppressionDecision,
    SuppressionMetrics,
    SuppressionResult,
)
from backend.ml.temporal_evidence.service import TemporalEvidenceService
from backend.ml.temporal_evidence.types import (
    CandidateRegionRef,
    CorrespondenceRelationship,
    PairwiseTemporalEvidenceInput,
    SpatialCorrespondenceStatus,
    TemporalEvidenceConfig,
    TemporalNodeStatus,
)
from backend.orchestrator.correspondence import (
    CandidateCorrespondenceResult,
    resolve_candidate_correspondence,
)


def make_test_region(
    region_id: str,
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    mean_score: float = 0.80,
) -> ChangeRegion:
    """Creates a synthetic ChangeRegion with explicit WGS84 bounding box and centroid."""
    return ChangeRegion(
        region_id=region_id,
        bbox_px=(10, 10, 30, 30),
        area_px=100,
        pixel_count=100,
        area_m2=1000.0,
        centroid_px=(20.0, 20.0),
        bbox_wgs84=GeoBoundingBox(
            min_lon=min_lon,
            min_lat=min_lat,
            max_lon=max_lon,
            max_lat=max_lat,
        ),
        centroid_wgs84=[(min_lon + max_lon) / 2.0, (min_lat + max_lat) / 2.0],
        mean_change_score=mean_score,
        max_change_score=min(1.0, mean_score + 0.10),
    )


def make_test_cdr(pair_id: str, regions: List[ChangeRegion]) -> ChangeDetectionResult:
    """Creates a synthetic ChangeDetectionResult containing given regions."""
    clean_pair_id = pair_id if len(pair_id) >= 5 else f"pair_{pair_id}"
    cdr_id = f"cdr_{clean_pair_id}"
    return ChangeDetectionResult(
        result_id=cdr_id,
        scene_pair_id=clean_pair_id,
        algorithm_id="pixel_diff",
        algorithm_version="1.0.0",
        config=ChangeDetectionConfig(),
        metrics=ChangeMetrics(
            total_pixels=1000,
            valid_pixels=1000,
            invalid_pixels=0,
            changed_pixels=len(regions) * 100,
            changed_fraction=0.10,
            number_of_regions=len(regions),
            changed_area_px=len(regions) * 100,
            threshold_used=0.20,
            threshold_method="otsu",
        ),
        regions=regions,
        provenance_id=f"prov_{cdr_id}",
    )


def make_test_suppression(
    pair_id: str,
    cdr_id: str,
    regions: List[RegionSuppression],
) -> SuppressionResult:
    """Creates a valid synthetic SuppressionResult."""
    retained = sum(1 for r in regions if r.decision == SuppressionDecision.RETAINED)
    flagged = sum(1 for r in regions if r.decision == SuppressionDecision.FLAGGED)
    suppressed = sum(1 for r in regions if r.decision == SuppressionDecision.SUPPRESSED)
    insufficient = sum(1 for r in regions if r.decision == SuppressionDecision.INSUFFICIENT_EVIDENCE)
    total = len(regions)
    sup_rate = suppressed / total if total > 0 else 0.0

    return SuppressionResult(
        suppression_id=f"sup_{pair_id}",
        scene_pair_id=pair_id,
        change_detection_result_id=cdr_id,
        evidence_id=f"evi_{pair_id}",
        classification_id=f"cls_{pair_id}",
        suppressor_id="test_sup",
        suppressor_version="1.0.0",
        config=SuppressionConfig(),
        metrics=SuppressionMetrics(
            total_input_regions=total,
            retained_count=retained,
            flagged_count=flagged,
            suppressed_count=suppressed,
            insufficient_evidence_count=insufficient,
            suppression_rate=sup_rate,
            total_area_px=total * 100,
            retained_area_px=retained * 100,
            flagged_area_px=flagged * 100,
            suppressed_area_px=suppressed * 100,
        ),
        regions=regions,
        filtered_change_mask_path="dummy.tif",
        provenance_id=f"prov_sup_{pair_id}",
    )


# ==============================================================================
# 1. Single subsequent region matching candidate
# ==============================================================================
def test_01_single_subsequent_region_matching():
    ref = make_test_region("reg_0001", 77.5900, 12.9700, 77.5950, 12.9750)
    target_cdr = make_test_cdr("pair_0002", [
        make_test_region("reg_0001", 77.5900, 12.9700, 77.5950, 12.9750),
    ])

    result = resolve_candidate_correspondence(
        reference_region=ref,
        target_cdr=target_cdr,
        target_pair_id="pair_0002",
    )

    assert result.status == SpatialCorrespondenceStatus.GEOREFERENCED_BBOX
    assert result.relationship == CorrespondenceRelationship.MATCHED
    assert result.matched_region_id == "reg_0001"
    assert result.metric_iou >= 0.99
    assert result.reference_candidate_id == "reg_0001"
    assert result.spatial_correspondence.is_spatially_compatible is True


# ==============================================================================
# 2. Candidate is reg_0001 in discovery but reg_0003 later
# ==============================================================================
def test_02_candidate_reg0001_in_discovery_but_reg0003_later():
    ref = make_test_region("reg_0001", 77.5900, 12.9700, 77.5950, 12.9750)
    # Target CDR has an unrelated reg_0001 at far away coordinates,
    # reg_0002 at different coordinates, and reg_0003 at exact candidate coordinates
    target_cdr = make_test_cdr("pair_0002", [
        make_test_region("reg_0001", 78.5000, 13.5000, 78.5050, 13.5050),
        make_test_region("reg_0002", 78.6000, 13.6000, 78.6050, 13.6050),
        make_test_region("reg_0003", 77.5900, 12.9700, 77.5950, 12.9750),
    ])

    result = resolve_candidate_correspondence(
        reference_region=ref,
        target_cdr=target_cdr,
        target_pair_id="pair_0002",
    )

    # Must match reg_0003 by spatial overlap, NEVER reg_0001 by ID!
    assert result.matched_region_id == "reg_0003"
    assert result.relationship == CorrespondenceRelationship.MATCHED
    assert result.reference_candidate_id == "reg_0001"
    assert result.metric_iou >= 0.99
    assert result.candidate_scores["reg_0001"] == 0.0
    assert result.candidate_scores["reg_0003"] >= 0.99


# ==============================================================================
# 3. Multiple later regions where candidate is NOT regions[0]
# ==============================================================================
def test_03_multiple_later_regions_candidate_not_regions0():
    ref = make_test_region("reg_cand", 77.5900, 12.9700, 77.5950, 12.9750)
    target_cdr = make_test_cdr("pair_0002", [
        make_test_region("reg_0001", 76.1000, 11.1000, 76.1050, 11.1050),  # index 0
        make_test_region("reg_0002", 76.2000, 11.2000, 76.2050, 11.2050),  # index 1
        make_test_region("reg_0003", 77.5900, 12.9700, 77.5950, 12.9750),  # index 2: MATCH
        make_test_region("reg_0004", 76.4000, 11.4000, 76.4050, 11.4050),  # index 3
    ])

    result = resolve_candidate_correspondence(
        reference_region=ref,
        target_cdr=target_cdr,
        target_pair_id="pair_0002",
    )

    assert result.matched_region_id == "reg_0003"
    assert result.matched_region_id != target_cdr.regions[0].region_id
    assert result.relationship == CorrespondenceRelationship.MATCHED


# ==============================================================================
# 4. Unrelated region with larger sequence position not selected merely by ID
# ==============================================================================
def test_04_unrelated_region_not_selected_by_id():
    ref = make_test_region("reg_0005", 77.5900, 12.9700, 77.5950, 12.9750)
    # Target CDR has reg_0005 elsewhere, but reg_0002 is at candidate position
    target_cdr = make_test_cdr("pair_0002", [
        make_test_region("reg_0002", 77.5900, 12.9700, 77.5950, 12.9750),
        make_test_region("reg_0005", 79.0000, 14.0000, 79.0050, 14.0050),
    ])

    result = resolve_candidate_correspondence(
        reference_region=ref,
        target_cdr=target_cdr,
        target_pair_id="pair_0002",
    )

    assert result.matched_region_id == "reg_0002"
    assert result.matched_region_id != "reg_0005"
    assert result.relationship == CorrespondenceRelationship.MATCHED


# ==============================================================================
# 5. No spatial overlap -> explicit no-match / insufficient outcome
# ==============================================================================
def test_05_no_spatial_overlap_explicit_outcome():
    ref = make_test_region("reg_0001", 77.5900, 12.9700, 77.5950, 12.9750)
    target_cdr = make_test_cdr("pair_0002", [
        make_test_region("reg_0001", 80.0000, 15.0000, 80.0050, 15.0050),
        make_test_region("reg_0002", 80.1000, 15.1000, 80.1050, 15.1050),
    ])

    result = resolve_candidate_correspondence(
        reference_region=ref,
        target_cdr=target_cdr,
        target_pair_id="pair_0002",
    )

    assert result.status == SpatialCorrespondenceStatus.DISJOINT
    assert result.relationship == CorrespondenceRelationship.NONE
    assert result.matched_region_id is None
    assert result.matched_region is None
    assert result.metric_iou == 0.0
    assert result.spatial_correspondence.is_spatially_compatible is False


def test_05b_empty_regions_explicit_outcome():
    ref = make_test_region("reg_0001", 77.5900, 12.9700, 77.5950, 12.9750)
    target_cdr = make_test_cdr("pair_0002", [])

    result = resolve_candidate_correspondence(
        reference_region=ref,
        target_cdr=target_cdr,
        target_pair_id="pair_0002",
    )

    assert result.status == SpatialCorrespondenceStatus.DISJOINT
    assert result.relationship == CorrespondenceRelationship.NONE
    assert result.matched_region_id is None


# ==============================================================================
# 6. Two plausible regions -> deterministic ambiguous outcome vs tie-break
# ==============================================================================
def test_06_two_plausible_regions_ambiguous_outcome():
    ref = make_test_region("reg_ref", 77.5900, 12.9700, 77.5950, 12.9750)
    # Two regions overlapping candidate with almost identical overlap
    # Target A overlaps 60%
    target_a = make_test_region("reg_A", 77.5900, 12.9700, 77.5950, 12.9740)
    # Target B overlaps 58%
    target_b = make_test_region("reg_B", 77.5900, 12.9710, 77.5950, 12.9750)

    target_cdr = make_test_cdr("pair_0002", [target_a, target_b])

    result = resolve_candidate_correspondence(
        reference_region=ref,
        target_cdr=target_cdr,
        target_pair_id="pair_0002",
        ambiguity_margin=0.10,  # Strict margin requiring >= 10% separation
    )

    # IoUs are very close (< 0.10 margin) -> must be AMBIGUOUS
    assert result.relationship == CorrespondenceRelationship.AMBIGUOUS
    assert result.matched_region_id is None
    assert result.spatial_correspondence.is_spatially_compatible is False
    assert any("Ambiguous spatial correspondence" in note for note in result.resolution_notes)


def test_06b_two_plausible_regions_clear_margin_tiebreak():
    ref = make_test_region("reg_ref", 77.5900, 12.9700, 77.5950, 12.9750)
    # Target A has 90% overlap
    target_a = make_test_region("reg_A", 77.5900, 12.9700, 77.5950, 12.9748)
    # Target B has only 35% overlap (meets 30% threshold but far below Target A)
    target_b = make_test_region("reg_B", 77.5900, 12.9730, 77.5950, 12.9750)

    target_cdr = make_test_cdr("pair_0002", [target_a, target_b])

    result = resolve_candidate_correspondence(
        reference_region=ref,
        target_cdr=target_cdr,
        target_pair_id="pair_0002",
        ambiguity_margin=0.05,
    )

    # Target A clearly beats Target B by margin >= 0.05
    assert result.relationship == CorrespondenceRelationship.MATCHED
    assert result.matched_region_id == "reg_A"
    assert any("Deterministic tie-break" in note for note in result.resolution_notes)


# ==============================================================================
# 7. Exact/strong bbox overlap
# ==============================================================================
def test_07_exact_strong_bbox_overlap():
    ref = make_test_region("reg_ref", 77.5900, 12.9700, 77.5950, 12.9750)
    target_reg = make_test_region("reg_target", 77.5900, 12.9700, 77.5950, 12.9750)
    target_cdr = make_test_cdr("pair_0002", [target_reg])

    result = resolve_candidate_correspondence(ref, target_cdr, "pair_0002")
    assert result.relationship == CorrespondenceRelationship.MATCHED
    assert result.metric_iou == 1.0


# ==============================================================================
# 8. Partial overlap
# ==============================================================================
def test_08_partial_overlap():
    ref = make_test_region("reg_ref", 77.5900, 12.9700, 77.5950, 12.9750)
    # Half overlap in longitude
    target_reg = make_test_region("reg_target", 77.5925, 12.9700, 77.5975, 12.9750)
    target_cdr = make_test_cdr("pair_0002", [target_reg])

    result = resolve_candidate_correspondence(ref, target_cdr, "pair_0002")
    assert result.relationship == CorrespondenceRelationship.MATCHED
    assert 0.30 <= result.metric_iou <= 0.40


# ==============================================================================
# 9. WGS84 geographic coordinates requiring metric-aware comparison
# ==============================================================================
def test_09_wgs84_metric_aware_comparison():
    # At 60 deg N, cos(lat) = 0.5; 1 deg lon is half the distance in meters of 1 deg lat
    # Box A: 0.01 deg lon x 0.005 deg lat at lat 60
    # In meters: lon ~= 0.01 * 111320 * 0.5 = 556.6m; lat ~= 0.005 * 110540 = 552.7m
    # This forms a nearly square box in metric projection
    ref = make_test_region("reg_arctic", 10.0000, 60.0000, 10.0100, 60.0050)
    target_reg = make_test_region("reg_target", 10.0000, 60.0000, 10.0100, 60.0050)
    target_cdr = make_test_cdr("pair_0002", [target_reg])

    result = resolve_candidate_correspondence(ref, target_cdr, "pair_0002")
    assert result.relationship == CorrespondenceRelationship.MATCHED
    assert result.metric_iou == 1.0


# ==============================================================================
# 10. Correspondence remains deterministic across repeated runs
# ==============================================================================
def test_10_deterministic_repeatability():
    ref = make_test_region("reg_ref", 77.5900, 12.9700, 77.5950, 12.9750)
    target_cdr = make_test_cdr("pair_0002", [
        make_test_region("reg_0001", 77.5800, 12.9600, 77.5850, 12.9650),
        make_test_region("reg_0002", 77.5900, 12.9700, 77.5950, 12.9750),
        make_test_region("reg_0003", 77.6000, 12.9800, 77.6050, 12.9850),
    ])

    results = [
        resolve_candidate_correspondence(ref, target_cdr, "pair_0002")
        for _ in range(10)
    ]

    first_dict = results[0].model_dump()
    for res in results[1:]:
        assert res.model_dump() == first_dict
        assert res.matched_region_id == "reg_0002"


# ==============================================================================
# 11. Original discovery candidate identity remains unchanged
# ==============================================================================
def test_11_original_discovery_candidate_identity_unchanged():
    ref = make_test_region("reg_discovery_candidate_01", 77.5900, 12.9700, 77.5950, 12.9750)
    orig_id = ref.region_id
    orig_bbox = ref.bbox_wgs84.model_dump()

    target_cdr = make_test_cdr("pair_0002", [
        make_test_region("reg_local_99", 77.5900, 12.9700, 77.5950, 12.9750),
    ])

    res = resolve_candidate_correspondence(ref, target_cdr, "pair_0002")

    assert res.reference_candidate_id == "reg_discovery_candidate_01"
    assert ref.region_id == orig_id
    assert ref.bbox_wgs84.model_dump() == orig_bbox


# ==============================================================================
# 12. Later region IDs remain their actual local M4B region IDs
# ==============================================================================
def test_12_later_region_ids_remain_actual_local_ids():
    ref = make_test_region("reg_0001", 77.5900, 12.9700, 77.5950, 12.9750)
    target_cdr = make_test_cdr("pair_0002", [
        make_test_region("reg_epoch2_0042", 77.5900, 12.9700, 77.5950, 12.9750),
    ])

    res = resolve_candidate_correspondence(ref, target_cdr, "pair_0002")
    assert res.matched_region_id == "reg_epoch2_0042"
    assert res.matched_region.region_id == "reg_epoch2_0042"


# ==============================================================================
# 13. M4E receives resolved correspondence rather than defaulting to regions[0]
# ==============================================================================
def test_13_m4e_consumes_resolved_correspondence(tmp_path):
    """Verifies that M4E evaluates the spatially resolved region and never falls back to regions[0]."""
    service = TemporalEvidenceService(output_dir=tmp_path / "tem", provenance_dir=tmp_path / "prov")

    t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2026, 2, 1, tzinfo=timezone.utc)
    t3 = datetime(2026, 3, 1, tzinfo=timezone.utc)

    bbox_candidate = GeoBoundingBox(min_lon=77.5900, min_lat=12.9700, max_lon=77.5950, max_lat=12.9750)
    bbox_other = GeoBoundingBox(min_lon=76.0000, min_lat=11.0000, max_lon=76.0050, max_lat=11.0050)

    obs1 = TemporalObservation(
        observation_id="obs_01",
        scene_id="S2A_REAL_SCENE_01",
        acquisition_time=t1,
        sensor="MSI",
        platform="Sentinel-2A",
        crs="EPSG:4326",
        source_hash="sha256_mock_obs_01",
        bounds_wgs84=GeoBoundingBox(min_lon=77.0, min_lat=12.0, max_lon=78.0, max_lat=13.0),
        metadata={"cloud_fraction": 0.05, "valid_pixel_ratio": 0.95},
    )
    obs2 = TemporalObservation(
        observation_id="obs_02",
        scene_id="S2A_REAL_SCENE_02",
        acquisition_time=t2,
        sensor="MSI",
        platform="Sentinel-2A",
        crs="EPSG:4326",
        source_hash="sha256_mock_obs_02",
        bounds_wgs84=GeoBoundingBox(min_lon=77.0, min_lat=12.0, max_lon=78.0, max_lat=13.0),
    )
    obs3 = TemporalObservation(
        observation_id="obs_03",
        scene_id="S2A_REAL_SCENE_03",
        acquisition_time=t3,
        sensor="MSI",
        platform="Sentinel-2A",
        crs="EPSG:4326",
        source_hash="sha256_mock_obs_03",
        bounds_wgs84=GeoBoundingBox(min_lon=77.0, min_lat=12.0, max_lon=78.0, max_lat=13.0),
    )

    series = TemporalSeries(
        series_id="ser_test_corr_01",
        target_id="target_01",
        bounds_wgs84=obs1.bounds_wgs84,
        observations=[obs1, obs2, obs3],
    )

    # Discovery pair: obs1 -> obs2, candidate is reg_0001
    disc_cdr = make_test_cdr("pair_obs_01__obs_02", [
        make_test_region("reg_0001", 77.5900, 12.9700, 77.5950, 12.9750, mean_score=0.85),
    ])
    disc_sup = make_test_suppression(
        pair_id="pair_obs_01__obs_02",
        cdr_id=disc_cdr.result_id,
        regions=[RegionSuppression(
            region_id="reg_0001",
            decision=SuppressionDecision.RETAINED,
            artifact_risk_score=0.1,
            artifact_risk_interpretation="Low risk",
            decision_basis="TEST",
            original_category="construction",
            retained_category="construction",
            confidence_tier_adjusted="high",
        )],
    )
    disc_input = PairwiseTemporalEvidenceInput(
        scene_pair_id="pair_obs_01__obs_02",
        change_detection_result_id=disc_cdr.result_id,
        evidence_id="evi_disc",
        classification_id="cls_disc",
        suppression_id=disc_sup.suppression_id,
        suppression_result=disc_sup,
        change_detection_result=disc_cdr,
        matched_region_id="reg_0001",
    )

    # Subsequent pair: obs2 -> obs3
    # Contains:
    # regions[0]: reg_0001 (unrelated artifact elsewhere, SUPPRESSED)
    # regions[1]: reg_0003 (matching candidate region, RETAINED, score 0.90)
    sub_cdr = make_test_cdr("pair_obs_02__obs_03", [
        make_test_region("reg_0001", 76.0000, 11.0000, 76.0050, 11.0050, mean_score=0.10),
        make_test_region("reg_0003", 77.5900, 12.9700, 77.5950, 12.9750, mean_score=0.90),
    ])
    sub_sup = make_test_suppression(
        pair_id="pair_obs_02__obs_03",
        cdr_id=sub_cdr.result_id,
        regions=[
            RegionSuppression(
                region_id="reg_0001",
                decision=SuppressionDecision.SUPPRESSED,
                artifact_risk_score=0.9,
                artifact_risk_interpretation="High risk",
                decision_basis="TEST",
                original_category="artifact",
                retained_category="suppressed",
                confidence_tier_adjusted="low",
            ),
            RegionSuppression(
                region_id="reg_0003",
                decision=SuppressionDecision.RETAINED,
                artifact_risk_score=0.05,
                artifact_risk_interpretation="Low risk",
                decision_basis="TEST",
                original_category="construction",
                retained_category="construction",
                confidence_tier_adjusted="high",
            ),
        ],
    )

    # Spatially resolve candidate correspondence for pair 2
    corr_res = resolve_candidate_correspondence(
        reference_region=disc_cdr.regions[0],
        target_cdr=sub_cdr,
        target_pair_id="pair_obs_02__obs_03",
    )
    assert corr_res.matched_region_id == "reg_0003"

    sub_input = PairwiseTemporalEvidenceInput(
        scene_pair_id="pair_obs_02__obs_03",
        change_detection_result_id=sub_cdr.result_id,
        evidence_id="evi_sub",
        classification_id="cls_sub",
        suppression_id=sub_sup.suppression_id,
        suppression_result=sub_sup,
        change_detection_result=sub_cdr,
        matched_region_id=corr_res.matched_region_id,
        spatial_correspondence=corr_res.spatial_correspondence,
    )

    candidate_ref = CandidateRegionRef(
        change_detection_result_id=disc_cdr.result_id,
        scene_pair_id=disc_cdr.scene_pair_id,
        region_id="reg_0001",
    )

    tem_result = service.evaluate_temporal_evidence(
        candidate_ref=candidate_ref,
        series=series,
        discovery_pair_evidence=disc_input,
        pairwise_evidence=[sub_input],
    )

    # Verify node 3 (from sub_pair) received RETAINED support from reg_0003, NOT SUPPRESSED from regions[0]!
    node3 = next(n for n in tem_result.timeline_nodes if n.observation_id == "obs_03")
    assert node3.m4d_decision == SuppressionDecision.RETAINED
    assert node3.node_status == TemporalNodeStatus.PERSISTENT_SUPPORT
    assert node3.heuristic_support_score > 0.5


def test_13b_m4e_absence_outcome_without_regions0_fallback(tmp_path):
    """When subsequent pair has no matching candidate, M4E reports absence/insufficient data without regions[0] fallback."""
    service = TemporalEvidenceService(output_dir=tmp_path / "tem2", provenance_dir=tmp_path / "prov2")

    t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2026, 2, 1, tzinfo=timezone.utc)
    t3 = datetime(2026, 3, 1, tzinfo=timezone.utc)

    obs1 = TemporalObservation(
        observation_id="obs_01",
        scene_id="S2A_01",
        acquisition_time=t1,
        sensor="MSI",
        platform="Sentinel-2A",
        crs="EPSG:4326",
        source_hash="sha256_mock_obs1",
        bounds_wgs84=GeoBoundingBox(min_lon=77.0, min_lat=12.0, max_lon=78.0, max_lat=13.0),
        metadata={"cloud_fraction": 0.05, "valid_pixel_ratio": 0.95},
    )
    obs2 = TemporalObservation(
        observation_id="obs_02",
        scene_id="S2A_02",
        acquisition_time=t2,
        sensor="MSI",
        platform="Sentinel-2A",
        crs="EPSG:4326",
        source_hash="sha256_mock_obs2",
        bounds_wgs84=GeoBoundingBox(min_lon=77.0, min_lat=12.0, max_lon=78.0, max_lat=13.0),
    )
    obs3 = TemporalObservation(
        observation_id="obs_03",
        scene_id="S2A_03",
        acquisition_time=t3,
        sensor="MSI",
        platform="Sentinel-2A",
        crs="EPSG:4326",
        source_hash="sha256_mock_obs3",
        bounds_wgs84=GeoBoundingBox(min_lon=77.0, min_lat=12.0, max_lon=78.0, max_lat=13.0),
    )

    series = TemporalSeries(
        series_id="ser_test_absence",
        target_id="target_01",
        bounds_wgs84=obs1.bounds_wgs84,
        observations=[obs1, obs2, obs3],
    )

    disc_cdr = make_test_cdr("pair_obs_01__obs_02", [
        make_test_region("reg_0001", 77.5900, 12.9700, 77.5950, 12.9750, mean_score=0.85),
    ])
    disc_sup = make_test_suppression(
        pair_id="pair_obs_01__obs_02",
        cdr_id=disc_cdr.result_id,
        regions=[RegionSuppression(
            region_id="reg_0001",
            decision=SuppressionDecision.RETAINED,
            artifact_risk_score=0.1,
            artifact_risk_interpretation="Low",
            decision_basis="T",
            original_category="construction",
            retained_category="construction",
            confidence_tier_adjusted="high",
        )],
    )
    disc_input = PairwiseTemporalEvidenceInput(
        scene_pair_id="pair_obs_01__obs_02",
        change_detection_result_id=disc_cdr.result_id,
        evidence_id="evi_disc",
        classification_id="cls_disc",
        suppression_id=disc_sup.suppression_id,
        suppression_result=disc_sup,
        change_detection_result=disc_cdr,
        matched_region_id="reg_0001",
    )

    # Subsequent pair has unrelated regions elsewhere
    sub_cdr = make_test_cdr("pair_obs_02__obs_03", [
        make_test_region("reg_elsewhere_01", 80.0, 15.0, 80.005, 15.005, mean_score=0.99),
    ])
    corr_res = resolve_candidate_correspondence(
        reference_region=disc_cdr.regions[0],
        target_cdr=sub_cdr,
        target_pair_id="pair_obs_02__obs_03",
    )
    assert corr_res.matched_region_id is None

    sub_input = PairwiseTemporalEvidenceInput(
        scene_pair_id="pair_obs_02__obs_03",
        change_detection_result_id=sub_cdr.result_id,
        evidence_id="evi_sub",
        classification_id="cls_sub",
        suppression_id="sup_sub",
        suppression_result=None,
        change_detection_result=sub_cdr,
        matched_region_id=None,  # No match!
        spatial_correspondence=corr_res.spatial_correspondence,
    )

    candidate_ref = CandidateRegionRef(
        change_detection_result_id=disc_cdr.result_id,
        scene_pair_id=disc_cdr.scene_pair_id,
        region_id="reg_0001",
    )

    tem_result = service.evaluate_temporal_evidence(
        candidate_ref=candidate_ref,
        series=series,
        discovery_pair_evidence=disc_input,
        pairwise_evidence=[sub_input],
    )

    # Must NOT fall back to reg_elsewhere_01
    node3 = next(n for n in tem_result.timeline_nodes if n.observation_id == "obs_03")
    assert node3.node_status == TemporalNodeStatus.INSUFFICIENT_DATA
    assert node3.heuristic_support_score == 0.0
    assert any("No corresponding change region" in r for r in node3.decision_reasons)


# ==============================================================================
# 14. No classification logic introduced in correspondence adapter
# ==============================================================================
def test_14_no_classification_logic_in_correspondence():
    from backend.orchestrator import correspondence
    import inspect

    src = inspect.getsource(correspondence)
    # Check prohibited classification terminology / heuristics
    prohibited_keywords = [
        "ChangeCategory",
        "ConfidenceTier",
        "classify",
        "ClassifierConfig",
        "ndvi",
        "ndwi",
        "spectral",
        "reflectance",
        "brightness_delta",
    ]
    for kw in prohibited_keywords:
        assert kw not in src, f"Prohibited classification keyword '{kw}' found in correspondence module!"


# ==============================================================================
# 15. No raster access or raster imports in correspondence adapter
# ==============================================================================
def test_15_no_raster_imports_or_access_in_correspondence():
    from backend.orchestrator import correspondence
    import inspect

    src = inspect.getsource(correspondence)
    tree = ast.parse(src)

    prohibited_modules = ["rasterio", "PIL", "cv2", "tifffile", "osgeo", "gdal"]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for pm in prohibited_modules:
                    assert pm not in alias.name, f"Prohibited raster import '{alias.name}' in correspondence!"
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                for pm in prohibited_modules:
                    assert pm not in node.module, f"Prohibited raster import from '{node.module}' in correspondence!"
