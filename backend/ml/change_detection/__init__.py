"""ASTRA Change Detection Module (Phase M4B).

Provides reproducible temporal change detection algorithms,
continuous change scoring, thresholding, connected component labeling,
and immutable provenance-backed service orchestration.
"""

from .base import ChangeDetector
from .baseline import ASTRAPixelDifferenceDetector
from .service import ChangeDetectionService
from .types import (
    ChangeDetectionConfig,
    ChangeDetectionResult,
    ChangeMetrics,
    ChangeRegion,
    NormalizationMethod,
    ThresholdMethod,
)

__all__ = [
    "ChangeDetector",
    "ASTRAPixelDifferenceDetector",
    "ChangeDetectionService",
    "ChangeDetectionConfig",
    "ChangeDetectionResult",
    "ChangeMetrics",
    "ChangeRegion",
    "NormalizationMethod",
    "ThresholdMethod",
]
