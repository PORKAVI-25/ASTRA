"""ASTRA Phase M4E: Observation Node Evaluator & Gating.

Evaluates an individual temporal observation node against upstream
M4A, M4B, M4C-A, M4C-B, and M4D evidence.
Enforces strict M4D authority, non-probabilistic heuristic support mapping,
and deterministic earliest-support eligibility gating.
"""

from typing import Any, Dict, List, Optional, Tuple

from geospatial.contracts import GeoBoundingBox
from backend.ml.change.types import TemporalObservation
from backend.ml.change_classification.types import ChangeCategory, ConfidenceTier, RegionClassification
from backend.ml.change_detection.types import ChangeRegion
from backend.ml.change_suppression.types import RegionSuppression, SuppressionDecision
from backend.ml.temporal_evidence.correspondence import evaluate_spatial_correspondence
from backend.ml.temporal_evidence.types import (
    CandidateRegionRef,
    CorrespondenceRelationship,
    PairwiseTemporalEvidenceInput,
    SpatialCorrespondence,
    SpatialCorrespondenceStatus,
    TemporalEvidenceConfig,
    TemporalEvidenceNode,
    TemporalNodeStatus,
)


def extract_observation_quality_metadata(
    obs: TemporalObservation,
) -> Tuple[Optional[float], Optional[float], bool]:
    """Extracts positively recorded cloud fraction and valid pixel ratio from observation metadata.

    M4E MUST NOT invent or infer these values when absent from upstream metadata.
    Returns: (cloud_fraction, valid_pixel_ratio, has_positive_metadata)
    """
    meta = obs.metadata or {}

    cloud_val: Optional[float] = None
    valid_val: Optional[float] = None

    # Check common satellite ingestion metadata keys
    for k in ("cloud_fraction", "cloud_cover_percentage", "cloud_cover", "cloud_ratio"):
        if k in meta and meta[k] is not None:
            raw_cloud = float(meta[k])
            # Normalize 0-100 percentage to 0.0-1.0 fraction if needed
            cloud_val = raw_cloud / 100.0 if raw_cloud > 1.0 else raw_cloud
            break

    for k in ("valid_pixel_ratio", "valid_pixel_fraction", "valid_pixels_fraction", "data_coverage"):
        if k in meta and meta[k] is not None:
            raw_valid = float(meta[k])
            valid_val = raw_valid / 100.0 if raw_valid > 1.0 else raw_valid
            break

    has_positive = (cloud_val is not None) and (valid_val is not None)
    return cloud_val, valid_val, has_positive


