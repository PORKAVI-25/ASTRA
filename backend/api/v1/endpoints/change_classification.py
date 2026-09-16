"""ASTRA Change Classification Evidence API Endpoints (Phase M4C-A).

Provides REST endpoints for extracting, querying, and auditing explainable
change evidence across morphology, geometry, temporal, and spectral families.
"""

from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.config import settings
from backend.ml.change.types import ScenePair
from backend.ml.change_classification.service import ChangeClassificationEvidenceService
from backend.ml.change_classification.types import (
    ChangeClassificationResult,
    ChangeEvidence,
    ClassifierConfig,
    EvidenceConfig,
)
from backend.ml.change_detection.service import ChangeDetectionService
from backend.ml.change_detection.types import ChangeDetectionResult

router = APIRouter(prefix="/change-classification")

_evidence_service: Optional[ChangeClassificationEvidenceService] = None


def get_evidence_service() -> ChangeClassificationEvidenceService:
    """Provides the active ChangeClassificationEvidenceService instance."""
    global _evidence_service
    if _evidence_service is None:
        _evidence_service = ChangeClassificationEvidenceService(
            output_dir=settings.ASTRA_CHANGE_CLASSIFICATION_DIR,
            provenance_dir=settings.ASTRA_MANIFESTS_DIR / "provenance",
        )
    return _evidence_service


def set_evidence_service(service: Optional[ChangeClassificationEvidenceService]) -> None:
    """Overrides the active ChangeClassificationEvidenceService instance."""
    global _evidence_service
    _evidence_service = service


class ChangeEvidenceRunRequest(BaseModel):
    """Request payload for change evidence extraction."""

    scene_pair_id: Optional[str] = Field(default=None, description="M4A ScenePair ID")
    change_detection_result_id: Optional[str] = Field(default=None, description="M4B ChangeDetectionResult ID")
    pair: Optional[ScenePair] = Field(default=None, description="Direct ScenePair contract")
    change_result: Optional[ChangeDetectionResult] = Field(default=None, description="Direct ChangeDetectionResult contract")
    earlier_path: Optional[str] = Field(default=None, description="Path to earlier imagery file")
    later_path: Optional[str] = Field(default=None, description="Path to later imagery file")
    config: Optional[EvidenceConfig] = Field(default=None, description="Evidence extraction hyperparameters")


class ChangeClassificationRunRequest(BaseModel):
    """Request payload for change-type classification."""

    evidence_id: Optional[str] = Field(default=None, description="M4C-A Evidence ID")
    evidence: Optional[ChangeEvidence] = Field(default=None, description="Direct ChangeEvidence contract")
    config: Optional[ClassifierConfig] = Field(default=None, description="Classification hyperparameters and thresholds")


class ChangeClassificationHealthResponse(BaseModel):
    """Telemetry schema for change classification subsystem."""

    status: str = "healthy"
    subsystem: str = "change_evidence_extraction"
    extractor_id: str = "astra_change_evidence"
    extractor_version: str = "1.0.0"
    classifier_id: str = "astra_deterministic_rule_classifier"
    classifier_version: str = "1.0.0"
    offline_mode: bool = True
    evidence_documents_stored: int
    classifications_stored: int


@router.get(
    "/health",
    response_model=ChangeClassificationHealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Change classification subsystem health",
)
async def change_classification_health(
    service: ChangeClassificationEvidenceService = Depends(get_evidence_service),
):
    """Reports status, active extractor and classifier versions, and counts of stored artifacts."""
    evi_count = len(service.list_evidence())
    cls_count = len(service.list_classifications())
    return ChangeClassificationHealthResponse(
        status="healthy",
        subsystem="change_evidence_extraction",
        extractor_id=service.extractor.config.extractor_id,
        extractor_version=service.extractor.config.extractor_version,
        classifier_id=service.classifier.config.classifier_id,
        classifier_version=service.classifier.config.classifier_version,
        offline_mode=settings.ASTRA_OFFLINE_MODE,
        evidence_documents_stored=evi_count,
        classifications_stored=cls_count,
    )


@router.post(
    "/evidence",
    response_model=ChangeEvidence,
    status_code=status.HTTP_200_OK,
    summary="Extract explainable change evidence",
)
async def extract_change_evidence(
    request: ChangeEvidenceRunRequest,
    service: ChangeClassificationEvidenceService = Depends(get_evidence_service),
):
    """Extracts structured, explainable evidence across spatial, temporal, and spectral families."""
    # Strict offline security check
    for path_val in (request.earlier_path, request.later_path):
        if path_val and (path_val.startswith("http://") or path_val.startswith("https://")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Remote URLs are strictly forbidden in offline mode. Provide local file paths.",
            )

    # Resolve ChangeDetectionResult
    change_result = request.change_result
    if change_result is None and request.change_detection_result_id:
        cd_service = ChangeDetectionService()
        change_result = cd_service.get_result(request.change_detection_result_id)
        if change_result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Change detection result '{request.change_detection_result_id}' not found.",
            )

    if change_result is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide either 'change_result' or a valid 'change_detection_result_id'.",
        )

    # Resolve ScenePair
    pair = request.pair
    if pair is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide 'pair' (M4A ScenePair contract).",
        )

    try:
        evidence = service.extract_evidence(
            scene_pair=pair,
            change_result=change_result,
            earlier_image=request.earlier_path,
            later_image=request.later_path,
            config=request.config,
        )
        return evidence
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Evidence extraction failed: {str(e)}",
        )


@router.get(
    "/evidence/{evidence_id}",
    response_model=ChangeEvidence,
    status_code=status.HTTP_200_OK,
    summary="Retrieve stored change evidence",
)
async def get_change_evidence(
    evidence_id: str,
    service: ChangeClassificationEvidenceService = Depends(get_evidence_service),
):
    """Retrieves a previously computed change evidence document by ID."""
    evidence = service.get_evidence(evidence_id)
    if evidence is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Change evidence document '{evidence_id}' not found.",
        )
    return evidence


@router.post(
    "/classify",
    response_model=ChangeClassificationResult,
    status_code=status.HTTP_200_OK,
    summary="Classify change types from evidence",
)
async def classify_changes(
    request: ChangeClassificationRunRequest,
    service: ChangeClassificationEvidenceService = Depends(get_evidence_service),
):
    """Executes deterministic, explainable change-type classification on extracted evidence."""
    evidence = request.evidence
    if evidence is None and request.evidence_id:
        evidence = service.get_evidence(request.evidence_id)
        if evidence is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Change evidence document '{request.evidence_id}' not found.",
            )

    if evidence is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide either 'evidence' (ChangeEvidence contract) or 'evidence_id'.",
        )

    try:
        classification = service.classify_evidence(evidence, config=request.config)
        return classification
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Change classification failed: {str(e)}",
        )


@router.get(
    "/classifications/{classification_id}",
    response_model=ChangeClassificationResult,
    status_code=status.HTTP_200_OK,
    summary="Retrieve stored change classification",
)
async def get_change_classification(
    classification_id: str,
    service: ChangeClassificationEvidenceService = Depends(get_evidence_service),
):
    """Retrieves a previously computed change classification document by ID."""
    cls_result = service.get_classification(classification_id)
    if cls_result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Change classification document '{classification_id}' not found.",
        )
    return cls_result
