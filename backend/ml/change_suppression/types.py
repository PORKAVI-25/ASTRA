"""ASTRA False-Alarm Suppression Data Contracts (Phase M4D).

Defines immutable Pydantic models for artifact evaluations, region suppression decisions,
suppression configuration, aggregated metrics, and comprehensive suppression results.
Conforms to ASTRA-DC-v0.1.
All risk scores are explicitly uncalibrated deterministic heuristic indices (non-probabilistic).
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SuppressionDecision(str, Enum):
    """Audited outcome of false-alarm screening.

    RETAINED does NOT mean verified ground truth; it means no sufficient false-alarm
    evidence was detected and the candidate continues downstream.
    """

    RETAINED = "retained"
    FLAGGED = "flagged"
    SUPPRESSED = "suppressed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class ArtifactType(str, Enum):
    """Taxonomy of false-alarm phenomena and limitations."""

    CLOUD_CONTAMINATION = "cloud_contamination"
    CLOUD_SHADOW = "cloud_shadow"
    HAZE_AEROSOL = "haze_aerosol"
    SNOW_ICE = "snow_ice"
    GLOBAL_ILLUMINATION_DRIFT = "global_illumination_drift"
    VIEWING_GEOMETRY_PARALLAX = "viewing_geometry_parallax"
    RADIOMETRIC_GAIN_INCONSISTENCY = "radiometric_gain_inconsistency"
    COREGISTRATION_EDGE_SHEAR = "coregistration_edge_shear"
    SENSOR_NOISE_DROPOUT = "sensor_noise_dropout"
    CROSS_SENSOR_LIMITATION = "cross_sensor_limitation"
    UNKNOWN_ARTIFACT = "unknown_artifact"


class ArtifactEvaluation(BaseModel):
    """Quantitative evaluation for an individual artifact detector."""

    artifact_type: ArtifactType = Field(..., description="Target artifact phenomenon")
    detected: bool = Field(..., description="Whether artifact condition was identified")
    artifact_score: float = Field(
        ..., ge=0.0, le=1.0, description="Heuristic strength index (0.0=none, 1.0=maximum, non-probabilistic)"
    )
    weight: float = Field(
        ..., ge=0.0, le=1.0, description="Configured weight in composite risk accumulation"
    )
    hard_triggered: bool = Field(
        default=False, description="Whether this detector triggered conservative multi-evidence suppression"
    )
    description: str = Field(..., description="Explainable description of detector findings")
    metrics_used: Dict[str, Any] = Field(
        default_factory=dict, description="Raw numerical features and thresholds inspected"
    )


class RegionSuppression(BaseModel):
    """Complete suppression decision bundle for a single M4B/M4C ChangeRegion."""

    region_id: str = Field(
        ..., min_length=3, description="Deterministic identifier matching M4B ChangeRegion and M4C ChangeRegionFeatures"
    )
    decision: SuppressionDecision = Field(..., description="Assigned suppression status")
    artifact_risk_score: float = Field(
        ..., ge=0.0, le=1.0, description="Uncalibrated deterministic heuristic risk index (non-probabilistic)"
    )
    artifact_risk_interpretation: str = Field(
        ..., description="Human-readable summary of risk level"
    )
    decision_basis: str = Field(
        ..., description="Categorical basis: 'CONSERVATIVE_MULTI_EVIDENCE', 'COMPOSITE_RISK_THRESHOLD', or 'DATA_LIMITATION'"
    )
    decision_reasons: List[str] = Field(
        default_factory=list, description="Explicit bulleted justifications for this decision"
    )
    primary_attribution: Optional[ArtifactType] = Field(
        default=None, description="Dominant contributing artifact if flagged or suppressed"
    )
    contributing_artifacts: List[ArtifactType] = Field(
        default_factory=list, description="All artifact detectors that contributed positive risk"
    )
    artifact_evaluations: List[ArtifactEvaluation] = Field(
        default_factory=list, description="Full audit trail across all evaluated artifact detectors"
    )
    original_category: str = Field(
        ..., description="M4C-B category prior to suppression (e.g. construction, road_development)"
    )
    retained_category: str = Field(
        ..., description="Effective category after suppression (original if retained, 'suppressed' if suppressed)"
    )
    confidence_tier_adjusted: str = Field(
        ..., description="Downstream confidence tier reflecting artifact uncertainty"
    )
    hard_triggered: bool = Field(
        default=False, description="True only if multi-evidence conservative gating triggered"
    )
    data_limitations: List[str] = Field(
        default_factory=list, description="Explicit record of missing bands, sensor metadata, or uncalibrated inputs"
    )


class SuppressionMetrics(BaseModel):
    """Scene-wide aggregate metrics for false-alarm screening."""

    total_input_regions: int = Field(..., ge=0, description="Total candidate regions evaluated")
    retained_count: int = Field(..., ge=0, description="Count of regions continuing downstream")
    flagged_count: int = Field(..., ge=0, description="Count of regions routed to analyst review")
    suppressed_count: int = Field(..., ge=0, description="Count of regions screened out as artifacts")
    insufficient_evidence_count: int = Field(..., ge=0, description="Count of regions with data limitations")
    suppression_rate: float = Field(
        ..., ge=0.0, le=1.0, description="Ratio of suppressed regions to total input regions"
    )
    total_area_px: int = Field(..., ge=0, description="Total pixel area of input regions")
    retained_area_px: int = Field(..., ge=0, description="Total pixel area of retained regions")
    flagged_area_px: int = Field(..., ge=0, description="Total pixel area of flagged regions")
    suppressed_area_px: int = Field(..., ge=0, description="Total pixel area of suppressed regions")
    artifact_counts: Dict[str, int] = Field(
        default_factory=dict, description="Counts per primary attribution artifact type"
    )


class SuppressionConfig(BaseModel):
    """Configurable hyperparameters for deterministic false-alarm screening."""

    suppressor_id: str = Field(default="astra_deterministic_suppressor")
    suppressor_version: str = Field(default="1.0.0")
    min_evaluation_area_px: int = Field(default=10, ge=1, description="Minimum region pixel area to evaluate")
    suppression_threshold: float = Field(
        default=0.70, ge=0.0, le=1.0, description="Composite risk threshold for flagging high-risk candidates"
    )
    flag_threshold: float = Field(
        default=0.35, ge=0.0, le=1.0, description="Composite risk threshold for flagging moderate-risk candidates"
    )

    # Co-registration parameters
    edge_shear_gradient_threshold: float = Field(
        default=0.15, ge=0.0, description="Threshold for static high-gradient edge detection"
    )
    edge_shear_overlap_ratio: float = Field(
        default=0.70, ge=0.0, le=1.0, description="Minimum ratio of region overlapping high-gradient static edges"
    )
    edge_shear_max_width_px: float = Field(
        default=2.0, ge=0.5, description="Maximum minor axis width in pixels to qualify as edge shear"
    )
    edge_shear_compactness_threshold: float = Field(
        default=0.08, ge=0.0, le=1.0, description="Maximum compactness for boundary fringe morphology"
    )

    # Atmospheric parameters
    cloud_whiteness_threshold: float = Field(
        default=0.15, ge=0.0, description="Maximum visible band deviation for cloud whiteness"
    )
    cloud_min_reflectance: float = Field(
        default=0.35, ge=0.0, le=1.0, description="Minimum visible reflectance for cloud candidate"
    )
    cloud_cirrus_threshold: float = Field(
        default=0.015, ge=0.0, description="Minimum Cirrus band reflectance for cloud confirmation"
    )
    snow_min_ndsi: float = Field(
        default=0.40, ge=-1.0, le=1.0, description="Minimum NDSI index for snow/ice confirmation"
    )
    shadow_max_vis_reflectance: float = Field(
        default=0.10, ge=0.0, le=1.0, description="Maximum visible reflectance for cloud shadow candidate"
    )
    shadow_max_nir_reflectance: float = Field(
        default=0.12, ge=0.0, le=1.0, description="Maximum NIR reflectance for cloud shadow candidate"
    )
    shadow_ray_max_distance_px: int = Field(
        default=60, ge=5, description="Maximum pixel search distance along solar azimuth ray"
    )

    # Radiometric & Illumination parameters
    illumination_coupling_threshold: float = Field(
        default=0.75, ge=0.0, le=1.0, description="Coupling ratio between region and background change"
    )
    illumination_tile_median_threshold: float = Field(
        default=0.20, ge=0.0, le=1.0, description="Tile-wide median change required for illumination drift"
    )
    local_contrast_retention_margin: float = Field(
        default=0.15, ge=0.0, description="Local contrast margin protecting genuine change from soft penalty"
    )


class SuppressionResult(BaseModel):
    """Structured, reproducible false-alarm suppression document conforming to ASTRA-DC-v0.1."""

    suppression_id: str = Field(
        ..., min_length=5, description="Deterministic document identifier (e.g. sup_{hash})"
    )
    scene_pair_id: str = Field(..., min_length=5, description="Associated M4A ScenePair identifier")
    change_detection_result_id: str = Field(
        ..., min_length=5, description="Associated M4B ChangeDetectionResult identifier"
    )
    evidence_id: str = Field(..., min_length=5, description="Associated M4C-A ChangeEvidence identifier")
    classification_id: Optional[str] = Field(
        default=None, description="Associated M4C-B ChangeClassificationResult identifier if available"
    )
    suppressor_id: str = Field(..., description="Suppressor algorithm identifier")
    suppressor_version: str = Field(..., description="Suppressor semantic version")
    config: SuppressionConfig = Field(..., description="Hyperparameters applied during screening")
    metrics: SuppressionMetrics = Field(..., description="Quantitative metrics summary")
    regions: List[RegionSuppression] = Field(
        default_factory=list, description="Per-region suppression decisions and audit trails"
    )
    filtered_change_mask_path: Optional[str] = Field(
        default=None, description="Path to raster mask: 0=background/suppressed, 1=retained, 2=flagged"
    )
    provenance_id: str = Field(..., description="Associated immutable provenance record: prov_sup_{hash}")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="UTC execution timestamp"
    )
