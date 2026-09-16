"""ASTRA Retrieval Data Contracts and Models.

Defines Pydantic models for semantic search requests, metadata filters,
result items, embedding storage records, and health responses.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator
from geospatial.contracts import GeoBoundingBox


class RetrievalFilter(BaseModel):
    """Metadata and geospatial filters for retrieval queries."""

    date_from: Optional[datetime] = Field(default=None, description="Earliest acquisition timestamp (UTC)")
    date_to: Optional[datetime] = Field(default=None, description="Latest acquisition timestamp (UTC)")
    sensor: Optional[str] = Field(default=None, description="Sensor name (e.g. Sentinel-2A MSI)")
    platform: Optional[str] = Field(default=None, description="Satellite platform (e.g. Sentinel-2)")
    aoi: Optional[GeoBoundingBox] = Field(default=None, description="Area of Interest bounding box in WGS84")
    scene_id: Optional[str] = Field(default=None, description="Specific scene identifier")

    @model_validator(mode="after")
    def validate_date_order(self) -> "RetrievalFilter":
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from cannot be later than date_to")
        return self


class TextRetrievalRequest(BaseModel):
    """Request payload for text-to-image semantic search."""

    query: str = Field(..., min_length=1, description="Natural language search prompt")
    top_k: int = Field(default=10, ge=1, le=100, description="Maximum results to return")
    filters: Optional[RetrievalFilter] = Field(default=None, description="Optional metadata and AOI filters")


class ImageRetrievalRequest(BaseModel):
    """Request payload for image-to-image visual similarity search."""

    file_path: Optional[str] = Field(default=None, description="Local path to query raster/chip")
    tile_id: Optional[str] = Field(default=None, description="Existing indexed tile ID to use as query")
    top_k: int = Field(default=10, ge=1, le=100, description="Maximum results to return")
    filters: Optional[RetrievalFilter] = Field(default=None, description="Optional metadata and AOI filters")
    exclude_query_tile: bool = Field(default=False, description="Whether to exclude the query tile itself from results")

    @model_validator(mode="after")
    def validate_source_provided(self) -> "ImageRetrievalRequest":
        if not self.file_path and not self.tile_id:
            raise ValueError("Either file_path or tile_id must be provided for image retrieval")
        return self


class RetrievalResultItem(BaseModel):
    """Individual ranked retrieval result item."""

    tile_id: str = Field(..., description="Unique tile identifier")
    scene_id: str = Field(..., description="Parent scene identifier")
    score: float = Field(..., description="Normalized similarity score (e.g. cosine similarity in [-1.0, 1.0])")
    rank: int = Field(..., ge=1, description="1-based ranking position")
    acquisition_time: Optional[datetime] = Field(default=None, description="Acquisition timestamp")
    sensor: str = Field(default="unknown", description="Sensor name")
    platform: str = Field(default="unknown", description="Platform name")
    bounds_wgs84: GeoBoundingBox = Field(..., description="Geographic bounding box")
    provenance_id: Optional[str] = Field(default=None, description="Lineage provenance record reference")
    embedding_model_id: str = Field(..., description="Model ID used to produce embedding")
    embedding_model_version: str = Field(..., description="Model version")
    file_path: Optional[str] = Field(default=None, description="Local filesystem path to tile")


class RetrievalResponse(BaseModel):
    """Complete response payload for a semantic search operation with clear candidate semantics."""

    query: str = Field(..., description="Text query or image path/ID representation")
    query_type: str = Field(..., description="'text' or 'image'")
    total_indexed_tiles: int = Field(default=0, ge=0, description="Total vectors currently present in index")
    filtered_candidates_count: int = Field(default=0, ge=0, description="Candidate tiles matching metadata/AOI pre-filters")
    scored_candidates_count: int = Field(default=0, ge=0, description="Candidate vectors actually scored by vector similarity")
    total_candidates_searched: int = Field(..., ge=0, description="Candidate count scored (alias for scored_candidates_count)")
    returned_count: int = Field(..., ge=0, description="Count of returned ranked results")
    results: List[RetrievalResultItem] = Field(default_factory=list, description="Ranked retrieval results")
    filters_applied: Optional[RetrievalFilter] = Field(default=None, description="Filters that were applied")
    execution_time_ms: float = Field(..., ge=0.0, description="Elapsed search latency in milliseconds")


class RetrievalHealthResponse(BaseModel):
    """Retrieval subsystem status and telemetry response."""

    index_size: int = Field(..., ge=0, description="Total vectors currently indexed")
    active_embedding_model: str = Field(..., description="Active embedding model candidate ID")
    embedding_dimension: int = Field(..., gt=0, description="Dimensionality of feature vectors")
    offline_status: bool = Field(default=True, description="Whether retrieval operates strictly offline")
    backend_type: str = Field(default="exact_numpy_cosine", description="Vector index implementation backend")
    indexed_scenes_count: int = Field(default=0, ge=0, description="Total unique scenes represented in index")


class EmbeddingRecord(BaseModel):
    """Persistent record of a generated embedding vector and its lineage."""

    tile_id: str = Field(..., description="Target tile identifier")
    scene_id: str = Field(..., description="Parent scene identifier")
    embedding_model_id: str = Field(..., description="Model candidate identifier")
    embedding_model_version: str = Field(..., description="Model version")
    embedding_dimension: int = Field(..., gt=0, description="Length of embedding vector")
    preprocessing_version: str = Field(..., description="Preprocessing pipeline version")
    source_sha256: str = Field(..., description="SHA-256 hash of the source tile image")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Generation timestamp")
    vector_index_reference: str = Field(..., description="Reference in vector index storage")
    provenance_reference: str = Field(..., description="Associated ProvenanceRecord ID")
