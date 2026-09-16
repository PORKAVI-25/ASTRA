"""ASTRA Change Evidence Data Contracts (Phase M4C-A).

Defines typed, immutable Pydantic models for structured, explainable change evidence
extracted across spatial, temporal, spectral, and contextual feature families.
Conforms to ASTRA-DC-v0.1.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from geospatial.contracts import GeoBoundingBox


class EvidenceFeature(BaseModel):
    """Represents an atomic, measurable evidence feature."""

    feature_id: str = Field(..., description="Deterministic feature identifier")
    feature_name: str = Field(..., description="Canonical feature name")
    value: Optional[float] = Field(default=None, description="Raw unnormalized numerical value")
    normalized_value: Optional[float] = Field(default=None, description="Normalized representation if computed")
    normalization_method: Optional[str] = Field(default=None, description="Algorithm used to normalize")
    unit: Optional[str] = Field(default=None, description="Unit of measurement where applicable")
    available: bool = Field(default=True, description="Whether this feature could be calculated")
    unavailability_reason: Optional[str] = Field(default=None, description="Explanation if feature is unavailable")
    source: str = Field(..., description="Evidence family: 'geometry', 'morphology', 'spectral', 'temporal', 'context'")
    method: Optional[str] = Field(default=None, description="Algorithm or equation identifier")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context or provenance")


class SpatialEvidence(BaseModel):
    """Measurable spatial morphology, geometry, and geospatial characteristics of a change region."""

    area_px: int = Field(..., ge=1, description="Region area in pixel count")
    pixel_count: int = Field(..., ge=1, description="Identical to area_px")
    width_px: int = Field(..., ge=1, description="Bounding box pixel width")
    height_px: int = Field(..., ge=1, description="Bounding box pixel height")
    aspect_ratio: float = Field(..., ge=1.0, description="Max dimension / min dimension")
    perimeter_px: float = Field(..., ge=0.0, description="Outer boundary perimeter in pixel units")
    compactness: float = Field(..., ge=0.0, le=1.0, description="Isoperimetric quotient 4*pi*area / perimeter^2")
    rectangularity: float = Field(..., ge=0.0, le=1.0, description="Area / (width * height)")
    elongation: float = Field(..., ge=1.0, description="Ratio of principal axes or bbox aspect ratio")
    major_axis_length: float = Field(..., ge=0.0, description="Estimated principal major axis length in pixels")
    minor_axis_length: float = Field(..., ge=0.0, description="Estimated principal minor axis length in pixels")
    axis_ratio: float = Field(..., ge=1.0, description="major_axis_length / max(1e-6, minor_axis_length)")
    linearity_score: float = Field(..., ge=0.0, le=1.0, description="Linearity proxy score based on 2D moments")
    orientation_degrees: float = Field(..., ge=-90.0, le=90.0, description="Orientation angle of primary axis")
    component_density: float = Field(..., ge=0.0, le=1.0, description="Pixel density within bounding box")
    shape_regularity: float = Field(..., ge=0.0, le=1.0, description="Regularity proxy comparing perimeter to circle")
    fragmentation: float = Field(..., ge=0.0, description="Interior boundary complexity or void proxy")
    neighboring_changed_regions_count: int = Field(
        default=0, ge=0, description="Count of other change regions within proximity"
    )
    centroid_wgs84: Optional[List[float]] = Field(default=None, min_length=2, max_length=2)
    bbox_wgs84: Optional[GeoBoundingBox] = Field(default=None)
    area_m2: Optional[float] = Field(default=None, ge=0.0)
    distance_to_boundary_px: Optional[float] = Field(default=None, ge=0.0)


class TemporalEvidence(BaseModel):
    """Chronological progression and observation metadata from M4A ScenePair."""

    earlier_acquisition_time: datetime = Field(..., description="UTC acquisition timestamp of T1")
    later_acquisition_time: datetime = Field(..., description="UTC acquisition timestamp of T2")
    temporal_separation_seconds: float = Field(..., gt=0.0, description="Strictly positive delta in seconds")
    temporal_separation_days: float = Field(..., gt=0.0, description="Separation in fractional days")
    temporal_separation_hours: float = Field(..., gt=0.0, description="Separation in fractional hours")
    earlier_scene_id: str = Field(..., description="Earlier observation scene identifier")
    later_scene_id: str = Field(..., description="Later observation scene identifier")
    earlier_tile_id: Optional[str] = Field(default=None, description="Earlier tile identifier if chipped")
    later_tile_id: Optional[str] = Field(default=None, description="Later tile identifier if chipped")
    earlier_sensor: str = Field(default="unknown")
    later_sensor: str = Field(default="unknown")
    is_cross_sensor: bool = Field(default=False)


class SpectralEvidence(BaseModel):
    """Measurable spectral and radiometric characteristics over the change region."""

    available: bool = Field(default=True, description="Whether spectral imagery could be evaluated")
    unavailability_reason: Optional[str] = Field(default=None)
    earlier_mean_per_band: Dict[str, float] = Field(default_factory=dict)
    later_mean_per_band: Dict[str, float] = Field(default_factory=dict)
    delta_per_band: Dict[str, float] = Field(default_factory=dict)
    abs_delta_per_band: Dict[str, float] = Field(default_factory=dict)
    band_names: List[str] = Field(default_factory=list)
    has_wavelength_metadata: bool = Field(
        default=False, description="True only if physical wavelength bands are explicitly established"
    )
    ndvi_mean: Optional[EvidenceFeature] = Field(
        default=None, description="Normalized Difference Vegetation Index (available only if NIR+Red known)"
    )
    ndwi_mean: Optional[EvidenceFeature] = Field(
        default=None, description="Normalized Difference Water Index (available only if Green+NIR known)"
    )
    water_spectral_criterion_fraction: Optional[EvidenceFeature] = Field(
        default=None, description="Fraction of region pixels matching water-like spectral response"
    )
    vegetation_proxy_delta: Optional[EvidenceFeature] = Field(default=None)
    brightness_delta: Optional[EvidenceFeature] = Field(default=None)


class ContextEvidence(BaseModel):
    """Local neighborhood context comparing the changed region to surrounding unchanged pixels."""

    available: bool = Field(default=True, description="Whether valid local context could be calculated")
    unavailability_reason: Optional[str] = Field(default=None)
    neighborhood_buffer_px: int = Field(default=15, description="Buffer ring radius in pixels")
    surrounding_mean_change: Optional[float] = Field(default=None)
    region_to_background_contrast: Optional[float] = Field(default=None)
    local_background_mean_per_band: Dict[str, float] = Field(default_factory=dict)


class ChangeRegionFeatures(BaseModel):
    """Complete bundle of extracted evidence features for a single M4B ChangeRegion."""

    region_id: str = Field(..., min_length=3, description="Deterministic identifier matching M4B ChangeRegion")
    spatial: SpatialEvidence = Field(..., description="Morphological and geometric features")
    spectral: SpectralEvidence = Field(..., description="Spectral reflectance and index features")
    context: ContextEvidence = Field(..., description="Surrounding background context features")
    change_score: Dict[str, float] = Field(
        default_factory=dict, description="Magnitude statistics: mean, peak, std, fraction"
    )
    features: Dict[str, EvidenceFeature] = Field(
        default_factory=dict, description="Flattened map of all atomic features by feature_name"
    )


class EvidenceConfig(BaseModel):
    """Configuration hyperparameters for feature/evidence extraction."""

    extractor_id: str = Field(default="astra_change_evidence")
    extractor_version: str = Field(default="1.0.0")
    neighborhood_buffer_px: int = Field(default=15, ge=1, le=100)
    water_criterion_threshold: float = Field(default=0.0)
    min_valid_context_pixels: int = Field(default=10, ge=1)
    band_mapping: Optional[Dict[str, int]] = Field(
        default=None, description="Explicit mapping of semantic names to 0-based band indices (e.g. {'red': 2, 'nir': 3})"
    )


class ChangeEvidence(BaseModel):
    """Structured, reproducible evidence document conforming to ASTRA-DC-v0.1."""

    evidence_id: str = Field(..., min_length=5, description="Deterministic evidence document identifier")
    scene_pair_id: str = Field(..., min_length=5, description="Associated M4A ScenePair identifier")
    change_detection_result_id: str = Field(..., min_length=5, description="Associated M4B ChangeDetectionResult identifier")
    extractor_id: str = Field(..., description="Feature extractor identifier")
    extractor_version: str = Field(..., description="Feature extractor semantic version")
    temporal: TemporalEvidence = Field(..., description="Chronological and pair evidence")
    regions: List[ChangeRegionFeatures] = Field(default_factory=list, description="Extracted features per change region")
    config: EvidenceConfig = Field(..., description="Configuration parameters applied during extraction")
    source_hashes: Dict[str, str] = Field(default_factory=dict, description="Cryptographic SHA-256 hashes of inputs")
    provenance_id: str = Field(..., description="Associated immutable provenance record identifier")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Execution timestamp"
    )


# ==============================================================================
# Phase M4C-B: Change-Type Classification Contracts
# ==============================================================================

class ChangeCategory(str, Enum):
    """Supported semantic change categories."""

    CONSTRUCTION = "construction"
    CLEARANCE = "clearance"
    WATER_EXTENT_CHANGE = "water_extent_change"
    ROAD_DEVELOPMENT = "road_development"
    UNKNOWN = "unknown"


class ConfidenceTier(str, Enum):
    """Stratified confidence tiers based on modality completeness and score margin."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNCERTAIN = "uncertain"


