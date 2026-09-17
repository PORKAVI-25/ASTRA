"""ASTRA Phase M4E: Temporal Evidence REST API Endpoints.

Provides REST endpoints for deterministic multi-temporal candidate evidence evaluation,
trajectory analysis, onset interval retrieval, and provenance tracking.
Enforces strict configuration validation (extra="forbid") and client-safe error reporting.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.config import settings
from backend.ml.change.types import TemporalSeries
from backend.ml.temporal_evidence.service import TemporalEvidenceService
from backend.ml.temporal_evidence.types import (
    CandidateRegionRef,
    PairwiseTemporalEvidenceInput,
    TemporalEvidenceConfig,
    TemporalEvidenceResult,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/temporal-evidence")

_temporal_service: Optional[TemporalEvidenceService] = None


def get_temporal_service() -> TemporalEvidenceService:
    """Provides the active TemporalEvidenceService instance."""
    global _temporal_service
    if _temporal_service is None:
        _temporal_service = TemporalEvidenceService(
            output_dir=settings.ASTRA_TEMPORAL_EVIDENCE_DIR,
            provenance_dir=settings.ASTRA_MANIFESTS_DIR / "provenance",
        )
    return _temporal_service


def set_temporal_service(service: Optional[TemporalEvidenceService]) -> None:
    """Overrides the active TemporalEvidenceService instance for testing."""
    global _temporal_service
    _temporal_service = service


class EvaluateTemporalEvidenceRequest(BaseModel):
    """Request payload for multi-temporal candidate evidence evaluation."""

    candidate_ref: CandidateRegionRef = Field(
        ..., description="Unique lineage reference to candidate region"
    )
    series_id: Optional[str] = Field(
        default=None, description="Series identifier (resolved from catalog/storage if omitted)"
    )
    series: Optional[TemporalSeries] = Field(
        default=None, description="Direct in-memory TemporalSeries payload"
    )
    discovery_pair_evidence: PairwiseTemporalEvidenceInput = Field(
        ..., description="Upstream pipeline bundle for discovery scene pair"
    )
    pairwise_evidence: List[PairwiseTemporalEvidenceInput] = Field(
        default_factory=list, description="Upstream pipeline bundles for subsequent scene pairs"
    )
    config_overrides: Optional[Dict[str, Any]] = Field(
        default=None, description="Optional hyperparameter overrides validated against TemporalEvidenceConfig"
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("config_overrides")
    @classmethod
    def validate_config_overrides(cls, v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Ensures config overrides match TemporalEvidenceConfig and rejects unknown keys."""
        if v is not None:
            # Enforces extra="forbid" validation
            TemporalEvidenceConfig(**v)
        return v


@router.get("/health", response_model=Dict[str, Any])
def health_check(
    service: TemporalEvidenceService = Depends(get_temporal_service),
) -> Dict[str, Any]:
    """Health check for Temporal Evidence Reasoner service."""
    return {
        "status": "healthy",
        "service": "ASTRA Temporal Evidence Reasoner API",
        "version": "1.0.0",
        "offline_mode": settings.ASTRA_OFFLINE_MODE,
        "output_dir": str(service.output_dir),
    }


@router.post("/evaluate", response_model=TemporalEvidenceResult)
def evaluate_temporal_evidence(
    payload: EvaluateTemporalEvidenceRequest,
    service: TemporalEvidenceService = Depends(get_temporal_service),
) -> TemporalEvidenceResult:
    """Evaluates candidate change support across an ordered TemporalSeries."""
    # 1. Enforce discovery pair consistency with candidate reference
    if payload.discovery_pair_evidence.scene_pair_id != payload.candidate_ref.scene_pair_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Discovery pair ID mismatch: discovery_pair_evidence.scene_pair_id "
                f"'{payload.discovery_pair_evidence.scene_pair_id}' != candidate_ref.scene_pair_id '{payload.candidate_ref.scene_pair_id}'."
            ),
        )

    if payload.discovery_pair_evidence.change_detection_result_id != payload.candidate_ref.change_detection_result_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Discovery change detection result ID mismatch: discovery_pair_evidence.change_detection_result_id "
                f"'{payload.discovery_pair_evidence.change_detection_result_id}' != candidate_ref.change_detection_result_id "
                f"'{payload.candidate_ref.change_detection_result_id}'."
            ),
        )

    # 2. Resolve TemporalSeries
    series = payload.series
    if series is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Direct 'series' payload is required for temporal evidence evaluation.",
        )

    # 3. Configure
    cfg = TemporalEvidenceConfig(**payload.config_overrides) if payload.config_overrides else None

    # 4. Execute evaluation with client-safe error reporting
    try:
        result = service.evaluate_temporal_evidence(
            candidate_ref=payload.candidate_ref,
            series=series,
            discovery_pair_evidence=payload.discovery_pair_evidence,
            pairwise_evidence=payload.pairwise_evidence,
            config=cfg,
        )
        return result
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )
    except Exception as e:
        logger.exception("Temporal evidence evaluation encountered an internal error.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Temporal evidence evaluation encountered an internal error. Please check system logs.",
        )


@router.get("/{result_id}", response_model=TemporalEvidenceResult)
def get_temporal_evidence_by_id(
    result_id: str,
    service: TemporalEvidenceService = Depends(get_temporal_service),
) -> TemporalEvidenceResult:
    """Retrieves a persisted TemporalEvidenceResult by its deterministic ID."""
    result = service.get_temporal_evidence(result_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"TemporalEvidenceResult '{result_id}' not found.",
        )
    return result
