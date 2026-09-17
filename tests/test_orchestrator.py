"""ASTRA Pipeline Orchestrator Test Suite (Phase M4F).

Verifies:
1. Valid orchestration contract serialization and deserialization
2. Unknown InvestigationRequest field rejection (ConfigDict extra="forbid")
3. Missing series rejected with structured stage failure
4. Missing discovery pair rejected with structured stage failure
5. Discovery pair belonging to another series rejected
6. Invalid candidate region rejected after discovery M4B detection
7. Upstream failure stops pipeline immediately without continuing
8. Lineage contains all executed pair artifact IDs (M4A, M4B, M4C-A, M4C-B, M4D, M4E)
9. M4D decision is preserved across pipeline execution
10. M4E result is preserved in final dossier
11. Deterministic investigation ID starting with inv_ and 16-hex hash
12. Same logical inputs produce identical dossier identity
13. Changed upstream hash changes dossier identity
14. No raster access occurs in orchestrator
15. No classification logic exists in orchestrator
16. REST API validation and error reporting
"""

import ast
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.config import settings
from backend.main import app
from backend.ml.change.scene_pairing import create_scene_pair
from backend.ml.change.temporal_catalog import TemporalCatalog
from backend.ml.change.types import (
    PairCompatibility,
    PairCompatibilityStatus,
    PairingConfig,
    ScenePair,
    SpatialOverlap,
    TemporalObservation,
    TemporalSeries,
)
from backend.ml.change_classification.service import ChangeClassificationEvidenceService
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
from backend.ml.change_detection.service import ChangeDetectionService
from backend.ml.change_detection.types import (
    ChangeDetectionConfig,
    ChangeDetectionResult,
    ChangeMetrics,
    ChangeRegion,
)
from backend.ml.change_suppression.service import ChangeSuppressionService
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
    PairwiseTemporalEvidenceInput,
    TemporalEvidenceConfig,
    TemporalEvidenceResult,
)
from backend.orchestrator.service import (
    ASTRAPipelineOrchestrator,
    compute_investigation_hash,
)
from backend.orchestrator.types import (
    InvestigationDossier,
    InvestigationLineage,
    InvestigationPipelineError,
    InvestigationRequest,
    InvestigationStageResult,
    InvestigationStageStatus,
)
from geospatial.contracts import GeoBoundingBox


# ==============================================================================
# Helper Factories
# ==============================================================================

def make_observation(
    obs_id: str,
    dt_str: str,
    scene_id: Optional[str] = None,
    sensor: str = "Sentinel-2A MSI",
    platform: str = "Sentinel-2",
) -> TemporalObservation:
    clean_obs_id = obs_id if len(obs_id) >= 3 else f"obs_{obs_id}"
    dt = datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc)
    return TemporalObservation(
        observation_id=clean_obs_id,
        scene_id=scene_id or f"SCENE_{clean_obs_id}",
        acquisition_time=dt,
        sensor=sensor,
        platform=platform,
        crs="EPSG:32643",
        bounds_wgs84=GeoBoundingBox(min_lon=77.10, min_lat=12.10, max_lon=77.20, max_lat=12.20),
        source_hash=f"hash_{clean_obs_id}_0123456789abcdef",
        metadata={"valid_pixel_ratio": 0.99, "cloud_fraction": 0.02},
    )


def make_scene_pair(obs_earlier: TemporalObservation, obs_later: TemporalObservation) -> ScenePair:
    return create_scene_pair(obs_earlier, obs_later)


def make_change_region(region_id: str = "reg_0001", mean_score: float = 0.75) -> ChangeRegion:
    clean_id = region_id if len(region_id) >= 3 else f"reg_{region_id}"
    return ChangeRegion(
        region_id=clean_id,
        pixel_count=150,
        area_px=150,
        area_m2=15000.0,
        bbox_px=[10, 10, 30, 30],
        bbox_wgs84=GeoBoundingBox(min_lon=77.12, min_lat=12.12, max_lon=77.15, max_lat=12.15),
        centroid_px=[20.0, 20.0],
        centroid_wgs84=[77.135, 12.135],
        mean_change_score=mean_score,
        max_change_score=0.92,
    )


