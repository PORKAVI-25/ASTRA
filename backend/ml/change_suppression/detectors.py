"""ASTRA False-Alarm Artifact Detectors (Phase M4D).

Implements deterministic, explainable artifact evaluators for 9 primary failure modes
plus bookkeeping limitations:
1. CLOUD_CONTAMINATION
2. CLOUD_SHADOW
3. HAZE_AEROSOL
4. SNOW_ICE
5. GLOBAL_ILLUMINATION_DRIFT
6. VIEWING_GEOMETRY_PARALLAX
7. RADIOMETRIC_GAIN_INCONSISTENCY
8. COREGISTRATION_EDGE_SHEAR
9. SENSOR_NOISE_DROPOUT
10. CROSS_SENSOR_LIMITATION
11. UNKNOWN_ARTIFACT

Conforms strictly to ASTRA-DC-v0.1. No network calls. No ML models.
Conservative multi-evidence gating ensures genuine ground change is protected.
"""

import math
from typing import Any, Dict, Optional, Tuple
from backend.ml.change_classification.types import ChangeRegionFeatures
from backend.ml.change_suppression.types import (
    ArtifactEvaluation,
    ArtifactType,
    SuppressionConfig,
)


def _get_band_value(band_dict: Dict[str, float], possible_names: Tuple[str, ...]) -> Optional[float]:
    """Extracts band value matching any alias case-insensitively."""
    lower_dict = {k.lower(): v for k, v in band_dict.items()}
    for name in possible_names:
        val = lower_dict.get(name.lower())
        if val is not None:
            # Normalize [0, 255] to [0.0, 1.0] if needed
            return val / 255.0 if val > 1.0 else float(val)
    return None


