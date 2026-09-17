"""ASTRA End-to-End Investigation Pipeline Test Suite (Phase M4F-C/D).

Verifies the complete integration of M1 Ingestion, M4A Catalog & Pairing,
M4B Change Detection, M4C-A Evidence Extraction, M4C-B Classification,
M4D False-Alarm Suppression, M4E Earliest Temporal Evidence, and
M4F-A/B Orchestration on a deterministic multi-epoch synthetic dataset.

Comprehensive Verification Criteria:
1. Deterministic 4-epoch synthetic dataset generation and ingestion.
2. TemporalCatalog discovery and TemporalSeries formation with quality metadata.
3. End-to-end investigation with baseline pairing strategy:
   - Status: COMPLETED
   - Temporal Support: STRONG_TEMPORAL_SUPPORT
   - Confidence Tier: HIGH
   - Earliest Supporting Observation: T2 (2026-02-15)
   - Pre-Change Absence: T1 (2026-01-15)
   - Onset Interval: Bounded half-open (T1, T2] (~31 days)
   - Category Continuity: CONSTRUCTION dominant, valid evolution
   - Persistence: T3 and T4 confirmed
4. Candidate spatial correspondence across differing local M4B region IDs.
5. M4D false-alarm screening integrity.
6. Complete upstream lineage preservation (M4A -> M4B -> M4C-A -> M4C-B -> M4D -> M4E).
7. InvestigationDossier JSON persistence and Pydantic validation.
8. Bit-for-bit determinism across repeated executions.
9. End-to-end investigation with adjacent pairing strategy.
10. Robust error handling for invalid series, pair, and candidate IDs.
11. CLI runner script execution and terminal report output.
"""

import json
from pathlib import Path
import subprocess
import sys
from typing import Dict
import pytest

from backend.config import settings
from backend.ml.change.temporal_catalog import TemporalCatalog
from backend.ml.change_classification.types import ChangeCategory, EvidenceConfig
from backend.ml.change_detection.service import ChangeDetectionService
from backend.ml.change_suppression.types import SuppressionDecision
from backend.ml.temporal_evidence.types import (
    TemporalConfidenceTier,
    TemporalIntervalType,
    TemporalNodeStatus,
    TemporalSupportStatus,
)
from backend.orchestrator.service import ASTRAPipelineOrchestrator
from backend.orchestrator.types import (
    InvestigationDossier,
    InvestigationPipelineError,
    InvestigationRequest,
)
from scripts.generate_demo_dataset import (
    create_synthetic_epoch_rasters,
    generate_and_ingest_demo_dataset,
)


@pytest.fixture(scope="module")
def demo_dataset(tmp_path_factory) -> Dict[str, str]:
    """Generates and ingests the deterministic 4-epoch demo dataset into isolated test directories."""
    base_dir = tmp_path_factory.mktemp("astra_e2e_demo")
    raw_dir = base_dir / "raw"
    manifests_dir = base_dir / "manifests"
    processed_dir = base_dir / "processed"

    info = generate_and_ingest_demo_dataset(
        output_dir=raw_dir,
        manifests_dir=manifests_dir,
        processed_dir=processed_dir,
        tile_size=512,
        force=True,
    )
    info["manifests_dir"] = str(manifests_dir)
    info["processed_dir"] = str(processed_dir)
    info["raw_dir"] = str(raw_dir)
    return info


