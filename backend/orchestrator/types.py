"""ASTRA Pipeline Orchestration Data Contracts (Phase M4F).

Defines immutable Pydantic data contracts for investigation requests,
stage execution metrics, complete upstream lineage, and finalized
analyst investigation dossiers conforming to ASTRA-DC-v0.1.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from backend.ml.change_classification.types import ClassifierConfig, EvidenceConfig
from backend.ml.change_detection.types import ChangeDetectionConfig
from backend.ml.change_suppression.types import SuppressionConfig
from backend.ml.temporal_evidence.types import (
    TemporalEvidenceConfig,
    TemporalEvidenceResult,
)


class InvestigationStageStatus(str, Enum):
    """Execution status for an individual pipeline orchestration stage."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class InvestigationRequest(BaseModel):
    """Strict request specification for an automated multi-temporal change investigation."""

    series_id: str = Field(
        ..., min_length=3, description="Target TemporalSeries identifier to evaluate"
    )
    discovery_pair_id: str = Field(
        ..., min_length=5, description="ScenePair identifier where the candidate change was discovered"
    )
    candidate_region_id: str = Field(
        ..., min_length=3, description="Locally unique region identifier within discovery change detection result"
    )
    output_dir: Optional[str] = Field(
        default=None, description="Optional custom directory path to persist investigation artifacts"
    )
    change_detection_config: Optional[ChangeDetectionConfig] = Field(
        default=None, description="Optional overrides for M4B ChangeDetectionConfig"
    )
    evidence_config: Optional[EvidenceConfig] = Field(
        default=None, description="Optional overrides for M4C-A EvidenceConfig"
    )
    classifier_config: Optional[ClassifierConfig] = Field(
        default=None, description="Optional overrides for M4C-B ClassifierConfig"
    )
    suppression_config: Optional[SuppressionConfig] = Field(
        default=None, description="Optional overrides for M4D SuppressionConfig"
    )
    temporal_evidence_config: Optional[TemporalEvidenceConfig] = Field(
        default=None, description="Optional overrides for M4E TemporalEvidenceConfig"
    )
    pairing_strategy: Optional[str] = Field(
        default="adjacent",
        description="Pairing strategy for subsequent observations: 'adjacent' (chronological steps) or 'baseline' (relative to T0)",
    )
    requested_format: Optional[str] = Field(
        default="json", description="Requested artifact serialization format ('json')"
    )

    model_config = ConfigDict(extra="forbid")


class InvestigationStageResult(BaseModel):
    """Detailed record of an executed pipeline stage."""

    stage: str = Field(..., description="Name of the pipeline stage")
    status: InvestigationStageStatus = Field(..., description="Stage execution outcome status")
    artifact_id: Optional[str] = Field(
        default=None, description="Primary artifact identifier produced by the stage"
    )
    provenance_id: Optional[str] = Field(
        default=None, description="Associated provenance record identifier if produced"
    )
    output_path: Optional[str] = Field(
        default=None, description="Filesystem path where stage artifact was persisted"
    )
    error_message: Optional[str] = Field(
        default=None, description="Error diagnostics if the stage failed"
    )
    details: Dict[str, Any] = Field(
        default_factory=dict, description="Stage-specific execution metrics and diagnostic details"
    )
    timestamp: Optional[datetime] = Field(
        default=None, description="Timestamp associated with stage execution"
    )

    model_config = ConfigDict(extra="forbid")


class InvestigationLineage(BaseModel):
    """Complete upstream lineage preserving exact artifact IDs and hashes across all evaluated pairs."""

    scene_pair_ids: List[str] = Field(
        default_factory=list, description="Ordered list of evaluated scene pair identifiers"
    )
    change_detection_result_ids: List[str] = Field(
        default_factory=list, description="Ordered list of upstream M4B change detection result IDs"
    )
    evidence_ids: List[str] = Field(
        default_factory=list, description="Ordered list of upstream M4C-A feature extraction IDs"
    )
    classification_ids: List[str] = Field(
        default_factory=list, description="Ordered list of upstream M4C-B classification IDs"
    )
    suppression_ids: List[str] = Field(
        default_factory=list, description="Ordered list of upstream M4D suppression IDs"
    )
    temporal_evidence_id: Optional[str] = Field(
        default=None, description="Final M4E temporal evidence evaluation ID"
    )
    upstream_hashes: Dict[str, str] = Field(
        default_factory=dict, description="Cryptographic hashes of all upstream source and artifact inputs"
    )
    candidate_correspondence: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Resolved spatial correspondence outcome mapping per evaluated pair: pair_id -> details",
    )

    model_config = ConfigDict(extra="forbid")


class InvestigationDossier(BaseModel):
    """Final, self-contained analyst dossier for an end-to-end multi-temporal change investigation."""

    investigation_id: str = Field(
        ..., min_length=5, description="Deterministic investigation identifier (inv_{hash})"
    )
    request: InvestigationRequest = Field(
        ..., description="Original validated investigation request"
    )
    series_id: str = Field(
        ..., description="Target TemporalSeries identifier"
    )
    discovery_pair_id: str = Field(
        ..., description="ScenePair identifier of the discovery epoch"
    )
    candidate_region_id: str = Field(
        ..., description="Candidate change region identifier (e.g. reg_0001)"
    )
    temporal_evidence_id: Optional[str] = Field(
        default=None, description="Final M4E temporal evidence reference"
    )
    stage_results: List[InvestigationStageResult] = Field(
        default_factory=list, description="Ordered results for all executed pipeline stages"
    )
    lineage: InvestigationLineage = Field(
        ..., description="Cryptographic lineage tracing back through all evaluated pairs"
    )
    provenance_id: str = Field(
        ..., min_length=5, description="Associated investigation provenance record identifier (prov_inv_{hash})"
    )
    created_at: datetime = Field(
        ..., description="Deterministic creation timestamp anchored to latest observation"
    )
    content_hash: str = Field(
        ..., min_length=16, description="Deterministic 16-character content identity hash"
    )
    temporal_evidence: Optional[TemporalEvidenceResult] = Field(
        default=None, description="Full M4E temporal evidence analysis result"
    )
    status: str = Field(
        default="COMPLETED", description="Overall investigation status: 'COMPLETED' or 'FAILED'"
    )
    dossier_path: Optional[str] = Field(
        default=None, description="Filesystem path where dossier artifact was saved"
    )

    model_config = ConfigDict(extra="forbid")


class InvestigationPipelineError(Exception):
    """Exception raised when a required pipeline orchestration stage fails."""

    def __init__(
        self,
        message: str,
        stage: str,
        stage_result: Optional[InvestigationStageResult] = None,
        partial_lineage: Optional[InvestigationLineage] = None,
    ):
        super().__init__(message)
        self.message = message
        self.stage = stage
        self.stage_result = stage_result
        self.partial_lineage = partial_lineage