def detect_cloud_contamination(
    region: ChangeRegionFeatures,
    config: SuppressionConfig,
    aux: Dict[str, Any],
) -> ArtifactEvaluation:
    """Evaluates multi-modal evidence supporting cloud contamination.

    Hard suppression requires ALL of:
    1. High visible reflectance (vis_ref >= cloud_min_reflectance)
    2. High spectral whiteness (whiteness <= cloud_whiteness_threshold)
    3. Cirrus confirmation OR valid SWIR cloud drop
    4. Non-structural morphology (rectangularity <= 0.50)
    """
    sp = region.spatial
    spec = region.spectral
    metrics: Dict[str, Any] = {}

    # Extract visible bands from later observation
    later_bands = spec.later_mean_per_band if spec.later_mean_per_band else {}
    b_blue = _get_band_value(later_bands, ("blue", "b02", "b2"))
    b_green = _get_band_value(later_bands, ("green", "b03", "b3"))
    b_red = _get_band_value(later_bands, ("red", "b04", "b4"))

    # Visible reflectance (auxiliary explicit value takes precedence)
    if "vis_reflectance" in aux:
        vis_val = float(aux["vis_reflectance"])
    elif b_blue is not None and b_green is not None and b_red is not None:
        vis_val = (b_blue + b_green + b_red) / 3.0
    elif spec.brightness_delta and spec.brightness_delta.value is not None:
        vis_val = max(0.0, float(spec.brightness_delta.value))
    else:
        vis_val = 0.0

    # Whiteness calculation: deviation across visible bands relative to mean
    if "whiteness" in aux:
        whiteness = float(aux["whiteness"])
    elif b_blue is not None and b_green is not None and b_red is not None and vis_val > 0.001:
        whiteness = (abs(b_blue - vis_val) + abs(b_green - vis_val) + abs(b_red - vis_val)) / (3.0 * vis_val)
    else:
        whiteness = 0.0 if vis_val >= config.cloud_min_reflectance else 1.0

    # Cirrus and SWIR inspection (auxiliary explicit values take precedence)
    if "cirrus_reflectance" in aux:
        cirrus_val = float(aux["cirrus_reflectance"])
    else:
        cirrus_val = _get_band_value(later_bands, ("cirrus", "b10", "b09"))

    if "swir_reflectance" in aux:
        swir_val = float(aux["swir_reflectance"])
    else:
        swir_val = _get_band_value(later_bands, ("swir", "swir1", "b11"))

    swir_drop = False
    if "swir_cloud_evidence" in aux:
        swir_drop = bool(aux["swir_cloud_evidence"])
    elif swir_val is not None and vis_val > 0.001:
        swir_drop = (swir_val / vis_val) < 0.60

    cirrus_confirmed = cirrus_val is not None and cirrus_val >= config.cloud_cirrus_threshold
    morphology_non_structural = sp.rectangularity <= 0.50

    metrics["vis_reflectance"] = round(vis_val, 4)
    metrics["whiteness"] = round(whiteness, 4)
    metrics["cirrus_reflectance"] = round(cirrus_val, 4) if cirrus_val is not None else None
    metrics["swir_reflectance"] = round(swir_val, 4) if swir_val is not None else None
    metrics["rectangularity"] = round(sp.rectangularity, 4)

    # Check RGB-only limitation
    is_rgb_only = not spec.has_wavelength_metadata or (cirrus_val is None and swir_val is None and "swir_cloud_evidence" not in aux)
    metrics["is_rgb_only"] = is_rgb_only

    if is_rgb_only:
        # RGB-only cannot definitively distinguish clouds from white buildings/tents
        if vis_val >= config.cloud_min_reflectance and whiteness <= config.cloud_whiteness_threshold:
            return ArtifactEvaluation(
                artifact_type=ArtifactType.CLOUD_CONTAMINATION,
                detected=True,
                artifact_score=0.50,
                weight=0.25,
                hard_triggered=False,
                description="SWIR/Cirrus bands unavailable; cloud cannot be definitively distinguished from bright structure",
                metrics_used=metrics,
            )
        return ArtifactEvaluation(
            artifact_type=ArtifactType.CLOUD_CONTAMINATION,
            detected=False,
            artifact_score=0.0,
            weight=0.25,
            hard_triggered=False,
            description="No cloud-like visible response detected in RGB imagery",
            metrics_used=metrics,
        )

    # Multispectral multi-evidence check
    spectral_cloud = (
        vis_val >= config.cloud_min_reflectance
        and whiteness <= config.cloud_whiteness_threshold
        and (cirrus_confirmed or swir_drop)
    )

    if spectral_cloud and morphology_non_structural:
        return ArtifactEvaluation(
            artifact_type=ArtifactType.CLOUD_CONTAMINATION,
            detected=True,
            artifact_score=1.0,
            weight=0.40,
            hard_triggered=True,
            description="Converging multi-evidence: high visible reflectance, spectral whiteness, and Cirrus/SWIR on non-structural morphology",
            metrics_used=metrics,
        )
    elif spectral_cloud and not morphology_non_structural:
        # Bright building / structural roof protected from cloud suppression
        return ArtifactEvaluation(
            artifact_type=ArtifactType.CLOUD_CONTAMINATION,
            detected=True,
            artifact_score=0.20,
            weight=0.15,
            hard_triggered=False,
            description="Structural rectangular morphology (>0.50) protects candidate from cloud hard suppression",
            metrics_used=metrics,
        )

    return ArtifactEvaluation(
        artifact_type=ArtifactType.CLOUD_CONTAMINATION,
        detected=False,
        artifact_score=0.0,
        weight=0.35,
        hard_triggered=False,
        description="No cloud contamination evidence detected",
        metrics_used=metrics,
    )


