"""ASTRA Phase M4F-E: End-to-End Investigation API Integration Test Suite.

Verifies the complete REST API contract for:
1. System Health & Telemetry (/api/v1/health, /health)
2. Temporal Series Discovery (/api/v1/temporal/series, /api/v1/temporal/series/{series_id})
3. Scene Pairs Generation (/api/v1/temporal/series/{series_id}/pairs)
4. Valid Investigation Orchestration (/api/v1/pipeline/investigate)
5. Cross-Epoch Candidate Spatial Correspondence (differing local region IDs)
6. Temporal Evidence Reasoning & Onset Interval
7. Structured Error Responses (validation failures, 404s, clean non-traceback payloads)
8. Strict Request Validation (rejection of unauthorized extra parameters)
9. Deterministic Repeatability (bit-for-bit, hash-for-hash identical responses)
10. CLI / API Investigation Parity (identical analytical identity)
"""

import json
from pathlib import Path
from typing import Dict, Tuple
import pytest
from starlette.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.api.v1.endpoints.pipeline import (
    get_pipeline_orchestrator,
    set_pipeline_orchestrator,
)
from backend.orchestrator.service import ASTRAPipelineOrchestrator
from scripts.generate_demo_dataset import generate_and_ingest_demo_dataset


@pytest.fixture(scope="module")
def api_client() -> TestClient:
    """Provides a fresh TestClient instance for API tests."""
    return TestClient(app)


@pytest.fixture(scope="module")
def demo_context() -> Dict[str, str]:
    """Ensures the deterministic 4-epoch demo dataset is available and returns canonical identifiers."""
    scenes_dir = settings.ASTRA_MANIFESTS_DIR / "scenes"
    demo_scenes = list(scenes_dir.glob("demo_synthetic_*.json")) if scenes_dir.exists() else []
    if len(demo_scenes) < 4:
        info = generate_and_ingest_demo_dataset(force=True)
    else:
        # Load active orchestrator and resolve demo identifiers
        orch = ASTRAPipelineOrchestrator()
        series_list = orch.catalog.list_series()
        if not series_list:
            orch.catalog.discover_manifests(
                tiles_dir=settings.ASTRA_MANIFESTS_DIR / "tiles",
                scenes_dir=settings.ASTRA_MANIFESTS_DIR / "scenes",
            )
            series_list = orch.catalog.list_series()

        target_series = next(
            (s for s in series_list if s.observation_count >= 4), series_list[0]
        )
        valid_pairs, _ = orch.catalog.generate_pairs(mode="adjacent")
        series_pairs = [p for p in valid_pairs if p.earlier_observation.observation_id in [o.observation_id for o in target_series.observations]]
        info = {
            "series_id": target_series.series_id,
            "discovery_pair_id": series_pairs[0].pair_id,
            "candidate_region_id": "reg_0002",
        }

    # Reset active orchestrator singleton to ensure fresh catalog discovery
    set_pipeline_orchestrator(None)
    return info