class RuleEvaluation(BaseModel):
    """Detailed evaluation of an individual domain rule."""

    rule_id: str = Field(..., description="Unique identifier of rule")
    category: ChangeCategory = Field(..., description="Target candidate category")
    matched: bool = Field(..., description="Whether condition evaluated to True")
    weight: float = Field(..., ge=0.0, description="Rule weight in scoring")
    score_contribution: float = Field(..., description="Net contribution of this rule to score")
    description: str = Field(..., description="Human-readable rule intent")
    evidence_used: Dict[str, Any] = Field(default_factory=dict, description="Feature values inspected by rule")


class CategoryCandidateScore(BaseModel):
    """Candidate category evidence support summary."""

    category: ChangeCategory
    evidence_score: float = Field(..., ge=0.0, le=1.0)
    matched_rule_count: int
    primary_reason: str


class RegionClassification(BaseModel):
    """Complete semantic classification and explainability bundle for a ChangeRegion."""

    region_id: str = Field(..., description="Matching M4B/M4C-A region identifier")
    category: ChangeCategory = Field(..., description="Assigned semantic change category")
    evidence_score: float = Field(
        ..., ge=0.0, le=1.0, description="Uncalibrated degree of evidence alignment (non-probabilistic)"
    )
    confidence_tier: ConfidenceTier = Field(..., description="Confidence stratification")
    decision_reason: str = Field(..., description="1-2 sentence human-readable decision explanation")
    rule_evaluations: List[RuleEvaluation] = Field(default_factory=list, description="Auditing trail of evaluated rules")
    candidate_scores: Dict[str, float] = Field(default_factory=dict, description="Scores per candidate category")
    conflicting_categories: List[str] = Field(default_factory=list, description="Close runner-up candidates if ambiguous")
    data_limitations: List[str] = Field(default_factory=list, description="Sensor/spectral data warnings")
    is_ambiguous: bool = Field(default=False, description="True if conflict margin threshold was breached")


