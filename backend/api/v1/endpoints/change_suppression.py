"""ASTRA Change Suppression API Endpoints (Phase M4D).

Provides REST endpoints for false-alarm screening, tri-state filtered change mask retrieval,
and auditable artifact provenance conforming to ASTRA-DC-v0.1.
"""

from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.config import settings
from backend.ml.change_classification.service import ChangeClassificationEvidenceService
from backend.ml.change_classification.types import (
    ChangeClassificationResult,
    ChangeEvidence,
)
from backend.ml.change_suppression.service import ChangeSuppressionService
from backend.ml.change_suppression.types import (
    SuppressionConfig,
    SuppressionResult,
)

router = APIRouter(prefix="/change-suppression")

_suppression_service: Optional[ChangeSuppressionService] = None


def get_suppression_service() -> ChangeSuppressionService:
    """Provides the active ChangeSuppressionService instance."""
    global _suppression_service
    if _suppression_service is None:
        _suppression_service = ChangeSuppressionService(
            output_dir=settings.ASTRA_CHANGE_SUPPRESSION_DIR,
            provenance_dir=settings.ASTRA_MANIFESTS_DIR / "provenance",
        )
    return _suppression_service


def set_suppression_service(service: Optional[ChangeSuppressionService]) -> None:
    """Overrides the active ChangeSuppressionService instance for testing."""
    global _suppression_service
    _suppression_service = service


class SuppressRequest(BaseModel):
    """Request payload for false-alarm suppression."""

    evidence_id: Optional[str] = Field(default=None, description="M4C-A Evidence ID")
    classification_id: Optional[str] = Field(default=None, description="M4C-B Classification ID")
    evidence: Optional[ChangeEvidence] = Field(default=None, description="Direct ChangeEvidence payload")
    classification: Optional[ChangeClassificationResult] = Field(default=None, description="Direct ChangeClassificationResult payload")
    config_overrides: Dict[str, Any] = Field(default_factory=dict, description="Suppression hyperparameters")
    auxiliary_data: Dict[str, Any] = Field(default_factory=dict, description="Scene or solar metadata")


@router.get("/health", response_model=Dict[str, Any])
def health_check(
    service: ChangeSuppressionService = Depends(get_suppression_service),
) -> Dict[str, Any]:
    """Returns false-alarm suppression service health and storage status."""
    suppressions = service.list_suppressions()
    return {
        "status": "ready",
        "suppressor_id": "astra_deterministic_suppressor",
        "suppressor_version": "1.0.0",
        "suppressions_stored": len(suppressions),
    }


@router.post("/suppress", response_model=SuppressionResult)
def suppress_changes(
    payload: SuppressRequest,
    service: ChangeSuppressionService = Depends(get_suppression_service),
) -> SuppressionResult:
    """Executes false-alarm screening and returns a structured SuppressionResult."""
    # 1. Resolve ChangeEvidence
    evidence = payload.evidence
    if evidence is None and payload.evidence_id:
        evi_service = ChangeClassificationEvidenceService(
            output_dir=settings.ASTRA_CHANGE_CLASSIFICATION_DIR,
            provenance_dir=settings.ASTRA_MANIFESTS_DIR / "provenance",
        )
        evidence = evi_service.get_evidence(payload.evidence_id)
        if evidence is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"ChangeEvidence '{payload.evidence_id}' not found.",
            )

    if evidence is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either 'evidence_id' or 'evidence' payload must be provided.",
        )

    # 2. Resolve ChangeClassificationResult (optional)
    classification = payload.classification
    if classification is None and payload.classification_id:
        evi_service = ChangeClassificationEvidenceService(
            output_dir=settings.ASTRA_CHANGE_CLASSIFICATION_DIR,
            provenance_dir=settings.ASTRA_MANIFESTS_DIR / "provenance",
        )
        classification = evi_service.get_classification(payload.classification_id)

    # 3. Configure
    cfg = SuppressionConfig(**payload.config_overrides) if payload.config_overrides else None

    # 4. Execute screening
    try:
        result = service.suppress_false_alarms(
            evidence=evidence,
            classification=classification,
            config=cfg,
            auxiliary_data=payload.auxiliary_data,
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Suppression execution error: {str(e)}",
        )


@router.get("/results/{suppression_id}", response_model=SuppressionResult)
def get_suppression_result_by_id(
    suppression_id: str,
    service: ChangeSuppressionService = Depends(get_suppression_service),
) -> SuppressionResult:
    """Retrieves a persisted SuppressionResult by ID."""
    result = service.get_suppression_result(suppression_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SuppressionResult '{suppression_id}' not found.",
        )
    return result


@router.get("/results/{suppression_id}/mask")
def get_filtered_change_mask(
    suppression_id: str,
    service: ChangeSuppressionService = Depends(get_suppression_service),
):
    """Streams the serialized tri-state filtered change mask GeoTIFF."""
    result = service.get_suppression_result(suppression_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SuppressionResult '{suppression_id}' not found.",
        )
    if not result.filtered_change_mask_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Filtered mask path for '{suppression_id}' is not recorded.",
        )

    mask_path = Path(result.filtered_change_mask_path)
    if not mask_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Filtered mask file at '{mask_path}' does not exist on disk.",
        )

    return FileResponse(
        str(mask_path),
        media_type="image/tiff",
        filename="filtered_change_mask.tif",
    )