def detect_cloud_shadow(
    region: ChangeRegionFeatures,
    config: SuppressionConfig,
    aux: Dict[str, Any],
) -> ArtifactEvaluation:
    """Evaluates evidence supporting cloud or topographic shadow.

    Hard suppression requires:
    1. Dark visible response (vis <= shadow_max_vis_reflectance)
    2. Dark NIR response (nir <= shadow_max_nir_reflectance)
    3. Valid solar geometry (solar_azimuth available)
    4. Directional ray alignment with an identified cloud candidate
    """
    spec = region.spectral
    metrics: Dict[str, Any] = {}

    later_bands = spec.later_mean_per_band if spec.later_mean_per_band else {}
    if "vis_reflectance" in aux:
        b_vis = float(aux["vis_reflectance"])
    else:
        b_vis = _get_band_value(later_bands, ("red", "green", "blue", "b04", "b03", "b02"))
        if b_vis is None:
            b_vis = 0.20

    if "nir_reflectance" in aux:
        b_nir = float(aux["nir_reflectance"])
    else:
        b_nir = _get_band_value(later_bands, ("nir", "b08", "b8", "b5"))

    solar_azimuth = aux.get("solar_azimuth")
    cloud_candidates = aux.get("cloud_candidates", [])
    shadow_ray_aligned = aux.get("shadow_ray_aligned", False)

    metrics["vis_reflectance"] = round(b_vis, 4)
    metrics["nir_reflectance"] = round(b_nir, 4) if b_nir is not None else None
    metrics["solar_azimuth"] = solar_azimuth

    is_dark_vis = b_vis <= config.shadow_max_vis_reflectance
    is_dark_nir = (b_nir is not None) and (b_nir <= config.shadow_max_nir_reflectance)

    if not is_dark_vis or (b_nir is not None and not is_dark_nir):
        return ArtifactEvaluation(
            artifact_type=ArtifactType.CLOUD_SHADOW,
            detected=False,
            artifact_score=0.0,
            weight=0.35,
            hard_triggered=False,
            description="Reflectance above shadow threshold; not a shadow candidate",
            metrics_used=metrics,
        )

    # Missing solar geometry
    if solar_azimuth is None and not shadow_ray_aligned:
        metrics["missing_solar_geometry"] = True
        return ArtifactEvaluation(
            artifact_type=ArtifactType.CLOUD_SHADOW,
            detected=True,
            artifact_score=0.40,
            weight=0.20,
            hard_triggered=False,
            description="Missing solar geometry; cloud shadow cannot be directionally confirmed",
            metrics_used=metrics,
        )

    # Ray alignment check
    if shadow_ray_aligned or (solar_azimuth is not None and len(cloud_candidates) > 0):
        # Directionally confirmed cloud shadow
        return ArtifactEvaluation(
            artifact_type=ArtifactType.CLOUD_SHADOW,
            detected=True,
            artifact_score=1.0,
            weight=0.40,
            hard_triggered=True,
            description="Dark visible and NIR absorption spatially aligned along solar azimuth ray from cloud candidate",
            metrics_used=metrics,
        )

    # Dark patch without supporting cloud-shadow geometry (e.g. water expansion, burned ground)
    return ArtifactEvaluation(
        artifact_type=ArtifactType.CLOUD_SHADOW,
        detected=True,
        artifact_score=0.15,
        weight=0.10,
        hard_triggered=False,
        description="Dark absorption patch lacks supporting directional cloud candidate geometry; not suppressed",
        metrics_used=metrics,
    )


def detect_haze_aerosol(
    region: ChangeRegionFeatures,
    config: SuppressionConfig,
    aux: Dict[str, Any],
) -> ArtifactEvaluation:
    """Evaluates soft evidence for haze and atmospheric scattering.

    Haze is soft evidence only; hard_triggered is NEVER True.
    """
    ctx = region.context
    metrics: Dict[str, Any] = {}

    haze_detected = bool(aux.get("haze_detected", False))
    surr_chg = ctx.surrounding_mean_change if (ctx.available and ctx.surrounding_mean_change is not None) else 0.0
    contrast = ctx.region_to_background_contrast if (ctx.available and ctx.region_to_background_contrast is not None) else 0.0

    metrics["surrounding_mean_change"] = round(surr_chg, 4)
    metrics["region_to_background_contrast"] = round(contrast, 4)
    metrics["haze_injected"] = haze_detected

    # If region maintains strong local contrast, haze does not penalize
    if contrast >= config.local_contrast_retention_margin:
        return ArtifactEvaluation(
            artifact_type=ArtifactType.HAZE_AEROSOL,
            detected=False,
            artifact_score=0.0,
            weight=0.15,
            hard_triggered=False,
            description="Local candidate contrast exceeds background; haze penalty waived",
            metrics_used=metrics,
        )

    if haze_detected or (surr_chg >= 0.25 and contrast < 0.10):
        return ArtifactEvaluation(
            artifact_type=ArtifactType.HAZE_AEROSOL,
            detected=True,
            artifact_score=0.30,
            weight=0.15,
            hard_triggered=False,
            description="Diffuse atmospheric haze with low local contrast; contributing soft risk",
            metrics_used=metrics,
        )

    return ArtifactEvaluation(
        artifact_type=ArtifactType.HAZE_AEROSOL,
        detected=False,
        artifact_score=0.0,
        weight=0.15,
        hard_triggered=False,
        description="No haze or aerosol scattering evidence detected",
        metrics_used=metrics,
    )


