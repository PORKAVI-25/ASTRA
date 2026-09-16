"""API v1 Endpoints for Scene Ingestion and Catalog Retrieval."""

from typing import List
from fastapi import APIRouter, HTTPException, status
from geospatial.contracts import (
    IngestionRequest,
    IngestionResponse,
    SceneManifest,
    SceneSummaryResponse,
    TileManifest,
)
from backend.ingestion.service import ingestion_service

router = APIRouter()


@router.post(
    "/ingestion",
    response_model=IngestionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a local GeoTIFF or COG raster",
    description="Validates, extracts metadata, executes windowed deterministic tiling, records provenance, and catalogs the scene.",
)
async def ingest_raster_scene(request: IngestionRequest) -> IngestionResponse:
    """Ingests a satellite scene from local filesystem path."""
    response = ingestion_service.ingest_raster(
        file_path=request.file_path,
        tile_size=request.tile_size,
        force_reprocess=request.force_reprocess,
    )

    if response.status == "failed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=response.message,
        )

    return response


@router.get(
    "/ingestion/{scene_id}",
    response_model=SceneManifest,
    summary="Get Scene Ingestion Manifest",
    description="Retrieves the complete ingestion manifest and metadata for a specific scene.",
)
async def get_ingestion_manifest(scene_id: str) -> SceneManifest:
    """Retrieves full manifest for a given scene ID."""
    scene = ingestion_service.get_scene(scene_id)
    if not scene:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scene with ID '{scene_id}' not found in catalog.",
        )
    return scene


@router.get(
    "/scenes",
    response_model=List[SceneSummaryResponse],
    summary="List all Ingested Scenes",
    description="Returns summary catalog listings for all successfully ingested satellite scenes.",
)
async def list_scenes() -> List[SceneSummaryResponse]:
    """Lists all cataloged scenes."""
    scenes = ingestion_service.list_scenes()
    return [
        SceneSummaryResponse(
            scene_id=s.scene_id,
            crs=s.crs,
            sensor=s.sensor,
            acquisition_time=s.acquisition_time,
            spatial_resolution_m=s.spatial_resolution_m,
            tile_count=s.tile_count,
            is_cog=s.is_cog,
            is_synthetic=s.is_synthetic,
            created_at=s.created_at,
        )
        for s in scenes
    ]


@router.get(
    "/scenes/{scene_id}/tiles",
    response_model=List[TileManifest],
    summary="List Tiles for a Scene",
    description="Returns all georeferenced tile manifests generated for the specified scene.",
)
async def get_scene_tiles(scene_id: str) -> List[TileManifest]:
    """Retrieves all chipped tile manifests for a given scene ID."""
    scene = ingestion_service.get_scene(scene_id)
    if not scene:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scene with ID '{scene_id}' not found.",
        )
    return ingestion_service.get_scene_tiles(scene_id)