def evaluate_node_support(
    observation: TemporalObservation,
    candidate_ref: CandidateRegionRef,
    candidate_region: Optional[ChangeRegion],
    pairwise_input: Optional[PairwiseTemporalEvidenceInput],
    is_pre_change_candidate: bool,
    is_simultaneous: bool,
    discovery_sensor: str,
    config: TemporalEvidenceConfig,
) -> TemporalEvidenceNode:
    """Evaluates candidate change support at a single temporal observation epoch."""
    reasons: List[str] = []
    limitations: List[str] = []

    # 1. Handle simultaneous co-temporal observations
    if is_simultaneous:
        spatial_corr = evaluate_spatial_correspondence(
            candidate_bbox_wgs84=candidate_region.bbox_wgs84 if candidate_region else None,
            candidate_centroid_wgs84=candidate_region.centroid_wgs84 if candidate_region else None,
            candidate_bbox_px=candidate_region.bbox_px if candidate_region else None,
            candidate_centroid_px=candidate_region.centroid_px if candidate_region else None,
            candidate_crs=observation.crs,
            target_bbox_wgs84=observation.bounds_wgs84,
            target_centroid_wgs84=[
                (observation.bounds_wgs84.min_lon + observation.bounds_wgs84.max_lon) / 2.0,
                (observation.bounds_wgs84.min_lat + observation.bounds_wgs84.max_lat) / 2.0,
            ],
            target_bbox_px=None,
            target_centroid_px=None,
            target_crs=observation.crs,
            matching_relationship=CorrespondenceRelationship.NONE,
        )
        return TemporalEvidenceNode(
            observation_id=observation.observation_id,
            acquisition_time=observation.acquisition_time,
            sensor=observation.sensor,
            platform=observation.platform,
            node_status=TemporalNodeStatus.SIMULTANEOUS_CO_TEMPORAL,
            m4d_decision=None,
            heuristic_support_score=0.0,
            eligible_for_earliest_support=False,
            spatial_correspondence=spatial_corr,
            category_observed=None,
            category_confidence=None,
            evidence_score_m4c=None,
            is_cross_sensor=observation.sensor != discovery_sensor,
            decision_reasons=["Observation shares identical acquisition timestamp with another series node; excluded from ordered onset interval."],
            data_limitations=["Simultaneous co-temporal observation retained for audit only."],
        )

    # 2. Check cross-sensor
    is_cross_sensor = observation.sensor != discovery_sensor
    if is_cross_sensor:
        limitations.append(
            f"Uncalibrated cross-sensor observation ({discovery_sensor} vs {observation.sensor}); radiometric equivalence unverified."
        )

    # 3. Handle PRE_CHANGE_ABSENCE verification
    if is_pre_change_candidate:
        cloud_frac, valid_ratio, has_quality_meta = extract_observation_quality_metadata(observation)

        # Pre-change observation has no change region; verify spatial coverage of candidate footprint
        has_spatial_coverage = True
        if candidate_region and candidate_region.bbox_wgs84 and observation.bounds_wgs84:
            cb = candidate_region.bbox_wgs84
            ob = observation.bounds_wgs84
            # Covered if candidate bbox intersects observation bounds
            has_spatial_coverage = not (
                cb.max_lon < ob.min_lon - 1e-4
                or cb.min_lon > ob.max_lon + 1e-4
                or cb.max_lat < ob.min_lat - 1e-4
                or cb.min_lat > ob.max_lat + 1e-4
            )

        spatial_corr = SpatialCorrespondence(
            status=SpatialCorrespondenceStatus.GEOREFERENCED_BBOX if has_spatial_coverage else SpatialCorrespondenceStatus.DISJOINT,
            relationship=CorrespondenceRelationship.NONE,
            is_spatially_compatible=has_spatial_coverage,
            iou_wgs84=1.0 if has_spatial_coverage else 0.0,
            centroid_distance_m=0.0 if has_spatial_coverage else None,
            centroid_distance_px=0.0 if has_spatial_coverage else None,
            crs_match=True,
            gsd_match=True,
        )

        if not has_quality_meta:
            limitations.append(
                "Missing upstream quality metadata (cloud_fraction or valid_pixel_ratio); pre-change absence cannot be positively verified."
            )
            return TemporalEvidenceNode(
                observation_id=observation.observation_id,
                acquisition_time=observation.acquisition_time,
                sensor=observation.sensor,
                platform=observation.platform,
                node_status=TemporalNodeStatus.INSUFFICIENT_DATA,
                m4d_decision=None,
                heuristic_support_score=0.0,
                eligible_for_earliest_support=False,
                spatial_correspondence=spatial_corr,
                category_observed=None,
                category_confidence=None,
                evidence_score_m4c=None,
                is_cross_sensor=is_cross_sensor,
                decision_reasons=["Pre-change absence could not be confirmed due to missing quality metadata."],
                data_limitations=limitations,
            )

        # Check positive absence criteria
        is_clear = (
            cloud_frac is not None
            and cloud_frac <= config.max_pre_change_cloud_fraction
            and valid_ratio is not None
            and valid_ratio >= config.min_pre_change_valid_pixel_ratio
        )

        if is_clear and spatial_corr.is_spatially_compatible:
            reasons.append(
                f"Verified pre-change absence: clear surface (cloud={cloud_frac:.1%}, valid={valid_ratio:.1%}) "
                f"with valid spatial coverage."
            )
            return TemporalEvidenceNode(
                observation_id=observation.observation_id,
                acquisition_time=observation.acquisition_time,
                sensor=observation.sensor,
                platform=observation.platform,
                node_status=TemporalNodeStatus.PRE_CHANGE_ABSENCE,
                m4d_decision=None,
                heuristic_support_score=0.0,
                eligible_for_earliest_support=False,
                spatial_correspondence=spatial_corr,
                category_observed=None,
                category_confidence=None,
                evidence_score_m4c=None,
                is_cross_sensor=is_cross_sensor,
                decision_reasons=reasons,
                data_limitations=limitations,
            )
        else:
            limitations.append(
                f"Pre-change observation fails quality thresholds (cloud={cloud_frac}, valid={valid_ratio})."
            )
            return TemporalEvidenceNode(
                observation_id=observation.observation_id,
                acquisition_time=observation.acquisition_time,
                sensor=observation.sensor,
                platform=observation.platform,
                node_status=TemporalNodeStatus.INSUFFICIENT_DATA,
                m4d_decision=None,
                heuristic_support_score=0.0,
                eligible_for_earliest_support=False,
                spatial_correspondence=spatial_corr,
                category_observed=None,
                category_confidence=None,
                evidence_score_m4c=None,
                is_cross_sensor=is_cross_sensor,
                decision_reasons=["Observation is obscured or invalid; cannot verify pre-change absence."],
                data_limitations=limitations,
            )

    # 4. Evaluate change support via upstream pairwise evidence
    if pairwise_input is None:
        spatial_corr = evaluate_spatial_correspondence(
            candidate_bbox_wgs84=candidate_region.bbox_wgs84 if candidate_region else None,
            candidate_centroid_wgs84=candidate_region.centroid_wgs84 if candidate_region else None,
            candidate_bbox_px=candidate_region.bbox_px if candidate_region else None,
            candidate_centroid_px=candidate_region.centroid_px if candidate_region else None,
            candidate_crs=observation.crs,
            target_bbox_wgs84=observation.bounds_wgs84,
            target_centroid_wgs84=None,
            target_bbox_px=None,
            target_centroid_px=None,
            target_crs=observation.crs,
        )
        limitations.append("Missing pairwise upstream evidence for this observation epoch.")
        return TemporalEvidenceNode(
            observation_id=observation.observation_id,
            acquisition_time=observation.acquisition_time,
            sensor=observation.sensor,
            platform=observation.platform,
            node_status=TemporalNodeStatus.INSUFFICIENT_DATA,
            m4d_decision=None,
            heuristic_support_score=0.0,
            eligible_for_earliest_support=False,
            spatial_correspondence=spatial_corr,
            category_observed=None,
            category_confidence=None,
            evidence_score_m4c=None,
            is_cross_sensor=is_cross_sensor,
            decision_reasons=["No upstream M4B/M4D evidence provided for this observation epoch."],
            data_limitations=limitations,
        )

    # 5. Extract upstream M4D suppression outcome
    supp_res = pairwise_input.suppression_result
    region_supp: Optional[RegionSuppression] = None
    if supp_res:
        for r in supp_res.regions:
            if r.region_id == candidate_ref.region_id:
                region_supp = r
                break
        if region_supp is None and supp_res.regions:
            # Match first region if only one exists in pairwise result
            region_supp = supp_res.regions[0]

    # 6. Extract upstream M4B ChangeRegion for S_chg
    cdr = pairwise_input.change_detection_result
    target_region: Optional[ChangeRegion] = None
    if cdr:
        for r in cdr.regions:
            if r.region_id == candidate_ref.region_id:
                target_region = r
                break
        if target_region is None and cdr.regions:
            target_region = cdr.regions[0]

    # Evaluate spatial correspondence with observed target region
    spatial_corr = evaluate_spatial_correspondence(
        candidate_bbox_wgs84=candidate_region.bbox_wgs84 if candidate_region else None,
        candidate_centroid_wgs84=candidate_region.centroid_wgs84 if candidate_region else None,
        candidate_bbox_px=candidate_region.bbox_px if candidate_region else None,
        candidate_centroid_px=candidate_region.centroid_px if candidate_region else None,
        candidate_crs=observation.crs,
        target_bbox_wgs84=target_region.bbox_wgs84 if target_region else observation.bounds_wgs84,
        target_centroid_wgs84=target_region.centroid_wgs84 if target_region else None,
        target_bbox_px=target_region.bbox_px if target_region else None,
        target_centroid_px=target_region.centroid_px if target_region else None,
        target_crs=observation.crs,
        min_bbox_iou_threshold=config.min_bbox_iou_threshold,
        max_centroid_distance_m=config.max_centroid_distance_m,
    )

    # Extract M4C-B classification if available
    cls_res = pairwise_input.classification
    region_cls: Optional[RegionClassification] = None
    if cls_res:
        for c in cls_res.classifications:
            if c.region_id == candidate_ref.region_id:
                region_cls = c
                break
        if region_cls is None and cls_res.classifications:
            region_cls = cls_res.classifications[0]

    category_observed: Optional[ChangeCategory] = region_cls.category if region_cls else None
    category_confidence: Optional[ConfidenceTier] = region_cls.confidence_tier if region_cls else None
    evidence_score_m4c: Optional[float] = region_cls.evidence_score if region_cls else None

    # Determine S_chg strictly from M4B
    if target_region is not None:
        s_chg = target_region.mean_change_score
    elif cdr is not None and len(cdr.regions) == 0:
        # Valid M4B executed and explicitly detected zero regions
        s_chg = 0.0
    else:
        # M4B missing or failed
        s_chg = 0.0
        limitations.append("M4B ChangeDetectionResult is missing or malformed; change signal unavailable.")

    # 7. Apply M4D Gating Factor
    m4d_decision = region_supp.decision if region_supp else SuppressionDecision.INSUFFICIENT_EVIDENCE
    g_m4d = 0.0

    if m4d_decision == SuppressionDecision.SUPPRESSED:
        g_m4d = 0.00
        reasons.append("Screened out by upstream M4D as false alarm artifact; zero temporal support.")
    elif m4d_decision == SuppressionDecision.INSUFFICIENT_EVIDENCE:
        g_m4d = 0.00
        reasons.append("Upstream M4D reported insufficient evidence / severe data limitation; zero temporal support.")
    elif m4d_decision == SuppressionDecision.FLAGGED:
        g_m4d = 0.40
        reasons.append("Upstream M4D flagged potential artifact risk; discounted support and barred from earliest support.")
    elif m4d_decision == SuppressionDecision.RETAINED:
        g_m4d = 1.00
        reasons.append("Passed upstream M4D false-alarm screening (RETAINED).")

    # 8. Compute Heuristic Support Score (uncalibrated audit index)
    w_spatial = 0.0
    if spatial_corr.iou_wgs84 >= config.min_bbox_iou_threshold:
        w_spatial = spatial_corr.iou_wgs84
    elif spatial_corr.centroid_distance_m is not None and spatial_corr.centroid_distance_m <= 30.0:
        w_spatial = 0.80
    elif spatial_corr.centroid_distance_m is not None and spatial_corr.centroid_distance_m <= 60.0:
        w_spatial = 0.50
    else:
        w_spatial = 0.00

    w_tier = 0.50
    if category_confidence == ConfidenceTier.HIGH:
        w_tier = 1.00
    elif category_confidence == ConfidenceTier.MEDIUM:
        w_tier = 0.85
    elif category_confidence == ConfidenceTier.LOW:
        w_tier = 0.70

    l_sensor = 0.80 if is_cross_sensor else 1.00

    s_cls = evidence_score_m4c if evidence_score_m4c is not None else 0.50

    if g_m4d == 0.00 or not spatial_corr.is_spatially_compatible:
        heuristic_score = 0.0
    else:
        s_raw = w_spatial * l_sensor * (0.40 * s_chg + 0.60 * (s_cls * w_tier))
        heuristic_score = round(min(1.0, g_m4d * s_raw), 4)

    # 9. Determine earliest-support eligibility and node status
    eligible_for_earliest = (
        m4d_decision == SuppressionDecision.RETAINED
        and spatial_corr.is_spatially_compatible
        and heuristic_score >= config.min_support_score_threshold
    )

    if m4d_decision == SuppressionDecision.SUPPRESSED:
        node_status = TemporalNodeStatus.SUPPRESSED_ARTIFACT
    elif m4d_decision == SuppressionDecision.INSUFFICIENT_EVIDENCE:
        node_status = TemporalNodeStatus.INSUFFICIENT_DATA
    elif m4d_decision == SuppressionDecision.FLAGGED:
        node_status = TemporalNodeStatus.FLAGGED_SUPPORT
    elif eligible_for_earliest:
        node_status = TemporalNodeStatus.EARLIEST_SUPPORTING  # Provisional; timeline engine marks subsequent as PERSISTENT_SUPPORT
        reasons.append(f"Satisfies M4E temporal support threshold (score={heuristic_score:.4f} >= {config.min_support_score_threshold}).")
    elif heuristic_score < config.min_support_score_threshold and spatial_corr.is_spatially_compatible:
        node_status = TemporalNodeStatus.NO_SUPPORT
        reasons.append(f"Heuristic support score ({heuristic_score:.4f}) is below threshold ({config.min_support_score_threshold}).")
    else:
        node_status = TemporalNodeStatus.INSUFFICIENT_DATA

    return TemporalEvidenceNode(
        observation_id=observation.observation_id,
        acquisition_time=observation.acquisition_time,
        sensor=observation.sensor,
        platform=observation.platform,
        node_status=node_status,
        m4d_decision=m4d_decision,
        heuristic_support_score=heuristic_score,
        eligible_for_earliest_support=eligible_for_earliest,
        spatial_correspondence=spatial_corr,
        category_observed=category_observed,
        category_confidence=category_confidence,
        evidence_score_m4c=evidence_score_m4c,
        is_cross_sensor=is_cross_sensor,
        decision_reasons=reasons,
        data_limitations=limitations,
    )