def make_cdr(scene_pair_id: str, regions: Optional[List[ChangeRegion]] = None) -> ChangeDetectionResult:
    chg_regs = regions or [make_change_region()]
    return ChangeDetectionResult(
        result_id=f"cdr_{scene_pair_id}",
        scene_pair_id=scene_pair_id,
        algorithm_id="pixel_diff",
        algorithm_version="1.0.0",
        config=ChangeDetectionConfig(),
        metrics=ChangeMetrics(
            total_pixels=10000,
            valid_pixels=9800,
            invalid_pixels=200,
            changed_pixels=len(chg_regs) * 150,
            changed_fraction=0.015,
            number_of_regions=len(chg_regs),
            changed_area_px=len(chg_regs) * 150,
            threshold_used=0.25,
            threshold_method="otsu",
        ),
        regions=chg_regs,
        mask_path=f"data/change_results/cdr_{scene_pair_id}/change_mask.png",
        provenance_id=f"prov_cdr_{scene_pair_id}",
    )


def make_evidence(scene_pair: ScenePair, cdr: ChangeDetectionResult) -> ChangeEvidence:
    reg_features: List[ChangeRegionFeatures] = []
    for reg in cdr.regions:
        reg_features.append(
            ChangeRegionFeatures(
                region_id=reg.region_id,
                spatial=SpatialEvidence(
                    area_px=reg.pixel_count,
                    pixel_count=reg.pixel_count,
                    width_px=20,
                    height_px=20,
                    aspect_ratio=1.0,
                    perimeter_px=80.0,
                    compactness=0.8,
                    rectangularity=0.9,
                    elongation=1.0,
                    major_axis_length=20.0,
                    minor_axis_length=20.0,
                    axis_ratio=1.0,
                    linearity_score=0.1,
                    orientation_degrees=0.0,
                    component_density=0.9,
                    shape_regularity=0.8,
                    fragmentation=1.0,
                    neighboring_changed_regions_count=0,
                ),
                spectral=SpectralEvidence(available=True),
                context=ContextEvidence(available=True),
            )
        )
    return ChangeEvidence(
        evidence_id=f"evi_{scene_pair.pair_id}",
        scene_pair_id=scene_pair.pair_id,
        change_detection_result_id=cdr.result_id,
        extractor_id="test_extractor",
        extractor_version="1.0.0",
        config=EvidenceConfig(),
        temporal=TemporalEvidence(
            earlier_acquisition_time=scene_pair.earlier_observation.acquisition_time,
            later_acquisition_time=scene_pair.later_observation.acquisition_time,
            temporal_separation_seconds=scene_pair.temporal_separation_seconds,
            temporal_separation_days=scene_pair.temporal_separation_days,
            temporal_separation_hours=round(scene_pair.temporal_separation_seconds / 3600.0, 2),
            earlier_scene_id=scene_pair.earlier_observation.scene_id,
            later_scene_id=scene_pair.later_observation.scene_id,
        ),
        regions=reg_features,
        source_hashes={"pair_hash": f"src_hash_{scene_pair.pair_id}"},
        provenance_id=f"prov_evi_{scene_pair.pair_id}",
    )


def make_classification(evidence: ChangeEvidence) -> ChangeClassificationResult:
    classifications: List[RegionClassification] = []
    for reg in evidence.regions:
        classifications.append(
            RegionClassification(
                region_id=reg.region_id,
                category=ChangeCategory.CONSTRUCTION,
                confidence_tier=ConfidenceTier.HIGH,
                evidence_score=0.88,
                candidate_scores={"construction": 0.88},
                decision_reason="High spectral and context evidence",
            )
        )
    return ChangeClassificationResult(
        classification_id=f"cls_{evidence.evidence_id}",
        evidence_id=evidence.evidence_id,
        scene_pair_id=evidence.scene_pair_id,
        change_detection_result_id=evidence.change_detection_result_id,
        classifier_id="test_classifier",
        classifier_version="1.0.0",
        config=ClassifierConfig(),
        classifications=classifications,
        metrics=ChangeClassificationMetrics(
            total_regions=len(classifications),
            category_counts={"construction": len(classifications)},
            high_confidence_count=len(classifications),
            ambiguous_count=0,
            unclassified_unknown_fraction=0.0,
        ),
        provenance_id=f"prov_cls_{evidence.evidence_id}",
    )


