"""System health & diagnostics endpoint."""

from datetime import datetime, timezone
from fastapi import APIRouter
from backend.config import settings
from geospatial.contracts import HealthResponse
from backend.ingestion import get_ingestion_status
from backend.retrieval import get_retrieval_status
from backend.change_analysis import get_change_analysis_status
from backend.provenance import get_provenance_status
from backend.evaluation import get_evaluation_status

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="System Health & Diagnostic Check",
    description="Returns real-time health telemetry across all ASTRA modules and reports offline readiness.",
)
async def check_health() -> HealthResponse:
    """Performs subsystem diagnostics and returns system health status."""
    return HealthResponse(
        status="healthy",
        version="0.1.0",
        service="ASTRA Backend API",
        timestamp=datetime.now(timezone.utc),
        environment=settings.ASTRA_ENV,
        offline_mode=settings.ASTRA_OFFLINE_MODE,
        modules={
            "api": "healthy",
            "ingestion": get_ingestion_status(),
            "retrieval": get_retrieval_status(),
            "change_analysis": get_change_analysis_status(),
            "provenance": get_provenance_status(),
            "evaluation": get_evaluation_status(),
        },
    )
