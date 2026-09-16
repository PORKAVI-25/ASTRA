"""ASTRA Change Classification Subsystem (Phase M4C).

Subphase M4C-A: Deterministic, Explainable Feature/Evidence Extraction Layer.
Extracts measurable evidence across spatial morphology, geometry, temporal progression,
spectral response, and local neighborhood context.
"""

from .evidence import ChangeEvidenceExtractor
from .service import ChangeClassificationEvidenceService
from .types import (
    ChangeEvidence,
    ChangeRegionFeatures,
    ContextEvidence,
    EvidenceConfig,
    EvidenceFeature,
    SpatialEvidence,
    SpectralEvidence,
    TemporalEvidence,
)

__all__ = [
    "ChangeEvidenceExtractor",
    "ChangeClassificationEvidenceService",
    "EvidenceFeature",
    "SpatialEvidence",
    "TemporalEvidence",
    "SpectralEvidence",
    "ContextEvidence",
    "ChangeRegionFeatures",
    "EvidenceConfig",
    "ChangeEvidence",
]
