"""ASTRA Temporal Series & Scene Pairs Discovery Endpoints.

Provides read-only REST endpoints for exploring ingested temporal series and
generating deterministic scene pairs. Thin adapter over TemporalCatalog and
pair_observations without duplicating temporal reasoning logic.
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from backend.config import settings
from backend.ml.change.scene_pairing import create_scene_pair, pair_observations
from backend.ml.change.temporal_catalog import TemporalCatalog
from backend.ml.change.types import PairingConfig, ScenePair, TemporalSeries
from backend.api.v1.endpoints.pipeline import get_pipeline_orchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/temporal")


def get_temporal_catalog() -> TemporalCatalog:
    """Provides the active TemporalCatalog instance from the pipeline orchestrator."""
    catalog = get_pipeline_orchestrator().catalog
    if len(catalog.list_series()) == 0:
        tiles_dir = (
            settings.ASTRA_MANIFESTS_DIR / "tiles"
            if (settings.ASTRA_MANIFESTS_DIR / "tiles").exists()
            else settings.ASTRA_PROCESSED_DIR / "tiles"
        )
        scenes_dir = settings.ASTRA_MANIFESTS_DIR / "scenes"
        if tiles_dir.exists() or scenes_dir.exists():
            catalog.discover_manifests(tiles_dir=tiles_dir, scenes_dir=scenes_dir)
    return catalog


class TemporalSeriesPairsResponse(BaseModel):
    """Response envelope for scene pairs generated for a temporal series."""

    series_id: str = Field(..., description="TemporalSeries identifier")
    mode: str = Field(..., description="Pairing mode ('baseline', 'adjacent', or 'all_pairwise')")
    valid_pairs: List[ScenePair] = Field(
        default_factory=list, description="Compatible scene pairs ready for change analysis"
    )
    rejected_pairs: List[ScenePair] = Field(
        default_factory=list, description="Incompatible scene pairs rejected by pairing rules"
    )
    total_pairs: int = Field(default=0, description="Total count of candidate pairs evaluated")

    model_config = ConfigDict(extra="forbid")


@router.get(
    "/series",
    response_model=List[TemporalSeries],
    status_code=status.HTTP_200_OK,
    summary="List Available Temporal Series",
    description="Returns all registered temporal series sorted by series identifier.",
)
def list_temporal_series(
    catalog: TemporalCatalog = Depends(get_temporal_catalog),
) -> List[TemporalSeries]:
    """Returns all available temporal series."""
    return catalog.list_series()


@router.get(
    "/series/{series_id}",
    response_model=TemporalSeries,
    status_code=status.HTTP_200_OK,
    summary="Get Temporal Series by ID",
    description="Retrieves a specific temporal series including its chronological observations.",
)
def get_temporal_series(
    series_id: str,
    catalog: TemporalCatalog = Depends(get_temporal_catalog),
) -> TemporalSeries:
    """Retrieves a single temporal series by ID."""
    series = catalog.get_series(series_id)
    if series is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "NOT_FOUND",
                "message": f"TemporalSeries '{series_id}' does not exist.",
                "details": {"series_id": series_id},
            },
        )
    return series


@router.get(
    "/series/{series_id}/pairs",
    response_model=TemporalSeriesPairsResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate Pairs for Temporal Series",
    description="Evaluates pairwise combinations across the series observations using standard pairing rules.",
)
def get_series_pairs(
    series_id: str,
    mode: str = Query(
        "baseline",
        description="Pairing strategy: 'baseline' (all relative to T0), 'adjacent' (consecutive steps), or 'all_pairwise'",
    ),
    catalog: TemporalCatalog = Depends(get_temporal_catalog),
) -> TemporalSeriesPairsResponse:
    """Generates and returns valid and rejected ScenePairs for the specified series."""
    series = catalog.get_series(series_id)
    if series is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "NOT_FOUND",
                "message": f"TemporalSeries '{series_id}' does not exist.",
                "details": {"series_id": series_id},
            },
        )

    if series.observation_count < 2:
        return TemporalSeriesPairsResponse(
            series_id=series_id,
            mode=mode,
            valid_pairs=[],
            rejected_pairs=[],
            total_pairs=0,
        )

    cfg = PairingConfig()
    if mode == "baseline":
        t0 = series.observations[0]
        all_pairs = [
            create_scene_pair(t0, obs_k, cfg, pairing_method="baseline_t0")
            for obs_k in series.observations[1:]
        ]
    elif mode in ["adjacent", "all_pairwise"]:
        all_pairs = pair_observations(series.observations, config=cfg, mode=mode)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "VALIDATION_ERROR",
                "message": f"Unknown pairing mode '{mode}'. Choose 'baseline', 'adjacent', or 'all_pairwise'.",
                "details": {"mode": mode},
            },
        )

    valid_pairs: List[ScenePair] = []
    rejected_pairs: List[ScenePair] = []

    for p in all_pairs:
        if p.compatibility.is_compatible:
            valid_pairs.append(p)
        else:
            rejected_pairs.append(p)

    sort_key = lambda p: (
        p.earlier_observation.acquisition_time,
        p.later_observation.acquisition_time,
        p.pair_id,
    )
    valid_sorted = sorted(valid_pairs, key=sort_key)
    rejected_sorted = sorted(rejected_pairs, key=sort_key)

    return TemporalSeriesPairsResponse(
        series_id=series_id,
        mode=mode,
        valid_pairs=valid_sorted,
        rejected_pairs=rejected_sorted,
        total_pairs=len(all_pairs),
    )
