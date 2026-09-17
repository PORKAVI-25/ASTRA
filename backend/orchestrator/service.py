"""ASTRA Pipeline Orchestration Service (Phase M4F).

Provides end-to-end orchestration connecting M4A Temporal Series, M4B Change Detection,
M4C-A Change Evidence, M4C-B Change Classification, M4D False-Alarm Suppression,
and M4E Temporal Evidence Reasoning into a deterministic, explainable pipeline.
"""

from datetime import datetime
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.config import settings
from backend.ml.change.scene_pairing import create_scene_pair, pair_observations
from backend.ml.change.temporal_catalog import TemporalCatalog
from backend.ml.change.types import ScenePair, TemporalObservation, TemporalSeries
from backend.ml.change_classification.service import ChangeClassificationEvidenceService
from backend.ml.change_detection.service import ChangeDetectionService
from backend.ml.change_detection.types import ChangeDetectionResult
from backend.ml.change_suppression.service import ChangeSuppressionService
from backend.ml.temporal_evidence.service import TemporalEvidenceService
from backend.ml.temporal_evidence.types import (
    CandidateRegionRef,
    PairwiseTemporalEvidenceInput,
)
from backend.orchestrator.correspondence import resolve_candidate_correspondence
from backend.orchestrator.types import (
    InvestigationDossier,
    InvestigationLineage,
    InvestigationPipelineError,
    InvestigationRequest,
    InvestigationStageResult,
    InvestigationStageStatus,
)
from geospatial.contracts import ProvenanceRecord

logger = logging.getLogger(__name__)


def compute_investigation_hash(
    request: InvestigationRequest,
    lineage: InvestigationLineage,
    temporal_evidence_id: Optional[str] = None,
) -> str:
    """Computes a deterministic 16-character hex hash from canonical investigation inputs."""
    sorted_pairs = ";".join(sorted(lineage.scene_pair_ids))
    sorted_cdrs = ";".join(sorted(lineage.change_detection_result_ids))
    sorted_evis = ";".join(sorted(lineage.evidence_ids))
    sorted_clss = ";".join(sorted(lineage.classification_ids))
    sorted_sups = ";".join(sorted(lineage.suppression_ids))
    sorted_hashes = ";".join(f"{k}={v}" for k, v in sorted(lineage.upstream_hashes.items()))

    cfg_parts: List[str] = []
    if request.change_detection_config:
        cfg_parts.append(f"cdr_cfg={request.change_detection_config.model_dump_json()}")
    if request.evidence_config:
        cfg_parts.append(f"evi_cfg={request.evidence_config.model_dump_json()}")
    if request.classifier_config:
        cfg_parts.append(f"cls_cfg={request.classifier_config.model_dump_json()}")
    if request.suppression_config:
        cfg_parts.append(f"sup_cfg={request.suppression_config.model_dump_json()}")
    if request.temporal_evidence_config:
        cfg_parts.append(f"tem_cfg={request.temporal_evidence_config.canonical_string()}")

    cfg_str = ";".join(sorted(cfg_parts))

    seed = (
        f"series={request.series_id}:"
        f"discovery_pair={request.discovery_pair_id}:"
        f"candidate_region={request.candidate_region_id}:"
        f"pairs={sorted_pairs}:"
        f"cdrs={sorted_cdrs}:"
        f"evis={sorted_evis}:"
        f"clss={sorted_clss}:"
        f"sups={sorted_sups}:"
        f"tem={temporal_evidence_id or 'none'}:"
        f"configs={cfg_str}:"
        f"hashes={sorted_hashes}"
    )
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


