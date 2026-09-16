"""ASTRA Change Suppression Service (Phase M4D).

Orchestrates deterministic false-alarm screening, tri-state mask generation,
artifact serialization, and immutable provenance recording conforming to ASTRA-DC-v0.1.
"""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import numpy as np

from backend.config import settings
from backend.ml.change.types import ScenePair
from backend.ml.change_classification.types import (
    ChangeClassificationResult,
    ChangeEvidence,
    RegionClassification,
)
from backend.ml.change_detection.types import ChangeDetectionResult
from backend.ml.change_suppression.decision import evaluate_region_suppression
from backend.ml.change_suppression.mask import generate_filtered_change_mask
from backend.ml.change_suppression.types import (
    RegionSuppression,
    SuppressionConfig,
    SuppressionDecision,
    SuppressionMetrics,
    SuppressionResult,
)
from geospatial.contracts import ProvenanceRecord


class ChangeSuppressionService:
    """Service managing false-alarm screening, artifact persistence, and lineage tracking."""

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        provenance_dir: Optional[Path] = None,
    ):
        self.output_dir = output_dir or settings.ASTRA_CHANGE_SUPPRESSION_DIR
        self.provenance_dir = provenance_dir or (settings.ASTRA_MANIFESTS_DIR / "provenance")

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.provenance_dir.mkdir(parents=True, exist_ok=True)

    def suppress_false_alarms(
        self,
        evidence: ChangeEvidence,
        classification: Optional[ChangeClassificationResult] = None,
        scene_pair: Optional[ScenePair] = None,
        change_result: Optional[ChangeDetectionResult] = None,
        change_mask: Optional[np.ndarray] = None,
        config: Optional[SuppressionConfig] = None,
        auxiliary_data: Optional[Dict[str, Any]] = None,
    ) -> SuppressionResult:
        """Executes conservative false-alarm screening across all candidate regions.

        Args:
            evidence: M4C-A multi-modal feature evidence document.
            classification: Optional M4C-B change classification result.
            scene_pair: Optional M4A ScenePair for cross-sensor or temporal metadata.
            change_result: Optional M4B ChangeDetectionResult for region coordinates.
            change_mask: Optional 2D binary change mask array from M4B.
            config: Optional configuration overrides.
            auxiliary_data: Optional dictionary with global/scene metadata (e.g. solar_azimuth).

        Returns:
            SuppressionResult document conforming to ASTRA-DC-v0.1.
        """
        cfg = config or SuppressionConfig()
        global_aux = dict(auxiliary_data or {})

        # Cross-sensor awareness from ScenePair if present
        if scene_pair is not None:
            if scene_pair.compatibility.is_cross_sensor:
                global_aux["is_cross_sensor"] = True

        # Build mapping for M4C-B classifications if provided
        cls_map: Dict[str, RegionClassification] = {}
        if classification is not None:
            for rc in classification.classifications:
                cls_map[rc.region_id] = rc

        # Build region mapping for M4B ChangeRegions if available
        reg_map = {}
        if change_result and change_result.regions:
            for r in change_result.regions:
                reg_map[r.region_id] = r

        regions_suppression: List[RegionSuppression] = []
        artifact_counts: Dict[str, int] = {}

        total_area = 0
        retained_area = 0
        flagged_area = 0
        suppressed_area = 0

        # Exact 1-to-1 processing: zero silent drops
        for reg_feat in evidence.regions:
            reg_id = reg_feat.region_id
            reg_area = reg_feat.spatial.area_px
            total_area += reg_area

            # Retrieve prior classification
            prior_cls = cls_map.get(reg_id)
            orig_cat = prior_cls.category.value if prior_cls else "unknown"
            orig_conf = prior_cls.confidence_tier.value if prior_cls else "uncertain"

            # Per-region auxiliary data inheritance
            reg_aux = dict(global_aux)
            if prior_cls and "auxiliary_data" in prior_cls.candidate_scores:
                reg_aux.update(prior_cls.candidate_scores.get("auxiliary_data", {}))

            # Run deterministic decision engine
            reg_sup = evaluate_region_suppression(
                region=reg_feat,
                original_category=orig_cat,
                original_confidence_tier=orig_conf,
                config=cfg,
                aux=reg_aux,
            )
            regions_suppression.append(reg_sup)

            # Accumulate metrics
            if reg_sup.decision == SuppressionDecision.RETAINED:
                retained_area += reg_area
            elif reg_sup.decision == SuppressionDecision.FLAGGED:
                flagged_area += reg_area
            elif reg_sup.decision == SuppressionDecision.SUPPRESSED:
                suppressed_area += reg_area

            if reg_sup.primary_attribution is not None:
                attr_name = reg_sup.primary_attribution.value
                artifact_counts[attr_name] = artifact_counts.get(attr_name, 0) + 1

        total_input = len(regions_suppression)
        retained_cnt = sum(1 for r in regions_suppression if r.decision == SuppressionDecision.RETAINED)
        flagged_cnt = sum(1 for r in regions_suppression if r.decision == SuppressionDecision.FLAGGED)
        suppressed_cnt = sum(1 for r in regions_suppression if r.decision == SuppressionDecision.SUPPRESSED)
        insufficient_cnt = sum(1 for r in regions_suppression if r.decision == SuppressionDecision.INSUFFICIENT_EVIDENCE)

        suppression_rate = float(suppressed_cnt / max(1, total_input))

        metrics = SuppressionMetrics(
            total_input_regions=total_input,
            retained_count=retained_cnt,
            flagged_count=flagged_cnt,
            suppressed_count=suppressed_cnt,
            insufficient_evidence_count=insufficient_cnt,
            suppression_rate=round(suppression_rate, 4),
            total_area_px=total_area,
            retained_area_px=retained_area,
            flagged_area_px=flagged_area,
            suppressed_area_px=suppressed_area,
            artifact_counts=artifact_counts,
        )

        # Deterministic document and provenance identity
        cls_id_str = classification.classification_id if classification else "none"
        seed = f"{evidence.evidence_id}:{cls_id_str}:{cfg.suppressor_id}:{cfg.suppressor_version}:{total_input}"
        content_hash = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
        suppression_id = f"sup_{content_hash}"
        provenance_id = f"prov_sup_{content_hash}"

        # Target directory setup
        target_dir = self.output_dir / suppression_id
        target_dir.mkdir(parents=True, exist_ok=True)

        # Serialize filtered tri-state change mask
        mask_file = target_dir / "filtered_change_mask.tif"
        m4b_regions = list(reg_map.values()) if reg_map else (change_result.regions if change_result else None)
        generate_filtered_change_mask(
            regions_suppression=regions_suppression,
            target_path=mask_file,
            change_mask=change_mask,
            change_regions=m4b_regions,
        )

        suppression_result = SuppressionResult(
            suppression_id=suppression_id,
            scene_pair_id=evidence.scene_pair_id,
            change_detection_result_id=evidence.change_detection_result_id,
            evidence_id=evidence.evidence_id,
            classification_id=classification.classification_id if classification else None,
            suppressor_id=cfg.suppressor_id,
            suppressor_version=cfg.suppressor_version,
            config=cfg,
            metrics=metrics,
            regions=regions_suppression,
            filtered_change_mask_path=str(mask_file),
            provenance_id=provenance_id,
            created_at=datetime.now(timezone.utc),
        )

        # Persist structured suppression JSON
        json_file = target_dir / "suppression.json"
        json_file.write_text(suppression_result.model_dump_json(indent=2), encoding="utf-8")

        # Record immutable provenance record conforming to ASTRA-DC-v0.1
        prov_record = ProvenanceRecord(
            provenance_id=provenance_id,
            source_scene_id=evidence.scene_pair_id,
            target_tile_id=None,
            processing_stage="false_alarm_suppression",
            pipeline_version="0.1.0",
            parameters={
                "suppressor_id": cfg.suppressor_id,
                "suppressor_version": cfg.suppressor_version,
                "evidence_id": evidence.evidence_id,
                "classification_id": classification.classification_id if classification else None,
                "change_detection_result_id": evidence.change_detection_result_id,
                "scene_pair_id": evidence.scene_pair_id,
                "total_input_regions": total_input,
                "retained_count": retained_cnt,
                "flagged_count": flagged_cnt,
                "suppressed_count": suppressed_cnt,
                "suppression_rate": round(suppression_rate, 4),
                "config": cfg.model_dump(),
                "input_hashes": evidence.source_hashes,
                "artifact_path": str(json_file),
                "filtered_mask_path": str(mask_file),
            },
            executed_by="astra.ml.change_suppression.engine",
            timestamp=suppression_result.created_at,
        )

        prov_file = self.provenance_dir / f"{provenance_id}.json"
        prov_file.write_text(prov_record.model_dump_json(indent=2), encoding="utf-8")

        return suppression_result

    def get_suppression_result(self, suppression_id: str) -> Optional[SuppressionResult]:
        """Loads a persisted SuppressionResult by its deterministic identifier."""
        json_file = self.output_dir / suppression_id / "suppression.json"
        if not json_file.exists():
            return None
        with open(json_file, "r", encoding="utf-8") as f:
            return SuppressionResult.model_validate_json(f.read())

    def list_suppressions(self) -> List[str]:
        """Lists all stored suppression document identifiers."""
        if not self.output_dir.exists():
            return []
        return [
            p.name
            for p in self.output_dir.iterdir()
            if p.is_dir() and (p / "suppression.json").exists()
        ]