def make_suppression(
    evidence: ChangeEvidence,
    decision: SuppressionDecision = SuppressionDecision.RETAINED,
) -> SuppressionResult:
    reg_suppressions: List[RegionSuppression] = []
    for reg in evidence.regions:
        reg_suppressions.append(
            RegionSuppression(
                region_id=reg.region_id,
                decision=decision,
                artifact_risk_score=0.10 if decision == SuppressionDecision.RETAINED else 0.85,
                artifact_risk_interpretation="Low risk" if decision == SuppressionDecision.RETAINED else "High risk",
                decision_basis="MULTI_EVIDENCE",
                decision_reasons=["Test decision"],
                original_category="construction",
                retained_category="construction" if decision == SuppressionDecision.RETAINED else "suppressed",
                confidence_tier_adjusted="high" if decision == SuppressionDecision.RETAINED else "uncertain",
            )
        )
    return SuppressionResult(
        suppression_id=f"sup_{evidence.evidence_id}",
        scene_pair_id=evidence.scene_pair_id,
        change_detection_result_id=evidence.change_detection_result_id,
        evidence_id=evidence.evidence_id,
        suppressor_id="test_suppressor",
        suppressor_version="1.0.0",
        config=SuppressionConfig(),
        metrics=SuppressionMetrics(
            total_input_regions=len(reg_suppressions),
            retained_count=len(reg_suppressions) if decision == SuppressionDecision.RETAINED else 0,
            flagged_count=0,
            suppressed_count=0 if decision == SuppressionDecision.RETAINED else len(reg_suppressions),
            insufficient_evidence_count=0,
            suppression_rate=0.0 if decision == SuppressionDecision.RETAINED else 1.0,
            total_area_px=150,
            retained_area_px=150 if decision == SuppressionDecision.RETAINED else 0,
            flagged_area_px=0,
            suppressed_area_px=0 if decision == SuppressionDecision.RETAINED else 150,
            artifact_counts={},
        ),
        regions=reg_suppressions,
        filtered_mask_path=f"data/change_suppression/sup_{evidence.evidence_id}/filtered_change_mask.png",
        provenance_id=f"prov_sup_{evidence.evidence_id}",
    )


def create_mock_pipeline_services():
    """Creates stubbed upstream services for change detection, evidence, classification, and suppression."""
    m_cd = MagicMock(spec=ChangeDetectionService)
    m_evi = MagicMock(spec=ChangeClassificationEvidenceService)
    m_sup = MagicMock(spec=ChangeSuppressionService)

    # Dynamic run_detection
    def fake_detection(pair, config=None):
        return make_cdr(pair.pair_id)

    m_cd.run_detection.side_effect = fake_detection

    # Dynamic extract_evidence
    def fake_extract(scene_pair, change_result, config=None):
        return make_evidence(scene_pair, change_result)

    m_evi.extract_evidence.side_effect = fake_extract

    # Dynamic classify_evidence
    def fake_classify(evidence, config=None):
        return make_classification(evidence)

    m_evi.classify_evidence.side_effect = fake_classify

    # Dynamic suppress_false_alarms
    def fake_suppress(evidence, classification=None, scene_pair=None, change_result=None, config=None):
        return make_suppression(evidence, decision=SuppressionDecision.RETAINED)

    m_sup.suppress_false_alarms.side_effect = fake_suppress

    return m_cd, m_evi, m_sup


# ==============================================================================
# Tests
# ==============================================================================

def test_1_valid_orchestration_contract():
    """1. Verifies that orchestration data contracts instantiate, validate, and serialize correctly."""
    req = InvestigationRequest(
        series_id="series_tile_001",
        discovery_pair_id="pair_obs_01__obs_02",
        candidate_region_id="reg_0001",
        output_dir="data/test_inv",
        pairing_strategy="adjacent",
    )
    assert req.series_id == "series_tile_001"
    assert req.discovery_pair_id == "pair_obs_01__obs_02"
    assert req.candidate_region_id == "reg_0001"

    # Stage result contract
    sr = InvestigationStageResult(
        stage="m4b_change_detection",
        status=InvestigationStageStatus.COMPLETED,
        artifact_id="cdr_001",
        provenance_id="prov_001",
    )
    assert sr.status == InvestigationStageStatus.COMPLETED

    # Lineage contract
    lineage = InvestigationLineage(
        scene_pair_ids=["pair_01"],
        change_detection_result_ids=["cdr_01"],
        evidence_ids=["evi_01"],
        classification_ids=["cls_01"],
        suppression_ids=["sup_01"],
        temporal_evidence_id="tem_01",
        upstream_hashes={"h1": "v1"},
    )
    assert len(lineage.scene_pair_ids) == 1
    assert lineage.upstream_hashes["h1"] == "v1"

    # Dossier serialization roundtrip
    dossier = InvestigationDossier(
        investigation_id="inv_1234567890abcdef",
        request=req,
        series_id="series_tile_001",
        discovery_pair_id="pair_obs_01__obs_02",
        candidate_region_id="reg_0001",
        stage_results=[sr],
        lineage=lineage,
        provenance_id="prov_inv_1234567890abcdef",
        created_at=datetime.now(timezone.utc),
        content_hash="1234567890abcdef",
        status="COMPLETED",
    )
    json_str = dossier.model_dump_json()
    loaded = InvestigationDossier.model_validate_json(json_str)
    assert loaded.investigation_id == "inv_1234567890abcdef"


