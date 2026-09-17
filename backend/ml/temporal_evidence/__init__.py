"""ASTRA Phase M4E: Earliest Supporting Observation & Temporal Evidence Chain.

Exposes domain models, spatial correspondence evaluators, and orchestration service.
"""

from backend.ml.temporal_evidence.service import TemporalEvidenceService
from backend.ml.temporal_evidence.types import (
    CandidateRegionRef,
    CorrespondenceRelationship,
    PairwiseTemporalEvidenceInput,
    SpatialCorrespondence,
    SpatialCorrespondenceStatus,
    TemporalCategoryEvolution,
    TemporalConfidenceTier,
    TemporalEvidenceConfig,
    TemporalEvidenceMetrics,
    TemporalEvidenceNode,
    TemporalEvidenceResult,
    TemporalIntervalType,
    TemporalNodeStatus,
    TemporalOnsetEstimate,
    TemporalSupportStatus,
)

__all__ = [
    "CandidateRegionRef",
    "CorrespondenceRelationship",
    "PairwiseTemporalEvidenceInput",
    "SpatialCorrespondence",
    "SpatialCorrespondenceStatus",
    "TemporalCategoryEvolution",
    "TemporalConfidenceTier",
    "TemporalEvidenceConfig",
    "TemporalEvidenceMetrics",
    "TemporalEvidenceNode",
    "TemporalEvidenceResult",
    "TemporalEvidenceService",
    "TemporalIntervalType",
    "TemporalNodeStatus",
    "TemporalOnsetEstimate",
    "TemporalSupportStatus",
]
