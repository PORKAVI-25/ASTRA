"""ASTRA False-Alarm Decision Engine (Phase M4D).

Implements conservative four-step decision logic:
1. Eligibility & Data Completeness Check
2. Conservative Multi-Evidence Hard Gates (Only hard gates can produce SUPPRESSED)
3. Non-Suppressing Artifact Gating (Parallax, RGB-only degradation, Cross-sensor)
4. Composite Heuristic Risk Accumulation (F alone NEVER hard suppresses)

Conforms to ASTRA-DC-v0.1. RETAINED != verified ground truth. F != probability.
"""

from typing import Any, Dict, List, Optional
from backend.ml.change_classification.types import ChangeRegionFeatures
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
from backend.ml.change_suppression.types import (
    ArtifactEvaluation,
    ArtifactType,
    RegionSuppression,
    SuppressionConfig,
    SuppressionDecision,
)


def _adjust_confidence_tier(tier: str, decision: SuppressionDecision) -> str:
    """Adjusts downstream confidence tier accounting for artifact risk."""
    t = tier.lower()
    if decision == SuppressionDecision.SUPPRESSED:
        return "suppressed"
    if decision in (SuppressionDecision.FLAGGED, SuppressionDecision.INSUFFICIENT_EVIDENCE):
        if t == "high":
            return "medium"
        elif t == "medium":
            return "low"
        elif t == "low":
            return "low"
        return "uncertain"
    return t