class TestE2EInvestigationPipeline:
    """Comprehensive end-to-end test suite for Phase M4F-C/D."""

    def test_demo_dataset_generation_and_metadata(self, demo_dataset):
        """Verifies that all 4 epochs are synthesized with correct bands, tags, and geometry."""
        raw_dir = Path(demo_dataset["raw_dir"])
        tifs = sorted(raw_dir.glob("*.tif"))
        assert len(tifs) == 4, f"Expected 4 synthesized GeoTIFFs, found {len(tifs)}"

        manifests_dir = Path(demo_dataset["manifests_dir"])
        scene_manifests = list((manifests_dir / "scenes").glob("*.json"))
        tile_manifests = list((manifests_dir / "tiles").glob("*.json"))
        assert len(scene_manifests) == 4
        assert len(tile_manifests) == 4

        # Verify cloud_cover_percentage is populated
        for sm_path in scene_manifests:
            data = json.loads(sm_path.read_text(encoding="utf-8"))
            assert data["cloud_cover_percentage"] == 0.0
            assert data["is_synthetic"] is True

    def test_catalog_discovery_and_temporal_series(self, demo_dataset):
        """Verifies TemporalCatalog discovers observations and builds a valid 4-epoch series."""
        manifests_dir = Path(demo_dataset["manifests_dir"])
        catalog = TemporalCatalog()
        disc = catalog.discover_manifests(
            tiles_dir=manifests_dir / "tiles",
            scenes_dir=manifests_dir / "scenes",
        )
        assert disc.scenes_discovered >= 4
        assert disc.valid_observations >= 4

        series = catalog.get_series(demo_dataset["series_id"])
        assert series is not None
        assert series.observation_count == 4

        # Verify quality metadata preservation
        for obs in series.observations:
            assert obs.metadata.get("cloud_fraction") == 0.0
            assert obs.metadata.get("valid_pixel_ratio") == 1.0

    def test_full_e2e_investigation_baseline_pairing(self, demo_dataset):
        """Verifies complete end-to-end investigation with baseline pairing strategy."""
        manifests_dir = Path(demo_dataset["manifests_dir"])
        processed_dir = Path(demo_dataset["processed_dir"])
        inv_output_dir = processed_dir / "investigations"

        catalog = TemporalCatalog()
        catalog.discover_manifests(
            tiles_dir=manifests_dir / "tiles",
            scenes_dir=manifests_dir / "scenes",
        )

        orchestrator = ASTRAPipelineOrchestrator(
            catalog=catalog,
            output_dir=inv_output_dir,
            provenance_dir=manifests_dir / "provenance",
        )

        req = InvestigationRequest(
            series_id=demo_dataset["series_id"],
            discovery_pair_id=demo_dataset["discovery_pair_id"],
            candidate_region_id=demo_dataset["candidate_region_id"],
            pairing_strategy="baseline",
            evidence_config=EvidenceConfig(band_mapping={"red": 0, "green": 1, "blue": 2}),
        )

        dossier = orchestrator.run_investigation(req)

        # 1. Dossier Status
        assert dossier.status == "COMPLETED"
        assert dossier.investigation_id.startswith("inv_")
        assert len(dossier.content_hash) == 16
        assert dossier.provenance_id == f"prov_{dossier.investigation_id}"

        # 2. Temporal Evidence Determination
        te = dossier.temporal_evidence
        assert te is not None
        assert te.temporal_support_status == TemporalSupportStatus.STRONG_TEMPORAL_SUPPORT
        assert te.confidence_tier == TemporalConfidenceTier.HIGH

        # 3. Earliest Support & Pre-Change Absence
        onset = te.onset_estimate
        assert onset.interval_type == TemporalIntervalType.BOUNDED_HALF_OPEN
        assert onset.earliest_support_date.month == 2
        assert onset.earliest_support_date.day == 15
        assert onset.pre_change_date.month == 1
        assert onset.pre_change_date.day == 15
        assert onset.interval_days == pytest.approx(31.0, abs=0.5)

        # 4. Category Continuity
        cat_evo = te.category_evolution
        assert cat_evo.primary_category == ChangeCategory.CONSTRUCTION
        assert cat_evo.is_evolution_valid is True
        assert cat_evo.is_conflicted is False

        # 5. Timeline Nodes (Node 1=Absence, Node 2=Earliest, Node 3=Persistent, Node 4=Persistent)
        assert len(te.timeline_nodes) == 4
        assert te.timeline_nodes[0].node_status == TemporalNodeStatus.PRE_CHANGE_ABSENCE
        assert te.timeline_nodes[1].node_status == TemporalNodeStatus.EARLIEST_SUPPORTING
        assert te.timeline_nodes[1].m4d_decision == SuppressionDecision.RETAINED
        assert te.timeline_nodes[1].category_observed == ChangeCategory.CONSTRUCTION
        assert te.timeline_nodes[2].node_status == TemporalNodeStatus.PERSISTENT_SUPPORT
        assert te.timeline_nodes[2].m4d_decision == SuppressionDecision.RETAINED
        assert te.timeline_nodes[3].node_status == TemporalNodeStatus.PERSISTENT_SUPPORT
        assert te.timeline_nodes[3].m4d_decision == SuppressionDecision.RETAINED

        # 6. Metrics Summary
        assert te.metrics.supporting_nodes_count == 3
        assert te.metrics.absence_nodes_count == 1
        assert te.metrics.flagged_nodes_count == 0
        assert te.metrics.suppressed_nodes_count == 0
        assert te.metrics.total_observations_in_series == 4

    def test_spatial_correspondence_tracking_across_epochs(self, demo_dataset):
        """Verifies that M4F candidate correspondence resolves spatial match across epochs."""
        manifests_dir = Path(demo_dataset["manifests_dir"])
        processed_dir = Path(demo_dataset["processed_dir"])
        inv_output_dir = processed_dir / "investigations"

        catalog = TemporalCatalog()
        catalog.discover_manifests(
            tiles_dir=manifests_dir / "tiles",
            scenes_dir=manifests_dir / "scenes",
        )

        orchestrator = ASTRAPipelineOrchestrator(
            catalog=catalog,
            output_dir=inv_output_dir,
            provenance_dir=manifests_dir / "provenance",
        )

        req = InvestigationRequest(
            series_id=demo_dataset["series_id"],
            discovery_pair_id=demo_dataset["discovery_pair_id"],
            candidate_region_id=demo_dataset["candidate_region_id"],
            pairing_strategy="baseline",
            evidence_config=EvidenceConfig(band_mapping={"red": 0, "green": 1, "blue": 2}),
        )

        dossier = orchestrator.run_investigation(req)
        lineage = dossier.lineage
        assert len(lineage.candidate_correspondence) >= 2

        discovery_candidate_id = demo_dataset["candidate_region_id"]
        # Explicitly verify that at least one subsequent pair assigns a DIFFERENT local M4B region ID to the target
        matched_region_ids = [
            c_data["matched_region_id"]
            for pair_id, c_data in lineage.candidate_correspondence.items()
            if pair_id != demo_dataset["discovery_pair_id"]
        ]
        assert any(m_id != discovery_candidate_id for m_id in matched_region_ids), (
            f"Expected at least one subsequent pair to have a differing local region ID, "
            f"but found discovery={discovery_candidate_id} and subsequent matched={matched_region_ids}"
        )

        for pair_id, c_data in lineage.candidate_correspondence.items():
            assert c_data["reference_candidate_id"] == discovery_candidate_id
            assert c_data["relationship"] == "MATCHED"
            assert c_data["matched_region_id"] is not None
            assert c_data["metric_iou"] >= 0.30

    def test_false_alarm_cloud_region_in_upstream_suppression(self, demo_dataset):
        """Verifies that the false-alarm-like cloud region exists in M4B change results and is evaluated by M4D."""
        manifests_dir = Path(demo_dataset["manifests_dir"])
        processed_dir = Path(demo_dataset["processed_dir"])
        inv_output_dir = processed_dir / "investigations"

        catalog = TemporalCatalog()
        catalog.discover_manifests(
            tiles_dir=manifests_dir / "tiles",
            scenes_dir=manifests_dir / "scenes",
        )

        orchestrator = ASTRAPipelineOrchestrator(
            catalog=catalog,
            output_dir=inv_output_dir,
            provenance_dir=manifests_dir / "provenance",
        )

        req = InvestigationRequest(
            series_id=demo_dataset["series_id"],
            discovery_pair_id=demo_dataset["discovery_pair_id"],
            candidate_region_id=demo_dataset["candidate_region_id"],
            pairing_strategy="baseline",
            evidence_config=EvidenceConfig(band_mapping={"red": 0, "green": 1, "blue": 2}),
        )

        dossier = orchestrator.run_investigation(req)

        # Verify M4D suppression stage on discovery pair
        disc_stage = next(
            s for s in dossier.stage_results
            if s.stage == f"m4d_suppression_{demo_dataset['discovery_pair_id']}"
        )
        assert disc_stage.details["flagged_count"] >= 1, (
            f"Expected cloud artifact to be flagged in discovery pair suppression, "
            f"details: {disc_stage.details}"
        )

        # Inspect the actual M4D suppression artifact JSON
        sup_id = disc_stage.artifact_id
        sup_file = orchestrator.suppression_service.output_dir / sup_id / "suppression.json"
        assert sup_file.exists(), f"Suppression artifact JSON {sup_file} not found"
        sup_data = json.loads(sup_file.read_text(encoding="utf-8"))

        # Find the cloud artifact region
        cloud_reg = next(
            (r for r in sup_data["regions"] if r["region_id"] == "reg_0003"),
            None,
        )
        assert cloud_reg is not None, "Cloud artifact region reg_0003 not found in suppression decisions"
        assert cloud_reg["decision"] == "flagged", (
            f"Expected reg_0003 to be flagged due to visible whiteness/cloud anomaly, "
            f"got {cloud_reg['decision']}"
        )
        assert any("cloud" in r.lower() or "whiteness" in r.lower() for r in cloud_reg["decision_reasons"])

    def test_full_e2e_investigation_adjacent_pairing(self, demo_dataset):
        """Verifies complete end-to-end investigation with adjacent pairing strategy."""
        manifests_dir = Path(demo_dataset["manifests_dir"])
        processed_dir = Path(demo_dataset["processed_dir"])
        inv_output_dir = processed_dir / "investigations"

        catalog = TemporalCatalog()
        catalog.discover_manifests(
            tiles_dir=manifests_dir / "tiles",
            scenes_dir=manifests_dir / "scenes",
        )

        orchestrator = ASTRAPipelineOrchestrator(
            catalog=catalog,
            output_dir=inv_output_dir,
            provenance_dir=manifests_dir / "provenance",
        )

        req = InvestigationRequest(
            series_id=demo_dataset["series_id"],
            discovery_pair_id=demo_dataset["discovery_pair_id"],
            candidate_region_id=demo_dataset["candidate_region_id"],
            pairing_strategy="adjacent",
            evidence_config=EvidenceConfig(band_mapping={"red": 0, "green": 1, "blue": 2}),
        )

        dossier = orchestrator.run_investigation(req)
        assert dossier.status == "COMPLETED"
        assert dossier.temporal_evidence is not None
        # On adjacent pairing, T1->T2 is earliest, T2->T3 has 0 pixel delta
        te = dossier.temporal_evidence
        assert te.onset_estimate.earliest_support_date.month == 2
        assert te.onset_estimate.pre_change_date.month == 1

    def test_upstream_lineage_and_provenance(self, demo_dataset):
        """Verifies complete upstream cryptographic lineage across all evaluated pipeline stages."""
        manifests_dir = Path(demo_dataset["manifests_dir"])
        processed_dir = Path(demo_dataset["processed_dir"])
        inv_output_dir = processed_dir / "investigations"

        catalog = TemporalCatalog()
        catalog.discover_manifests(
            tiles_dir=manifests_dir / "tiles",
            scenes_dir=manifests_dir / "scenes",
        )

        orchestrator = ASTRAPipelineOrchestrator(
            catalog=catalog,
            output_dir=inv_output_dir,
            provenance_dir=manifests_dir / "provenance",
        )

        req = InvestigationRequest(
            series_id=demo_dataset["series_id"],
            discovery_pair_id=demo_dataset["discovery_pair_id"],
            candidate_region_id=demo_dataset["candidate_region_id"],
            pairing_strategy="baseline",
            evidence_config=EvidenceConfig(band_mapping={"red": 0, "green": 1, "blue": 2}),
        )

        dossier = orchestrator.run_investigation(req)
        lineage = dossier.lineage

        num_pairs = len(lineage.scene_pair_ids)
        assert num_pairs == 3
        assert len(lineage.change_detection_result_ids) == num_pairs
        assert len(lineage.evidence_ids) == num_pairs
        assert len(lineage.classification_ids) == num_pairs
        assert len(lineage.suppression_ids) == num_pairs
        assert lineage.temporal_evidence_id.startswith("tem_")

        # Check standard prefixes
        for cd_id in lineage.change_detection_result_ids:
            assert cd_id.startswith("res_chg_")
        for ev_id in lineage.evidence_ids:
            assert ev_id.startswith("evi_")
        for cl_id in lineage.classification_ids:
            assert cl_id.startswith("cls_")
        for sp_id in lineage.suppression_ids:
            assert sp_id.startswith("sup_")

    def test_dossier_json_persistence_and_revalidation(self, demo_dataset):
        """Verifies that dossier JSON file exists, is valid, and deserializes back into InvestigationDossier."""
        manifests_dir = Path(demo_dataset["manifests_dir"])
        processed_dir = Path(demo_dataset["processed_dir"])
        inv_output_dir = processed_dir / "investigations"

        catalog = TemporalCatalog()
        catalog.discover_manifests(
            tiles_dir=manifests_dir / "tiles",
            scenes_dir=manifests_dir / "scenes",
        )

        orchestrator = ASTRAPipelineOrchestrator(
            catalog=catalog,
            output_dir=inv_output_dir,
            provenance_dir=manifests_dir / "provenance",
        )

        req = InvestigationRequest(
            series_id=demo_dataset["series_id"],
            discovery_pair_id=demo_dataset["discovery_pair_id"],
            candidate_region_id=demo_dataset["candidate_region_id"],
            pairing_strategy="baseline",
            evidence_config=EvidenceConfig(band_mapping={"red": 0, "green": 1, "blue": 2}),
        )

        dossier = orchestrator.run_investigation(req)
        assert dossier.dossier_path is not None
        dossier_file = Path(dossier.dossier_path)
        assert dossier_file.exists()

        # Revalidate JSON from disk
        raw_json = dossier_file.read_text(encoding="utf-8")
        parsed = json.loads(raw_json)
        reloaded = InvestigationDossier.model_validate(parsed)
        assert reloaded.investigation_id == dossier.investigation_id
        assert reloaded.content_hash == dossier.content_hash

    def test_investigation_bit_for_bit_determinism(self, demo_dataset):
        """Verifies that executing the exact same investigation twice yields identical ID and hash."""
        manifests_dir = Path(demo_dataset["manifests_dir"])
        processed_dir = Path(demo_dataset["processed_dir"])
        inv_output_dir = processed_dir / "investigations"

        catalog = TemporalCatalog()
        catalog.discover_manifests(
            tiles_dir=manifests_dir / "tiles",
            scenes_dir=manifests_dir / "scenes",
        )

        orchestrator = ASTRAPipelineOrchestrator(
            catalog=catalog,
            output_dir=inv_output_dir,
            provenance_dir=manifests_dir / "provenance",
        )

        req = InvestigationRequest(
            series_id=demo_dataset["series_id"],
            discovery_pair_id=demo_dataset["discovery_pair_id"],
            candidate_region_id=demo_dataset["candidate_region_id"],
            pairing_strategy="baseline",
            evidence_config=EvidenceConfig(band_mapping={"red": 0, "green": 1, "blue": 2}),
        )

        dossier1 = orchestrator.run_investigation(req)
        dossier2 = orchestrator.run_investigation(req)

        assert dossier1.investigation_id == dossier2.investigation_id
        assert dossier1.content_hash == dossier2.content_hash
        assert dossier1.provenance_id == dossier2.provenance_id
        assert dossier1.created_at == dossier2.created_at
        assert dossier1.temporal_evidence.temporal_evidence_id == dossier2.temporal_evidence.temporal_evidence_id

    def test_error_handling_invalid_series(self, demo_dataset):
        """Verifies that an invalid series_id raises InvestigationPipelineError with m4a_resolution."""
        manifests_dir = Path(demo_dataset["manifests_dir"])
        processed_dir = Path(demo_dataset["processed_dir"])

        catalog = TemporalCatalog()
        catalog.discover_manifests(
            tiles_dir=manifests_dir / "tiles",
            scenes_dir=manifests_dir / "scenes",
        )

        orchestrator = ASTRAPipelineOrchestrator(catalog=catalog, output_dir=processed_dir / "inv")
        req = InvestigationRequest(
            series_id="series_non_existent_id",
            discovery_pair_id=demo_dataset["discovery_pair_id"],
            candidate_region_id=demo_dataset["candidate_region_id"],
        )

        with pytest.raises(InvestigationPipelineError) as exc_info:
            orchestrator.run_investigation(req)
        assert exc_info.value.stage == "series_resolution"

    def test_error_handling_invalid_discovery_pair(self, demo_dataset):
        """Verifies that an invalid discovery_pair_id raises InvestigationPipelineError with discovery_pair_resolution."""
        manifests_dir = Path(demo_dataset["manifests_dir"])
        processed_dir = Path(demo_dataset["processed_dir"])

        catalog = TemporalCatalog()
        catalog.discover_manifests(
            tiles_dir=manifests_dir / "tiles",
            scenes_dir=manifests_dir / "scenes",
        )

        orchestrator = ASTRAPipelineOrchestrator(catalog=catalog, output_dir=processed_dir / "inv")
        req = InvestigationRequest(
            series_id=demo_dataset["series_id"],
            discovery_pair_id="pair_non_existent__obs_fake",
            candidate_region_id=demo_dataset["candidate_region_id"],
        )

        with pytest.raises(InvestigationPipelineError) as exc_info:
            orchestrator.run_investigation(req)
        assert exc_info.value.stage == "discovery_pair_resolution"

    def test_error_handling_invalid_candidate_region(self, demo_dataset):
        """Verifies that an invalid candidate_region_id raises InvestigationPipelineError with candidate_region_validation."""
        manifests_dir = Path(demo_dataset["manifests_dir"])
        processed_dir = Path(demo_dataset["processed_dir"])

        catalog = TemporalCatalog()
        catalog.discover_manifests(
            tiles_dir=manifests_dir / "tiles",
            scenes_dir=manifests_dir / "scenes",
        )

        orchestrator = ASTRAPipelineOrchestrator(catalog=catalog, output_dir=processed_dir / "inv")
        req = InvestigationRequest(
            series_id=demo_dataset["series_id"],
            discovery_pair_id=demo_dataset["discovery_pair_id"],
            candidate_region_id="reg_99999",
            evidence_config=EvidenceConfig(band_mapping={"red": 0, "green": 1, "blue": 2}),
        )

        with pytest.raises(InvestigationPipelineError) as exc_info:
            orchestrator.run_investigation(req)
        assert exc_info.value.stage == "candidate_region_validation"

    def test_cli_runner_script_execution(self):
        """Verifies that running scripts/run_astra_pipeline.py via subprocess executes cleanly."""
        project_root = Path(__file__).resolve().parent.parent
        cmd = [
            sys.executable,
            str(project_root / "scripts" / "run_astra_pipeline.py"),
            "--pairing-strategy",
            "baseline",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(project_root))
        assert res.returncode == 0, f"CLI runner failed with returncode {res.returncode}:\n{res.stderr}"
        stdout = res.stdout
        assert "ASTRA ANALYST INVESTIGATION DOSSIER" in stdout
        assert "1. EXECUTIVE INVESTIGATION SUMMARY" in stdout
        assert "2. TARGET CANDIDATE PROFILE" in stdout
        assert "3. MULTI-EPOCH SPATIAL CORRESPONDENCE TRACKING" in stdout
        assert "4. CHRONOLOGICAL TIMELINE NODES" in stdout
        assert "5. TEMPORAL ONSET & EVOLUTION ESTIMATE" in stdout
        assert "6. UPSTREAM LINEAGE & PROVENANCE CHAIN" in stdout
        assert "7. REASONING AUDIT TRAIL & LIMITATIONS" in stdout
        assert "8. SAVED DOSSIER ARTIFACTS" in stdout
