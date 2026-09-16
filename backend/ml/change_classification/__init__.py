"""ASTRA Change Classification Subsystem (Phase M4C).

Subphase M4C-A: Deterministic, Explainable Feature/Evidence Extraction Layer.
Extracts measurable evidence across spatial morphology, geometry, temporal progression,
spectral response, and local neighborhood context.
"""

from .classifier import DeterministicChangeClassifier
from .evidence import ChangeEvidenceExtractor
from .service import ChangeClassificationEvidenceService
from .types import (
    CategoryCandidateScore,
    ChangeCategory,
    ChangeClassificationMetrics,
    ChangeClassificationResult,
    ChangeEvidence,
    ChangeRegionFeatures,
    ClassifierConfig,
    ConfidenceTier,
    ContextEvidence,
    EvidenceConfig,
    EvidenceFeature,
    RegionClassification,
    RuleEvaluation,
    SpatialEvidence,
    SpectralEvidence,
    TemporalEvidence,
)

__all__ = [
    # M4C-A Evidence Extraction
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
    # M4C-B Change-Type Classification
    "DeterministicChangeClassifier",
    "ChangeCategory",
    "ConfidenceTier",
    "RuleEvaluation",
    "CategoryCandidateScore",
    "RegionClassification",
    "ChangeClassificationMetrics",
    "ClassifierConfig",
    "ChangeClassificationResult",
]
