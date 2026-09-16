"""ASTRA Temporal Domain Models & Data Contracts.

Defines immutable Pydantic data contracts for temporal observations,
spatial overlap metrics, scene/tile pairs, temporal series, and pairing configuration.
Conforms to ASTRA-DC-v0.1 and integrates with existing geospatial contracts.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator
from geospatial.contracts import GeoBoundingBox


class PairCompatibilityStatus(str, Enum):
    """Enumeration of scene pair compatibility outcomes."""

    COMPATIBLE = "COMPATIBLE"
    INSUFFICIENT_OVERLAP = "INSUFFICIENT_OVERLAP"
    INVALID_TEMPORAL_ORDER = "INVALID_TEMPORAL_ORDER"
    IDENTICAL_TIMESTAMPS = "IDENTICAL_TIMESTAMPS"
    BELOW_MIN_INTERVAL = "BELOW_MIN_INTERVAL"
    EXCEEDS_MAX_INTERVAL = "EXCEEDS_MAX_INTERVAL"
    INCOMPATIBLE_SENSOR = "INCOMPATIBLE_SENSOR"
    INCOMPATIBLE_PLATFORM = "INCOMPATIBLE_PLATFORM"


class TemporalObservation(BaseModel):
    """Represents a single satellite observation of a geographic footprint at a point in time."""

    observation_id: str = Field(..., min_length=3, description="Deterministic observation identifier")
    scene_id: str = Field(..., min_length=3, description="Parent satellite scene identifier")
    tile_id: Optional[str] = Field(default=None, description="Tile chip identifier if observation is a chipped tile")
    acquisition_time: datetime = Field(..., description="UTC acquisition timestamp (must be timezone-aware)")
    sensor: str = Field(default="unknown", description="Sensor instrument (e.g. Sentinel-2A MSI, Landsat-8 OLI)")
    platform: str = Field(default="unknown", description="Satellite platform (e.g. Sentinel-2, Landsat-8)")
    crs: str = Field(..., description="Coordinate reference system (e.g. EPSG:32643)")
    bounds_wgs84: GeoBoundingBox = Field(..., description="Geographic bounding box in WGS84 coordinates")
    source_hash: str = Field(..., min_length=16, description="Cryptographic hash of source pixels/file")
    file_path: Optional[str] = Field(default=None, description="Local filesystem path to imagery")
    provenance_reference: Optional[str] = Field(default=None, description="Associated provenance record identifier")
    is_synthetic: bool = Field(default=False, description="Flag indicating synthetic or demo data")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional ingestion or platform metadata")

    @field_validator("acquisition_time")
    @classmethod
    def ensure_utc_timezone(cls, v: datetime) -> datetime:
        """Ensures acquisition timestamp is timezone-aware and normalized to UTC."""
        if v.tzinfo is None:
            # Assume UTC if naive, but enforce UTC timezone
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)


class SpatialOverlap(BaseModel):
    """Exact 2D axis-aligned bounding box spatial overlap metrics between two observations."""

    intersection_bounds: Optional[GeoBoundingBox] = Field(
        default=None, description="Geographic intersection bounding box, or None if disjoint"
    )
    intersection_area_deg2: float = Field(
        default=0.0, ge=0.0, description="Intersection area in square degrees"
    )
    earlier_area_deg2: float = Field(..., gt=0.0, description="Earlier observation bbox area in square degrees")
    later_area_deg2: float = Field(..., gt=0.0, description="Later observation bbox area in square degrees")
    overlap_ratio_earlier: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Intersection area / earlier observation area"
    )
    overlap_ratio_later: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Intersection area / later observation area"
    )
    overlap_ratio_iou: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Intersection over Union (IoU) ratio"
    )
    overlap_ratio_min: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Intersection area / min(earlier_area, later_area)"
    )
    is_overlapping: bool = Field(default=False, description="Whether observations have non-zero spatial overlap")


class PairCompatibility(BaseModel):
    """Compatibility evaluation results for a candidate observation pair."""

    is_compatible: bool = Field(..., description="Whether the pair satisfies all configured constraints")
    status: PairCompatibilityStatus = Field(..., description="Primary compatibility status code")
    reasons: List[str] = Field(default_factory=list, description="Explanatory reasons or warnings")
    is_cross_sensor: bool = Field(default=False, description="Flag indicating observations use different sensors")
    is_cross_platform: bool = Field(default=False, description="Flag indicating observations use different platforms")


class ScenePair(BaseModel):
    """Represents an ordered, co-registered temporal pair (T1 earlier, T2 later)."""

    pair_id: str = Field(..., min_length=5, description="Deterministic pair identifier")
    earlier_observation: TemporalObservation = Field(..., description="Before observation at T1")
    later_observation: TemporalObservation = Field(..., description="After observation at T2")
    temporal_separation_seconds: float = Field(..., ge=0.0, description="Time delta (T2 - T1) in seconds")
    temporal_separation_days: float = Field(..., ge=0.0, description="Time delta in fractional days")
    spatial_overlap: SpatialOverlap = Field(..., description="Computed 2D spatial overlap metrics")
    pairing_method: str = Field(default="exact_tile_identity", description="Heuristic or rule used for pairing")
    compatibility: PairCompatibility = Field(..., description="Compatibility evaluation result")
    provenance_reference: Optional[str] = Field(default=None, description="Optional provenance lineage ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary pair metadata")

    @field_validator("later_observation")
    @classmethod
    def validate_chronological_order(cls, v: TemporalObservation, info: Any) -> TemporalObservation:
        """Validates that later_observation is chronologically after or equal to earlier_observation."""
        earlier = info.data.get("earlier_observation")
        if earlier is not None:
            if v.acquisition_time < earlier.acquisition_time:
                raise ValueError("later_observation acquisition_time must be >= earlier_observation acquisition_time")
        return v

    @field_validator("compatibility")
    @classmethod
    def validate_positive_separation_for_compatible_pair(
        cls, v: PairCompatibility, info: Any
    ) -> PairCompatibility:
        """Enforces that any compatible ScenePair must have strictly positive temporal separation (T2 > T1)."""
        earlier = info.data.get("earlier_observation")
        later = info.data.get("later_observation")
        if v.is_compatible and earlier is not None and later is not None:
            if later.acquisition_time <= earlier.acquisition_time:
                raise ValueError(
                    "A compatible ScenePair must have strictly positive temporal separation (later_observation > earlier_observation)"
                )
        return v


class TemporalSeries(BaseModel):
    """An ordered chronological sequence of observations for a specific geographic area or tile."""

    series_id: str = Field(..., min_length=3, description="Deterministic series identifier")
    target_id: str = Field(..., description="Tile ID or geographic cell anchor identifier")
    bounds_wgs84: GeoBoundingBox = Field(..., description="Covering geographic bounding box")
    observations: List[TemporalObservation] = Field(
        default_factory=list, description="Chronologically sorted list of observations (T1 <= T2 <= ... <= TN)"
    )
    observation_count: int = Field(default=0, ge=0, description="Total observations in the series")
    earliest_date: Optional[datetime] = Field(default=None, description="Timestamp of earliest observation")
    latest_date: Optional[datetime] = Field(default=None, description="Timestamp of latest observation")


class PairingConfig(BaseModel):
    """Configuration parameters for deterministic scene/tile pairing."""

    min_temporal_separation_seconds: float = Field(
        default=0.0,
        ge=0.0,
        description="Minimum additional temporal separation in seconds beyond strict chronological progression (T2 > T1). Default 0.0 imposes no extra minimum gap, but zero-second / same-timestamp pairs are always rejected.",
    )
    max_temporal_separation_seconds: Optional[float] = Field(
        default=None, gt=0.0, description="Maximum allowed separation in seconds (null allows unbounded separation)"
    )
    min_spatial_overlap_ratio: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Minimum spatial overlap ratio required for valid pair"
    )
    overlap_metric: str = Field(
        default="iou",
        description="Metric used for overlap ratio threshold ('iou', 'min', 'earlier', 'later')",
    )
    require_same_sensor: bool = Field(
        default=False, description="If True, rejects pairs where sensors do not match"
    )
    require_same_platform: bool = Field(
        default=False, description="If True, rejects pairs where platforms do not match"
    )
    prefer_same_tile_identity: bool = Field(
        default=True, description="Prefer pairing tiles sharing exact tile grid coordinates"
    )
    allow_cross_sensor: bool = Field(
        default=True, description="Allow cross-sensor pairs with explicit compatibility status"
    )