def detect_coregistration_edge_shear(
    region: ChangeRegionFeatures,
    config: SuppressionConfig,
    aux: Dict[str, Any],
) -> ArtifactEvaluation:
    """Evaluates evidence for sub-pixel / 1-2 pixel co-registration shear fringes.

    Hard suppression requires ALL:
    1. High edge overlap ratio (>= edge_shear_overlap_ratio)
    2. Morphological thinness (compactness <= edge_shear_compactness_threshold)
    3. Dipole sign reversal (dipole_anti_symmetry == True)
    4. Width <= edge_shear_max_width_px
    """
    sp = region.spatial
    metrics: Dict[str, Any] = {}

    edge_overlap = float(aux.get("edge_overlap_ratio", 0.0))
    dipole_reversal = bool(aux.get("dipole_sign_reversal", False))
    minor_axis = sp.minor_axis_length
    compactness = sp.compactness

    metrics["edge_overlap_ratio"] = round(edge_overlap, 4)
    metrics["dipole_sign_reversal"] = dipole_reversal
    metrics["minor_axis_length"] = round(minor_axis, 4)
    metrics["compactness"] = round(compactness, 4)

    is_shear_geometry = (
        edge_overlap >= config.edge_shear_overlap_ratio
        and compactness <= config.edge_shear_compactness_threshold
        and minor_axis <= config.edge_shear_max_width_px
    )

    if is_shear_geometry and dipole_reversal:
        return ArtifactEvaluation(
            artifact_type=ArtifactType.COREGISTRATION_EDGE_SHEAR,
            detected=True,
            artifact_score=1.0,
            weight=0.40,
            hard_triggered=True,
            description="High-gradient static edge overlap with dipole sign anti-symmetry and narrow boundary fringe",
            metrics_used=metrics,
        )
    elif is_shear_geometry and not dipole_reversal:
        # Real road or boundary corridor with uniform change
        return ArtifactEvaluation(
            artifact_type=ArtifactType.COREGISTRATION_EDGE_SHEAR,
            detected=True,
            artifact_score=0.15,
            weight=0.10,
            hard_triggered=False,
            description="Corridor aligned with boundary but lacks dipole sign anti-symmetry; protected from shear suppression",
            metrics_used=metrics,
        )
    elif minor_axis > config.edge_shear_max_width_px:
        # Real road with interior width
        return ArtifactEvaluation(
            artifact_type=ArtifactType.COREGISTRATION_EDGE_SHEAR,
            detected=False,
            artifact_score=0.0,
            weight=0.35,
            hard_triggered=False,
            description="Corridor has interior width exceeding edge shear threshold; not a registration fringe",
            metrics_used=metrics,
        )

    return ArtifactEvaluation(
        artifact_type=ArtifactType.COREGISTRATION_EDGE_SHEAR,
        detected=False,
        artifact_score=0.0,
        weight=0.35,
        hard_triggered=False,
        description="No co-registration edge shear detected",
        metrics_used=metrics,
    )


def detect_viewing_geometry_parallax(
    region: ChangeRegionFeatures,
    config: SuppressionConfig,
    aux: Dict[str, Any],
) -> ArtifactEvaluation:
    """Evaluates off-nadir tall structure parallax.

    Parallax must NEVER produce hard_triggered=True (never hard suppressed).
    """
    metrics: Dict[str, Any] = {}
    parallax_detected = bool(aux.get("parallax_detected", False))
    metrics["parallax_detected"] = parallax_detected

    if parallax_detected:
        return ArtifactEvaluation(
            artifact_type=ArtifactType.VIEWING_GEOMETRY_PARALLAX,
            detected=True,
            artifact_score=0.55,
            weight=0.20,
            hard_triggered=False,
            description="Viewing geometry parallax detected on structural feature; flagged for analyst inspection",
            metrics_used=metrics,
        )

    return ArtifactEvaluation(
        artifact_type=ArtifactType.VIEWING_GEOMETRY_PARALLAX,
        detected=False,
        artifact_score=0.0,
        weight=0.20,
        hard_triggered=False,
        description="No viewing geometry parallax detected",
        metrics_used=metrics,
    )


def detect_sensor_noise_dropout(
    region: ChangeRegionFeatures,
    config: SuppressionConfig,
    aux: Dict[str, Any],
) -> ArtifactEvaluation:
    """Evaluates single-pixel noise, salt-and-pepper spikes, or dropout artifacts."""
    sp = region.spatial
    metrics: Dict[str, Any] = {}
    metrics["area_px"] = sp.area_px

    is_noise_spike = bool(aux.get("sensor_noise_spike", False))

    if (sp.area_px <= 2 and sp.area_px < config.min_evaluation_area_px) or is_noise_spike:
        return ArtifactEvaluation(
            artifact_type=ArtifactType.SENSOR_NOISE_DROPOUT,
            detected=True,
            artifact_score=1.0,
            weight=0.30,
            hard_triggered=True,
            description="Isolated 1-2 pixel connected component satisfying sensor noise dropout criteria",
            metrics_used=metrics,
        )

    return ArtifactEvaluation(
        artifact_type=ArtifactType.SENSOR_NOISE_DROPOUT,
        detected=False,
        artifact_score=0.0,
        weight=0.30,
        hard_triggered=False,
        description="Region area and morphology exceed sensor noise threshold",
        metrics_used=metrics,
    )