def test_2_unknown_investigation_request_field_rejected():
    """2. Verifies that InvestigationRequest rejects unknown fields (ConfigDict extra='forbid')."""
    with pytest.raises(ValidationError):
        InvestigationRequest(
            series_id="series_01",
            discovery_pair_id="pair_01",
            candidate_region_id="reg_0001",
            unauthorized_field="malicious_payload",
        )


def test_3_missing_series_rejected(tmp_path):
    """3. Verifies that orchestrator fails explicitly when requested series does not exist."""
    catalog = TemporalCatalog()
    orchestrator = ASTRAPipelineOrchestrator(
        catalog=catalog,
        output_dir=tmp_path / "out",
        provenance_dir=tmp_path / "prov",
    )
    req = InvestigationRequest(
        series_id="nonexistent_series_999",
        discovery_pair_id="pair_obs_01__obs_02",
        candidate_region_id="reg_0001",
    )
    with pytest.raises(InvestigationPipelineError) as exc_info:
        orchestrator.run_investigation(req)

    assert exc_info.value.stage == "series_resolution"
    assert "does not exist" in exc_info.value.message


def test_4_missing_discovery_pair_rejected(tmp_path):
    """4. Verifies that orchestrator fails explicitly when discovery pair does not exist."""
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-10T00:00:00")
    series = TemporalSeries(
        series_id="series_01",
        target_id="tile_01",
        bounds_wgs84=obs1.bounds_wgs84,
        observations=[obs1, obs2],
        observation_count=2,
    )
    catalog = TemporalCatalog()
    catalog._series["series_01"] = series

    orchestrator = ASTRAPipelineOrchestrator(
        catalog=catalog,
        output_dir=tmp_path / "out",
        provenance_dir=tmp_path / "prov",
    )
    req = InvestigationRequest(
        series_id="series_01",
        discovery_pair_id="pair_missing__pair_nonexistent",
        candidate_region_id="reg_0001",
    )
    with pytest.raises(InvestigationPipelineError) as exc_info:
        orchestrator.run_investigation(req)

    assert exc_info.value.stage == "discovery_pair_resolution"
    assert "does not exist" in exc_info.value.message


def test_5_discovery_pair_belonging_to_another_series_rejected(tmp_path):
    """5. Verifies that a pair belonging to Series B is rejected when requested on Series A."""
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-10T00:00:00")
    series_a = TemporalSeries(
        series_id="series_A",
        target_id="tile_A",
        bounds_wgs84=obs1.bounds_wgs84,
        observations=[obs1, obs2],
        observation_count=2,
    )

    obs3 = make_observation("obs_03", "2026-02-01T00:00:00")
    obs4 = make_observation("obs_04", "2026-02-10T00:00:00")
    series_b = TemporalSeries(
        series_id="series_B",
        target_id="tile_B",
        bounds_wgs84=obs3.bounds_wgs84,
        observations=[obs3, obs4],
        observation_count=2,
    )

    pair_b = make_scene_pair(obs3, obs4)

    catalog = TemporalCatalog()
    catalog._series["series_A"] = series_a
    catalog._series["series_B"] = series_b

    orchestrator = ASTRAPipelineOrchestrator(
        catalog=catalog,
        known_pairs={pair_b.pair_id: pair_b},
        output_dir=tmp_path / "out",
        provenance_dir=tmp_path / "prov",
    )
    req = InvestigationRequest(
        series_id="series_A",
        discovery_pair_id=pair_b.pair_id,
        candidate_region_id="reg_0001",
    )
    with pytest.raises(InvestigationPipelineError) as exc_info:
        orchestrator.run_investigation(req)

    assert exc_info.value.stage == "discovery_pair_resolution"
    assert "does not belong" in exc_info.value.message


