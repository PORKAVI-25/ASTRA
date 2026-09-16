"""ASTRA Temporal Change Detection API Endpoints.

Provides REST endpoints for executing reproducible offline change detection,
retrieving quantitative metrics and spatial regions, and serving change mask imagery.
"""

from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.config import settings
from backend.ml.change.types import ScenePair
from backend.ml.change_detection.service import ChangeDetectionService
from backend.ml.change_detection.types import ChangeDetectionConfig, ChangeDetectionResult

router = APIRouter(prefix="/change-detection")

_change_service: Optional[ChangeDetectionService] = None


def get_change_detection_service() -> ChangeDetectionService:
    """Provides the active ChangeDetectionService instance."""
    global _change_service
    if _change_service is None:
        _change_service = ChangeDetectionService(
            output_dir=settings.ASTRA_CHANGE_RESULTS_DIR,
            provenance_dir=settings.ASTRA_MANIFESTS_DIR / "provenance",
        )
    return _change_service


def set_change_detection_service(service: Optional[ChangeDetectionService]) -> None:
    """Overrides the active ChangeDetectionService instance (useful for testing/isolation)."""
    global _change_service
    _change_service = service


class ChangeDetectionRunRequest(BaseModel):
    """Request schema for executing change detection."""

    earlier_path: Optional[str] = Field(default=None, description="Local path to earlier raster")
    later_path: Optional[str] = Field(default=None, description="Local path to later raster")
    pair: Optional[ScenePair] = Field(default=None, description="M4A ScenePair contract")
    config: Optional[ChangeDetectionConfig] = Field(default=None, description="Detection hyperparameters")


class ChangeDetectionHealthResponse(BaseModel):
    """Telemetry and status schema for change detection subsystem."""

    status: str = "healthy"
    algorithm_id: str = "pixel_difference"
    algorithm_version: str = "1.0.0"
    offline_mode: bool = True
    results_stored: int


@router.get(
    "/health",
    response_model=ChangeDetectionHealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Change detection subsystem health",
)
async def change_detection_health(
    service: ChangeDetectionService = Depends(get_change_detection_service),
):
    """Reports status, active algorithm version, and stored change detection runs."""
    results_count = 0
    if service.output_dir.exists():
        results_count = sum(1 for p in service.output_dir.iterdir() if p.is_dir() and (p / "result.json").exists())

    return ChangeDetectionHealthResponse(
        status="healthy",
        algorithm_id=service.detector.algorithm_id,
        algorithm_version=service.detector.algorithm_version,
        offline_mode=settings.ASTRA_OFFLINE_MODE,
        results_stored=results_count,
    )


@router.post(
    "/run",
    response_model=ChangeDetectionResult,
    status_code=status.HTTP_200_OK,
    summary="Execute temporal change detection",
)
async def run_change_detection(
    request: ChangeDetectionRunRequest,
    service: ChangeDetectionService = Depends(get_change_detection_service),
):
    """Executes deterministic offline change detection between two rasters or a ScenePair."""
    # Check for prohibited remote URLs (strict offline compliance)
    for path_val in (request.earlier_path, request.later_path):
        if path_val and (path_val.startswith("http://") or path_val.startswith("https://")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Remote URLs are strictly forbidden in offline mode. Provide local file paths.",
            )

    try:
        if request.pair is not None:
            return service.run_detection(pair=request.pair, config=request.config)
        elif request.earlier_path and request.later_path:
            p1 = Path(request.earlier_path)
            p2 = Path(request.later_path)
            if not p1.exists():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Earlier raster file not found: {p1}",
                )
            if not p2.exists():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Later raster file not found: {p2}",
                )
            return service.run_detection(
                earlier_input=p1,
                later_input=p2,
                config=request.config,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Must provide either a ScenePair ('pair') or both 'earlier_path' and 'later_path'.",
            )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Change detection execution failed: {str(e)}",
        )


@router.get(
    "/{result_id}",
    response_model=ChangeDetectionResult,
    status_code=status.HTTP_200_OK,
    summary="Retrieve change detection result",
)
async def get_change_detection_result(
    result_id: str,
    service: ChangeDetectionService = Depends(get_change_detection_service),
):
    """Retrieves a previously computed change detection result by its deterministic ID."""
    result = service.get_result(result_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Change detection result '{result_id}' not found.",
        )
    return result


@router.get(
    "/{result_id}/mask",
    summary="Download binary change mask PNG",
)
async def get_change_mask_image(
    result_id: str,
    service: ChangeDetectionService = Depends(get_change_detection_service),
):
    """Serves the binary change mask image PNG for a given change detection result."""
    mask_path = service.get_mask_path(result_id)
    if mask_path is None or not mask_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Change mask for result '{result_id}' not found.",
        )
    return FileResponse(str(mask_path), media_type="image/png")
