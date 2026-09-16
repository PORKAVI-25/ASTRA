"""ASTRA Change Detection Base Interface.

Defines the abstract base class for temporal change detection algorithms,
ensuring algorithmic interchangeability, contract conformity, and offline reproducibility.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional, Tuple, Union
import numpy as np

from backend.ml.change.types import TemporalObservation
from backend.ml.change_detection.types import ChangeDetectionConfig, ChangeDetectionResult


class ChangeDetector(ABC):
    """Abstract base class for all ASTRA change detection algorithms."""

    algorithm_id: str = "base_detector"
    algorithm_version: str = "1.0.0"

    @abstractmethod
    def detect(
        self,
        earlier_raster: Union[str, np.ndarray, Any],
        later_raster: Union[str, np.ndarray, Any],
        earlier_obs: Optional[TemporalObservation] = None,
        later_obs: Optional[TemporalObservation] = None,
        config: Optional[ChangeDetectionConfig] = None,
        pair_id: Optional[str] = None,
    ) -> Tuple[ChangeDetectionResult, np.ndarray, np.ndarray]:
        """Executes change detection between earlier (T1) and later (T2) rasters.

        Args:
            earlier_raster: File path or NumPy array representing the earlier observation.
            later_raster: File path or NumPy array representing the later observation.
            earlier_obs: Optional TemporalObservation metadata contract for earlier scene.
            later_obs: Optional TemporalObservation metadata contract for later scene.
            config: Hyperparameters governing thresholding, normalization, and filtering.
            pair_id: Optional identifier for the scene pair.

        Returns:
            Tuple containing:
                - ChangeDetectionResult: Structured metrics, configuration, and regions.
                - np.ndarray: Continuous change score map in [0.0, 1.0] with shape (H, W).
                - np.ndarray: Binary change mask (uint8 with values 0 or 255) with shape (H, W).
        """
        pass
