"""ASTRA Change Suppression Package (Phase M4D).

Provides deterministic, explainable false-alarm screening and quality assurance
for satellite change detection, filtering atmospheric, geometric, and radiometric artifacts.
Conforms to ASTRA-DC-v0.1.
"""

from backend.ml.change_suppression.decision import evaluate_region_suppression
from backend.ml.change_suppression.detectors import (
    detect_cloud_contamination,
    detect_cloud_shadow,
    detect_coregistration_edge_shear,
    detect_cross_sensor_limitation,
    detect_global_illumination_drift,
    detect_haze_aerosol,
    detect_radiometric_gain_inconsistency,
    detect_sensor_noise_dropout,
    detect_snow_ice,
    detect_unknown_artifact,
    detect_viewing_geometry_parallax,
)
from backend.ml.change_suppression.mask import generate_filtered_change_mask
from backend.ml.change_suppression.service import ChangeSuppressionService
from backend.ml.change_suppression.types import (
    ArtifactEvaluation,
    ArtifactType,
    RegionSuppression,
    SuppressionConfig,
    SuppressionDecision,
    SuppressionMetrics,
    SuppressionResult,
)

__all__ = [
    "SuppressionDecision",
    "ArtifactType",
    "ArtifactEvaluation",
    "RegionSuppression",
    "SuppressionMetrics",
    "SuppressionConfig",
    "SuppressionResult",
    "evaluate_region_suppression",
    "generate_filtered_change_mask",
    "ChangeSuppressionService",
    "detect_cloud_contamination",
    "detect_cloud_shadow",
    "detect_haze_aerosol",
    "detect_coregistration_edge_shear",
    "detect_viewing_geometry_parallax",
    "detect_sensor_noise_dropout",
    "detect_global_illumination_drift",
    "detect_snow_ice",
    "detect_radiometric_gain_inconsistency",
    "detect_cross_sensor_limitation",
    "detect_unknown_artifact",
]