def test_6_invalid_candidate_region_rejected(tmp_path):
    """6. Verifies that candidate region not present in discovery M4B result is rejected."""
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-10T00:00:00")
    pair = make_scene_pair(obs1, obs2)

    series = TemporalSeries(
        series_id="series_01",
        target_id="tile_01",
        bounds_wgs84=obs1.bounds_wgs84,
        observations=[obs1, obs2],
        observation_count=2,
    )
    catalog = TemporalCatalog()
    catalog._series["series_01"] = series

    m_cd, m_evi, m_sup = create_mock_pipeline_services()
    # Mock returns only reg_0001
    m_cd.run_detection.return_value = make_cdr(pair.pair_id, regions=[make_change_region("reg_0001")])

    orchestrator = ASTRAPipelineOrchestrator(
        catalog=catalog,
        change_detection_service=m_cd,
        evidence_service=m_evi,
        suppression_service=m_sup,
        known_pairs={pair.pair_id: pair},
        output_dir=tmp_path / "out",
        provenance_dir=tmp_path / "prov",
    )
    req = InvestigationRequest(
        series_id="series_01",
        discovery_pair_id=pair.pair_id,
        candidate_region_id="reg_9999_invalid",
    )
    with pytest.raises(InvestigationPipelineError) as exc_info:
        orchestrator.run_investigation(req)

    assert exc_info.value.stage == "candidate_region_validation"
    assert "reg_9999_invalid" in exc_info.value.message


def test_7_upstream_failure_stops_pipeline(tmp_path):
    """7. Verifies that failure in an upstream service immediately halts the pipeline."""
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-10T00:00:00")
    pair = make_scene_pair(obs1, obs2)

    series = TemporalSeries(
        series_id="series_01",
        target_id="tile_01",
        bounds_wgs84=obs1.bounds_wgs84,
        observations=[obs1, obs2],
        observation_count=2,
    )
    catalog = TemporalCatalog()
    catalog._series["series_01"] = series

    m_cd, m_evi, m_sup = create_mock_pipeline_services()
    # Simulate M4C-A catastrophic failure
    m_evi.extract_evidence.side_effect = RuntimeError("Disk read corruption in evidence extractor")

    orchestrator = ASTRAPipelineOrchestrator(
        catalog=catalog,
        change_detection_service=m_cd,
        evidence_service=m_evi,
        suppression_service=m_sup,
        known_pairs={pair.pair_id: pair},
        output_dir=tmp_path / "out",
        provenance_dir=tmp_path / "prov",
    )
    req = InvestigationRequest(
        series_id="series_01",
        discovery_pair_id=pair.pair_id,
        candidate_region_id="reg_0001",
    )
    with pytest.raises(InvestigationPipelineError) as exc_info:
        orchestrator.run_investigation(req)

    assert "m4c_evidence_extraction" in exc_info.value.stage
    assert "Disk read corruption" in exc_info.value.message
    # Verify M4C-B, M4D, and M4E were never invoked
    m_evi.classify_evidence.assert_not_called()
    m_sup.suppress_false_alarms.assert_not_called()