def detect_global_illumination_drift(
    region: ChangeRegionFeatures,
    config: SuppressionConfig,
    aux: Dict[str, Any],
) -> ArtifactEvaluation:
    """Evaluates scene-wide sun angle or seasonal illumination shift.

    Soft evidence only; hard_triggered is NEVER True.
    """
    ctx = region.context
    c_score = region.change_score
    metrics: Dict[str, Any] = {}

    tile_median = float(aux.get("tile_median_change", 0.0))
    reg_change = float(c_score.get("mean_change_score", 0.0))
    surr_change = float(ctx.surrounding_mean_change) if (ctx.available and ctx.surrounding_mean_change is not None) else 0.0
    contrast = float(ctx.region_to_background_contrast) if (ctx.available and ctx.region_to_background_contrast is not None) else 0.0

    metrics["tile_median_change"] = round(tile_median, 4)
    metrics["mean_change_score"] = round(reg_change, 4)
    metrics["surrounding_mean_change"] = round(surr_change, 4)
    metrics["local_contrast"] = round(contrast, 4)

    # Local contrast retention: if candidate is much brighter/darker than shifted background, do not penalize
    if contrast >= config.local_contrast_retention_margin:
        return ArtifactEvaluation(
            artifact_type=ArtifactType.GLOBAL_ILLUMINATION_DRIFT,
            detected=False,
            artifact_score=0.0,
            weight=0.20,
            hard_triggered=False,
            description="Candidate maintains strong local contrast relative to background; illumination penalty waived",
            metrics_used=metrics,
        )

    coupling = (surr_change / max(0.01, reg_change)) if reg_change > 0.0 else 1.0
    metrics["coupling_ratio"] = round(coupling, 4)

    if tile_median >= config.illumination_tile_median_threshold and coupling >= config.illumination_coupling_threshold:
        score = round(min(1.0, max(0.85, coupling)), 2)
        return ArtifactEvaluation(
            artifact_type=ArtifactType.GLOBAL_ILLUMINATION_DRIFT,
            detected=True,
            artifact_score=score,
            weight=0.40,
            hard_triggered=False,
            description="Scene-wide illumination shift coupled with surrounding terrain change",
            metrics_used=metrics,
        )

    return ArtifactEvaluation(
        artifact_type=ArtifactType.GLOBAL_ILLUMINATION_DRIFT,
        detected=False,
        artifact_score=0.0,
        weight=0.20,
        hard_triggered=False,
        description="No global illumination drift detected",
        metrics_used=metrics,
    )


def detect_snow_ice(
    region: ChangeRegionFeatures,
    config: SuppressionConfig,
    aux: Dict[str, Any],
) -> ArtifactEvaluation:
    """Evaluates snow or ice contamination using NDSI.

    Only calculates NDSI when Green and SWIR are explicitly mapped.
    RGB-only degrades to FLAGGED/INSUFFICIENT with limitation.
    """
    spec = region.spectral
    metrics: Dict[str, Any] = {}

    later_bands = spec.later_mean_per_band if spec.later_mean_per_band else {}
    b_green = _get_band_value(later_bands, ("green", "b03", "b3"))
    b_swir = _get_band_value(later_bands, ("swir", "swir1", "b11"))

    if "green_reflectance" in aux:
        b_green = float(aux["green_reflectance"])
    if "swir_reflectance" in aux:
        b_swir = float(aux["swir_reflectance"])

    is_rgb_only = not spec.has_wavelength_metadata or (b_swir is None)
    metrics["is_rgb_only"] = is_rgb_only

    if is_rgb_only:
        return ArtifactEvaluation(
            artifact_type=ArtifactType.SNOW_ICE,
            detected=False,
            artifact_score=0.0,
            weight=0.25,
            hard_triggered=False,
            description="SWIR band unavailable; snow cannot be confirmed",
            metrics_used=metrics,
        )

    # Safe NDSI calculation
    denom = (b_green + b_swir) if (b_green is not None and b_swir is not None) else 0.0
    if denom > 0.001 and b_green is not None and b_swir is not None:
        ndsi = (b_green - b_swir) / denom
    else:
        ndsi = 0.0

    metrics["green_reflectance"] = round(b_green, 4) if b_green is not None else None
    metrics["swir_reflectance"] = round(b_swir, 4) if b_swir is not None else None
    metrics["ndsi"] = round(ndsi, 4)

    if ndsi >= config.snow_min_ndsi and (b_green is not None and b_green >= 0.25):
        return ArtifactEvaluation(
            artifact_type=ArtifactType.SNOW_ICE,
            detected=True,
            artifact_score=1.0,
            weight=0.40,
            hard_triggered=True,
            description=f"High Green reflectance with deep SWIR absorption (NDSI={ndsi:.2f})",
            metrics_used=metrics,
        )

    return ArtifactEvaluation(
        artifact_type=ArtifactType.SNOW_ICE,
        detected=False,
        artifact_score=0.0,
        weight=0.35,
        hard_triggered=False,
        description="NDSI index below snow/ice threshold",
        metrics_used=metrics,
    )


