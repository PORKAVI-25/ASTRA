"""Base interface for multi-temporal change detection adapters."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import numpy as np
from pydantic import BaseModel, Field


class ChangeDetectionResult(BaseModel):
    """Output contract from a change detector adapter."""

    change_mask: Any = Field(..., description="Binary or probability change mask array")
    change_ratio: float = Field(..., ge=0.0, le=1.0, description="Fraction of tile area changed")
    transition_class: Optional[str] = Field(default=None, description="Dominant categorical transition")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Model confidence score")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional model telemetry")

    model_config = {"arbitrary_types_allowed": True}


class BaseChangeDetectorAdapter(ABC):
    """Abstract base class for bi-temporal and multi-temporal change detection models."""

    def __init__(self, model_id: str, weights_path: Optional[str] = None):
        self.model_id = model_id
        self.weights_path = weights_path
        self._is_loaded = False

    @property
    def is_loaded(self) -> bool:
        """Returns whether detector weights are in memory."""
        return self._is_loaded

    @abstractmethod
    def load(self) -> None:
        """Loads model weights from local offline storage."""
        pass

    @abstractmethod
    def detect_change(self, image_t1: np.ndarray, image_t2: np.ndarray) -> ChangeDetectionResult:
        """Performs change analysis between co-registered imagery tiles.

        Args:
            image_t1: Imagery tile at observation time T1 (C, H, W).
            image_t2: Imagery tile at observation time T2 (C, H, W).

        Returns:
            ChangeDetectionResult containing mask and summary metrics.
        """
        pass