def test_8_lineage_contains_all_executed_pair_artifact_ids(tmp_path):
    """8. Verifies that the final dossier preserves complete upstream lineage across all evaluated pairs."""
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-10T00:00:00")
    obs3 = make_observation("obs_03", "2026-01-20T00:00:00")
    pair12 = make_scene_pair(obs1, obs2)
    pair23 = make_scene_pair(obs2, obs3)

    series = TemporalSeries(
        series_id="series_01",
        target_id="tile_01",
        bounds_wgs84=obs1.bounds_wgs84,
        observations=[obs1, obs2, obs3],
        observation_count=3,
    )
    catalog = TemporalCatalog()
    catalog._series["series_01"] = series

    m_cd, m_evi, m_sup = create_mock_pipeline_services()
    tem_service = TemporalEvidenceService(output_dir=tmp_path / "tem", provenance_dir=tmp_path / "prov")

    orchestrator = ASTRAPipelineOrchestrator(
        catalog=catalog,
        change_detection_service=m_cd,
        evidence_service=m_evi,
        suppression_service=m_sup,
        temporal_evidence_service=tem_service,
        known_pairs={pair12.pair_id: pair12, pair23.pair_id: pair23},
        output_dir=tmp_path / "out",
        provenance_dir=tmp_path / "prov",
    )
    req = InvestigationRequest(
        series_id="series_01",
        discovery_pair_id=pair12.pair_id,
        candidate_region_id="reg_0001",
    )
    dossier = orchestrator.run_investigation(req)

    # Both pairs executed
    assert len(dossier.lineage.scene_pair_ids) == 2
    assert pair12.pair_id in dossier.lineage.scene_pair_ids
    assert pair23.pair_id in dossier.lineage.scene_pair_ids

    # All upstream artifact IDs preserved
    assert len(dossier.lineage.change_detection_result_ids) == 2
    assert len(dossier.lineage.evidence_ids) == 2
    assert len(dossier.lineage.classification_ids) == 2
    assert len(dossier.lineage.suppression_ids) == 2
    assert dossier.lineage.temporal_evidence_id is not None
    assert dossier.lineage.temporal_evidence_id.startswith("tem_")


def test_9_m4d_decision_is_preserved(tmp_path):
    """9. Verifies that M4D decision is preserved through to M4E and final dossier."""
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-10T00:00:00")
    pair12 = make_scene_pair(obs1, obs2)

    series = TemporalSeries(
        series_id="series_01",
        target_id="tile_01",
        bounds_wgs84=obs1.bounds_wgs84,
        observations=[obs1, obs2],
        observation_count=2,
    )
    catalog = TemporalCatalog()
    catalog._series["series_01"] = series

    m_cd, m_evi, m_sup = create_mock_pipeline_services()
    # Explicitly verify RETAINED decision is preserved
    m_sup.suppress_false_alarms.return_value = make_suppression(
        make_evidence(pair12, make_cdr(pair12.pair_id)),
        decision=SuppressionDecision.RETAINED,
    )
    tem_service = TemporalEvidenceService(output_dir=tmp_path / "tem", provenance_dir=tmp_path / "prov")

    orchestrator = ASTRAPipelineOrchestrator(
        catalog=catalog,
        change_detection_service=m_cd,
        evidence_service=m_evi,
        suppression_service=m_sup,
        temporal_evidence_service=tem_service,
        known_pairs={pair12.pair_id: pair12},
        output_dir=tmp_path / "out",
        provenance_dir=tmp_path / "prov",
    )
    req = InvestigationRequest(
        series_id="series_01",
        discovery_pair_id=pair12.pair_id,
        candidate_region_id="reg_0001",
    )
    dossier = orchestrator.run_investigation(req)

    # Verify M4E node got EARLIEST_SUPPORTING because M4D was RETAINED
    assert dossier.temporal_evidence is not None
    node_o2 = [n for n in dossier.temporal_evidence.timeline_nodes if n.observation_id == "obs_02"][0]
    assert node_o2.m4d_decision == SuppressionDecision.RETAINED
    assert node_o2.node_status.value == "EARLIEST_SUPPORTING"


def test_10_m4e_result_is_preserved(tmp_path):
    """10. Verifies that M4E TemporalEvidenceResult is attached and matches evaluation outcome."""
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-10T00:00:00")
    pair12 = make_scene_pair(obs1, obs2)

    series = TemporalSeries(
        series_id="series_01",
        target_id="tile_01",
        bounds_wgs84=obs1.bounds_wgs84,
        observations=[obs1, obs2],
        observation_count=2,
    )
    catalog = TemporalCatalog()
    catalog._series["series_01"] = series

    m_cd, m_evi, m_sup = create_mock_pipeline_services()
    tem_service = TemporalEvidenceService(output_dir=tmp_path / "tem", provenance_dir=tmp_path / "prov")

    orchestrator = ASTRAPipelineOrchestrator(
        catalog=catalog,
        change_detection_service=m_cd,
        evidence_service=m_evi,
        suppression_service=m_sup,
        temporal_evidence_service=tem_service,
        known_pairs={pair12.pair_id: pair12},
        output_dir=tmp_path / "out",
        provenance_dir=tmp_path / "prov",
    )
    req = InvestigationRequest(
        series_id="series_01",
        discovery_pair_id=pair12.pair_id,
        candidate_region_id="reg_0001",
    )
    dossier = orchestrator.run_investigation(req)

    assert dossier.temporal_evidence is not None
    assert dossier.temporal_evidence_id == dossier.temporal_evidence.temporal_evidence_id
    assert dossier.temporal_evidence.onset_estimate.earliest_support_observation_id == "obs_02"


