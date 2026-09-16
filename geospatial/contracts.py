"""ASTRA Geospatial & Metadata Data Contracts.

Defines Pydantic models for stable tile identities, scene manifests,
provenance records, health responses, and ingestion API models conforming to ASTRA-DC-v0.1.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class GeoBoundingBox(BaseModel):
    """Geographic bounding box in WGS84 (EPSG:4326) coordinates."""

    min_lon: float = Field(..., ge=-180.0, le=180.0, description="Minimum longitude (West)")
    min_lat: float = Field(..., ge=-90.0, le=90.0, description="Minimum latitude (South)")
    max_lon: float = Field(..., ge=-180.0, le=180.0, description="Maximum longitude (East)")
    max_lat: float = Field(..., ge=-90.0, le=90.0, description="Maximum latitude (North)")

    @field_validator("max_lon")
    @classmethod
    def validate_longitude_range(cls, v: float, info: Any) -> float:
        min_lon = info.data.get("min_lon")
        if min_lon is not None and v < min_lon:
            raise ValueError("max_lon must be greater than or equal to min_lon")
        return v

    @field_validator("max_lat")
    @classmethod
    def validate_latitude_range(cls, v: float, info: Any) -> float:
        min_lat = info.data.get("min_lat")
        if min_lat is not None and v < min_lat:
            raise ValueError("max_lat must be greater than or equal to min_lat")
        return v


class TileDimensions(BaseModel):
    """Pixel dimensions of an extracted imagery tile."""

    width_px: int = Field(default=512, gt=0, description="Width in pixels")
    height_px: int = Field(default=512, gt=0, description="Height in pixels")
    channels: int = Field(default=3, gt=0, description="Number of spectral channels")


class SceneManifest(BaseModel):
    """Full satellite scene ingestion manifest."""

    scene_id: str = Field(..., min_length=3, description="Deterministic scene identifier")
    sensor: str = Field(default="unknown", description="Sensor instrument (e.g. Sentinel-2A MSI, Landsat-8 OLI)")
    platform: str = Field(default="unknown", description="Satellite platform (e.g. Sentinel-2, Landsat-8)")
    acquisition_time: Optional[datetime] = Field(default=None, description="UTC acquisition timestamp (null if unavailable)")
    crs: str = Field(..., description="Coordinate Reference System (e.g. EPSG:32643)")
    bounds_wgs84: GeoBoundingBox = Field(..., description="Geographic bounding box in WGS84")
    spatial_resolution_m: Optional[float] = Field(default=None, gt=0.0, description="Spatial resolution in meters")
    cloud_cover_percentage: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    bands: List[str] = Field(default_factory=list, description="List of spectral band identifiers")
    source_file_path: str = Field(..., description="Local path to scene file")
    is_cog: bool = Field(default=False, description="Whether raster is a Cloud Optimized GeoTIFF")
    tile_count: int = Field(default=0, ge=0, description="Number of chipped tiles produced")
    nodata_value: Optional[float] = Field(default=None, description="Raster nodata value")
    quality_info: Dict[str, Any] = Field(default_factory=dict, description="Basic quality & nodata statistics")
    file_hash: Optional[str] = Field(default=None, description="SHA-256 hash of the source raster file")
    processing_warnings: List[str] = Field(default_factory=list, description="Warnings logged during ingestion")
    is_synthetic: bool = Field(default=False, description="Flag indicating synthetic or demo data")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Ingestion record timestamp")


class TileManifest(BaseModel):
    """Individual chipped satellite imagery tile manifest."""

    tile_id: str = Field(..., min_length=3, description="Deterministic stable tile identifier")
    source_scene_id: str = Field(..., min_length=3, description="Link to parent scene manifest")
    tile_col: int = Field(..., ge=0, description="Tile grid column index")
    tile_row: int = Field(..., ge=0, description="Tile grid row index")
    zoom_level: int = Field(default=14, ge=0, description="Tiling pyramid zoom level")
    dimensions: TileDimensions = Field(default_factory=TileDimensions)
    crs: str = Field(..., description="Tile CRS (e.g. EPSG:32643)")
    bounds_wgs84: GeoBoundingBox = Field(..., description="Tile geographic bounds in WGS84")
    acquisition_time: Optional[datetime] = Field(default=None, description="Acquisition timestamp inherited from source scene")
    sensor: str = Field(default="unknown", description="Sensor name inherited from source scene")
    file_path: str = Field(..., description="Local path to tile image file")
    sha256_hash: str = Field(..., min_length=64, max_length=64, description="Cryptographic SHA-256 hash of tile pixels")
    nodata_pixel_count: Optional[int] = Field(default=None, ge=0, description="Count of nodata pixels in tile")
    valid_pixel_ratio: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Ratio of valid non-nodata pixels")
    is_synthetic: bool = Field(default=False, description="Flag indicating synthetic or demo data")


class ProvenanceRecord(BaseModel):
    """Processing lineage record tracking transformation history."""

    provenance_id: str = Field(..., description="Unique provenance record identifier")
    target_tile_id: Optional[str] = Field(default=None, description="Target tile ID if tile-specific")
    source_scene_id: str = Field(..., description="Identifier of the parent source scene")
    processing_stage: str = Field(..., description="Name of processing stage")
    pipeline_version: str = Field(default="0.1.0", description="Version of processing code")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Transform hyperparameters")
    executed_by: str = Field(..., description="Module or operator that executed the stage")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Execution timestamp")


class HealthResponse(BaseModel):
    """System health response model."""

    status: str = Field(default="healthy", description="Overall health status")
    version: str = Field(default="0.1.0", description="ASTRA version")
    service: str = Field(default="ASTRA Backend API", description="Service identifier")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Server timestamp")
    environment: str = Field(default="development", description="Environment mode")
    offline_mode: bool = Field(default=True, description="Whether strict offline mode is active")
    modules: Dict[str, str] = Field(default_factory=dict, description="Subsystem health statuses")


# API Ingestion Models
class IngestionRequest(BaseModel):
    """Request model for scene ingestion."""

    file_path: str = Field(..., description="Local filesystem path to GeoTIFF/COG raster")
    tile_size: int = Field(default=512, ge=64, le=4096, description="Dimension of square chips in pixels")
    force_reprocess: bool = Field(default=False, description="Whether to reprocess an already-ingested scene")


class IngestionResponse(BaseModel):
    """Response model for scene ingestion."""

    status: str = Field(..., description="'ingested', 'already_ingested', or 'failed'")
    message: str = Field(..., description="Summary status message")
    scene: Optional[SceneManifest] = Field(default=None, description="Ingested scene manifest")
    tile_count: int = Field(default=0, description="Total chipped tiles")
    provenance_id: Optional[str] = Field(default=None, description="Recorded provenance ID")


class SceneSummaryResponse(BaseModel):
    """Summary representation for scene listings."""

    scene_id: str
    crs: str
    sensor: str
    acquisition_time: Optional[datetime] = None
    spatial_resolution_m: Optional[float] = None
    tile_count: int
    is_cog: bool
    is_synthetic: bool
    created_at: datetime