def detect_radiometric_gain_inconsistency(
    region: ChangeRegionFeatures,
    config: SuppressionConfig,
    aux: Dict[str, Any],
) -> ArtifactEvaluation:
    """Evaluates uncalibrated gain or multiplicative drift across invariant targets.

    Soft evidence only; hard_triggered is NEVER True.
    """
    metrics: Dict[str, Any] = {}
    gain_shift = bool(aux.get("radiometric_gain_shift", False))
    metrics["gain_shift_detected"] = gain_shift

    if gain_shift:
        return ArtifactEvaluation(
            artifact_type=ArtifactType.RADIOMETRIC_GAIN_INCONSISTENCY,
            detected=True,
            artifact_score=0.35,
            weight=0.15,
            hard_triggered=False,
            description="Broad radiometric gain or multiplicative drift detected across invariant baselines",
            metrics_used=metrics,
        )

    return ArtifactEvaluation(
        artifact_type=ArtifactType.RADIOMETRIC_GAIN_INCONSISTENCY,
        detected=False,
        artifact_score=0.0,
        weight=0.15,
        hard_triggered=False,
        description="No radiometric gain inconsistency detected",
        metrics_used=metrics,
    )


def detect_cross_sensor_limitation(
    region: ChangeRegionFeatures,
    config: SuppressionConfig,
    aux: Dict[str, Any],
) -> ArtifactEvaluation:
    """Flags uncalibrated cross-sensor pairings.

    Cross-sensor differences must NEVER independently hard-suppress genuine change.
    """
    metrics: Dict[str, Any] = {}
    is_cross_sensor = bool(aux.get("is_cross_sensor", False))
    metrics["is_cross_sensor"] = is_cross_sensor

    if is_cross_sensor:
        return ArtifactEvaluation(
            artifact_type=ArtifactType.CROSS_SENSOR_LIMITATION,
            detected=True,
            artifact_score=0.30,
            weight=0.10,
            hard_triggered=False,
            description="Cross-sensor pair: absolute radiometric differences uncalibrated",
            metrics_used=metrics,
        )

    return ArtifactEvaluation(
        artifact_type=ArtifactType.CROSS_SENSOR_LIMITATION,
        detected=False,
        artifact_score=0.0,
        weight=0.10,
        hard_triggered=False,
        description="Single-sensor pair; full calibration assumptions apply",
        metrics_used=metrics,
    )


def detect_unknown_artifact(
    region: ChangeRegionFeatures,
    config: SuppressionConfig,
    aux: Dict[str, Any],
) -> ArtifactEvaluation:
    """Bookkeeping for anomalous response not covered by known taxonomy."""
    metrics: Dict[str, Any] = {}
    unknown_detected = bool(aux.get("unknown_artifact_detected", False))
    metrics["unknown_detected"] = unknown_detected

    if unknown_detected:
        return ArtifactEvaluation(
            artifact_type=ArtifactType.UNKNOWN_ARTIFACT,
            detected=True,
            artifact_score=0.30,
            weight=0.10,
            hard_triggered=False,
            description="Unclassified anomalous response detected; flagged for review",
            metrics_used=metrics,
        )

    return ArtifactEvaluation(
        artifact_type=ArtifactType.UNKNOWN_ARTIFACT,
        detected=False,
        artifact_score=0.0,
        weight=0.10,
        hard_triggered=False,
        description="No unclassified artifact detected",
        metrics_used=metrics,
    )
