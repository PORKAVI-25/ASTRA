"""ASTRA Temporal Modeling & Change Analysis Subsystem (Phase M4A).

Exposes temporal data models, bounding-box spatial overlap analysis,
chronological observation ordering, and deterministic scene/tile pairing.
"""

from .types import (
    PairCompatibility,
    PairCompatibilityStatus,
    PairingConfig,
    ScenePair,
    SpatialOverlap,
    TemporalObservation,
    TemporalSeries,
)
from .scene_pairing import (
    compute_spatial_overlap,
    create_deterministic_pair_id,
    create_scene_pair,
    evaluate_pair_compatibility,
    pair_observations,
)
from .temporal_catalog import (
    CatalogDiscoveryResult,
    TemporalCatalog,
)

__all__ = [
    # Contracts
    "TemporalObservation",
    "SpatialOverlap",
    "PairCompatibility",
    "PairCompatibilityStatus",
    "ScenePair",
    "TemporalSeries",
    "PairingConfig",
    # Pairing Functions
    "compute_spatial_overlap",
    "create_deterministic_pair_id",
    "create_scene_pair",
    "evaluate_pair_compatibility",
    "pair_observations",
    # Catalog
    "CatalogDiscoveryResult",
    "TemporalCatalog",
]
