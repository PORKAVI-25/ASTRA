"""ASTRA Change Evidence Data Contracts (Phase M4C-A).

Defines typed, immutable Pydantic models for structured, explainable change evidence
extracted across spatial, temporal, spectral, and contextual feature families.
Conforms to ASTRA-DC-v0.1.
"""

from datetime import datetime, timezone
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
