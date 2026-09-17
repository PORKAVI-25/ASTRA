"""ASTRA Pipeline Orchestration REST API Endpoints.

Provides thin orchestration endpoint for multi-temporal change investigations.
Enforces strict configuration validation (extra="forbid") and client-safe error reporting.
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, status

from backend.orchestrator.service import ASTRAPipelineOrchestrator
from backend.orchestrator.types import (
    InvestigationDossier,
    InvestigationPipelineError,
    InvestigationRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pipeline")

_pipeline_orchestrator: Optional[ASTRAPipelineOrchestrator] = None


def get_pipeline_orchestrator() -> ASTRAPipelineOrchestrator:
    """Provides the singleton ASTRAPipelineOrchestrator instance."""
    global _pipeline_orchestrator
    if _pipeline_orchestrator is None:
        _pipeline_orchestrator = ASTRAPipelineOrchestrator()
    return _pipeline_orchestrator


def set_pipeline_orchestrator(orchestrator: Optional[ASTRAPipelineOrchestrator]) -> None:
    """Overrides the active ASTRAPipelineOrchestrator instance (for testing)."""
    global _pipeline_orchestrator
    _pipeline_orchestrator = orchestrator


@router.post(
    "/investigate",
    response_model=InvestigationDossier,
    status_code=status.HTTP_200_OK,
    summary="Execute End-to-End Pipeline Investigation",
    description="Orchestrates M4A temporal series pairing through M4E temporal evidence reasoning.",
)
def investigate_pipeline(request: InvestigationRequest) -> InvestigationDossier:
    """Executes deterministic end-to-end multi-temporal investigation."""
    orchestrator = get_pipeline_orchestrator()
    try:
        return orchestrator.run_investigation(request)
    except InvestigationPipelineError as e:
        logger.warning("Pipeline orchestration failed at stage '%s': %s", e.stage, e.message)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "InvestigationPipelineError",
                "stage": e.stage,
                "message": e.message,
                "stage_result": e.stage_result.model_dump() if e.stage_result else None,
            },
        )
    except ValueError as e:
        logger.warning("Validation error during pipeline orchestration: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "ValueError", "message": str(e)},
        )
    except Exception as e:
        logger.error("Unhandled error during pipeline orchestration: %s", str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "InternalServerError", "message": str(e)},
        )