class ASTRAPipelineOrchestrator:
    """Deterministic, offline-first pipeline orchestrator coordinating M4A through M4E."""

    def __init__(
        self,
        catalog: Optional[TemporalCatalog] = None,
        change_detection_service: Optional[ChangeDetectionService] = None,
        evidence_service: Optional[ChangeClassificationEvidenceService] = None,
        suppression_service: Optional[ChangeSuppressionService] = None,
        temporal_evidence_service: Optional[TemporalEvidenceService] = None,
        known_pairs: Optional[Dict[str, ScenePair]] = None,
        output_dir: Optional[Path] = None,
        provenance_dir: Optional[Path] = None,
    ):
        self.catalog = catalog or TemporalCatalog()
        self.change_detection_service = change_detection_service or ChangeDetectionService()
        self.evidence_service = evidence_service or ChangeClassificationEvidenceService()
        self.suppression_service = suppression_service or ChangeSuppressionService()
        self.temporal_evidence_service = temporal_evidence_service or TemporalEvidenceService()
        self.known_pairs: Dict[str, ScenePair] = dict(known_pairs or {})
        self.output_dir = output_dir or settings.ASTRA_INVESTIGATIONS_DIR
        self.provenance_dir = provenance_dir or (settings.ASTRA_MANIFESTS_DIR / "provenance")

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.provenance_dir.mkdir(parents=True, exist_ok=True)

    def register_pair(self, pair: ScenePair) -> None:
        """Explicitly registers a pre-computed or mock ScenePair for pair resolution."""
        self.known_pairs[pair.pair_id] = pair

    def run_investigation(
        self,
        request: InvestigationRequest,
    ) -> InvestigationDossier:
        """Executes a deterministic multi-temporal investigation pipeline.

        Sequence:
        1. Resolve TemporalSeries using explicit series_id.
        2. Resolve explicitly supplied discovery_pair_id.
        3. Validate discovery pair belongs to requested series.
        4. Validate candidate_region_id against discovery M4B change detection result.
        5. Determine chronological pair sequence needed for temporal evidence.
        6-9. Run M4B -> M4C-A -> M4C-B -> M4D for all required pairs.
        10-12. Run M4E TemporalEvidenceService.
        13. Assemble InvestigationDossier with complete lineage and provenance.

        Raises:
            InvestigationPipelineError: If any stage fails, stops execution immediately.
        """
        stage_results: List[InvestigationStageResult] = []
        lineage = InvestigationLineage()

        # 1. Resolve TemporalSeries using explicit series_id
        series = self.catalog.get_series(request.series_id)
        if series is None and len(self.catalog.list_series()) == 0:
            # Attempt discovery if catalog has no series registered
            tiles_dir = (
                settings.ASTRA_MANIFESTS_DIR / "tiles"
                if (settings.ASTRA_MANIFESTS_DIR / "tiles").exists()
                else settings.ASTRA_PROCESSED_DIR / "tiles"
            )
            scenes_dir = settings.ASTRA_MANIFESTS_DIR / "scenes"
            if tiles_dir.exists() or scenes_dir.exists():
                self.catalog.discover_manifests(tiles_dir=tiles_dir, scenes_dir=scenes_dir)
                series = self.catalog.get_series(request.series_id)

        if series is None:
            err_msg = f"TemporalSeries '{request.series_id}' does not exist."
            stage_res = InvestigationStageResult(
                stage="series_resolution",
                status=InvestigationStageStatus.FAILED,
                error_message=err_msg,
            )
            stage_results.append(stage_res)
            raise InvestigationPipelineError(
                message=err_msg,
                stage="series_resolution",
                stage_result=stage_res,
                partial_lineage=lineage,
            )

        stage_results.append(
            InvestigationStageResult(
                stage="series_resolution",
                status=InvestigationStageStatus.COMPLETED,
                artifact_id=series.series_id,
                details={"observation_count": series.observation_count},
            )
        )

        series_obs_ids = {obs.observation_id for obs in series.observations}

        # 2 & 3. Resolve and validate discovery_pair_id
        discovery_pair: Optional[ScenePair] = None

        # Check known_pairs first
        if request.discovery_pair_id in self.known_pairs:
            pair_candidate = self.known_pairs[request.discovery_pair_id]
            earlier_in = pair_candidate.earlier_observation.observation_id in series_obs_ids
            later_in = pair_candidate.later_observation.observation_id in series_obs_ids
            if earlier_in and later_in:
                discovery_pair = pair_candidate
            else:
                err_msg = (
                    f"Discovery pair '{request.discovery_pair_id}' does not belong to "
                    f"requested series '{request.series_id}'."
                )
                stage_res = InvestigationStageResult(
                    stage="discovery_pair_resolution",
                    status=InvestigationStageStatus.FAILED,
                    error_message=err_msg,
                )
                stage_results.append(stage_res)
                raise InvestigationPipelineError(
                    message=err_msg,
                    stage="discovery_pair_resolution",
                    stage_result=stage_res,
                    partial_lineage=lineage,
                )

        # Check pairs derivable from series observations
        if discovery_pair is None and len(series.observations) >= 2:
            all_series_pairs = pair_observations(series.observations, mode="all_pairwise")
            for p in all_series_pairs:
                if p.pair_id == request.discovery_pair_id:
                    discovery_pair = p
                    break

        # If still not found, check if pair belongs to another series in the catalog
        if discovery_pair is None:
            other_catalog_pairs, _ = self.catalog.generate_pairs(mode="all_pairwise")
            belongs_to_other = any(p.pair_id == request.discovery_pair_id for p in other_catalog_pairs)
            if belongs_to_other:
                err_msg = (
                    f"Discovery pair '{request.discovery_pair_id}' belongs to another series, "
                    f"not requested series '{request.series_id}'."
                )
            else:
                err_msg = f"Discovery pair '{request.discovery_pair_id}' does not exist."

            stage_res = InvestigationStageResult(
                stage="discovery_pair_resolution",
                status=InvestigationStageStatus.FAILED,
                error_message=err_msg,
            )
            stage_results.append(stage_res)
            raise InvestigationPipelineError(
                message=err_msg,
                stage="discovery_pair_resolution",
                stage_result=stage_res,
                partial_lineage=lineage,
            )

        stage_results.append(
            InvestigationStageResult(
                stage="discovery_pair_resolution",
                status=InvestigationStageStatus.COMPLETED,
                artifact_id=discovery_pair.pair_id,
                details={
                    "earlier_observation": discovery_pair.earlier_observation.observation_id,
                    "later_observation": discovery_pair.later_observation.observation_id,
                },
            )
        )

        # 4. Run discovery pair change detection to validate candidate_region_id
        try:
            discovery_cdr = self.change_detection_service.run_detection(
                pair=discovery_pair,
                config=request.change_detection_config,
            )
            stage_results.append(
                InvestigationStageResult(
                    stage=f"m4b_change_detection_{discovery_pair.pair_id}",
                    status=InvestigationStageStatus.COMPLETED,
                    artifact_id=discovery_cdr.result_id,
                    provenance_id=discovery_cdr.provenance_id,
                    output_path=discovery_cdr.mask_path,
                    details={
                        "changed_pixels": discovery_cdr.metrics.changed_pixels,
                        "region_count": len(discovery_cdr.regions),
                    },
                )
            )
        except Exception as e:
            err_msg = f"Change detection failed on discovery pair '{discovery_pair.pair_id}': {e}"
            stage_res = InvestigationStageResult(
                stage=f"m4b_change_detection_{discovery_pair.pair_id}",
                status=InvestigationStageStatus.FAILED,
                error_message=err_msg,
            )
            stage_results.append(stage_res)
            raise InvestigationPipelineError(
                message=err_msg,
                stage="m4b_change_detection",
                stage_result=stage_res,
                partial_lineage=lineage,
            )

        available_regions = [r.region_id for r in discovery_cdr.regions]
        if request.candidate_region_id not in available_regions:
            err_msg = (
                f"Candidate region '{request.candidate_region_id}' does not exist in discovery "
                f"change detection result '{discovery_cdr.result_id}'. Available: {available_regions}"
            )
            stage_res = InvestigationStageResult(
                stage="candidate_region_validation",
                status=InvestigationStageStatus.FAILED,
                error_message=err_msg,
            )
            stage_results.append(stage_res)
            raise InvestigationPipelineError(
                message=err_msg,
                stage="candidate_region_validation",
                stage_result=stage_res,
                partial_lineage=lineage,
            )

        stage_results.append(
            InvestigationStageResult(
                stage="candidate_region_validation",
                status=InvestigationStageStatus.COMPLETED,
                artifact_id=request.candidate_region_id,
            )
        )

        # 5. Determine chronological pair sequence needed for temporal evidence
        sorted_obs = sorted(series.observations, key=lambda o: (o.acquisition_time, o.observation_id))
        disc_later_obs_id = discovery_pair.later_observation.observation_id
        disc_later_idx = next(
            (i for i, o in enumerate(sorted_obs) if o.observation_id == disc_later_obs_id),
            len(sorted_obs) - 1,
        )

        evaluated_pairs: List[ScenePair] = [discovery_pair]

        # For observations occurring after discovery, pair them to evaluate persistence
        for k in range(disc_later_idx + 1, len(sorted_obs)):
            obs_k = sorted_obs[k]
            if request.pairing_strategy == "baseline":
                earlier_obs = discovery_pair.earlier_observation
            else:
                earlier_obs = sorted_obs[k - 1]

            pair_id_key = f"pair_{earlier_obs.observation_id}__{obs_k.observation_id}"
            if pair_id_key in self.known_pairs:
                sub_pair = self.known_pairs[pair_id_key]
            else:
                sub_pair = create_scene_pair(earlier_obs, obs_k)
            evaluated_pairs.append(sub_pair)

        # Helper to run a pair through M4B (if not cached) -> M4C-A -> M4C-B -> M4D
        def _execute_pair_pipeline(
            pair: ScenePair,
            existing_cdr: Optional[ChangeDetectionResult] = None,
        ) -> PairwiseTemporalEvidenceInput:
            # M4B Change Detection
            if existing_cdr is not None:
                cdr = existing_cdr
            else:
                try:
                    cdr = self.change_detection_service.run_detection(
                        pair=pair,
                        config=request.change_detection_config,
                    )
                    stage_results.append(
                        InvestigationStageResult(
                            stage=f"m4b_change_detection_{pair.pair_id}",
                            status=InvestigationStageStatus.COMPLETED,
                            artifact_id=cdr.result_id,
                            provenance_id=cdr.provenance_id,
                            output_path=cdr.mask_path,
                            details={
                                "changed_pixels": cdr.metrics.changed_pixels,
                                "region_count": len(cdr.regions),
                            },
                        )
                    )
                except Exception as ex:
                    err_text = f"M4B Change detection failed on pair '{pair.pair_id}': {ex}"
                    stage_r = InvestigationStageResult(
                        stage=f"m4b_change_detection_{pair.pair_id}",
                        status=InvestigationStageStatus.FAILED,
                        error_message=err_text,
                    )
                    stage_results.append(stage_r)
                    raise InvestigationPipelineError(
                        message=err_text,
                        stage=f"m4b_change_detection_{pair.pair_id}",
                        stage_result=stage_r,
                        partial_lineage=lineage,
                    )

            # M4C-A Evidence Extraction
            try:
                evidence = self.evidence_service.extract_evidence(
                    scene_pair=pair,
                    change_result=cdr,
                    config=request.evidence_config,
                )
                stage_results.append(
                    InvestigationStageResult(
                        stage=f"m4c_evidence_extraction_{pair.pair_id}",
                        status=InvestigationStageStatus.COMPLETED,
                        artifact_id=evidence.evidence_id,
                        provenance_id=evidence.provenance_id,
                        details={"extracted_regions": len(evidence.regions)},
                    )
                )
            except Exception as ex:
                err_text = f"M4C-A Evidence extraction failed on pair '{pair.pair_id}': {ex}"
                stage_r = InvestigationStageResult(
                    stage=f"m4c_evidence_extraction_{pair.pair_id}",
                    status=InvestigationStageStatus.FAILED,
                    error_message=err_text,
                )
                stage_results.append(stage_r)
                raise InvestigationPipelineError(
                    message=err_text,
                    stage=f"m4c_evidence_extraction_{pair.pair_id}",
                    stage_result=stage_r,
                    partial_lineage=lineage,
                )

            # M4C-B Classification
            try:
                classification = self.evidence_service.classify_evidence(
                    evidence=evidence,
                    config=request.classifier_config,
                )
                stage_results.append(
                    InvestigationStageResult(
                        stage=f"m4c_classification_{pair.pair_id}",
                        status=InvestigationStageStatus.COMPLETED,
                        artifact_id=classification.classification_id,
                        provenance_id=classification.provenance_id,
                        details={"classified_regions": len(classification.classifications)},
                    )
                )
            except Exception as ex:
                err_text = f"M4C-B Classification failed on pair '{pair.pair_id}': {ex}"
                stage_r = InvestigationStageResult(
                    stage=f"m4c_classification_{pair.pair_id}",
                    status=InvestigationStageStatus.FAILED,
                    error_message=err_text,
                )
                stage_results.append(stage_r)
                raise InvestigationPipelineError(
                    message=err_text,
                    stage=f"m4c_classification_{pair.pair_id}",
                    stage_result=stage_r,
                    partial_lineage=lineage,
                )

            # M4D False-Alarm Suppression
            try:
                suppression = self.suppression_service.suppress_false_alarms(
                    evidence=evidence,
                    classification=classification,
                    scene_pair=pair,
                    change_result=cdr,
                    config=request.suppression_config,
                )
                stage_results.append(
                    InvestigationStageResult(
                        stage=f"m4d_suppression_{pair.pair_id}",
                        status=InvestigationStageStatus.COMPLETED,
                        artifact_id=suppression.suppression_id,
                        provenance_id=suppression.provenance_id,
                        output_path=suppression.filtered_change_mask_path,
                        details={
                            "retained_count": suppression.metrics.retained_count,
                            "flagged_count": suppression.metrics.flagged_count,
                            "suppressed_count": suppression.metrics.suppressed_count,
                        },
                    )
                )
            except Exception as ex:
                err_text = f"M4D Suppression failed on pair '{pair.pair_id}': {ex}"
                stage_r = InvestigationStageResult(
                    stage=f"m4d_suppression_{pair.pair_id}",
                    status=InvestigationStageStatus.FAILED,
                    error_message=err_text,
                )
                stage_results.append(stage_r)
                raise InvestigationPipelineError(
                    message=err_text,
                    stage=f"m4d_suppression_{pair.pair_id}",
                    stage_result=stage_r,
                    partial_lineage=lineage,
                )

            # Update lineage
            lineage.scene_pair_ids.append(pair.pair_id)
            lineage.change_detection_result_ids.append(cdr.result_id)
            lineage.evidence_ids.append(evidence.evidence_id)
            lineage.classification_ids.append(classification.classification_id)
            lineage.suppression_ids.append(suppression.suppression_id)
            if evidence.source_hashes:
                lineage.upstream_hashes.update(evidence.source_hashes)

            return PairwiseTemporalEvidenceInput(
                scene_pair_id=pair.pair_id,
                change_detection_result_id=cdr.result_id,
                evidence_id=evidence.evidence_id,
                classification_id=classification.classification_id,
                suppression_id=suppression.suppression_id,
                suppression_result=suppression,
                change_detection_result=cdr,
                evidence=evidence,
                classification=classification,
            )

        # Extract discovery candidate ChangeRegion for spatial correspondence
        discovery_candidate_region: Optional[ChangeRegion] = None
        for r in discovery_cdr.regions:
            if r.region_id == request.candidate_region_id:
                discovery_candidate_region = r
                break

        # 6-9. Run pairwise pipelines
        discovery_pairwise = _execute_pair_pipeline(discovery_pair, existing_cdr=discovery_cdr)
        discovery_pairwise.matched_region_id = request.candidate_region_id
        lineage.candidate_correspondence[discovery_pair.pair_id] = {
            "reference_candidate_id": request.candidate_region_id,
            "target_pair_id": discovery_pair.pair_id,
            "status": "EXACT_REFERENCE",
            "relationship": "MATCHED",
            "matched_region_id": request.candidate_region_id,
            "metric_iou": 1.0,
            "centroid_distance_m": 0.0,
            "candidate_scores": {request.candidate_region_id: 1.0},
            "resolution_notes": ["Discovery candidate reference region."],
        }

        min_iou = (
            request.temporal_evidence_config.min_bbox_iou_threshold
            if request.temporal_evidence_config
            else 0.30
        )
        max_dist = (
            request.temporal_evidence_config.max_centroid_distance_m
            if request.temporal_evidence_config
            else 60.0
        )

        subsequent_pairwise_list: List[PairwiseTemporalEvidenceInput] = []
        for sub_pair in evaluated_pairs[1:]:
            sub_input = _execute_pair_pipeline(sub_pair)

            # Resolve spatial correspondence against discovery candidate reference
            corr_res = resolve_candidate_correspondence(
                reference_region=discovery_candidate_region,
                target_cdr=sub_input.change_detection_result,
                target_pair_id=sub_pair.pair_id,
                min_bbox_iou_threshold=min_iou,
                max_centroid_distance_m=max_dist,
                reference_crs=discovery_pair.earlier_observation.crs,
                target_crs=sub_pair.earlier_observation.crs,
            )

            sub_input.matched_region_id = corr_res.matched_region_id
            sub_input.spatial_correspondence = corr_res.spatial_correspondence

            lineage.candidate_correspondence[sub_pair.pair_id] = {
                "reference_candidate_id": request.candidate_region_id,
                "target_pair_id": sub_pair.pair_id,
                "status": corr_res.status.value,
                "relationship": corr_res.relationship.value,
                "matched_region_id": corr_res.matched_region_id,
                "metric_iou": corr_res.metric_iou,
                "centroid_distance_m": corr_res.centroid_distance_m,
                "candidate_scores": corr_res.candidate_scores,
                "resolution_notes": corr_res.resolution_notes,
            }

            stage_results.append(
                InvestigationStageResult(
                    stage=f"candidate_correspondence_{sub_pair.pair_id}",
                    status=InvestigationStageStatus.COMPLETED,
                    artifact_id=corr_res.matched_region_id,
                    details={
                        "reference_candidate_id": request.candidate_region_id,
                        "target_pair_id": sub_pair.pair_id,
                        "status": corr_res.status.value,
                        "relationship": corr_res.relationship.value,
                        "matched_region_id": corr_res.matched_region_id,
                        "metric_iou": corr_res.metric_iou,
                        "centroid_distance_m": corr_res.centroid_distance_m,
                        "resolution_notes": corr_res.resolution_notes,
                    },
                )
            )

            subsequent_pairwise_list.append(sub_input)

        # 10-12. Run M4E TemporalEvidenceService
        candidate_ref = CandidateRegionRef(
            change_detection_result_id=discovery_cdr.result_id,
            scene_pair_id=discovery_pair.pair_id,
            region_id=request.candidate_region_id,
        )

        try:
            temporal_res = self.temporal_evidence_service.evaluate_temporal_evidence(
                candidate_ref=candidate_ref,
                series=series,
                discovery_pair_evidence=discovery_pairwise,
                pairwise_evidence=subsequent_pairwise_list,
                config=request.temporal_evidence_config,
            )
            lineage.temporal_evidence_id = temporal_res.temporal_evidence_id
            lineage.upstream_hashes.update(temporal_res.upstream_hashes)
            stage_results.append(
                InvestigationStageResult(
                    stage="m4e_temporal_evidence",
                    status=InvestigationStageStatus.COMPLETED,
                    artifact_id=temporal_res.temporal_evidence_id,
                    provenance_id=temporal_res.provenance_id,
                    details={
                        "temporal_support_status": temporal_res.temporal_support_status.value,
                        "confidence_tier": temporal_res.confidence_tier.value,
                        "onset_interval_type": temporal_res.onset_estimate.interval_type.value,
                    },
                )
            )
        except Exception as e:
            err_msg = f"M4E Temporal evidence evaluation failed: {e}"
            stage_res = InvestigationStageResult(
                stage="m4e_temporal_evidence",
                status=InvestigationStageStatus.FAILED,
                error_message=err_msg,
            )
            stage_results.append(stage_res)
            raise InvestigationPipelineError(
                message=err_msg,
                stage="m4e_temporal_evidence",
                stage_result=stage_res,
                partial_lineage=lineage,
            )

        # 13. Assemble InvestigationDossier
        content_hash = compute_investigation_hash(
            request=request,
            lineage=lineage,
            temporal_evidence_id=temporal_res.temporal_evidence_id,
        )
        investigation_id = f"inv_{content_hash}"
        provenance_id = f"prov_inv_{content_hash}"

        # Deterministic created_at anchored to latest observation
        deterministic_created_at = max(obs.acquisition_time for obs in sorted_obs)

        # Persist dossier
        output_dir = Path(request.output_dir) if request.output_dir else self.output_dir
        inv_dir = output_dir / investigation_id
        inv_dir.mkdir(parents=True, exist_ok=True)
        dossier_path = inv_dir / "dossier.json"

        dossier = InvestigationDossier(
            investigation_id=investigation_id,
            request=request,
            series_id=request.series_id,
            discovery_pair_id=request.discovery_pair_id,
            candidate_region_id=request.candidate_region_id,
            temporal_evidence_id=temporal_res.temporal_evidence_id,
            stage_results=stage_results,
            lineage=lineage,
            provenance_id=provenance_id,
            created_at=deterministic_created_at,
            content_hash=content_hash,
            temporal_evidence=temporal_res,
            status="COMPLETED",
            dossier_path=str(dossier_path),
        )

        dossier_path.write_text(dossier.model_dump_json(indent=2), encoding="utf-8")

        # Persist ProvenanceRecord
        source_scene_id = sorted_obs[0].scene_id if sorted_obs else "unknown_scene"
        for obs in sorted_obs:
            if obs.observation_id == discovery_pair.later_observation.observation_id:
                source_scene_id = obs.scene_id
                break

        prov_record = ProvenanceRecord(
            provenance_id=provenance_id,
            source_scene_id=source_scene_id,
            target_tile_id=series.target_id,
            processing_stage="pipeline_investigation_orchestration",
            pipeline_version="0.1.0",
            parameters={
                "investigation_id": investigation_id,
                "series_id": request.series_id,
                "discovery_pair_id": request.discovery_pair_id,
                "candidate_region_id": request.candidate_region_id,
                "lineage": lineage.model_dump(),
                "content_hash": content_hash,
                "dossier_path": str(dossier_path),
            },
            executed_by="astra.orchestrator",
            timestamp=deterministic_created_at,
        )

        prov_path = self.provenance_dir / f"{provenance_id}.json"
        prov_path.write_text(prov_record.model_dump_json(indent=2), encoding="utf-8")

        return dossier
