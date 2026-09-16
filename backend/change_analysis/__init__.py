"""ASTRA Change Analysis Subsystem.

Responsible for co-registered tile temporal pairing, observation cataloging,
and change detection pipelines.
"""

from backend.ml.change import (
    CatalogDiscoveryResult,
    PairCompatibility,
    PairCompatibilityStatus,
    PairingConfig,
    ScenePair,
    SpatialOverlap,
    TemporalCatalog,
    TemporalObservation,
    TemporalSeries,
    compute_spatial_overlap,
    create_deterministic_pair_id,
    create_scene_pair,
    evaluate_pair_compatibility,
    pair_observations,
)
from backend.ml.change_detection import (
    ASTRAPixelDifferenceDetector,
    ChangeDetectionConfig,
    ChangeDetectionResult,
    ChangeDetectionService,
    ChangeDetector,
    ChangeMetrics,
    ChangeRegion,
    NormalizationMethod,
    ThresholdMethod,
)
from backend.ml.change_classification import (
    CategoryCandidateScore,
    ChangeCategory,
    ChangeClassificationEvidenceService,
    ChangeClassificationMetrics,
    ChangeClassificationResult,
    ChangeEvidence,
    ChangeEvidenceExtractor,
    ChangeRegionFeatures,
    ClassifierConfig,
    ConfidenceTier,
    DeterministicChangeClassifier,
    EvidenceConfig,
    EvidenceFeature,
    RegionClassification,
    RuleEvaluation,
)


def get_change_analysis_status() -> str:
    """Returns readiness status of change analysis subsystem."""
    return "ready"


__all__ = [
    "get_change_analysis_status",
    "TemporalObservation",
    "SpatialOverlap",
    "PairCompatibility",
    "PairCompatibilityStatus",
    "ScenePair",
    "TemporalSeries",
    "PairingConfig",
    "compute_spatial_overlap",
    "create_deterministic_pair_id",
    "create_scene_pair",
    "evaluate_pair_compatibility",
    "pair_observations",
    "CatalogDiscoveryResult",
    "TemporalCatalog",
    # M4B Change Detection
    "ChangeDetector",
    "ASTRAPixelDifferenceDetector",
    "ChangeDetectionService",
    "ChangeDetectionConfig",
    "ChangeDetectionResult",
    "ChangeMetrics",
    "ChangeRegion",
    "NormalizationMethod",
    "ThresholdMethod",
    # M4C-A Change Evidence Extraction
    "ChangeEvidenceExtractor",
    "ChangeClassificationEvidenceService",
    "ChangeEvidence",
    "ChangeRegionFeatures",
    "EvidenceConfig",
    "EvidenceFeature",
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
