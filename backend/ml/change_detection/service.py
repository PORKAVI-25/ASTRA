"""ASTRA Temporal Change Detection Service.

Coordinates execution of change detection algorithms on ScenePair instances
or raw raster inputs, persists deterministic artifacts (score_map.npy, change_mask.png, result.json),
and records immutable provenance tracking conforming to ASTRA-DC-v0.1.
"""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
from PIL import Image

from backend.config import settings
from backend.ml.change.types import PairCompatibilityStatus, ScenePair, TemporalObservation
from backend.ml.change_detection.base import ChangeDetector
from backend.ml.change_detection.baseline import ASTRAPixelDifferenceDetector
from backend.ml.change_detection.types import ChangeDetectionConfig, ChangeDetectionResult
from geospatial.contracts import ProvenanceRecord


def _compute_sha256(data: Union[str, Path, np.ndarray]) -> str:
    """Computes SHA-256 hash from file path or NumPy array bytes."""
    hasher = hashlib.sha256()
    if isinstance(data, (str, Path)):
        p = Path(data)
        if p.exists() and p.is_file():
            with open(p, "rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
            return hasher.hexdigest()
        hasher.update(str(data).encode("utf-8"))
    elif isinstance(data, np.ndarray):
        hasher.update(data.tobytes())
    else:
        hasher.update(str(data).encode("utf-8"))
    return hasher.hexdigest()


class ChangeDetectionService:
    """Service orchestrating offline change detection and immutable artifact persistence."""

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        provenance_dir: Optional[Path] = None,
        detector: Optional[ChangeDetector] = None,
    ):
        self.output_dir = output_dir or settings.ASTRA_CHANGE_RESULTS_DIR
        self.provenance_dir = provenance_dir or (settings.ASTRA_MANIFESTS_DIR / "provenance")
        self.detector = detector or ASTRAPixelDifferenceDetector()

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.provenance_dir.mkdir(parents=True, exist_ok=True)

    def run_detection(
        self,
        earlier_input: Optional[Union[str, Path, np.ndarray, TemporalObservation]] = None,
        later_input: Optional[Union[str, Path, np.ndarray, TemporalObservation]] = None,
        pair: Optional[ScenePair] = None,
        config: Optional[ChangeDetectionConfig] = None,
        earlier_obs: Optional[TemporalObservation] = None,
        later_obs: Optional[TemporalObservation] = None,
        pair_id: Optional[str] = None,
    ) -> ChangeDetectionResult:
        """Runs change detection on a ScenePair or observation pair and persists artifacts.

        Args:
            earlier_input: Earlier raster path, array, or TemporalObservation.
            later_input: Later raster path, array, or TemporalObservation.
            pair: Optional M4A ScenePair instance.
            config: Change detection configuration hyperparameters.
            earlier_obs: Optional TemporalObservation for earlier raster.
            later_obs: Optional TemporalObservation for later raster.
            pair_id: Optional identifier for the scene pair.

        Returns:
            ChangeDetectionResult containing metrics, regions, and artifact paths.
        """
        if config is None:
            config = ChangeDetectionConfig()

        # Handle ScenePair input
        if pair is not None:
            if not pair.compatibility.is_compatible:
                raise ValueError(
                    f"Cannot run change detection on incompatible ScenePair '{pair.pair_id}': "
                    f"status={pair.compatibility.status.value}, reasons={pair.compatibility.reasons}"
                )
            if pair.later_observation.acquisition_time <= pair.earlier_observation.acquisition_time:
                raise ValueError(
                    f"Temporal separation must be strictly positive (later > earlier). "
                    f"Got T1={pair.earlier_observation.acquisition_time} and T2={pair.later_observation.acquisition_time}."
                )
            earlier_input = pair.earlier_observation.file_path
            later_input = pair.later_observation.file_path
            earlier_obs = pair.earlier_observation
            later_obs = pair.later_observation
            pair_id = pair.pair_id

        # Handle TemporalObservation inputs
        if isinstance(earlier_input, TemporalObservation):
            earlier_obs = earlier_input
            earlier_input = earlier_obs.file_path
        if isinstance(later_input, TemporalObservation):
            later_obs = later_input
            later_input = later_obs.file_path

        if earlier_input is None or later_input is None:
            raise ValueError("Both earlier_input and later_input must be provided.")

        # Temporal order validation if observations are provided
        if earlier_obs is not None and later_obs is not None:
            if later_obs.acquisition_time <= earlier_obs.acquisition_time:
                raise ValueError(
                    f"Temporal separation must be strictly positive: "
                    f"later ({later_obs.acquisition_time}) <= earlier ({earlier_obs.acquisition_time})"
                )

        # Calculate input hashes for lineage
        earlier_hash = _compute_sha256(earlier_input)
        later_hash = _compute_sha256(later_input)

        # Run core detector
        result, score_map, change_mask = self.detector.detect(
            earlier_raster=earlier_input,
            later_raster=later_input,
            earlier_obs=earlier_obs,
            later_obs=later_obs,
            config=config,
            pair_id=pair_id,
        )

        # Persist deterministic artifacts in output_dir / result_id
        result_dir = self.output_dir / result.result_id
        result_dir.mkdir(parents=True, exist_ok=True)

        score_file = result_dir / "score_map.npy"
        np.save(score_file, score_map)
        result.score_path = str(score_file)

        mask_file = result_dir / "change_mask.png"
        mask_img = Image.fromarray(change_mask)
        mask_img.save(mask_file)
        result.mask_path = str(mask_file)

        result_json_file = result_dir / "result.json"
        result_json_file.write_text(result.model_dump_json(indent=2), encoding="utf-8")

        # Record immutable provenance
        source_scene = (
            earlier_obs.scene_id
            if earlier_obs
            else (pair.pair_id if pair else (pair_id or "unassigned_scene"))
        )
        target_tile = earlier_obs.tile_id if earlier_obs else None

        prov_record = ProvenanceRecord(
            provenance_id=result.provenance_id,
            source_scene_id=source_scene,
            target_tile_id=target_tile,
            processing_stage="temporal_change_detection",
            pipeline_version="0.1.0",
            parameters={
                "algorithm_id": result.algorithm_id,
                "algorithm_version": result.algorithm_version,
                "scene_pair_id": result.scene_pair_id,
                "config": result.config.model_dump(),
                "metrics": result.metrics.model_dump(),
                "artifacts": {
                    "score_map": str(score_file),
                    "change_mask": str(mask_file),
                    "result_json": str(result_json_file),
                },
                "input_hashes": {
                    "earlier": earlier_hash,
                    "later": later_hash,
                },
            },
            executed_by="astra.ml.change_detection",
            timestamp=result.created_at,
        )

        prov_file = self.provenance_dir / f"{result.provenance_id}.json"
        prov_file.write_text(prov_record.model_dump_json(indent=2), encoding="utf-8")

        return result

    def get_result(self, result_id: str) -> Optional[ChangeDetectionResult]:
        """Loads a persisted ChangeDetectionResult by ID."""
        result_file = self.output_dir / result_id / "result.json"
        if not result_file.exists():
            return None
        with open(result_file, "r", encoding="utf-8") as f:
            return ChangeDetectionResult.model_validate_json(f.read())

    def get_mask_path(self, result_id: str) -> Optional[Path]:
        """Returns the local path to the change mask image for a result ID."""
        mask_file = self.output_dir / result_id / "change_mask.png"
        if mask_file.exists():
            return mask_file
        return None

    def get_score_map(self, result_id: str) -> Optional[np.ndarray]:
        """Loads the continuous score map array for a result ID."""
        score_file = self.output_dir / result_id / "score_map.npy"
        if score_file.exists():
            return np.load(score_file)
        return None