def test_11_deterministic_investigation_id(tmp_path):
    """11. Verifies that investigation ID is formatted as inv_{16-hex} and provenance as prov_inv_{16-hex}."""
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-10T00:00:00")
    pair = make_scene_pair(obs1, obs2)
    series = TemporalSeries(
        series_id="series_01",
        target_id="tile_01",
        bounds_wgs84=obs1.bounds_wgs84,
        observations=[obs1, obs2],
        observation_count=2,
    )
    catalog = TemporalCatalog()
    catalog._series["series_01"] = series

    m_cd, m_evi, m_sup = create_mock_pipeline_services()
    tem_service = TemporalEvidenceService(output_dir=tmp_path / "tem", provenance_dir=tmp_path / "prov")

    orchestrator = ASTRAPipelineOrchestrator(
        catalog=catalog,
        change_detection_service=m_cd,
        evidence_service=m_evi,
        suppression_service=m_sup,
        temporal_evidence_service=tem_service,
        known_pairs={pair.pair_id: pair},
        output_dir=tmp_path / "out",
        provenance_dir=tmp_path / "prov",
    )
    req = InvestigationRequest(
        series_id="series_01",
        discovery_pair_id=pair.pair_id,
        candidate_region_id="reg_0001",
    )
    dossier = orchestrator.run_investigation(req)

    assert dossier.investigation_id.startswith("inv_")
    assert len(dossier.investigation_id) == 20  # "inv_" (4) + 16 hex chars
    assert dossier.provenance_id.startswith("prov_inv_")
    assert dossier.provenance_id == f"prov_{dossier.investigation_id}"
    assert len(dossier.content_hash) == 16


def test_12_same_logical_inputs_produce_same_dossier_identity(tmp_path):
    """12. Verifies bit-for-bit identity reproduction on multiple runs with same logical inputs."""
    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-10T00:00:00")
    pair = make_scene_pair(obs1, obs2)
    series = TemporalSeries(
        series_id="series_01",
        target_id="tile_01",
        bounds_wgs84=obs1.bounds_wgs84,
        observations=[obs1, obs2],
        observation_count=2,
    )
    catalog = TemporalCatalog()
    catalog._series["series_01"] = series

    m_cd, m_evi, m_sup = create_mock_pipeline_services()
    tem_service = TemporalEvidenceService(output_dir=tmp_path / "tem", provenance_dir=tmp_path / "prov")

    orchestrator = ASTRAPipelineOrchestrator(
        catalog=catalog,
        change_detection_service=m_cd,
        evidence_service=m_evi,
        suppression_service=m_sup,
        temporal_evidence_service=tem_service,
        known_pairs={pair.pair_id: pair},
        output_dir=tmp_path / "out",
        provenance_dir=tmp_path / "prov",
    )
    req = InvestigationRequest(
        series_id="series_01",
        discovery_pair_id=pair.pair_id,
        candidate_region_id="reg_0001",
    )
    dossier1 = orchestrator.run_investigation(req)
    dossier2 = orchestrator.run_investigation(req)

    assert dossier1.investigation_id == dossier2.investigation_id
    assert dossier1.content_hash == dossier2.content_hash
    assert dossier1.provenance_id == dossier2.provenance_id
    assert dossier1.created_at == dossier2.created_at


def test_13_changed_upstream_hash_changes_dossier_identity(tmp_path):
    """13. Verifies that altering an upstream input hash alters the resulting dossier identity."""
    req = InvestigationRequest(
        series_id="series_01",
        discovery_pair_id="pair_01",
        candidate_region_id="reg_0001",
    )
    lineage_a = InvestigationLineage(
        scene_pair_ids=["pair_01"],
        change_detection_result_ids=["cdr_01"],
        evidence_ids=["evi_01"],
        classification_ids=["cls_01"],
        suppression_ids=["sup_01"],
        temporal_evidence_id="tem_01",
        upstream_hashes={"hash_tile": "aaaa000011112222"},
    )
    lineage_b = InvestigationLineage(
        scene_pair_ids=["pair_01"],
        change_detection_result_ids=["cdr_01"],
        evidence_ids=["evi_01"],
        classification_ids=["cls_01"],
        suppression_ids=["sup_01"],
        temporal_evidence_id="tem_01",
        upstream_hashes={"hash_tile": "bbbb000011112222"},
    )

    hash_a = compute_investigation_hash(req, lineage_a, temporal_evidence_id="tem_01")
    hash_b = compute_investigation_hash(req, lineage_b, temporal_evidence_id="tem_01")

    assert hash_a != hash_b