class TestAPIHealthAndDiscovery:
    """Tests system health and read-only temporal discovery endpoints."""

    def test_api_health_endpoint(self, api_client: TestClient):
        """Verifies GET /api/v1/health conforms to health contract."""
        res = api_client.get("/api/v1/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "healthy"
        assert data["service"] == "ASTRA Backend API"
        assert data["offline_mode"] is True
        assert "timestamp" in data
        assert "modules" in data
        assert data["modules"]["api"] == "healthy"

    def test_direct_health_alias(self, api_client: TestClient):
        """Verifies GET /health alias produces identical health metadata."""
        res = api_client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "healthy"

    def test_temporal_series_discovery(self, api_client: TestClient, demo_context: Dict[str, str]):
        """Verifies GET /api/v1/temporal/series returns all registered temporal series."""
        res = api_client.get("/api/v1/temporal/series")
        assert res.status_code == 200
        series_list = res.json()
        assert isinstance(series_list, list)
        assert len(series_list) >= 1

        demo_series = next((s for s in series_list if s["series_id"] == demo_context["series_id"]), None)
        assert demo_series is not None, f"Demo series '{demo_context['series_id']}' not in discovery response"
        assert demo_series["observation_count"] >= 4
        assert len(demo_series["observations"]) >= 4
        assert "bounds_wgs84" in demo_series
        assert demo_series["earliest_date"] is not None
        assert demo_series["latest_date"] is not None

    def test_temporal_series_detail_valid(self, api_client: TestClient, demo_context: Dict[str, str]):
        """Verifies GET /api/v1/temporal/series/{series_id} returns the requested series."""
        series_id = demo_context["series_id"]
        res = api_client.get(f"/api/v1/temporal/series/{series_id}")
        assert res.status_code == 200
        data = res.json()
        assert data["series_id"] == series_id
        assert data["observation_count"] >= 4
        assert len(data["observations"]) >= 4

    def test_temporal_series_detail_not_found(self, api_client: TestClient):
        """Verifies GET /api/v1/temporal/series/{series_id} returns structured 404 for unknown series."""
        res = api_client.get("/api/v1/temporal/series/series_nonexistent_9999")
        assert res.status_code == 404
        data = res.json()
        assert "detail" in data
        assert data["detail"]["error"] == "NOT_FOUND"
        assert "does not exist" in data["detail"]["message"]

    def test_temporal_series_pairs_generation(self, api_client: TestClient, demo_context: Dict[str, str]):
        """Verifies GET /api/v1/temporal/series/{series_id}/pairs generates valid chronological pairs."""
        series_id = demo_context["series_id"]
        res = api_client.get(f"/api/v1/temporal/series/{series_id}/pairs?mode=baseline")
        assert res.status_code == 200
        data = res.json()
        assert data["series_id"] == series_id
        assert data["mode"] == "baseline"
        assert len(data["valid_pairs"]) >= 3
        assert data["total_pairs"] >= 3

        for pair in data["valid_pairs"]:
            assert pair["pair_id"].startswith("pair_")
            assert pair["temporal_separation_seconds"] > 0
            assert pair["compatibility"]["is_compatible"] is True
            assert pair["spatial_overlap"]["overlap_ratio_iou"] >= 0.5


class TestAPIPipelineInvestigation:
    """Tests the complete end-to-end investigation API workflow."""

    def test_valid_investigation_request(self, api_client: TestClient, demo_context: Dict[str, str]):
        """Executes a valid POST /api/v1/pipeline/investigate on the demo dataset."""
        payload = {
            "series_id": demo_context["series_id"],
            "discovery_pair_id": demo_context["discovery_pair_id"],
            "candidate_region_id": demo_context["candidate_region_id"],
            "pairing_strategy": "baseline",
            "requested_format": "json",
        }
        res = api_client.post("/api/v1/pipeline/investigate", json=payload)
        assert res.status_code == 200, f"Investigation failed: {res.text}"
        dossier = res.json()

        # Complete InvestigationDossier contract verification
        assert dossier["status"] == "COMPLETED"
        assert dossier["investigation_id"].startswith("inv_")
        assert dossier["series_id"] == demo_context["series_id"]
        assert dossier["discovery_pair_id"] == demo_context["discovery_pair_id"]
        assert dossier["candidate_region_id"] == demo_context["candidate_region_id"]
        assert len(dossier["content_hash"]) >= 16
        assert dossier["provenance_id"].startswith("prov_inv_")
        assert "created_at" in dossier
        assert dossier["dossier_path"] is not None

        # Stage results ordering and completion
        assert len(dossier["stage_results"]) >= 5
        stage_names = [s["stage"] for s in dossier["stage_results"]]
        assert "series_resolution" in stage_names
        assert "discovery_pair_resolution" in stage_names
        assert any("m4b_change_detection" in s for s in stage_names)
        assert any("m4e_temporal_evidence" in s for s in stage_names)
        assert all(s["status"] == "COMPLETED" for s in dossier["stage_results"])

        # Lineage verification
        lineage = dossier["lineage"]
        assert len(lineage["scene_pair_ids"]) == 3
        assert len(lineage["change_detection_result_ids"]) == 3
        assert len(lineage["classification_ids"]) == 3
        assert len(lineage["suppression_ids"]) == 3
        assert lineage["temporal_evidence_id"] is not None
        assert len(lineage["upstream_hashes"]) >= 2

    def test_cross_epoch_spatial_correspondence_tracking(
        self, api_client: TestClient, demo_context: Dict[str, str]
    ):
        """Verifies candidate correspondence resolves physical target across differing local region IDs."""
        payload = {
            "series_id": demo_context["series_id"],
            "discovery_pair_id": demo_context["discovery_pair_id"],
            "candidate_region_id": demo_context["candidate_region_id"],
            "pairing_strategy": "baseline",
        }
        res = api_client.post("/api/v1/pipeline/investigate", json=payload)
        assert res.status_code == 200
        dossier = res.json()

        corr = dossier["lineage"]["candidate_correspondence"]
        assert len(corr) == 3, f"Expected 3 correspondence evaluations, found {len(corr)}"

        # Verify discovery candidate is reg_0002
        disc_pair = corr[demo_context["discovery_pair_id"]]
        assert disc_pair["matched_region_id"] == "reg_0002"
        assert disc_pair["relationship"] == "MATCHED"

        # Verify subsequent pairs resolve to different local region IDs (reg_0001, reg_0003)
        subsequent_matched_ids = [
            details["matched_region_id"]
            for pid, details in corr.items()
            if pid != demo_context["discovery_pair_id"]
        ]
        assert len(subsequent_matched_ids) == 2
        # Crucial: verify target receives different local region IDs
        assert any(mid != "reg_0002" for mid in subsequent_matched_ids), (
            f"Expected at least one differing local region ID, got: {subsequent_matched_ids}"
        )
        assert "reg_0001" in subsequent_matched_ids
        assert "reg_0003" in subsequent_matched_ids

        # All resolved spatially with high IoU
        for pid, details in corr.items():
            assert details["relationship"] == "MATCHED"
            assert details["metric_iou"] >= 0.30

    def test_temporal_evidence_reasoning_and_onset(
        self, api_client: TestClient, demo_context: Dict[str, str]
    ):
        """Verifies M4E earliest supporting observation, persistence, and onset interval."""
        payload = {
            "series_id": demo_context["series_id"],
            "discovery_pair_id": demo_context["discovery_pair_id"],
            "candidate_region_id": demo_context["candidate_region_id"],
            "pairing_strategy": "baseline",
        }
        res = api_client.post("/api/v1/pipeline/investigate", json=payload)
        assert res.status_code == 200
        dossier = res.json()

        tem = dossier["temporal_evidence"]
        assert tem is not None
        assert tem["temporal_support_status"] == "STRONG_TEMPORAL_SUPPORT"
        assert tem["confidence_tier"].lower() == "high"

        # Onset estimate interval (T1, T2]
        onset = tem["onset_estimate"]
        assert onset["interval_type"] == "BOUNDED_HALF_OPEN"
        assert onset["pre_change_observation_id"] is not None
        assert "2026-01-15" in onset["pre_change_date"]
        assert onset["earliest_support_observation_id"] is not None
        assert "2026-02-15" in onset["earliest_support_date"]

        # Timeline nodes
        nodes = tem["timeline_nodes"]
        assert len(nodes) == 4
        assert nodes[0]["node_status"] == "PRE_CHANGE_ABSENCE"
        assert nodes[1]["node_status"] == "EARLIEST_SUPPORTING"
        assert nodes[2]["node_status"] == "PERSISTENT_SUPPORT"
        assert nodes[3]["node_status"] == "PERSISTENT_SUPPORT"


class TestAPIErrorContracts:
    """Tests structured error contracts and strict schema validation."""

    def test_invalid_series_id_returns_structured_error(
        self, api_client: TestClient, demo_context: Dict[str, str]
    ):
        """Verifies non-existent series returns structured HTTP 400 with VALIDATION_ERROR."""
        payload = {
            "series_id": "series_nonexistent_abc",
            "discovery_pair_id": demo_context["discovery_pair_id"],
            "candidate_region_id": demo_context["candidate_region_id"],
        }
        res = api_client.post("/api/v1/pipeline/investigate", json=payload)
        assert res.status_code == 400
        data = res.json()
        assert "detail" in data
        detail = data["detail"]
        assert detail["error"] == "VALIDATION_ERROR"
        assert "does not exist" in detail["message"]
        assert detail["stage"] == "series_resolution"
        # Backwards compatibility check
        assert "details" in detail

    def test_invalid_discovery_pair_returns_structured_error(
        self, api_client: TestClient, demo_context: Dict[str, str]
    ):
        """Verifies unmatched discovery pair returns structured HTTP 400 with VALIDATION_ERROR."""
        payload = {
            "series_id": demo_context["series_id"],
            "discovery_pair_id": "pair_foreign_series_pair_001",
            "candidate_region_id": demo_context["candidate_region_id"],
        }
        res = api_client.post("/api/v1/pipeline/investigate", json=payload)
        assert res.status_code == 400
        data = res.json()
        assert "detail" in data
        detail = data["detail"]
        assert detail["error"] == "VALIDATION_ERROR"
        assert "does not exist" in detail["message"]
        assert detail["stage"] == "discovery_pair_resolution"

    def test_invalid_candidate_region_returns_structured_error(
        self, api_client: TestClient, demo_context: Dict[str, str]
    ):
        """Verifies non-existent candidate region returns structured HTTP 400 with VALIDATION_ERROR."""
        payload = {
            "series_id": demo_context["series_id"],
            "discovery_pair_id": demo_context["discovery_pair_id"],
            "candidate_region_id": "reg_9999_nonexistent",
        }
        res = api_client.post("/api/v1/pipeline/investigate", json=payload)
        assert res.status_code == 400
        data = res.json()
        assert "detail" in data
        detail = data["detail"]
        assert detail["error"] == "VALIDATION_ERROR"
        assert "does not exist in discovery change detection" in detail["message"]
        assert detail["stage"] == "candidate_region_validation"

    def test_strict_request_validation_extra_field_rejected(
        self, api_client: TestClient, demo_context: Dict[str, str]
    ):
        """Verifies unrecognized extra fields are strictly rejected with HTTP 422."""
        payload = {
            "series_id": demo_context["series_id"],
            "discovery_pair_id": demo_context["discovery_pair_id"],
            "candidate_region_id": demo_context["candidate_region_id"],
            "unauthorized_extra_param": "invalid_value",
        }
        res = api_client.post("/api/v1/pipeline/investigate", json=payload)
        assert res.status_code == 422


class TestAPIDeterminismAndParity:
    """Tests deterministic reproducibility and CLI/API parity."""

    def test_api_deterministic_repeatability(
        self, api_client: TestClient, demo_context: Dict[str, str]
    ):
        """Verifies consecutive API requests produce identical content hashes and IDs."""
        payload = {
            "series_id": demo_context["series_id"],
            "discovery_pair_id": demo_context["discovery_pair_id"],
            "candidate_region_id": demo_context["candidate_region_id"],
            "pairing_strategy": "baseline",
        }
        res1 = api_client.post("/api/v1/pipeline/investigate", json=payload)
        res2 = api_client.post("/api/v1/pipeline/investigate", json=payload)
        assert res1.status_code == 200
        assert res2.status_code == 200

        dossier1 = res1.json()
        dossier2 = res2.json()

        assert dossier1["investigation_id"] == dossier2["investigation_id"]
        assert dossier1["content_hash"] == dossier2["content_hash"]
        assert dossier1["provenance_id"] == dossier2["provenance_id"]
        assert (
            dossier1["temporal_evidence"]["temporal_evidence_id"]
            == dossier2["temporal_evidence"]["temporal_evidence_id"]
        )

    def test_api_cli_investigation_parity(
        self, api_client: TestClient, demo_context: Dict[str, str]
    ):
        """Verifies API investigation dossier matches CLI runner dossier on all analytical metrics."""
        payload = {
            "series_id": demo_context["series_id"],
            "discovery_pair_id": demo_context["discovery_pair_id"],
            "candidate_region_id": demo_context["candidate_region_id"],
            "pairing_strategy": "baseline",
        }
        api_res = api_client.post("/api/v1/pipeline/investigate", json=payload)
        assert api_res.status_code == 200
        api_dossier = api_res.json()

        # Check against persisted CLI dossier in data/processed/investigations
        dossier_dir = Path(settings.ASTRA_PROCESSED_DIR) / "investigations" / api_dossier["investigation_id"]
        dossier_path = dossier_dir / "dossier.json"
        assert dossier_path.exists(), f"Persisted dossier file '{dossier_path}' missing"

        with open(dossier_path, "r", encoding="utf-8") as f:
            cli_dossier = json.load(f)

        # Core identity parity
        assert api_dossier["investigation_id"] == cli_dossier["investigation_id"]
        assert api_dossier["content_hash"] == cli_dossier["content_hash"]
        assert api_dossier["provenance_id"] == cli_dossier["provenance_id"]
        assert api_dossier["status"] == cli_dossier["status"]

        # Analytical consensus
        api_tem = api_dossier["temporal_evidence"]
        cli_tem = cli_dossier["temporal_evidence"]
        assert api_tem["temporal_support_status"] == cli_tem["temporal_support_status"]
        assert api_tem["confidence_tier"] == cli_tem["confidence_tier"]
        assert (
            api_tem["onset_estimate"]["interval_type"]
            == cli_tem["onset_estimate"]["interval_type"]
        )
        assert (
            api_tem["onset_estimate"]["earliest_support_observation_id"]
            == cli_tem["onset_estimate"]["earliest_support_observation_id"]
        )