def evaluate_region_suppression(
    region: ChangeRegionFeatures,
    original_category: str = "unknown",
    original_confidence_tier: str = "uncertain",
    config: Optional[SuppressionConfig] = None,
    aux: Optional[Dict[str, Any]] = None,
) -> RegionSuppression:
    """Executes the four-step conservative decision engine on a single change region."""
    cfg = config or SuppressionConfig()
    aux_data = aux or {}
    data_limitations: List[str] = []
    decision_reasons: List[str] = []

    reg_id = region.region_id
    sp = region.spatial
    spec = region.spectral

    # --------------------------------------------------------------------------
    # STEP 1: Eligibility & Basic Modality Checks
    # --------------------------------------------------------------------------
    is_sensor_noise = sp.area_px <= 2 and bool(aux_data.get("sensor_noise_spike", False))

    if sp.area_px < cfg.min_evaluation_area_px and not is_sensor_noise:
        lim = f"Region size ({sp.area_px} px) below minimum evaluation threshold ({cfg.min_evaluation_area_px} px)"
        data_limitations.append(lim)
        return RegionSuppression(
            region_id=reg_id,
            decision=SuppressionDecision.INSUFFICIENT_EVIDENCE,
            artifact_risk_score=0.0,
            artifact_risk_interpretation="INSUFFICIENT: Region size below minimum evaluation threshold",
            decision_basis="DATA_LIMITATION",
            decision_reasons=[lim],
            primary_attribution=None,
            contributing_artifacts=[],
            artifact_evaluations=[],
            original_category=original_category,
            retained_category=original_category,
            confidence_tier_adjusted=_adjust_confidence_tier(original_confidence_tier, SuppressionDecision.INSUFFICIENT_EVIDENCE),
            hard_triggered=False,
            data_limitations=data_limitations,
        )

    if not spec.available:
        lim = "Required spectral imagery modality is unavailable for artifact screening"
        data_limitations.append(lim)
        return RegionSuppression(
            region_id=reg_id,
            decision=SuppressionDecision.INSUFFICIENT_EVIDENCE,
            artifact_risk_score=0.0,
            artifact_risk_interpretation="INSUFFICIENT: Required spectral imagery is unavailable",
            decision_basis="DATA_LIMITATION",
            decision_reasons=[lim],
            primary_attribution=None,
            contributing_artifacts=[],
            artifact_evaluations=[],
            original_category=original_category,
            retained_category=original_category,
            confidence_tier_adjusted=_adjust_confidence_tier(original_confidence_tier, SuppressionDecision.INSUFFICIENT_EVIDENCE),
            hard_triggered=False,
            data_limitations=data_limitations,
        )

    # --------------------------------------------------------------------------
    # STEP 2: Multi-Evidence Detectors Execution
    # --------------------------------------------------------------------------
    eval_cloud = detect_cloud_contamination(region, cfg, aux_data)
    eval_shadow = detect_cloud_shadow(region, cfg, aux_data)
    eval_haze = detect_haze_aerosol(region, cfg, aux_data)
    eval_shear = detect_coregistration_edge_shear(region, cfg, aux_data)
    eval_parallax = detect_viewing_geometry_parallax(region, cfg, aux_data)
    eval_noise = detect_sensor_noise_dropout(region, cfg, aux_data)
    eval_illum = detect_global_illumination_drift(region, cfg, aux_data)
    eval_snow = detect_snow_ice(region, cfg, aux_data)
    eval_gain = detect_radiometric_gain_inconsistency(region, cfg, aux_data)
    eval_cross = detect_cross_sensor_limitation(region, cfg, aux_data)
    eval_unknown = detect_unknown_artifact(region, cfg, aux_data)

    all_evals: List[ArtifactEvaluation] = [
        eval_cloud,
        eval_shadow,
        eval_haze,
        eval_shear,
        eval_parallax,
        eval_noise,
        eval_illum,
        eval_snow,
        eval_gain,
        eval_cross,
        eval_unknown,
    ]

    # Track contributing artifacts and data limitations
    contributing: List[ArtifactType] = []
    for ev in all_evals:
        if ev.detected and ev.artifact_score > 0.0:
            contributing.append(ev.artifact_type)

    if eval_cloud.metrics_used.get("is_rgb_only"):
        data_limitations.append("SWIR/Cirrus bands unavailable; cloud cannot be definitively distinguished from bright structure")
    if eval_shadow.metrics_used.get("missing_solar_geometry"):
        data_limitations.append("Solar geometry missing; cloud shadow cannot be directionally confirmed")
    if eval_snow.metrics_used.get("is_rgb_only"):
        data_limitations.append("SWIR band unavailable; snow cannot be confirmed")
    if eval_cross.detected:
        data_limitations.append("Cross-sensor pair: absolute radiometric differences uncalibrated")

    # --------------------------------------------------------------------------
    # STEP 2b: Conservative Multi-Evidence Hard Gates
    # (ONLY qualifying hard gates can produce SUPPRESSED)
    # --------------------------------------------------------------------------
    hard_triggers = [ev for ev in all_evals if ev.hard_triggered]

    if len(hard_triggers) > 0:
        primary_ev = hard_triggers[0]
        reasons = [f"Conservative hard gate triggered by {ev.artifact_type.value}: {ev.description}" for ev in hard_triggers]
        return RegionSuppression(
            region_id=reg_id,
            decision=SuppressionDecision.SUPPRESSED,
            artifact_risk_score=1.0,
            artifact_risk_interpretation=f"SUPPRESSED: Conservative multi-evidence confirmed {primary_ev.artifact_type.value}",
            decision_basis="CONSERVATIVE_MULTI_EVIDENCE",
            decision_reasons=reasons,
            primary_attribution=primary_ev.artifact_type,
            contributing_artifacts=contributing,
            artifact_evaluations=all_evals,
            original_category=original_category,
            retained_category="suppressed",
            confidence_tier_adjusted="suppressed",
            hard_triggered=True,
            data_limitations=data_limitations,
        )

    # --------------------------------------------------------------------------
    # STEP 3: Composite Heuristic Risk Accumulation
    # F = min(1.0, sum(weight_k * score_k))
    # --------------------------------------------------------------------------
    raw_f = sum(ev.weight * ev.artifact_score for ev in all_evals)
    f_score = round(min(1.0, max(0.0, raw_f)), 4)

    # Determine primary attribution by weighted score
    sorted_contrib = sorted(
        [ev for ev in all_evals if ev.detected and ev.artifact_score > 0.0],
        key=lambda ev: ev.weight * ev.artifact_score,
        reverse=True,
    )
    primary_attr = sorted_contrib[0].artifact_type if len(sorted_contrib) > 0 else None

    # Check non-suppressing triggers requiring at least FLAGGED
    force_flag = False
    force_flag_reasons: List[str] = []

    if eval_parallax.detected:
        force_flag = True
        force_flag_reasons.append("Viewing geometry parallax detected on structural feature (never hard suppressed)")
    if eval_cloud.detected and eval_cloud.metrics_used.get("is_rgb_only") and eval_cloud.artifact_score >= 0.40:
        force_flag = True
        force_flag_reasons.append("RGB-only visible whiteness anomaly flagged due to missing Cirrus/SWIR confirmation")
    if eval_shadow.detected and eval_shadow.metrics_used.get("missing_solar_geometry") and eval_shadow.artifact_score >= 0.35:
        force_flag = True
        force_flag_reasons.append("Dark absorption patch flagged due to missing solar geometry for directional validation")

    # --------------------------------------------------------------------------
    # STEP 4: Decision Assignment (CRITICAL: F ALONE NEVER SUPPRESSES)
    # --------------------------------------------------------------------------
    if force_flag:
        decision = SuppressionDecision.FLAGGED
        decision_basis = "DATA_LIMITATION_OR_PARALLAX_FLAG"
        interpretation = f"FLAGGED: Candidate flagged for analyst review due to {primary_attr.value if primary_attr else 'artifact uncertainty'}"
        reasons = force_flag_reasons + [f"Artifact evidence: {ev.description}" for ev in sorted_contrib]
    elif f_score < cfg.flag_threshold:
        decision = SuppressionDecision.RETAINED
        decision_basis = "LOW_ARTIFACT_RISK"
        interpretation = "LOW: No sufficient false-alarm evidence detected; candidate continues downstream"
        reasons = ["Artifact risk score below flag threshold; candidate retained for downstream analysis"]
    elif cfg.flag_threshold <= f_score < cfg.suppression_threshold:
        decision = SuppressionDecision.FLAGGED
        decision_basis = "MODERATE_ARTIFACT_RISK"
        interpretation = f"MODERATE: Ambiguous or sub-threshold artifact evidence ({primary_attr.value if primary_attr else 'general'})"
        reasons = [f"Moderate artifact risk index ({f_score:.2f}) indicates potential {ev.artifact_type.value}" for ev in sorted_contrib]
    else:
        # F >= suppression_threshold BUT NO HARD GATE SATISFIED!
        # Mandatory rule: Composite risk score alone MUST NEVER cause hard suppression!
        decision = SuppressionDecision.FLAGGED
        decision_basis = "HIGH_ARTIFACT_RISK_UNCONFIRMED"
        interpretation = "HIGH: Significant artifact evidence present, but conservative multi-evidence hard gate was not satisfied; flagged for analyst triage"
        reasons = [
            f"High composite risk index ({f_score:.2f}) without hard gate confirmation; candidate flagged rather than suppressed",
        ] + [f"Contributing evidence: {ev.description}" for ev in sorted_contrib]

    tier_adj = _adjust_confidence_tier(original_confidence_tier, decision)

    return RegionSuppression(
        region_id=reg_id,
        decision=decision,
        artifact_risk_score=f_score,
        artifact_risk_interpretation=interpretation,
        decision_basis=decision_basis,
        decision_reasons=reasons,
        primary_attribution=primary_attr,
        contributing_artifacts=contributing,
        artifact_evaluations=all_evals,
        original_category=original_category,
        retained_category=original_category if decision != SuppressionDecision.SUPPRESSED else "suppressed",
        confidence_tier_adjusted=tier_adj,
        hard_triggered=False,
        data_limitations=data_limitations,
    )
