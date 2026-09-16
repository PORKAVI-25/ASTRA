"""ASTRA Change-Type Classifier (Phase M4C-B).

Implements a deterministic, explainable rule-based classification layer
that consumes M4C-A ChangeEvidence and produces audited semantic change categories:
construction, clearance, water_extent_change, road_development, and unknown.
Conforms to ASTRA-DC-v0.1.
"""

from datetime import datetime, timezone
import hashlib
from typing import Any, Dict, List, Optional, Tuple

from backend.ml.change_classification.types import (
    CategoryCandidateScore,
    ChangeCategory,
    ChangeClassificationMetrics,
    ChangeClassificationResult,
    ChangeEvidence,
    ChangeRegionFeatures,
    ClassifierConfig,
    ConfidenceTier,
    RegionClassification,
    RuleEvaluation,
)


class DeterministicChangeClassifier:
    """Deterministic, explainable rule-based classifier for satellite change regions."""

    def __init__(self, config: Optional[ClassifierConfig] = None):
        self.config = config or ClassifierConfig()

    def _evaluate_construction(
        self,
        region: ChangeRegionFeatures,
        config: ClassifierConfig,
    ) -> Tuple[float, List[RuleEvaluation], str]:
        """Evaluates evidence supporting the 'construction' category."""
        evals: List[RuleEvaluation] = []
        pos_score = 0.0
        max_possible = 100.0
        neg_penalty = 0.0

        sp = region.spatial
        spec = region.spectral
        ctx = region.context

        # 1. Geometry: Rectangularity (weight: 30)
        rect_matched = sp.rectangularity >= config.construction_min_rectangularity
        w_rect = 30.0
        contrib = w_rect if rect_matched else 0.0
        pos_score += contrib
        evals.append(
            RuleEvaluation(
                rule_id="rule_const_geom_rectangularity",
                category=ChangeCategory.CONSTRUCTION,
                matched=rect_matched,
                weight=w_rect,
                score_contribution=contrib,
                description=f"Rectangularity >= {config.construction_min_rectangularity} (structural bounds)",
                evidence_used={"rectangularity": sp.rectangularity},
            )
        )

        # 2. Geometry: Compactness (weight: 15)
        compact_matched = sp.compactness >= 0.20
        w_comp = 15.0
        contrib = w_comp if compact_matched else 0.0
        pos_score += contrib
        evals.append(
            RuleEvaluation(
                rule_id="rule_const_geom_compactness",
                category=ChangeCategory.CONSTRUCTION,
                matched=compact_matched,
                weight=w_comp,
                score_contribution=contrib,
                description="Compactness >= 0.20 (solid contiguous surface footprint)",
                evidence_used={"compactness": sp.compactness},
            )
        )

        # 3. Geometry: Non-linear corridor check (weight: 15)
        non_linear_matched = sp.linearity_score <= 0.65 and sp.aspect_ratio <= 4.0
        w_nlin = 15.0
        contrib = w_nlin if non_linear_matched else 0.0
        pos_score += contrib
        evals.append(
            RuleEvaluation(
                rule_id="rule_const_geom_non_linear",
                category=ChangeCategory.CONSTRUCTION,
                matched=non_linear_matched,
                weight=w_nlin,
                score_contribution=contrib,
                description="Linearity <= 0.65 and Aspect Ratio <= 4.0 (distinguishes building footprint from road)",
                evidence_used={"linearity_score": sp.linearity_score, "aspect_ratio": sp.aspect_ratio},
            )
        )

        # 4. Spectral: Brightness increase (weight: 25)
        b_val = spec.brightness_delta.value if (spec.brightness_delta and spec.brightness_delta.value is not None) else 0.0
        bright_matched = b_val > 0.05
        w_brt = 25.0
        contrib = w_brt if bright_matched else 0.0
        pos_score += contrib
        evals.append(
            RuleEvaluation(
                rule_id="rule_const_spec_brightness_increase",
                category=ChangeCategory.CONSTRUCTION,
                matched=bright_matched,
                weight=w_brt,
                score_contribution=contrib,
                description="Brightness delta > 0.05 (reflectance increase typical of new concrete, metal, or roof)",
                evidence_used={"brightness_delta": b_val},
            )
        )

        # 5. Context: Contrast with background (weight: 15)
        c_val = ctx.region_to_background_contrast if (ctx.available and ctx.region_to_background_contrast is not None) else 0.0
        contrast_matched = c_val >= 0.15
        w_cnt = 15.0
        contrib = w_cnt if contrast_matched else 0.0
        pos_score += contrib
        evals.append(
            RuleEvaluation(
                rule_id="rule_const_ctx_contrast",
                category=ChangeCategory.CONSTRUCTION,
                matched=contrast_matched,
                weight=w_cnt,
                score_contribution=contrib,
                description="Region-to-background contrast >= 0.15 (stands out from surroundings)",
                evidence_used={"region_to_background_contrast": c_val},
            )
        )

        # Disqualifier 1: High water response
        water_val = (
            spec.water_spectral_criterion_fraction.value
            if (spec.water_spectral_criterion_fraction and spec.water_spectral_criterion_fraction.value is not None)
            else 0.0
        )
        if water_val > 0.30:
            neg_penalty += 50.0
            evals.append(
                RuleEvaluation(
                    rule_id="disqual_const_water_presence",
                    category=ChangeCategory.CONSTRUCTION,
                    matched=True,
                    weight=50.0,
                    score_contribution=-50.0,
                    description="Water spectral fraction > 0.30 disqualifies construction",
                    evidence_used={"water_spectral_criterion_fraction": water_val},
                )
            )

        # Disqualifier 2: Severe corridor elongation
        if sp.linearity_score > 0.85 and sp.aspect_ratio > 6.0:
            neg_penalty += 40.0
            evals.append(
                RuleEvaluation(
                    rule_id="disqual_const_extreme_elongation",
                    category=ChangeCategory.CONSTRUCTION,
                    matched=True,
                    weight=40.0,
                    score_contribution=-40.0,
                    description="Extreme linearity (>0.85) and elongation (>6.0) indicates transportation corridor, not building",
                    evidence_used={"linearity_score": sp.linearity_score, "aspect_ratio": sp.aspect_ratio},
                )
            )

        # Disqualifier 3: Absence of positive brightness increase (darkening or neutral reflectance)
        if b_val is None or b_val <= 0.0:
            neg_penalty += 35.0
            evals.append(
                RuleEvaluation(
                    rule_id="disqual_const_no_brightness_increase",
                    category=ChangeCategory.CONSTRUCTION,
                    matched=True,
                    weight=35.0,
                    score_contribution=-35.0,
                    description="Absence of positive brightness delta (<=0.0) disqualifies structural construction",
                    evidence_used={"brightness_delta": b_val},
                )
            )

        final_score = max(0.0, min(1.0, (pos_score - neg_penalty) / max_possible))
        reason = f"Rectangularity {sp.rectangularity:.2f}, compactness {sp.compactness:.2f}, brightness delta {b_val:+.2f}"
        return final_score, evals, reason

    def _evaluate_clearance(
        self,
        region: ChangeRegionFeatures,
        config: ClassifierConfig,
    ) -> Tuple[float, List[RuleEvaluation], str]:
        """Evaluates evidence supporting the 'clearance' category."""
        evals: List[RuleEvaluation] = []
        pos_score = 0.0
        max_possible = 100.0
        neg_penalty = 0.0

        sp = region.spatial
        spec = region.spectral
        ctx = region.context

        veg_delta = (
            spec.vegetation_proxy_delta.value
            if (spec.vegetation_proxy_delta and spec.vegetation_proxy_delta.value is not None)
            else None
        )
        post_ndvi = (
            spec.ndvi_mean.value
            if (spec.ndvi_mean and spec.ndvi_mean.value is not None)
            else None
        )

        # 1. Spectral: Vegetation decline (weight: 45)
        if spec.has_wavelength_metadata and veg_delta is not None:
            veg_loss_matched = veg_delta <= config.clearance_max_ndvi_delta
            w_veg = 45.0
            contrib = w_veg if veg_loss_matched else 0.0
            pos_score += contrib
            evals.append(
                RuleEvaluation(
                    rule_id="rule_clear_spec_ndvi_decline",
                    category=ChangeCategory.CLEARANCE,
                    matched=veg_loss_matched,
                    weight=w_veg,
                    score_contribution=contrib,
                    description=f"NDVI delta <= {config.clearance_max_ndvi_delta} (severe vegetation removal)",
                    evidence_used={"vegetation_proxy_delta": veg_delta},
                )
            )

            # Post-change low NDVI (bare ground proxy) (weight: 15)
            bare_matched = post_ndvi is not None and post_ndvi <= 0.25
            w_bare = 15.0
            contrib_bare = w_bare if bare_matched else 0.0
            pos_score += contrib_bare
            evals.append(
                RuleEvaluation(
                    rule_id="rule_clear_spec_post_ndvi_low",
                    category=ChangeCategory.CLEARANCE,
                    matched=bare_matched,
                    weight=w_bare,
                    score_contribution=contrib_bare,
                    description="Post-change NDVI <= 0.25 (exposed soil or non-vegetated ground)",
                    evidence_used={"post_ndvi": post_ndvi},
                )
            )
        else:
            # Fallback for RGB: Brightness shift or red band increase (weight: 35)
            b_val = (
                spec.brightness_delta.value
                if (spec.brightness_delta and spec.brightness_delta.value is not None)
                else 0.0
            )
            rgb_clearing = b_val > 0.05
            w_rgb = 35.0
            contrib_rgb = w_rgb if rgb_clearing else 0.0
            pos_score += contrib_rgb
            evals.append(
                RuleEvaluation(
                    rule_id="rule_clear_spec_rgb_brightness_proxy",
                    category=ChangeCategory.CLEARANCE,
                    matched=rgb_clearing,
                    weight=w_rgb,
                    score_contribution=contrib_rgb,
                    description="RGB visible brightness increase > 0.05 (bare soil proxy in uncalibrated imagery)",
                    evidence_used={"brightness_delta": b_val},
                )
            )

        # 2. Geometry: Non-linear corridor check (weight: 20)
        nlin_matched = sp.linearity_score <= 0.70
        w_nlin = 20.0
        contrib = w_nlin if nlin_matched else 0.0
        pos_score += contrib
        evals.append(
            RuleEvaluation(
                rule_id="rule_clear_geom_non_linear",
                category=ChangeCategory.CLEARANCE,
                matched=nlin_matched,
                weight=w_nlin,
                score_contribution=contrib,
                description="Linearity <= 0.70 (broad areal clearing, not narrow corridor)",
                evidence_used={"linearity_score": sp.linearity_score},
            )
        )

        # 3. Geometry: Organic / parcel shape (weight: 10)
        shape_matched = sp.rectangularity <= 0.85
        w_shp = 10.0
        contrib = w_shp if shape_matched else 0.0
        pos_score += contrib
        evals.append(
            RuleEvaluation(
                rule_id="rule_clear_geom_organic_shape",
                category=ChangeCategory.CLEARANCE,
                matched=shape_matched,
                weight=w_shp,
                score_contribution=contrib,
                description="Rectangularity <= 0.85 (organic or natural parcel boundary, not structural footprint)",
                evidence_used={"rectangularity": sp.rectangularity},
            )
        )

        # 4. Context: Surrounding background change low (weight: 10)
        surr_chg = ctx.surrounding_mean_change if (ctx.available and ctx.surrounding_mean_change is not None) else 0.0
        ctx_matched = surr_chg <= 0.30
        w_ctx = 10.0
        contrib = w_ctx if ctx_matched else 0.0
        pos_score += contrib
        evals.append(
            RuleEvaluation(
                rule_id="rule_clear_ctx_isolated",
                category=ChangeCategory.CLEARANCE,
                matched=ctx_matched,
                weight=w_ctx,
                score_contribution=contrib,
                description="Surrounding background change <= 0.30 (clearing is locally isolated)",
                evidence_used={"surrounding_mean_change": surr_chg},
            )
        )

        # Disqualifier: Vegetation gain (re-greening)
        if veg_delta is not None and veg_delta > 0.05:
            neg_penalty += 60.0
            evals.append(
                RuleEvaluation(
                    rule_id="disqual_clear_vegetation_gain",
                    category=ChangeCategory.CLEARANCE,
                    matched=True,
                    weight=60.0,
                    score_contribution=-60.0,
                    description="Vegetation delta > +0.05 strictly disqualifies clearance",
                    evidence_used={"vegetation_proxy_delta": veg_delta},
                )
            )

        # Disqualifier: Water presence
        water_val = (
            spec.water_spectral_criterion_fraction.value
            if (spec.water_spectral_criterion_fraction and spec.water_spectral_criterion_fraction.value is not None)
            else 0.0
        )
        if water_val > 0.35:
            neg_penalty += 50.0
            evals.append(
                RuleEvaluation(
                    rule_id="disqual_clear_water_presence",
                    category=ChangeCategory.CLEARANCE,
                    matched=True,
                    weight=50.0,
                    score_contribution=-50.0,
                    description="Water spectral fraction > 0.35 indicates water body/flooding, not vegetation clearance",
                    evidence_used={"water_spectral_criterion_fraction": water_val},
                )
            )

        # Disqualifier: Narrow linear corridor
        if sp.linearity_score > 0.80 and sp.aspect_ratio > 5.0:
            neg_penalty += 40.0
            evals.append(
                RuleEvaluation(
                    rule_id="disqual_clear_linear_corridor",
                    category=ChangeCategory.CLEARANCE,
                    matched=True,
                    weight=40.0,
                    score_contribution=-40.0,
                    description="High linearity (>0.80) and aspect ratio (>5.0) indicates narrow corridor, not broad areal clearance",
                    evidence_used={"linearity_score": sp.linearity_score, "aspect_ratio": sp.aspect_ratio},
                )
            )

        final_score = max(0.0, min(1.0, (pos_score - neg_penalty) / max_possible))
        v_str = f"NDVI delta {veg_delta:+.2f}" if veg_delta is not None else "visible reflectance shift"
        reason = f"Vegetation decline ({v_str}) across broad non-linear patch ({sp.area_px} px)"
        return final_score, evals, reason

    def _evaluate_water_extent_change(
        self,
        region: ChangeRegionFeatures,
        config: ClassifierConfig,
    ) -> Tuple[float, List[RuleEvaluation], str]:
        """Evaluates evidence supporting the 'water_extent_change' category.

        Strict physical policy: Water cannot be asserted without calibrated Green and NIR bands.
        """
        evals: List[RuleEvaluation] = []
        spec = region.spectral

        # Hard gating: Check if physical bands are available
        if (
            not spec.has_wavelength_metadata
            or not spec.water_spectral_criterion_fraction
            or not spec.water_spectral_criterion_fraction.available
        ):
            evals.append(
                RuleEvaluation(
                    rule_id="gate_water_spectral_bands_required",
                    category=ChangeCategory.WATER_EXTENT_CHANGE,
                    matched=False,
                    weight=100.0,
                    score_contribution=0.0,
                    description="Water extent change strictly requires calibrated Green and NIR bands for NDWI",
                    evidence_used={"has_wavelength_metadata": spec.has_wavelength_metadata},
                )
            )
            return 0.0, evals, "Water indices unavailable without calibrated Green and NIR bands"

        pos_score = 0.0
        max_possible = 100.0
        neg_penalty = 0.0

        w_frac = (
            spec.water_spectral_criterion_fraction.value
            if spec.water_spectral_criterion_fraction.value is not None
            else 0.0
        )
        ndwi_val = spec.ndwi_mean.value if (spec.ndwi_mean and spec.ndwi_mean.value is not None) else None

        # 1. Spectral: Water spectral criterion fraction (weight: 55)
        frac_matched = w_frac >= config.water_min_criterion_fraction
        w_f = 55.0
        contrib = w_f if frac_matched else 0.0
        pos_score += contrib
        evals.append(
            RuleEvaluation(
                rule_id="rule_water_spec_criterion_fraction",
                category=ChangeCategory.WATER_EXTENT_CHANGE,
                matched=frac_matched,
                weight=w_f,
                score_contribution=contrib,
                description=f"Water spectral criterion fraction >= {config.water_min_criterion_fraction} (NDWI > 0)",
                evidence_used={"water_spectral_criterion_fraction": w_frac},
            )
        )

        # 2. Spectral: Positive mean NDWI (weight: 25)
        ndwi_matched = ndwi_val is not None and ndwi_val >= 0.10
        w_nd = 25.0
        contrib_nd = w_nd if ndwi_matched else 0.0
        pos_score += contrib_nd
        evals.append(
            RuleEvaluation(
                rule_id="rule_water_spec_mean_ndwi",
                category=ChangeCategory.WATER_EXTENT_CHANGE,
                matched=ndwi_matched,
                weight=w_nd,
                score_contribution=contrib_nd,
                description="Mean regional NDWI >= 0.10 (dominant open water signature)",
                evidence_used={"ndwi_mean": ndwi_val},
            )
        )

        # 3. Context & Regularity: Smooth change magnitude (weight: 20)
        c_score = region.change_score
        score_std = c_score.get("score_std", 0.0)
        smooth_matched = score_std <= 0.25
        w_sm = 20.0
        contrib_sm = w_sm if smooth_matched else 0.0
        pos_score += contrib_sm
        evals.append(
            RuleEvaluation(
                rule_id="rule_water_uniformity",
                category=ChangeCategory.WATER_EXTENT_CHANGE,
                matched=smooth_matched,
                weight=w_sm,
                score_contribution=contrib_sm,
                description="Score std <= 0.25 (uniform radiometric response typical of water surface)",
                evidence_used={"score_std": score_std},
            )
        )

        # Disqualifier: High vegetation
        post_ndvi = spec.ndvi_mean.value if (spec.ndvi_mean and spec.ndvi_mean.value is not None) else None
        if post_ndvi is not None and post_ndvi > 0.30:
            neg_penalty += 50.0
            evals.append(
                RuleEvaluation(
                    rule_id="disqual_water_high_vegetation",
                    category=ChangeCategory.WATER_EXTENT_CHANGE,
                    matched=True,
                    weight=50.0,
                    score_contribution=-50.0,
                    description="Post-change NDVI > 0.30 indicates active vegetation canopy, not water",
                    evidence_used={"ndvi_mean": post_ndvi},
                )
            )

        final_score = max(0.0, min(1.0, (pos_score - neg_penalty) / max_possible))
        reason = f"Water spectral criterion fraction {w_frac:.2f} with NDWI {ndwi_val if ndwi_val is not None else 0.0:+.2f}"
        return final_score, evals, reason

    def _evaluate_road_development(
        self,
        region: ChangeRegionFeatures,
        config: ClassifierConfig,
    ) -> Tuple[float, List[RuleEvaluation], str]:
        """Evaluates evidence supporting the 'road_development' category."""
        evals: List[RuleEvaluation] = []
        pos_score = 0.0
        max_possible = 100.0
        neg_penalty = 0.0

        sp = region.spatial
        spec = region.spectral
        ctx = region.context

        # 1. Geometry: Linearity score (weight: 35)
        lin_matched = sp.linearity_score >= config.road_min_linearity
        w_lin = 35.0
        contrib = w_lin if lin_matched else 0.0
        pos_score += contrib
        evals.append(
            RuleEvaluation(
                rule_id="rule_road_geom_linearity",
                category=ChangeCategory.ROAD_DEVELOPMENT,
                matched=lin_matched,
                weight=w_lin,
                score_contribution=contrib,
                description=f"Linearity score >= {config.road_min_linearity} (strong directional moment of inertia)",
                evidence_used={"linearity_score": sp.linearity_score},
            )
        )

        # 2. Geometry: Aspect ratio / axis ratio (weight: 25)
        asp_matched = sp.aspect_ratio >= config.road_min_aspect_ratio or sp.axis_ratio >= config.road_min_aspect_ratio
        w_asp = 25.0
        contrib = w_asp if asp_matched else 0.0
        pos_score += contrib
        evals.append(
            RuleEvaluation(
                rule_id="rule_road_geom_elongation",
                category=ChangeCategory.ROAD_DEVELOPMENT,
                matched=asp_matched,
                weight=w_asp,
                score_contribution=contrib,
                description=f"Aspect ratio or axis ratio >= {config.road_min_aspect_ratio} (elongated transportation corridor)",
                evidence_used={"aspect_ratio": sp.aspect_ratio, "axis_ratio": sp.axis_ratio},
            )
        )

        # 3. Geometry: Major axis length minimum (weight: 15)
        len_matched = sp.major_axis_length >= 40.0
        w_len = 15.0
        contrib = w_len if len_matched else 0.0
        pos_score += contrib
        evals.append(
            RuleEvaluation(
                rule_id="rule_road_geom_corridor_length",
                category=ChangeCategory.ROAD_DEVELOPMENT,
                matched=len_matched,
                weight=w_len,
                score_contribution=contrib,
                description="Major axis length >= 40.0 px (sufficient length to represent road corridor)",
                evidence_used={"major_axis_length": sp.major_axis_length},
            )
        )

        # 4. Geometry: Minor axis width bounded (weight: 15)
        width_bounded = sp.minor_axis_length <= config.road_max_minor_axis_px
        w_wdt = 15.0
        contrib = w_wdt if width_bounded else 0.0
        pos_score += contrib
        evals.append(
            RuleEvaluation(
                rule_id="rule_road_geom_corridor_width_bounded",
                category=ChangeCategory.ROAD_DEVELOPMENT,
                matched=width_bounded,
                weight=w_wdt,
                score_contribution=contrib,
                description=f"Minor axis length <= {config.road_max_minor_axis_px} px (bounded corridor width, not wide clearing)",
                evidence_used={"minor_axis_length": sp.minor_axis_length},
            )
        )

        # 5. Context: Contrast with flanking terrain (weight: 10)
        c_val = ctx.region_to_background_contrast if (ctx.available and ctx.region_to_background_contrast is not None) else 0.0
        ctx_matched = c_val >= 0.10
        w_ctx = 10.0
        contrib = w_ctx if ctx_matched else 0.0
        pos_score += contrib
        evals.append(
            RuleEvaluation(
                rule_id="rule_road_ctx_contrast",
                category=ChangeCategory.ROAD_DEVELOPMENT,
                matched=ctx_matched,
                weight=w_ctx,
                score_contribution=contrib,
                description="Region-to-background contrast >= 0.10 (distinct corridor boundary contrast)",
                evidence_used={"region_to_background_contrast": c_val},
            )
        )

        # Disqualifier 1: Canal / Water corridor
        water_val = (
            spec.water_spectral_criterion_fraction.value
            if (spec.water_spectral_criterion_fraction and spec.water_spectral_criterion_fraction.value is not None)
            else 0.0
        )
        if water_val > 0.35:
            neg_penalty += 60.0
            evals.append(
                RuleEvaluation(
                    rule_id="disqual_road_water_canal",
                    category=ChangeCategory.ROAD_DEVELOPMENT,
                    matched=True,
                    weight=60.0,
                    score_contribution=-60.0,
                    description="Water spectral criterion > 0.35 indicates drainage ditch or canal, not roadway",
                    evidence_used={"water_spectral_criterion_fraction": water_val},
                )
            )

        # Disqualifier 2: Excessively wide minor axis (massive clearing)
        if sp.minor_axis_length > (config.road_max_minor_axis_px * 1.5):
            neg_penalty += 40.0
            evals.append(
                RuleEvaluation(
                    rule_id="disqual_road_excessive_width",
                    category=ChangeCategory.ROAD_DEVELOPMENT,
                    matched=True,
                    weight=40.0,
                    score_contribution=-40.0,
                    description=f"Corridor minor axis ({sp.minor_axis_length:.1f} px) far exceeds road width limit",
                    evidence_used={"minor_axis_length": sp.minor_axis_length},
                )
            )

        # Disqualifier 3: High compactness with low aspect ratio
        if sp.compactness > 0.50 and sp.aspect_ratio < 2.5:
            neg_penalty += 50.0
            evals.append(
                RuleEvaluation(
                    rule_id="disqual_road_compact_blob",
                    category=ChangeCategory.ROAD_DEVELOPMENT,
                    matched=True,
                    weight=50.0,
                    score_contribution=-50.0,
                    description="High compactness (>0.50) with low aspect ratio (<2.5) strictly disqualifies road corridor",
                    evidence_used={"compactness": sp.compactness, "aspect_ratio": sp.aspect_ratio},
                )
            )

        # Disqualifier 4: Flanking contextual evidence unavailable
        if not ctx.available or ctx.region_to_background_contrast is None:
            neg_penalty += 50.0
            evals.append(
                RuleEvaluation(
                    rule_id="disqual_road_missing_context",
                    category=ChangeCategory.ROAD_DEVELOPMENT,
                    matched=True,
                    weight=50.0,
                    score_contribution=-50.0,
                    description="Flanking context unavailable; linear geometry alone is insufficient for road classification",
                    evidence_used={"context_available": ctx.available},
                )
            )
        elif c_val < 0.05:
            neg_penalty += 20.0
            evals.append(
                RuleEvaluation(
                    rule_id="penalty_road_negligible_contrast",
                    category=ChangeCategory.ROAD_DEVELOPMENT,
                    matched=True,
                    weight=20.0,
                    score_contribution=-20.0,
                    description="Corridor lacks visible contrast with flanking terrain (< 0.05)",
                    evidence_used={"region_to_background_contrast": c_val},
                )
            )

        final_score = max(0.0, min(1.0, (pos_score - neg_penalty) / max_possible))
        reason = f"Linearity {sp.linearity_score:.2f}, aspect ratio {sp.aspect_ratio:.1f}, bounded width {sp.minor_axis_length:.1f} px"
        return final_score, evals, reason

    def _classify_region(
        self,
        region: ChangeRegionFeatures,
        config: ClassifierConfig,
    ) -> RegionClassification:
        """Executes the complete three-stage evidentiary decision network on a single region."""
        reg_id = region.region_id
        sp = region.spatial
        spec = region.spectral
        data_limitations: List[str] = []

        # Stage 1: Size eligibility check
        if sp.area_px < config.min_classification_area_px:
            return RegionClassification(
                region_id=reg_id,
                category=ChangeCategory.UNKNOWN,
                evidence_score=0.0,
                confidence_tier=ConfidenceTier.UNCERTAIN,
                decision_reason=(
                    f"Insufficient region size ({sp.area_px} px < {config.min_classification_area_px} px) "
                    "for reliable geometric or spectral shape classification"
                ),
                rule_evaluations=[],
                candidate_scores={},
                conflicting_categories=[],
                data_limitations=["Region size below minimum classification threshold"],
                is_ambiguous=False,
            )

        # Stage 1b: Required spectral modality check
        if not spec.available:
            return RegionClassification(
                region_id=reg_id,
                category=ChangeCategory.UNKNOWN,
                evidence_score=0.0,
                confidence_tier=ConfidenceTier.UNCERTAIN,
                decision_reason=(
                    "Required spectral imagery modality is unavailable for semantic change classification"
                ),
                rule_evaluations=[],
                candidate_scores={},
                conflicting_categories=[],
                data_limitations=["Spectral imagery modality unavailable"],
                is_ambiguous=False,
            )

        # Data limitation tracking
        if not spec.has_wavelength_metadata:
            data_limitations.append(
                "Uncalibrated or RGB imagery: physical vegetation (NDVI) and water (NDWI) indices unavailable"
            )

        # Stage 2: Category Evaluators
        s_const, evals_const, r_const = self._evaluate_construction(region, config)
        s_clear, evals_clear, r_clear = self._evaluate_clearance(region, config)
        s_water, evals_water, r_water = self._evaluate_water_extent_change(region, config)
        s_road, evals_road, r_road = self._evaluate_road_development(region, config)

        candidate_scores: Dict[str, float] = {
            ChangeCategory.CONSTRUCTION.value: round(s_const, 4),
            ChangeCategory.CLEARANCE.value: round(s_clear, 4),
            ChangeCategory.WATER_EXTENT_CHANGE.value: round(s_water, 4),
            ChangeCategory.ROAD_DEVELOPMENT.value: round(s_road, 4),
        }

        all_evals = evals_const + evals_clear + evals_water + evals_road

        # Sort candidates descending by evidence score
        sorted_candidates = sorted(
            [
                (ChangeCategory.CONSTRUCTION, s_const, r_const),
                (ChangeCategory.CLEARANCE, s_clear, r_clear),
                (ChangeCategory.WATER_EXTENT_CHANGE, s_water, r_water),
                (ChangeCategory.ROAD_DEVELOPMENT, s_road, r_road),
            ],
            key=lambda item: item[1],
            reverse=True,
        )

        top_cat, top_score, top_reason = sorted_candidates[0]
        runner_cat, runner_score, _ = sorted_candidates[1]

        # Stage 3: Arbitration & Conflict Resolution

        # Check 1: Minimum score threshold
        if top_score < config.min_evidence_score_threshold:
            return RegionClassification(
                region_id=reg_id,
                category=ChangeCategory.UNKNOWN,
                evidence_score=round(top_score, 4),
                confidence_tier=ConfidenceTier.UNCERTAIN,
                decision_reason=(
                    f"Highest evidence alignment ({top_score:.2f} for {top_cat.value}) "
                    f"failed minimum threshold {config.min_evidence_score_threshold:.2f}"
                ),
                rule_evaluations=all_evals,
                candidate_scores=candidate_scores,
                conflicting_categories=[],
                data_limitations=data_limitations,
                is_ambiguous=False,
            )

        # Check 2: Disambiguation margin
        score_diff = top_score - runner_score
        if score_diff < config.ambiguity_margin_threshold and runner_score >= config.min_evidence_score_threshold:
            return RegionClassification(
                region_id=reg_id,
                category=ChangeCategory.UNKNOWN,
                evidence_score=round(top_score, 4),
                confidence_tier=ConfidenceTier.UNCERTAIN,
                decision_reason=(
                    f"Ambiguous evidence conflict between {top_cat.value} ({top_score:.2f}) and "
                    f"{runner_cat.value} ({runner_score:.2f}) within margin {config.ambiguity_margin_threshold:.2f}"
                ),
                rule_evaluations=all_evals,
                candidate_scores=candidate_scores,
                conflicting_categories=[top_cat.value, runner_cat.value],
                data_limitations=data_limitations,
                is_ambiguous=True,
            )

        # Check 3: Final Category Assignment & Confidence Tier Stratification
        if not spec.has_wavelength_metadata and top_cat in (ChangeCategory.CLEARANCE, ChangeCategory.CONSTRUCTION):
            # Without calibrated multispectral bands, confidence is downgraded to LOW
            tier = ConfidenceTier.LOW
        elif top_score >= 0.75 and score_diff >= 0.30 and sp.area_px >= 25:
            tier = ConfidenceTier.HIGH
        elif top_score >= 0.55 and score_diff >= 0.18:
            tier = ConfidenceTier.MEDIUM
        else:
            tier = ConfidenceTier.LOW

        decision_reason = (
            f"Classified as {top_cat.value} (evidence score {top_score:.2f}, margin +{score_diff:.2f}): {top_reason}"
        )

        return RegionClassification(
            region_id=reg_id,
            category=top_cat,
            evidence_score=round(top_score, 4),
            confidence_tier=tier,
            decision_reason=decision_reason,
            rule_evaluations=all_evals,
            candidate_scores=candidate_scores,
            conflicting_categories=[],
            data_limitations=data_limitations,
            is_ambiguous=False,
        )

    def classify(
        self,
        evidence: ChangeEvidence,
        config: Optional[ClassifierConfig] = None,
    ) -> ChangeClassificationResult:
        """Executes full change-type classification across all regions in the evidence document."""
        cfg = config or self.config
        classifications: List[RegionClassification] = []

        cat_counts: Dict[str, int] = {cat.value: 0 for cat in ChangeCategory}
        high_conf_count = 0
        ambig_count = 0

        for region in evidence.regions:
            reg_cls = self._classify_region(region, cfg)
            classifications.append(reg_cls)
            cat_counts[reg_cls.category.value] += 1
            if reg_cls.confidence_tier == ConfidenceTier.HIGH:
                high_conf_count += 1
            if reg_cls.is_ambiguous:
                ambig_count += 1

        total_reg = len(classifications)
        unknown_fraction = float(cat_counts[ChangeCategory.UNKNOWN.value] / max(1, total_reg))

        metrics = ChangeClassificationMetrics(
            total_regions=total_reg,
            category_counts=cat_counts,
            high_confidence_count=high_conf_count,
            ambiguous_count=ambig_count,
            unclassified_unknown_fraction=round(unknown_fraction, 4),
        )

        # Deterministic Identity and Provenance Linkage
        seed = (
            f"{evidence.evidence_id}:"
            f"{cfg.classifier_id}:{cfg.classifier_version}:"
            f"{total_reg}"
        )
        content_hash = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
        classification_id = f"cls_{content_hash}"
        provenance_id = f"prov_cls_{content_hash}"

        return ChangeClassificationResult(
            classification_id=classification_id,
            evidence_id=evidence.evidence_id,
            scene_pair_id=evidence.scene_pair_id,
            change_detection_result_id=evidence.change_detection_result_id,
            classifier_id=cfg.classifier_id,
            classifier_version=cfg.classifier_version,
            config=cfg,
            metrics=metrics,
            classifications=classifications,
            provenance_id=provenance_id,
            created_at=datetime.now(timezone.utc),
        )
