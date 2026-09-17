"""ASTRA Phase M4E: Temporal Evidence Reasoner Contracts.

Defines Pydantic data contracts for candidate lineage grounding,
chronological timeline evaluation, metric-projected spatial correspondence,
earliest supporting observation determination, onset interval bounding,
and multi-pair provenance tracking conforming to ASTRA-DC-v0.1.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.ml.change_classification.types import ChangeCategory, ConfidenceTier
from backend.ml.change_detection.types import ChangeDetectionResult
from backend.ml.change_classification.types import ChangeEvidence, ChangeClassificationResult
from backend.ml.change_suppression.types import SuppressionDecision, SuppressionResult


class TemporalNodeStatus(str, Enum):
    """Mutually exclusive evaluation status of a candidate region at a single temporal observation."""

    PRE_CHANGE_ABSENCE = "PRE_CHANGE_ABSENCE"
    """Sufficient positive upstream evidence confirms candidate change was absent (clear surface, valid pixels)."""

    EARLIEST_SUPPORTING = "EARLIEST_SUPPORTING"
    """Chronologically earliest valid observation satisfying M4D RETAINED and M4E support criteria."""

    PERSISTENT_SUPPORT = "PERSISTENT_SUPPORT"
    """Subsequent valid observation after earliest support that continues to satisfy support criteria."""

    FLAGGED_SUPPORT = "FLAGGED_SUPPORT"
    """Observation exhibits change features but carries M4D FLAGGED status or unresolved risk. Cannot be earliest."""

    SUPPRESSED_ARTIFACT = "SUPPRESSED_ARTIFACT"
    """Observation screened out by M4D as false alarm (cloud, shadow, edge shear, etc.). Zero support."""

    NO_SUPPORT = "NO_SUPPORT"
    """Observation valid and clear, but shows no detectable change features or support score is below threshold."""

    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    """Observation unusable due to cloud obstruction, nodata, out-of-footprint, or missing required bands/metadata."""

    SIMULTANEOUS_CO_TEMPORAL = "SIMULTANEOUS_CO_TEMPORAL"
    """Observation shares identical acquisition timestamp with another node; retained for audit, excluded from ordered interval."""


class TemporalSupportStatus(str, Enum):
    """Overall temporal evidence determination for a candidate change region."""

    STRONG_TEMPORAL_SUPPORT = "STRONG_TEMPORAL_SUPPORT"
    """Candidate has an earliest supporting observation plus at least (min_persistent_observations - 1) subsequent supporting observations (total supporting >= min_persistent_observations)."""

    SINGLE_OBSERVATION_SUPPORT = "SINGLE_OBSERVATION_SUPPORT"
    """Candidate is supported at only 1 observation (earliest supporting) with no persistent subsequent support."""

    FLAGGED_PENDING_REVIEW = "FLAGGED_PENDING_REVIEW"
    """Earliest potential evidence is M4D FLAGGED or unresolved; requires analyst review."""

    TEMPORALLY_AMBIGUOUS = "TEMPORALLY_AMBIGUOUS"
    """Contradictory evidence across the timeline (e.g. mutually incompatible persistent categories or erratic reappearance)."""

    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    """Series lacks usable observations (e.g. persistent cloud cover, missing geographic coverage)."""

    NO_SUPPORT = "NO_SUPPORT"
    """Zero observations in the series provide valid supporting evidence for the candidate."""


class TemporalConfidenceTier(str, Enum):
    """Stratified confidence in the temporal trajectory determination."""

    HIGH = "high"
    """Clear pre-change absence established, total supporting observations >= min_persistent, same-sensor calibration, complete evidence."""

    MEDIUM = "medium"
    """Supported across persistent observations, but pre-change absence has minor data limitations, or cross-sensor pairing is uncalibrated."""

    LOW = "low"
    """Single observation support only, wide temporal gaps (>90 days), or significant spectral limitations."""

    UNCERTAIN = "uncertain"
    """Flagged artifact risk, unresolved spatial correspondence, or conflicting category signals."""


class SpatialCorrespondenceStatus(str, Enum):
    """HOW geometry was compared between candidate and observation."""

    EXACT_PIXEL_GRID = "EXACT_PIXEL_GRID"
    """CRS, GSD, origin, and pixel alignment verified identical; pixel coordinates valid."""

    GEOREFERENCED_BBOX = "GEOREFERENCED_BBOX"
    """Heterogeneous grids; comparison reprojected to local metric CRS using WGS84 bboxes."""

    GEOREFERENCED_CENTROID_ONLY = "GEOREFERENCED_CENTROID_ONLY"
    """Bbox unavailable; comparison uses geodesic centroid distance in meters."""

    DISJOINT = "DISJOINT"
    """Spatial footprints do not overlap (distance > max_centroid_distance_m)."""

    INSUFFICIENT_METADATA = "INSUFFICIENT_METADATA"
    """Missing CRS, bounding box, or georeferencing metadata."""


class CorrespondenceRelationship(str, Enum):
    """WHAT spatial relationship exists between candidate and observed regions."""

    NONE = "NONE"
    """No spatial correspondence detected."""

    MATCHED = "MATCHED"
    """Unambiguous 1-to-1 spatial correspondence."""

    SPLIT = "SPLIT"
    """Single candidate region corresponds to >= 2 observed sub-regions in this epoch."""

    MERGED = "MERGED"
    """Candidate region has coalesced with adjacent development into a single larger region."""

    AMBIGUOUS = "AMBIGUOUS"
    """Multiple partial overlapping regions; topology cannot be established reliably."""


class TemporalIntervalType(str, Enum):
    """Topological type of the estimated change onset interval."""

    BOUNDED_HALF_OPEN = "BOUNDED_HALF_OPEN"
    """Pre-change absence confirmed at T_pre; earliest support confirmed at T_earliest. Physical onset lies in (T_pre, T_earliest]."""

    LEFT_UNBOUNDED = "LEFT_UNBOUNDED"
    """Earliest support confirmed at T_earliest, but no pre-change observation available. Physical onset lies in (-infinity, T_earliest]."""

    UNRESOLVED = "UNRESOLVED"
    """Earliest support not confirmed or series contains insufficient data to bound onset."""


class CandidateRegionRef(BaseModel):
    """Globally unique lineage reference identifying a candidate change region."""

    change_detection_result_id: str = Field(
        ..., min_length=5, description="M4B ChangeDetectionResult identifier where candidate was discovered"
    )
    scene_pair_id: str = Field(
        ..., min_length=5, description="M4A ScenePair identifier of discovery pair"
    )
    region_id: str = Field(
        ..., min_length=3, description="Locally unique region identifier within M4B result (e.g. reg_0001)"
    )

    @property
    def canonical_id(self) -> str:
        """Deterministic canonical string representation."""
        return f"{self.change_detection_result_id}:{self.region_id}"

    model_config = ConfigDict(extra="forbid")


class PairwiseTemporalEvidenceInput(BaseModel):
    """Complete upstream pipeline lineage bundle for a single evaluated scene pair."""

    scene_pair_id: str = Field(
        ..., min_length=5, description="Associated M4A ScenePair identifier"
    )
    change_detection_result_id: str = Field(
        ..., min_length=5, description="Associated M4B ChangeDetectionResult identifier"
    )
    evidence_id: str = Field(
        ..., min_length=5, description="Associated M4C-A ChangeEvidence identifier"
    )
    classification_id: Optional[str] = Field(
        default=None, description="Associated M4C-B ChangeClassificationResult identifier if classified"
    )
    suppression_id: str = Field(
        ..., min_length=5, description="Associated M4D SuppressionResult identifier"
    )
    # Direct model payloads (used when calling in-memory, or resolved from storage via IDs):
    suppression_result: Optional[SuppressionResult] = Field(
        default=None, description="Loaded M4D SuppressionResult"
    )
    change_detection_result: Optional[ChangeDetectionResult] = Field(
        default=None, description="Loaded M4B ChangeDetectionResult"
    )
    evidence: Optional[ChangeEvidence] = Field(
        default=None, description="Loaded M4C-A ChangeEvidence"
    )
    classification: Optional[ChangeClassificationResult] = Field(
        default=None, description="Loaded M4C-B ChangeClassificationResult"
    )

    model_config = ConfigDict(extra="forbid")


class SpatialCorrespondence(BaseModel):
    """Complete spatial alignment and topological correspondence bundle."""

    status: SpatialCorrespondenceStatus = Field(
        ..., description="Geometric comparison method applied"
    )
    relationship: CorrespondenceRelationship = Field(
        default=CorrespondenceRelationship.MATCHED,
        description="Topological relationship between candidate and observed regions",
    )
    is_spatially_compatible: bool = Field(
        ..., description="True if correspondence meets minimum spatial thresholds"
    )
    iou_wgs84: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Metric-projected 2D axis-aligned BOUNDING-BOX IoU from WGS84 source bboxes (NOT mask IoU)",
    )
    centroid_distance_m: Optional[float] = Field(
        default=None, ge=0.0, description="Geodesic distance between centroids in meters"
    )
    centroid_distance_px: Optional[float] = Field(
        default=None, ge=0.0,
        description="Pixel distance; present ONLY when CRS, GSD, and grid origin match identically",
    )
    crs_match: bool = Field(default=False, description="True if CRS strings are identical")
    gsd_match: bool = Field(default=False, description="True if ground sample distances match within 1%")

    model_config = ConfigDict(extra="forbid")


class TemporalEvidenceNode(BaseModel):
    """Detailed evaluation record of candidate change support at a single temporal observation."""

    observation_id: str = Field(..., description="M4A TemporalObservation identifier")
    acquisition_time: datetime = Field(..., description="Observation UTC acquisition timestamp")
    sensor: str = Field(..., description="Sensor instrument identifier")
    platform: str = Field(..., description="Satellite platform identifier")
    node_status: TemporalNodeStatus = Field(..., description="Assigned evaluation status at this epoch")
    m4d_decision: Optional[SuppressionDecision] = Field(
        default=None, description="M4D screening outcome (RETAINED, FLAGGED, SUPPRESSED, INSUFFICIENT_EVIDENCE)"
    )
    heuristic_support_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="M4E-derived, uncalibrated temporal evidence-strength index (non-probabilistic audit score)",
    )
    eligible_for_earliest_support: bool = Field(
        ...,
        description="Explicit deterministic downstream gate: True ONLY for RETAINED nodes with valid correspondence and support >= threshold",
    )
    spatial_correspondence: SpatialCorrespondence = Field(..., description="Spatial alignment metrics")
    category_observed: Optional[ChangeCategory] = Field(
        default=None, description="M4C-B category evaluated at this epoch if available"
    )
    category_confidence: Optional[ConfidenceTier] = Field(
        default=None, description="M4C-B confidence tier evaluated at this epoch"
    )
    evidence_score_m4c: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description="Raw uncalibrated M4C-B rule evidence score (distinct from M4E support score)",
    )
    is_cross_sensor: bool = Field(
        default=False, description="True if sensor differs from discovery pair later sensor"
    )
    decision_reasons: List[str] = Field(
        default_factory=list, description="Bulleted audit justifications for this node's status"
    )
    data_limitations: List[str] = Field(
        default_factory=list, description="Missing quality metadata, cloud obstruction, or uncalibrated sensor notes"
    )

    model_config = ConfigDict(extra="forbid")


class TemporalCategoryEvolution(BaseModel):
    """Semantic progression and consistency audit of change categories across the timeline."""

    earliest_observed_category: Optional[ChangeCategory] = Field(
        default=None, description="First category observed in the timeline"
    )
    latest_observed_category: Optional[ChangeCategory] = Field(
        default=None, description="Most recent category observed in the timeline"
    )
    primary_category: ChangeCategory = Field(
        ..., description="Dominant confirmed semantic category (preserves M4C-B determination)"
    )
    is_evolution_valid: bool = Field(
        default=True, description="True if category transition matches valid progression patterns"
    )
    is_conflicted: bool = Field(
        default=False, description="True if persistent incompatible categories co-occur"
    )
    evolution_trajectory: List[str] = Field(
        default_factory=list, description="Chronological sequence of transitions"
    )
    audit_notes: List[str] = Field(
        default_factory=list, description="Notes on classifier disagreements or transitions"
    )

    model_config = ConfigDict(extra="forbid")


class TemporalOnsetEstimate(BaseModel):
    """Bounded temporal interval during which candidate change first emerged."""

    pre_change_observation_id: Optional[str] = Field(
        default=None, description="Latest observation ID confirming absence before change"
    )
    pre_change_date: Optional[datetime] = Field(
        default=None, description="Timestamp of latest confirmed absence (T_pre)"
    )
    earliest_support_observation_id: Optional[str] = Field(
        default=None, description="Earliest observation ID confirming valid change support (T_earliest)"
    )
    earliest_support_date: Optional[datetime] = Field(
        default=None, description="Timestamp of earliest supporting observation (T_earliest)"
    )
    interval_days: Optional[float] = Field(
        default=None, ge=0.0, description="Sampling interval span in fractional days (T_earliest - T_pre)"
    )
    provisional_flagged_observation_id: Optional[str] = Field(
        default=None, description="Provisional earliest flagged observation ID if any preceded earliest support"
    )
    provisional_flagged_date: Optional[datetime] = Field(
        default=None, description="Timestamp of provisional flagged observation"
    )
    interval_type: TemporalIntervalType = Field(
        ..., description="Topological classification of the onset interval"
    )
    display_bounding_span: Optional[str] = Field(
        default=None, description="Formatted string representation of bounding observation epochs, e.g. '[T_pre, T_earliest]'"
    )
    physical_onset_interval: Optional[str] = Field(
        default=None, description="Formatted half-open physical interval, e.g. '(T_pre, T_earliest]'"
    )
    interval_limitation: Optional[str] = Field(
        default="Interval represents discrete satellite sampling bounds; exact physical date of occurrence is unobservable.",
        description="Formal epistemic limitation notice",
    )

    model_config = ConfigDict(extra="forbid")


class TemporalEvidenceConfig(BaseModel):
    """Deterministic hyperparameters for M4E temporal evidence evaluation."""

    evaluator_id: str = Field(default="astra_temporal_evidence_evaluator")
    evaluator_version: str = Field(default="1.0.0")
    min_persistent_observations: int = Field(
        default=2, ge=1,
        description="TOTAL supporting observations (including earliest) required for STRONG_TEMPORAL_SUPPORT",
    )
    min_support_score_threshold: float = Field(
        default=0.45, ge=0.0, le=1.0, description="Minimum M4E heuristic support score to assign support"
    )
    min_bbox_iou_threshold: float = Field(
        default=0.30, ge=0.0, le=1.0, description="Minimum metric-projected bbox IoU for spatial correspondence"
    )
    max_centroid_distance_m: float = Field(
        default=60.0, ge=0.0, description="Maximum centroid distance in meters for spatial correspondence"
    )
    max_pre_change_cloud_fraction: float = Field(
        default=0.10, ge=0.0, le=1.0, description="Maximum cloud fraction to establish pre-change absence"
    )
    min_pre_change_valid_pixel_ratio: float = Field(
        default=0.90, ge=0.0, le=1.0, description="Minimum valid pixel fraction to establish pre-change absence"
    )
    max_temporal_gap_days: float = Field(
        default=90.0, ge=1.0, description="Gap threshold in days triggering wide-interval warning"
    )

    model_config = ConfigDict(extra="forbid")

    def canonical_string(self) -> str:
        """Deterministic canonical representation for hashing."""
        return (
            f"eval={self.evaluator_id}:{self.evaluator_version}:"
            f"persist={self.min_persistent_observations}:"
            f"sup_thresh={self.min_support_score_threshold:.4f}:"
            f"iou_thresh={self.min_bbox_iou_threshold:.4f}:"
            f"dist_thresh={self.max_centroid_distance_m:.1f}:"
            f"cloud_thresh={self.max_pre_change_cloud_fraction:.4f}:"
            f"valid_thresh={self.min_pre_change_valid_pixel_ratio:.4f}:"
            f"gap_thresh={self.max_temporal_gap_days:.1f}"
        )


class TemporalEvidenceMetrics(BaseModel):
    """Quantitative summary of temporal timeline evaluation."""

    total_observations_in_series: int = Field(..., ge=0)
    evaluated_nodes_count: int = Field(..., ge=0)
    supporting_nodes_count: int = Field(
        ..., ge=0, description="Total nodes with EARLIEST_SUPPORTING or PERSISTENT_SUPPORT"
    )
    flagged_nodes_count: int = Field(..., ge=0)
    suppressed_nodes_count: int = Field(..., ge=0)
    absence_nodes_count: int = Field(..., ge=0)
    insufficient_data_nodes_count: int = Field(..., ge=0)
    simultaneous_nodes_count: int = Field(..., ge=0)
    cross_sensor_nodes_count: int = Field(..., ge=0)

    model_config = ConfigDict(extra="forbid")


class TemporalEvidenceResult(BaseModel):
    """Structured, reproducible M4E temporal evidence document conforming to ASTRA-DC-v0.1."""

    temporal_evidence_id: str = Field(
        ..., min_length=5, description="Deterministic document identifier: tem_{hash}"
    )
    candidate_ref: CandidateRegionRef = Field(
        ..., description="Unique lineage reference identifying candidate change region"
    )
    series_id: str = Field(..., description="Associated M4A TemporalSeries identifier")
    evaluator_id: str = Field(..., description="Evaluator algorithm identifier")
    evaluator_version: str = Field(..., description="Evaluator semantic version")
    config: TemporalEvidenceConfig = Field(..., description="Hyperparameters applied during evaluation")
    temporal_support_status: TemporalSupportStatus = Field(
        ..., description="Overall candidate temporal support determination"
    )
    confidence_tier: TemporalConfidenceTier = Field(
        ..., description="Overall confidence in temporal trajectory"
    )
    onset_estimate: TemporalOnsetEstimate = Field(
        ..., description="Bounded temporal onset interval [T_pre, T_earliest]"
    )
    category_evolution: TemporalCategoryEvolution = Field(
        ..., description="Category progression and conflict audit"
    )
    metrics: TemporalEvidenceMetrics = Field(
        ..., description="Summary counts across evaluated timeline nodes"
    )
    timeline_nodes: List[TemporalEvidenceNode] = Field(
        default_factory=list, description="Chronologically sorted audit trail of evaluated observation nodes"
    )
    decision_reasons: List[str] = Field(
        default_factory=list, description="Bulleted justifications for overall temporal determination"
    )
    evidence_limitations: List[str] = Field(
        default_factory=list, description="Explicit record of data gaps, uncalibrated sensors, or bounding caveats"
    )
    discovery_scene_pair_id: str = Field(
        ..., description="Associated M4A ScenePair identifier where candidate was discovered"
    )
    evaluated_scene_pair_ids: List[str] = Field(
        default_factory=list, description="List of all evaluated upstream scene pair IDs"
    )
    evaluated_change_detection_result_ids: List[str] = Field(
        default_factory=list, description="List of all evaluated upstream M4B change detection result IDs"
    )
    evaluated_evidence_ids: List[str] = Field(
        default_factory=list, description="List of all evaluated upstream M4C-A evidence IDs"
    )
    evaluated_classification_ids: List[str] = Field(
        default_factory=list, description="List of all evaluated upstream M4C-B classification IDs"
    )
    upstream_suppression_ids: List[str] = Field(
        default_factory=list, description="List of all evaluated upstream M4D suppression IDs"
    )
    upstream_hashes: Dict[str, str] = Field(
        default_factory=dict, description="Cryptographic SHA-256 hashes of all evaluated inputs"
    )
    provenance_id: str = Field(
        ..., description="Associated immutable provenance record identifier: prov_tem_{hash}"
    )
    created_at: datetime = Field(
        ..., description="Deterministic timestamp derived from latest observation acquisition time"
    )

    model_config = ConfigDict(extra="forbid")
