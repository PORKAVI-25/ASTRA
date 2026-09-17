"""ASTRA Phase M4E: Temporal Evidence Reasoner Service.

Orchestrates multi-temporal candidate change evaluation across TemporalSeries
and upstream M4A, M4B, M4C-A, M4C-B, and M4D artifact chains.
Enforces deterministic hashing, full provenance tracking, and offline persistence.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from geospatial.contracts import ProvenanceRecord
from backend.config import settings
from backend.ml.change.types import TemporalObservation, TemporalSeries
from backend.ml.change_detection.types import ChangeRegion
from backend.ml.temporal_evidence.chronology import (
    align_pairwise_evidence_to_observations,
    check_temporal_gaps,
    order_and_validate_observations,
)
from backend.ml.temporal_evidence.evaluator import evaluate_node_support
from backend.ml.temporal_evidence.timeline import assemble_timeline_and_trajectory
from backend.ml.temporal_evidence.types import (
    CandidateRegionRef,
    PairwiseTemporalEvidenceInput,
    TemporalEvidenceConfig,
    TemporalEvidenceNode,
    TemporalEvidenceResult,
)


def compute_temporal_evidence_hash(
    series_id: str,
    candidate_ref: CandidateRegionRef,
    evaluator_id: str,
    evaluator_version: str,
    config: TemporalEvidenceConfig,
    pairwise_inputs: List[PairwiseTemporalEvidenceInput],
    upstream_hashes: Dict[str, str],
) -> str:
    """Computes a 16-character deterministic hex hash from complete lineage inputs."""
    sorted_pairs = ";".join(sorted(p.scene_pair_id for p in pairwise_inputs))
    sorted_suppressions = ";".join(sorted(p.suppression_id for p in pairwise_inputs))
    sorted_hashes = ";".join(f"{k}={v}" for k, v in sorted(upstream_hashes.items()))

    seed = (
        f"{series_id}:"
        f"{candidate_ref.canonical_id}:"
        f"{evaluator_id}:"
        f"{evaluator_version}:"
        f"{config.canonical_string()}:"
        f"{sorted_pairs}:"
        f"{sorted_suppressions}:"
        f"{sorted_hashes}"
    )
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


class TemporalEvidenceService:
    """Orchestration service for Phase M4E Temporal Evidence Reasoning."""

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        provenance_dir: Optional[Path] = None,
    ) -> None:
        self.output_dir = output_dir or settings.ASTRA_TEMPORAL_EVIDENCE_DIR
        self.provenance_dir = provenance_dir or (settings.ASTRA_MANIFESTS_DIR / "provenance")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.provenance_dir.mkdir(parents=True, exist_ok=True)

    def evaluate_temporal_evidence(
        self,
        candidate_ref: CandidateRegionRef,
        series: TemporalSeries,
        discovery_pair_evidence: PairwiseTemporalEvidenceInput,
        pairwise_evidence: Optional[List[PairwiseTemporalEvidenceInput]] = None,
        config: Optional[TemporalEvidenceConfig] = None,
    ) -> TemporalEvidenceResult:
        """Evaluates a candidate change region across an ordered TemporalSeries."""
        cfg = config or TemporalEvidenceConfig()
        pairwise_inputs = [discovery_pair_evidence] + (pairwise_evidence or [])

        # 1. Enforce discovery pair consistency with candidate reference
        if discovery_pair_evidence.scene_pair_id != candidate_ref.scene_pair_id:
            raise ValueError(
                f"Discovery pair ID mismatch: discovery_pair_evidence.scene_pair_id "
                f"'{discovery_pair_evidence.scene_pair_id}' != candidate_ref.scene_pair_id '{candidate_ref.scene_pair_id}'."
            )

        if discovery_pair_evidence.change_detection_result_id != candidate_ref.change_detection_result_id:
            raise ValueError(
                f"Discovery change detection result ID mismatch: discovery_pair_evidence.change_detection_result_id "
                f"'{discovery_pair_evidence.change_detection_result_id}' != candidate_ref.change_detection_result_id '{candidate_ref.change_detection_result_id}'."
            )

        # 2. Chronological ordering and simultaneous observation detection
        sorted_obs, simultaneous_ids, chrono_warnings = order_and_validate_observations(series.observations)
        if not sorted_obs:
            raise ValueError(f"Temporal series '{series.series_id}' contains zero observations.")

        # 3. Align pairwise inputs to timeline observations
        (
            obs_id_to_pairwise,
            disc_earlier_id,
            disc_later_id,
            alignment_errors,
        ) = align_pairwise_evidence_to_observations(
            observations=sorted_obs,
            discovery_pair_evidence=discovery_pair_evidence,
            pairwise_evidence=pairwise_evidence or [],
            candidate_ref=candidate_ref,
        )
        if alignment_errors:
            raise ValueError(f"Timeline alignment failed: {'; '.join(alignment_errors)}")

        # 4. Resolve candidate ChangeRegion geometry from discovery M4B result
        candidate_region: Optional[ChangeRegion] = None
        if discovery_pair_evidence.change_detection_result:
            for reg in discovery_pair_evidence.change_detection_result.regions:
                if reg.region_id == candidate_ref.region_id:
                    candidate_region = reg
                    break

        # 5. Extract baseline reference sensor identity for cross-sensor checks
        discovery_sensor = "unknown"
        if disc_earlier_id:
            for obs in sorted_obs:
                if obs.observation_id == disc_earlier_id:
                    discovery_sensor = obs.sensor
                    break
        if discovery_sensor == "unknown" and sorted_obs:
            discovery_sensor = sorted_obs[0].sensor

        # 6. Evaluate each observation node in the timeline
        timeline_nodes: List[TemporalEvidenceNode] = []
        for obs in sorted_obs:
            is_simul = obs.observation_id in simultaneous_ids
            is_pre = (obs.observation_id == disc_earlier_id)
            pairwise_for_obs = obs_id_to_pairwise.get(obs.observation_id)

            node = evaluate_node_support(
                observation=obs,
                candidate_ref=candidate_ref,
                candidate_region=candidate_region,
                pairwise_input=pairwise_for_obs,
                is_pre_change_candidate=is_pre,
                is_simultaneous=is_simul,
                discovery_sensor=discovery_sensor,
                config=cfg,
            )
            timeline_nodes.append(node)

        # 7. Assemble timeline, determine earliest support, onset, and metrics
        (
            final_nodes,
            support_status,
            confidence_tier,
            onset_estimate,
            category_evolution,
            metrics,
            decision_reasons,
            evidence_limitations,
        ) = assemble_timeline_and_trajectory(
            nodes=timeline_nodes,
            candidate_ref=candidate_ref,
            config=cfg,
            total_series_observations=len(sorted_obs),
        )

        # 8. Check temporal gaps
        gap_warnings = check_temporal_gaps(sorted_obs, max_gap_days=cfg.max_temporal_gap_days)
        evidence_limitations.extend(gap_warnings)
        evidence_limitations.extend(chrono_warnings)

        # 9. Aggregate upstream input hashes
        upstream_hashes: Dict[str, str] = {}
        for p in pairwise_inputs:
            if p.evidence and p.evidence.source_hashes:
                upstream_hashes.update(p.evidence.source_hashes)
            else:
                upstream_hashes[f"pair_{p.scene_pair_id}"] = hashlib.sha256(p.scene_pair_id.encode("utf-8")).hexdigest()

        # 10. Compute deterministic document and provenance identities
        content_hash = compute_temporal_evidence_hash(
            series_id=series.series_id,
            candidate_ref=candidate_ref,
            evaluator_id=cfg.evaluator_id,
            evaluator_version=cfg.evaluator_version,
            config=cfg,
            pairwise_inputs=pairwise_inputs,
            upstream_hashes=upstream_hashes,
        )
        temporal_evidence_id = f"tem_{content_hash}"
        provenance_id = f"prov_tem_{content_hash}"

        # 11. Deterministic created_at timestamp derived from latest observation
        deterministic_created_at = max(obs.acquisition_time for obs in sorted_obs)

        # 12. Assemble final result
        result = TemporalEvidenceResult(
            temporal_evidence_id=temporal_evidence_id,
            candidate_ref=candidate_ref,
            series_id=series.series_id,
            evaluator_id=cfg.evaluator_id,
            evaluator_version=cfg.evaluator_version,
            config=cfg,
            temporal_support_status=support_status,
            confidence_tier=confidence_tier,
            onset_estimate=onset_estimate,
            category_evolution=category_evolution,
            metrics=metrics,
            timeline_nodes=final_nodes,
            decision_reasons=decision_reasons,
            evidence_limitations=evidence_limitations,
            discovery_scene_pair_id=candidate_ref.scene_pair_id,
            evaluated_scene_pair_ids=[p.scene_pair_id for p in pairwise_inputs],
            evaluated_change_detection_result_ids=[p.change_detection_result_id for p in pairwise_inputs],
            evaluated_evidence_ids=[p.evidence_id for p in pairwise_inputs],
            evaluated_classification_ids=[p.classification_id for p in pairwise_inputs if p.classification_id],
            upstream_suppression_ids=[p.suppression_id for p in pairwise_inputs],
            upstream_hashes=upstream_hashes,
            provenance_id=provenance_id,
            created_at=deterministic_created_at,
        )

        # 13. Persist structured JSON artifact
        target_dir = self.output_dir / temporal_evidence_id
        target_dir.mkdir(parents=True, exist_ok=True)
        json_file = target_dir / "temporal_evidence.json"
        json_file.write_text(result.model_dump_json(indent=2), encoding="utf-8")

        # 14. Record immutable ProvenanceRecord conforming to geospatial contracts
        # source_scene_id MUST be an actual satellite scene_id
        discovery_scene_id = "unknown_scene"
        for obs in sorted_obs:
            if obs.observation_id == disc_later_id or obs.observation_id == disc_earlier_id:
                discovery_scene_id = obs.scene_id
                break
        if discovery_scene_id == "unknown_scene" and sorted_obs:
            discovery_scene_id = sorted_obs[0].scene_id

        prov_record = ProvenanceRecord(
            provenance_id=provenance_id,
            source_scene_id=discovery_scene_id,  # Real satellite scene_id
            target_tile_id=series.target_id,     # Geographic anchor / tile ID
            processing_stage="temporal_evidence_evaluation",
            pipeline_version="0.1.0",
            parameters={
                "candidate_ref": candidate_ref.model_dump(),
                "series_id": series.series_id,
                "evaluator_id": cfg.evaluator_id,
                "evaluator_version": cfg.evaluator_version,
                "config": cfg.model_dump(),
                "discovery_scene_pair_id": candidate_ref.scene_pair_id,
                "evaluated_scene_pair_ids": [p.scene_pair_id for p in pairwise_inputs],
                "evaluated_change_detection_result_ids": [p.change_detection_result_id for p in pairwise_inputs],
                "evaluated_evidence_ids": [p.evidence_id for p in pairwise_inputs],
                "evaluated_classification_ids": [p.classification_id for p in pairwise_inputs if p.classification_id],
                "upstream_suppression_ids": [p.suppression_id for p in pairwise_inputs],
                "upstream_hashes": upstream_hashes,
                "temporal_support_status": support_status.value,
                "onset_interval_type": onset_estimate.interval_type.value,
                "artifact_path": str(json_file),
            },
            executed_by="astra.ml.temporal_evidence.evaluator",
            timestamp=deterministic_created_at,
        )

        prov_file = self.provenance_dir / f"{provenance_id}.json"
        prov_file.write_text(prov_record.model_dump_json(indent=2), encoding="utf-8")

        return result

    def get_temporal_evidence(self, temporal_evidence_id: str) -> Optional[TemporalEvidenceResult]:
        """Retrieves a persisted TemporalEvidenceResult by its deterministic identifier."""
        json_file = self.output_dir / temporal_evidence_id / "temporal_evidence.json"
        if not json_file.exists():
            return None
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            return TemporalEvidenceResult.model_validate(data)
        except Exception:
            return None