def test_14_no_raster_access_occurs_in_orchestrator():
    """14. Verifies statically and structurally that orchestrator does not import or execute raster I/O."""
    service_file = Path("backend/orchestrator/service.py")
    tree = ast.parse(service_file.read_text(encoding="utf-8"))

    prohibited_modules = {"rasterio", "PIL", "cv2", "tifffile", "imageio"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in prohibited_modules, f"Prohibited import in orchestrator: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                assert node.module.split(".")[0] not in prohibited_modules, f"Prohibited import in orchestrator: {node.module}"


def test_15_no_classification_logic_exists_in_orchestrator():
    """15. Verifies that orchestrator contains no classification decision heuristics or category rules."""
    service_file = Path("backend/orchestrator/service.py")
    content = service_file.read_text(encoding="utf-8")

    # Orchestrator must not contain hardcoded category branching or thresholds
    forbidden_terms = [
        "ChangeCategory.CONSTRUCTION",
        "ChangeCategory.VEGETATION_LOSS",
        "ChangeCategory.WATER_EXTENT",
        "ndvi_mean",
        "ndwi_mean",
        "pixel_difference",
    ]
    for term in forbidden_terms:
        assert term not in content, f"Orchestrator must not duplicate classification logic: '{term}' found"


def test_16_api_endpoints_integration(tmp_path):
    """16. Verifies FastAPI endpoint validation, 422 for extra fields, and 400 for errors."""
    from backend.api.v1.endpoints.pipeline import set_pipeline_orchestrator

    obs1 = make_observation("obs_01", "2026-01-01T00:00:00")
    obs2 = make_observation("obs_02", "2026-01-10T00:00:00")
    pair = make_scene_pair(obs1, obs2)
    series = TemporalSeries(
        series_id="series_01",
        target_id="tile_01",
        bounds_wgs84=obs1.bounds_wgs84,
        observations=[obs1, obs2],
        observation_count=2,
    )
    catalog = TemporalCatalog()
    catalog._series["series_01"] = series

    m_cd, m_evi, m_sup = create_mock_pipeline_services()
    tem_service = TemporalEvidenceService(output_dir=tmp_path / "tem", provenance_dir=tmp_path / "prov")

    orchestrator = ASTRAPipelineOrchestrator(
        catalog=catalog,
        change_detection_service=m_cd,
        evidence_service=m_evi,
        suppression_service=m_sup,
        temporal_evidence_service=tem_service,
        known_pairs={pair.pair_id: pair},
        output_dir=tmp_path / "out",
        provenance_dir=tmp_path / "prov",
    )
    set_pipeline_orchestrator(orchestrator)

    client = TestClient(app)

    # 1. Unknown field rejected with 422
    res_422 = client.post(
        "/api/v1/pipeline/investigate",
        json={
            "series_id": "series_01",
            "discovery_pair_id": pair.pair_id,
            "candidate_region_id": "reg_0001",
            "unauthorized_key": 999,
        },
    )
    assert res_422.status_code == 422

    # 2. Missing series returns 400
    res_400 = client.post(
        "/api/v1/pipeline/investigate",
        json={
            "series_id": "nonexistent_series",
            "discovery_pair_id": pair.pair_id,
            "candidate_region_id": "reg_0001",
        },
    )
    assert res_400.status_code == 400
    assert "does not exist" in res_400.json()["detail"]["message"]

    # 3. Valid investigation returns 200 and valid dossier
    res_200 = client.post(
        "/api/v1/pipeline/investigate",
        json={
            "series_id": "series_01",
            "discovery_pair_id": pair.pair_id,
            "candidate_region_id": "reg_0001",
        },
    )
    assert res_200.status_code == 200
    data = res_200.json()
    assert data["investigation_id"].startswith("inv_")
    assert data["status"] == "COMPLETED"
    assert data["temporal_evidence_id"] is not None

    # Reset active orchestrator
    set_pipeline_orchestrator(None)
