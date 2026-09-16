"""ASTRA Change Detection Data Contracts.

Defines immutable Pydantic models for change detection configuration,
extracted change regions, quantitative metrics, and comprehensive results conforming to ASTRA-DC-v0.1.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator
from geospatial.contracts import GeoBoundingBox


class ThresholdMethod(str, Enum):
    """Supported change detection thresholding algorithms."""

    FIXED = "fixed"
    STATISTICAL = "statistical"
    PERCENTILE = "percentile"


class NormalizationMethod(str, Enum):
    """Supported raster normalization methods."""

    ROBUST_PERCENTILE = "robust_percentile"
    MIN_MAX = "min_max"
    NONE = "none"


class ChangeDetectionConfig(BaseModel):
    """Configuration hyperparameters for temporal change detection."""

    algorithm_id: str = Field(default="pixel_difference", description="Identifier of change detection algorithm")
    algorithm_version: str = Field(default="1.0.0", description="Semantic version of algorithm implementation")
    threshold_method: ThresholdMethod = Field(
        default=ThresholdMethod.STATISTICAL,
        description="Method used to calculate the binary change mask threshold ('fixed', 'statistical', 'percentile')",
    )
    fixed_threshold: Optional[float] = Field(
        default=0.2, ge=0.0, le=1.0, description="Fixed change score threshold when threshold_method is 'fixed'"
    )
    threshold_std_multiplier: float = Field(
        default=2.0, ge=0.0, description="Multiplier k for statistical threshold (mean + k * std)"
    )
    threshold_percentile: float = Field(
        default=95.0, ge=0.0, le=100.0, description="Percentile threshold when threshold_method is 'percentile'"
    )
    minimum_region_area: int = Field(
        default=20, ge=1, description="Minimum pixel count required to retain a connected change component"
    )
    connectivity: int = Field(
        default=8, description="Pixel neighborhood connectivity for region labeling (4 or 8)"
    )
    normalization_method: NormalizationMethod = Field(
        default=NormalizationMethod.ROBUST_PERCENTILE,
        description="Method used for radiometric normalization ('robust_percentile', 'min_max', 'none')",
    )
    percentile_lower: float = Field(
        default=2.0, ge=0.0, le=50.0, description="Lower percentile for robust normalization"
    )
    percentile_upper: float = Field(
        default=98.0, ge=50.0, le=100.0, description="Upper percentile for robust normalization"
    )
    alignment_mode: str = Field(
        default="exact", description="Spatial alignment mode ('exact' requires identical dimensions)"
    )
    bands: Optional[List[int]] = Field(
        default=None, description="Optional explicit band indices to evaluate (1-based or 0-based list)"
    )
    nodata_value: Optional[float] = Field(
        default=None, description="Explicit nodata override value"
    )
    quality_mask: bool = Field(
        default=True, description="Whether to isolate and exclude nodata/invalid pixels"
    )

    @field_validator("connectivity")
    @classmethod
    def validate_connectivity(cls, v: int) -> int:
        if v not in (4, 8):
            raise ValueError("connectivity must be either 4 or 8")
        return v


class ChangeRegion(BaseModel):
    """Represents a discrete, spatially coherent connected component of detected change."""

    region_id: str = Field(..., min_length=3, description="Deterministic identifier (e.g. reg_0001)")
    pixel_count: int = Field(..., gt=0, description="Number of changed pixels inside this region")
    area_px: int = Field(..., gt=0, description="Area in pixels")
    area_m2: Optional[float] = Field(default=None, ge=0.0, description="Estimated ground surface area in square meters")
    bbox_px: List[int] = Field(
        ..., min_length=4, max_length=4, description="Pixel bounding box [min_row, min_col, max_row, max_col]"
    )
    bbox_wgs84: Optional[GeoBoundingBox] = Field(
        default=None, description="Geographic bounding box in WGS84 coordinates"
    )
    centroid_px: List[float] = Field(
        ..., min_length=2, max_length=2, description="Centroid coordinates in pixel space [row, col]"
    )
    centroid_wgs84: Optional[List[float]] = Field(
        default=None, min_length=2, max_length=2, description="Centroid coordinates in WGS84 [lon, lat]"
    )
    mean_change_score: float = Field(..., ge=0.0, le=1.0, description="Mean change magnitude of pixels in region")
    max_change_score: float = Field(..., ge=0.0, le=1.0, description="Peak change magnitude of pixels in region")
    geometry: Optional[Dict[str, Any]] = Field(
        default=None, description="GeoJSON polygon geometry representation of the region"
    )


class ChangeMetrics(BaseModel):
    """Quantitative statistical metrics summarizing a change detection run."""

    total_pixels: int = Field(..., ge=0, description="Total pixels in observation footprint")
    valid_pixels: int = Field(..., ge=0, description="Valid, non-nodata pixels evaluated")
    invalid_pixels: int = Field(..., ge=0, description="Excluded nodata/invalid pixels")
    changed_pixels: int = Field(..., ge=0, description="Count of pixels flagged as changed after filtering")
    changed_fraction: float = Field(
        ..., ge=0.0, le=1.0, description="Ratio of changed pixels relative to valid pixels (changed / valid)"
    )
    number_of_regions: int = Field(..., ge=0, description="Count of discrete connected change regions retained")
    changed_area_px: int = Field(..., ge=0, description="Total changed area in pixel count")
    changed_area_m2: Optional[float] = Field(
        default=None, ge=0.0, description="Total changed ground area in square meters"
    )
    mean_change_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Mean change score over all changed pixels"
    )
    max_change_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Maximum change score encountered in changed pixels"
    )
    threshold_used: float = Field(..., ge=0.0, le=1.0, description="Numerical cutoff threshold applied to score raster")
    threshold_method: str = Field(..., description="Method applied to calculate the threshold")


class ChangeDetectionResult(BaseModel):
    """Comprehensive, reproducible result of a temporal change detection evaluation."""

    result_id: str = Field(..., min_length=5, description="Deterministic result identifier")
    scene_pair_id: str = Field(..., min_length=5, description="Associated M4A ScenePair identifier")
    algorithm_id: str = Field(..., description="Algorithm identifier (e.g. pixel_difference)")
    algorithm_version: str = Field(..., description="Algorithm semantic version")
    config: ChangeDetectionConfig = Field(..., description="Exact hyperparameters applied for this run")
    metrics: ChangeMetrics = Field(..., description="Quantitative change metrics summary")
    regions: List[ChangeRegion] = Field(default_factory=list, description="Extracted discrete spatial change regions")
    mask_path: Optional[str] = Field(default=None, description="Local path to serialized binary change mask")
    score_path: Optional[str] = Field(default=None, description="Local path to serialized continuous change score map")
    provenance_id: str = Field(..., description="Associated immutable provenance record identifier")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Execution timestamp"
    )