class ChangeClassificationMetrics(BaseModel):
    """Aggregated classification metrics across all regions in the scene."""

    total_regions: int = Field(..., ge=0)
    category_counts: Dict[str, int] = Field(default_factory=dict)
    high_confidence_count: int = Field(..., ge=0)
    ambiguous_count: int = Field(..., ge=0)
    unclassified_unknown_fraction: float = Field(..., ge=0.0, le=1.0)


class ClassifierConfig(BaseModel):
    """Deterministic classification hyperparameters and rule thresholds."""

    classifier_id: str = Field(default="astra_deterministic_rule_classifier")
    classifier_version: str = Field(default="1.0.0")
    min_classification_area_px: int = Field(default=10, ge=1, description="Minimum region pixel count to classify")
    min_evidence_score_threshold: float = Field(default=0.45, ge=0.0, le=1.0, description="Minimum score to assign category")
    ambiguity_margin_threshold: float = Field(default=0.15, ge=0.0, le=1.0, description="Required margin over runner-up")
    construction_min_rectangularity: float = Field(default=0.60, ge=0.0, le=1.0)
    road_min_linearity: float = Field(default=0.75, ge=0.0, le=1.0)
    road_min_aspect_ratio: float = Field(default=5.0, ge=1.0)
    road_max_minor_axis_px: float = Field(default=30.0, ge=1.0)
    clearance_max_ndvi_delta: float = Field(default=-0.15, le=0.0)
    water_min_criterion_fraction: float = Field(default=0.40, ge=0.0, le=1.0)


class ChangeClassificationResult(BaseModel):
    """Structured, reproducible change classification document conforming to ASTRA-DC-v0.1."""

    classification_id: str = Field(..., min_length=5, description="Deterministic classification document identifier")
    evidence_id: str = Field(..., min_length=5, description="Associated M4C-A ChangeEvidence identifier")
    scene_pair_id: str = Field(..., min_length=5, description="Associated M4A ScenePair identifier")
    change_detection_result_id: str = Field(..., min_length=5, description="Associated M4B ChangeDetectionResult identifier")
    classifier_id: str = Field(..., description="Classifier algorithm identifier")
    classifier_version: str = Field(..., description="Classifier semantic version")
    config: ClassifierConfig = Field(..., description="Configuration parameters applied during classification")
    metrics: ChangeClassificationMetrics = Field(..., description="Summary counts and distribution")
    classifications: List[RegionClassification] = Field(default_factory=list, description="Per-region classifications")
    provenance_id: str = Field(..., description="Associated immutable provenance record identifier")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Execution timestamp"
    )
