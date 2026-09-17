"""ASTRA Pipeline Orchestrator Module (Phase M4F).

Provides deterministic end-to-end orchestration across M4A temporal pairing,
M4B change detection, M4C-A evidence extraction, M4C-B classification,
M4D false-alarm suppression, and M4E temporal evidence reasoning.
"""

from backend.orchestrator.types import (
    InvestigationDossier,
    InvestigationLineage,
    InvestigationPipelineError,
    InvestigationRequest,
    InvestigationStageResult,
    InvestigationStageStatus,
)
from backend.orchestrator.service import ASTRAPipelineOrchestrator

__all__ = [
    "ASTRAPipelineOrchestrator",
    "InvestigationDossier",
    "InvestigationLineage",
    "InvestigationPipelineError",
    "InvestigationRequest",
    "InvestigationStageResult",
    "InvestigationStageStatus",
]
