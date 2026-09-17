"""ASTRA Phase M4F: Candidate-Region Temporal Correspondence Resolver.

Provides deterministic, metric-projected spatial correspondence resolution
mapping an explicitly selected discovery candidate region to its physical
counterpart across subsequent temporal pair ChangeDetectionResults.

Conforms to ASTRA-DC-v0.1 and strict spatial comparison semantics:
- Never matches by local region_id string equality across pairs.
- Never falls back to regions[0].
- Computes WGS84 metric-projected bounding box IoU.
- Resolves unambiguous matches, deterministic tie-breaking, or explicit
  NO_MATCH / AMBIGUOUS / INSUFFICIENT outcomes.
- Contains zero raster imports, zero raster loading, and zero classification logic.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from backend.ml.change_detection.types import ChangeDetectionResult, ChangeRegion
from backend.ml.temporal_evidence.correspondence import (
    compute_geodesic_distance_m,
    compute_metric_bbox_iou,
    evaluate_spatial_correspondence,
)
from backend.ml.temporal_evidence.types import (
    CorrespondenceRelationship,
    SpatialCorrespondence,
    SpatialCorrespondenceStatus,
)


class CandidateCorrespondenceResult(BaseModel):
    """Deterministic spatial correspondence outcome for a candidate region in a target temporal pair."""

    reference_candidate_id: str = Field(
        ..., min_length=3, description="Region ID of the discovery candidate reference"
    )
    target_pair_id: str = Field(
        ..., min_length=5, description="ScenePair ID of the evaluated target observation pair"
    )
    target_cdr_id: str = Field(
        ..., min_length=5, description="ChangeDetectionResult ID in the target pair"
    )
    status: SpatialCorrespondenceStatus = Field(
        ..., description="Geometric comparison method or failure status"
    )
    relationship: CorrespondenceRelationship = Field(
        ..., description="Topological relationship: MATCHED, NONE, AMBIGUOUS, etc."
    )
    matched_region_id: Optional[str] = Field(
        default=None, description="Locally unique region ID in target CDR if matched"
    )
    matched_region: Optional[ChangeRegion] = Field(
        default=None, description="Resolved ChangeRegion object if matched"
    )
    metric_iou: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Metric-projected bbox IoU with matched region"
    )
    centroid_distance_m: Optional[float] = Field(
        default=None, ge=0.0, description="Geodesic distance between centroids in meters"
    )
    spatial_correspondence: SpatialCorrespondence = Field(
        ..., description="Complete M4E SpatialCorrespondence contract"
    )
    candidate_scores: Dict[str, float] = Field(
        default_factory=dict, description="Metric IoU scores for all evaluated regions in target CDR"
    )
    resolution_notes: List[str] = Field(
        default_factory=list, description="Diagnostic trail explaining correspondence resolution"
    )

    model_config = ConfigDict(extra="forbid")


def resolve_candidate_correspondence(
    reference_region: ChangeRegion,
    target_cdr: ChangeDetectionResult,
    target_pair_id: str,
    min_bbox_iou_threshold: float = 0.30,
    max_centroid_distance_m: float = 60.0,
    ambiguity_margin: float = 0.05,
    reference_crs: Optional[str] = None,
    target_crs: Optional[str] = None,
) -> CandidateCorrespondenceResult:
    """Deterministically resolves spatial correspondence between discovery candidate and a target CDR.

    Inspects ALL detected regions in target_cdr. Compares geometry using metric-projected
    bbox IoU in square meters. Never compares region_id strings across different pairs.
    Never falls back to regions[0].
    """
    notes: List[str] = []
    scores: Dict[str, float] = {}

    ref_id = reference_region.region_id
    cdr_id = target_cdr.result_id

    # 1. Target CDR has zero detected regions
    if not target_cdr.regions:
        notes.append("Target pair ChangeDetectionResult detected zero change regions.")
        empty_corr = SpatialCorrespondence(
            status=SpatialCorrespondenceStatus.DISJOINT,
            relationship=CorrespondenceRelationship.NONE,
            is_spatially_compatible=False,
            iou_wgs84=0.0,
            centroid_distance_m=None,
            centroid_distance_px=None,
            crs_match=False,
            gsd_match=False,
        )
        return CandidateCorrespondenceResult(
            reference_candidate_id=ref_id,
            target_pair_id=target_pair_id,
            target_cdr_id=cdr_id,
            status=SpatialCorrespondenceStatus.DISJOINT,
            relationship=CorrespondenceRelationship.NONE,
            matched_region_id=None,
            matched_region=None,
            metric_iou=0.0,
            centroid_distance_m=None,
            spatial_correspondence=empty_corr,
            candidate_scores={},
            resolution_notes=notes,
        )

    # 2. Reference candidate lacks required georeferencing metadata
    if reference_region.bbox_wgs84 is None and reference_region.centroid_wgs84 is None:
        notes.append("Reference candidate region lacks WGS84 bounding box and centroid metadata.")
        meta_corr = SpatialCorrespondence(
            status=SpatialCorrespondenceStatus.INSUFFICIENT_METADATA,
            relationship=CorrespondenceRelationship.NONE,
            is_spatially_compatible=False,
            iou_wgs84=0.0,
            centroid_distance_m=None,
            centroid_distance_px=None,
            crs_match=False,
            gsd_match=False,
        )
        return CandidateCorrespondenceResult(
            reference_candidate_id=ref_id,
            target_pair_id=target_pair_id,
            target_cdr_id=cdr_id,
            status=SpatialCorrespondenceStatus.INSUFFICIENT_METADATA,
            relationship=CorrespondenceRelationship.NONE,
            matched_region_id=None,
            matched_region=None,
            metric_iou=0.0,
            centroid_distance_m=None,
            spatial_correspondence=meta_corr,
            candidate_scores={},
            resolution_notes=notes,
        )

    # 3. Evaluate metric bbox IoU and centroid distance for all detected regions
    iou_per_region: Dict[str, float] = {}
    dist_per_region: Dict[str, float] = {}
    region_map: Dict[str, ChangeRegion] = {}

    for reg in target_cdr.regions:
        region_map[reg.region_id] = reg
        # Metric bbox IoU
        if reference_region.bbox_wgs84 is not None and reg.bbox_wgs84 is not None:
            iou = compute_metric_bbox_iou(
                reference_region.bbox_wgs84,
                reg.bbox_wgs84,
                target_crs=reference_crs or target_crs,
            )
        else:
            iou = 0.0
        iou_per_region[reg.region_id] = iou
        scores[reg.region_id] = iou

        # Centroid geodesic distance
        if reference_region.centroid_wgs84 is not None and reg.centroid_wgs84 is not None:
            dist_m = compute_geodesic_distance_m(
                reference_region.centroid_wgs84[0],
                reference_region.centroid_wgs84[1],
                reg.centroid_wgs84[0],
                reg.centroid_wgs84[1],
            )
            dist_per_region[reg.region_id] = dist_m

    # 4. Check for bbox IoU candidates meeting threshold
    qualifying_iou = [
        (rid, score) for rid, score in iou_per_region.items() if score >= min_bbox_iou_threshold
    ]

    if qualifying_iou:
        # Sort descending by IoU, tie-break by region_id for deterministic execution
        qualifying_iou.sort(key=lambda item: (-item[1], item[0]))
        best_rid, best_iou = qualifying_iou[0]
        best_reg = region_map[best_rid]

        if len(qualifying_iou) == 1:
            # Single unambiguous match
            notes.append(
                f"Unambiguous spatial correspondence: {best_rid} with metric IoU={best_iou:.4f} "
                f"(>= threshold {min_bbox_iou_threshold:.2f})."
            )
            dist_m = dist_per_region.get(best_rid)
            best_corr = evaluate_spatial_correspondence(
                candidate_bbox_wgs84=reference_region.bbox_wgs84,
                candidate_centroid_wgs84=reference_region.centroid_wgs84,
                candidate_bbox_px=reference_region.bbox_px,
                candidate_centroid_px=reference_region.centroid_px,
                candidate_crs=reference_crs,
                target_bbox_wgs84=best_reg.bbox_wgs84,
                target_centroid_wgs84=best_reg.centroid_wgs84,
                target_bbox_px=best_reg.bbox_px,
                target_centroid_px=best_reg.centroid_px,
                target_crs=target_crs or reference_crs,
                min_bbox_iou_threshold=min_bbox_iou_threshold,
                max_centroid_distance_m=max_centroid_distance_m,
                matching_relationship=CorrespondenceRelationship.MATCHED,
            )
            return CandidateCorrespondenceResult(
                reference_candidate_id=ref_id,
                target_pair_id=target_pair_id,
                target_cdr_id=cdr_id,
                status=SpatialCorrespondenceStatus.GEOREFERENCED_BBOX,
                relationship=CorrespondenceRelationship.MATCHED,
                matched_region_id=best_rid,
                matched_region=best_reg,
                metric_iou=best_iou,
                centroid_distance_m=dist_m,
                spatial_correspondence=best_corr,
                candidate_scores=scores,
                resolution_notes=notes,
            )

        # Multiple regions meet min_bbox_iou_threshold: evaluate ambiguity margin
        second_rid, second_iou = qualifying_iou[1]
        iou_delta = best_iou - second_iou

        if iou_delta >= ambiguity_margin:
            # Clear margin tie-breaking justified by spatial geometry
            notes.append(
                f"Deterministic tie-break: {best_rid} (IoU={best_iou:.4f}) exceeds runner-up "
                f"{second_rid} (IoU={second_iou:.4f}) by margin={iou_delta:.4f} "
                f"(>= required {ambiguity_margin:.2f})."
            )
            dist_m = dist_per_region.get(best_rid)
            best_corr = evaluate_spatial_correspondence(
                candidate_bbox_wgs84=reference_region.bbox_wgs84,
                candidate_centroid_wgs84=reference_region.centroid_wgs84,
                candidate_bbox_px=reference_region.bbox_px,
                candidate_centroid_px=reference_region.centroid_px,
                candidate_crs=reference_crs,
                target_bbox_wgs84=best_reg.bbox_wgs84,
                target_centroid_wgs84=best_reg.centroid_wgs84,
                target_bbox_px=best_reg.bbox_px,
                target_centroid_px=best_reg.centroid_px,
                target_crs=target_crs or reference_crs,
                min_bbox_iou_threshold=min_bbox_iou_threshold,
                max_centroid_distance_m=max_centroid_distance_m,
                matching_relationship=CorrespondenceRelationship.MATCHED,
            )
            return CandidateCorrespondenceResult(
                reference_candidate_id=ref_id,
                target_pair_id=target_pair_id,
                target_cdr_id=cdr_id,
                status=SpatialCorrespondenceStatus.GEOREFERENCED_BBOX,
                relationship=CorrespondenceRelationship.MATCHED,
                matched_region_id=best_rid,
                matched_region=best_reg,
                metric_iou=best_iou,
                centroid_distance_m=dist_m,
                spatial_correspondence=best_corr,
                candidate_scores=scores,
                resolution_notes=notes,
            )
        else:
            # Ambiguous spatial correspondence: do not arbitrarily pick one
            notes.append(
                f"Ambiguous spatial correspondence: {best_rid} (IoU={best_iou:.4f}) and "
                f"{second_rid} (IoU={second_iou:.4f}) differ by only {iou_delta:.4f} "
                f"(< ambiguity margin {ambiguity_margin:.2f}). No candidate selected."
            )
            ambig_corr = SpatialCorrespondence(
                status=SpatialCorrespondenceStatus.GEOREFERENCED_BBOX,
                relationship=CorrespondenceRelationship.AMBIGUOUS,
                is_spatially_compatible=False,
                iou_wgs84=best_iou,
                centroid_distance_m=dist_per_region.get(best_rid),
                centroid_distance_px=None,
                crs_match=True if reference_crs and target_crs and reference_crs == target_crs else False,
                gsd_match=True,
            )
            return CandidateCorrespondenceResult(
                reference_candidate_id=ref_id,
                target_pair_id=target_pair_id,
                target_cdr_id=cdr_id,
                status=SpatialCorrespondenceStatus.GEOREFERENCED_BBOX,
                relationship=CorrespondenceRelationship.AMBIGUOUS,
                matched_region_id=None,
                matched_region=None,
                metric_iou=best_iou,
                centroid_distance_m=dist_per_region.get(best_rid),
                spatial_correspondence=ambig_corr,
                candidate_scores=scores,
                resolution_notes=notes,
            )

    # 5. Bbox IoU below threshold for all regions; check centroid geodesic distance
    qualifying_dist = [
        (rid, d) for rid, d in dist_per_region.items() if d <= max_centroid_distance_m
    ]

    if qualifying_dist:
        # Sort ascending by distance, tie-break by region_id
        qualifying_dist.sort(key=lambda item: (item[1], item[0]))
        best_rid, best_dist = qualifying_dist[0]
        best_reg = region_map[best_rid]

        if len(qualifying_dist) == 1:
            notes.append(
                f"Spatial correspondence matched via centroid geodesic distance: {best_rid} at "
                f"{best_dist:.1f}m (<= max {max_centroid_distance_m:.1f}m)."
            )
            best_corr = evaluate_spatial_correspondence(
                candidate_bbox_wgs84=reference_region.bbox_wgs84,
                candidate_centroid_wgs84=reference_region.centroid_wgs84,
                candidate_bbox_px=reference_region.bbox_px,
                candidate_centroid_px=reference_region.centroid_px,
                candidate_crs=reference_crs,
                target_bbox_wgs84=best_reg.bbox_wgs84,
                target_centroid_wgs84=best_reg.centroid_wgs84,
                target_bbox_px=best_reg.bbox_px,
                target_centroid_px=best_reg.centroid_px,
                target_crs=target_crs or reference_crs,
                min_bbox_iou_threshold=min_bbox_iou_threshold,
                max_centroid_distance_m=max_centroid_distance_m,
                matching_relationship=CorrespondenceRelationship.MATCHED,
            )
            return CandidateCorrespondenceResult(
                reference_candidate_id=ref_id,
                target_pair_id=target_pair_id,
                target_cdr_id=cdr_id,
                status=SpatialCorrespondenceStatus.GEOREFERENCED_CENTROID_ONLY,
                relationship=CorrespondenceRelationship.MATCHED,
                matched_region_id=best_rid,
                matched_region=best_reg,
                metric_iou=iou_per_region.get(best_rid, 0.0),
                centroid_distance_m=best_dist,
                spatial_correspondence=best_corr,
                candidate_scores=scores,
                resolution_notes=notes,
            )

        second_rid, second_dist = qualifying_dist[1]
        dist_delta = second_dist - best_dist

        if dist_delta >= 15.0:  # 15 meter centroid margin
            notes.append(
                f"Deterministic centroid tie-break: {best_rid} ({best_dist:.1f}m) closer than "
                f"{second_rid} ({second_dist:.1f}m) by delta={dist_delta:.1f}m."
            )
            best_corr = evaluate_spatial_correspondence(
                candidate_bbox_wgs84=reference_region.bbox_wgs84,
                candidate_centroid_wgs84=reference_region.centroid_wgs84,
                candidate_bbox_px=reference_region.bbox_px,
                candidate_centroid_px=reference_region.centroid_px,
                candidate_crs=reference_crs,
                target_bbox_wgs84=best_reg.bbox_wgs84,
                target_centroid_wgs84=best_reg.centroid_wgs84,
                target_bbox_px=best_reg.bbox_px,
                target_centroid_px=best_reg.centroid_px,
                target_crs=target_crs or reference_crs,
                min_bbox_iou_threshold=min_bbox_iou_threshold,
                max_centroid_distance_m=max_centroid_distance_m,
                matching_relationship=CorrespondenceRelationship.MATCHED,
            )
            return CandidateCorrespondenceResult(
                reference_candidate_id=ref_id,
                target_pair_id=target_pair_id,
                target_cdr_id=cdr_id,
                status=SpatialCorrespondenceStatus.GEOREFERENCED_CENTROID_ONLY,
                relationship=CorrespondenceRelationship.MATCHED,
                matched_region_id=best_rid,
                matched_region=best_reg,
                metric_iou=iou_per_region.get(best_rid, 0.0),
                centroid_distance_m=best_dist,
                spatial_correspondence=best_corr,
                candidate_scores=scores,
                resolution_notes=notes,
            )
        else:
            notes.append(
                f"Ambiguous centroid correspondence: {best_rid} ({best_dist:.1f}m) and "
                f"{second_rid} ({second_dist:.1f}m) differ by only {dist_delta:.1f}m (< 15.0m margin)."
            )
            ambig_corr = SpatialCorrespondence(
                status=SpatialCorrespondenceStatus.GEOREFERENCED_CENTROID_ONLY,
                relationship=CorrespondenceRelationship.AMBIGUOUS,
                is_spatially_compatible=False,
                iou_wgs84=0.0,
                centroid_distance_m=best_dist,
                centroid_distance_px=None,
                crs_match=True if reference_crs and target_crs and reference_crs == target_crs else False,
                gsd_match=True,
            )
            return CandidateCorrespondenceResult(
                reference_candidate_id=ref_id,
                target_pair_id=target_pair_id,
                target_cdr_id=cdr_id,
                status=SpatialCorrespondenceStatus.GEOREFERENCED_CENTROID_ONLY,
                relationship=CorrespondenceRelationship.AMBIGUOUS,
                matched_region_id=None,
                matched_region=None,
                metric_iou=0.0,
                centroid_distance_m=best_dist,
                spatial_correspondence=ambig_corr,
                candidate_scores=scores,
                resolution_notes=notes,
            )

    # 6. No region has sufficient spatial correspondence (disjoint or beyond centroid threshold)
    max_observed_iou = max(iou_per_region.values()) if iou_per_region else 0.0
    min_observed_dist = min(dist_per_region.values()) if dist_per_region else None
    notes.append(
        f"No spatial correspondence: max IoU={max_observed_iou:.4f} (< threshold {min_bbox_iou_threshold:.2f}), "
        f"closest centroid={min_observed_dist if min_observed_dist is not None else 'N/A'}m (> {max_centroid_distance_m:.1f}m)."
    )
    disjoint_corr = SpatialCorrespondence(
        status=SpatialCorrespondenceStatus.DISJOINT,
        relationship=CorrespondenceRelationship.NONE,
        is_spatially_compatible=False,
        iou_wgs84=max_observed_iou,
        centroid_distance_m=min_observed_dist,
        centroid_distance_px=None,
        crs_match=True if reference_crs and target_crs and reference_crs == target_crs else False,
        gsd_match=True,
    )
    return CandidateCorrespondenceResult(
        reference_candidate_id=ref_id,
        target_pair_id=target_pair_id,
        target_cdr_id=cdr_id,
        status=SpatialCorrespondenceStatus.DISJOINT,
        relationship=CorrespondenceRelationship.NONE,
        matched_region_id=None,
        matched_region=None,
        metric_iou=max_observed_iou,
        centroid_distance_m=min_observed_dist,
        spatial_correspondence=disjoint_corr,
        candidate_scores=scores,
        resolution_notes=notes,
    )
