"""ASTRA Change Evidence Service (Phase M4C-A).

Orchestrates deterministic change evidence extraction, persists evidence JSON documents,
and records immutable provenance conforming to ASTRA-DC-v0.1.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import numpy as np

from backend.config import settings
from backend.ml.change.types import ScenePair
from backend.ml.change_classification.classifier import DeterministicChangeClassifier
from backend.ml.change_classification.evidence import ChangeEvidenceExtractor
from backend.ml.change_classification.types import (
    ChangeClassificationResult,
    ChangeEvidence,
    ClassifierConfig,
    EvidenceConfig,
)
from backend.ml.change_detection.types import ChangeDetectionResult
from geospatial.contracts import ProvenanceRecord


class ChangeClassificationEvidenceService:
    """Service managing evidence extraction and change classification execution, artifact persistence, and lineage."""

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        provenance_dir: Optional[Path] = None,
        extractor: Optional[ChangeEvidenceExtractor] = None,
        classifier: Optional[DeterministicChangeClassifier] = None,
    ):
        self.output_dir = output_dir or settings.ASTRA_CHANGE_CLASSIFICATION_DIR
        self.provenance_dir = provenance_dir or (settings.ASTRA_MANIFESTS_DIR / "provenance")
        self.extractor = extractor or ChangeEvidenceExtractor()
        self.classifier = classifier or DeterministicChangeClassifier()

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.provenance_dir.mkdir(parents=True, exist_ok=True)

    def extract_evidence(
        self,
        scene_pair: ScenePair,
        change_result: ChangeDetectionResult,
        earlier_image: Optional[Union[str, Path, np.ndarray]] = None,
        later_image: Optional[Union[str, Path, np.ndarray]] = None,
        score_map: Optional[np.ndarray] = None,
        change_mask: Optional[np.ndarray] = None,
        config: Optional[EvidenceConfig] = None,
    ) -> ChangeEvidence:
        """Executes evidence extraction, serializes evidence JSON, and records lineage."""
        evidence = self.extractor.extract(
            scene_pair=scene_pair,
            change_result=change_result,
            earlier_image=earlier_image,
            later_image=later_image,
            score_map=score_map,
            change_mask=change_mask,
            config=config,
        )

        # Persist structured evidence artifact
        target_dir = self.output_dir / evidence.evidence_id
        target_dir.mkdir(parents=True, exist_ok=True)
        evidence_file = target_dir / "evidence.json"
        evidence_file.write_text(evidence.model_dump_json(indent=2), encoding="utf-8")

        # Record immutable provenance record
        prov_record = ProvenanceRecord(
            provenance_id=evidence.provenance_id,
            source_scene_id=scene_pair.pair_id,
            target_tile_id=scene_pair.earlier_observation.tile_id,
            processing_stage="change_evidence_extraction",
            pipeline_version="0.1.0",
            parameters={
                "extractor_id": evidence.extractor_id,
                "extractor_version": evidence.extractor_version,
                "scene_pair_id": evidence.scene_pair_id,
                "change_detection_result_id": evidence.change_detection_result_id,
                "earlier_observation_id": scene_pair.earlier_observation.observation_id,
                "later_observation_id": scene_pair.later_observation.observation_id,
                "region_count": len(evidence.regions),
                "config": evidence.config.model_dump(),
                "source_hashes": evidence.source_hashes,
                "input_hashes": evidence.source_hashes,
                "artifact_path": str(evidence_file),
            },
            executed_by="astra.ml.change_classification",
            timestamp=evidence.created_at,
        )

        prov_file = self.provenance_dir / f"{evidence.provenance_id}.json"
        prov_file.write_text(prov_record.model_dump_json(indent=2), encoding="utf-8")

        return evidence

    def get_evidence(self, evidence_id: str) -> Optional[ChangeEvidence]:
        """Loads a persisted ChangeEvidence document by its deterministic identifier."""
        evidence_file = self.output_dir / evidence_id / "evidence.json"
        if not evidence_file.exists():
            return None
        with open(evidence_file, "r", encoding="utf-8") as f:
            return ChangeEvidence.model_validate_json(f.read())

    def list_evidence(self) -> List[str]:
        """Lists all stored change evidence identifiers."""
        if not self.output_dir.exists():
            return []
        return [
            p.name
            for p in self.output_dir.iterdir()
            if p.is_dir() and (p / "evidence.json").exists()
        ]

    def classify_evidence(
        self,
        evidence: ChangeEvidence,
        config: Optional[ClassifierConfig] = None,
    ) -> ChangeClassificationResult:
        """Executes change-type classification, serializes classification JSON, and records lineage."""
        classification = self.classifier.classify(evidence, config=config)

        # Persist structured classification artifact
        target_dir = self.output_dir / classification.classification_id
        target_dir.mkdir(parents=True, exist_ok=True)
        cls_file = target_dir / "classification.json"
        cls_file.write_text(classification.model_dump_json(indent=2), encoding="utf-8")

        # Record immutable provenance record conforming to ASTRA-DC-v0.1
        prov_record = ProvenanceRecord(
            provenance_id=classification.provenance_id,
            source_scene_id=classification.scene_pair_id,
            target_tile_id=None,
            processing_stage="change_type_classification",
            pipeline_version="0.1.0",
            parameters={
                "classifier_id": classification.classifier_id,
                "classifier_version": classification.classifier_version,
                "evidence_id": classification.evidence_id,
                "scene_pair_id": classification.scene_pair_id,
                "change_detection_result_id": classification.change_detection_result_id,
                "total_regions": classification.metrics.total_regions,
                "category_counts": classification.metrics.category_counts,
                "config": classification.config.model_dump(),
                "input_hashes": evidence.source_hashes,
                "artifact_path": str(cls_file),
            },
            executed_by="astra.ml.change_classification.classifier",
            timestamp=classification.created_at,
        )

        prov_file = self.provenance_dir / f"{classification.provenance_id}.json"
        prov_file.write_text(prov_record.model_dump_json(indent=2), encoding="utf-8")

        return classification

    def get_classification(self, classification_id: str) -> Optional[ChangeClassificationResult]:
        """Loads a persisted ChangeClassificationResult document by its deterministic identifier."""
        cls_file = self.output_dir / classification_id / "classification.json"
        if not cls_file.exists():
            return None
        with open(cls_file, "r", encoding="utf-8") as f:
            return ChangeClassificationResult.model_validate_json(f.read())

    def list_classifications(self) -> List[str]:
        """Lists all stored change classification identifiers."""
        if not self.output_dir.exists():
            return []
        return [
            p.name
            for p in self.output_dir.iterdir()
            if p.is_dir() and (p / "classification.json").exists()
        ]
