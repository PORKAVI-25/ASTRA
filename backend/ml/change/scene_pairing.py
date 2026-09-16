"""ASTRA Deterministic Scene & Tile Pairing Engine.

Provides exact 2D bounding-box spatial overlap analysis, chronological ordering,
compatibility evaluation, and deterministic pair generation for multi-temporal satellite imagery.
"""

from datetime import datetime
from typing import List, Optional, Tuple
from geospatial.contracts import GeoBoundingBox
from .types import (
    PairCompatibility,
    PairCompatibilityStatus,
    PairingConfig,
    ScenePair,
    SpatialOverlap,
    TemporalObservation,
)


def compute_spatial_overlap(
    box_a: GeoBoundingBox, box_b: GeoBoundingBox
) -> SpatialOverlap:
    """Computes exact 2D axis-aligned bounding box intersection and overlap ratios in WGS84 coordinates.

    Bounding Box Overlap Formula:
        int_min_lon = max(A.min_lon, B.min_lon)
        int_max_lon = min(A.max_lon, B.max_lon)
        int_min_lat = max(A.min_lat, B.min_lat)
        int_max_lat = min(A.max_lat, B.max_lat)

        Overlap occurs iff:
            int_min_lon < int_max_lon and int_min_lat < int_max_lat
    """
    area_a = max(0.0, box_a.max_lon - box_a.min_lon) * max(0.0, box_a.max_lat - box_a.min_lat)
    area_b = max(0.0, box_b.max_lon - box_b.min_lon) * max(0.0, box_b.max_lat - box_b.min_lat)

    int_min_lon = max(box_a.min_lon, box_b.min_lon)
    int_max_lon = min(box_a.max_lon, box_b.max_lon)
    int_min_lat = max(box_a.min_lat, box_b.min_lat)
    int_max_lat = min(box_a.max_lat, box_b.max_lat)

    is_overlapping = (int_min_lon < int_max_lon) and (int_min_lat < int_max_lat)

    if not is_overlapping or area_a <= 0.0 or area_b <= 0.0:
        return SpatialOverlap(
            intersection_bounds=None,
            intersection_area_deg2=0.0,
            earlier_area_deg2=max(area_a, 1e-12),
            later_area_deg2=max(area_b, 1e-12),
            overlap_ratio_earlier=0.0,
            overlap_ratio_later=0.0,
            overlap_ratio_iou=0.0,
            overlap_ratio_min=0.0,
            is_overlapping=False,
        )

    int_area = (int_max_lon - int_min_lon) * (int_max_lat - int_min_lat)
    union_area = area_a + area_b - int_area

    ratio_earlier = min(1.0, max(0.0, int_area / area_a)) if area_a > 0 else 0.0
    ratio_later = min(1.0, max(0.0, int_area / area_b)) if area_b > 0 else 0.0
    ratio_iou = min(1.0, max(0.0, int_area / union_area)) if union_area > 0 else 0.0
    min_area = min(area_a, area_b)
    ratio_min = min(1.0, max(0.0, int_area / min_area)) if min_area > 0 else 0.0

    int_bounds = GeoBoundingBox(
        min_lon=round(int_min_lon, 6),
        min_lat=round(int_min_lat, 6),
        max_lon=round(int_max_lon, 6),
        max_lat=round(int_max_lat, 6),
    )

    return SpatialOverlap(
        intersection_bounds=int_bounds,
        intersection_area_deg2=round(int_area, 8),
        earlier_area_deg2=round(area_a, 8),
        later_area_deg2=round(area_b, 8),
        overlap_ratio_earlier=round(ratio_earlier, 4),
        overlap_ratio_later=round(ratio_later, 4),
        overlap_ratio_iou=round(ratio_iou, 4),
        overlap_ratio_min=round(ratio_min, 4),
        is_overlapping=True,
    )


def create_deterministic_pair_id(
    obs_earlier: TemporalObservation,
    obs_later: TemporalObservation,
    method: str = "pair",
) -> str:
    """Generates a stable, reproducible pair ID based on observation identities.

    Never uses random UUIDs. Format:
        pair_{earlier_id}__{later_id}
    """
    id_earlier = obs_earlier.observation_id
    id_later = obs_later.observation_id
    return f"pair_{id_earlier}__{id_later}"


def evaluate_pair_compatibility(
    obs_earlier: TemporalObservation,
    obs_later: TemporalObservation,
    config: PairingConfig,
) -> Tuple[SpatialOverlap, PairCompatibility]:
    """Evaluates compatibility between two observations against pairing constraints."""
    overlap = compute_spatial_overlap(obs_earlier.bounds_wgs84, obs_later.bounds_wgs84)
    delta_sec = (obs_later.acquisition_time - obs_earlier.acquisition_time).total_seconds()

    reasons: List[str] = []
    is_cross_sensor = obs_earlier.sensor.lower() != obs_later.sensor.lower()
    is_cross_platform = obs_earlier.platform.lower() != obs_later.platform.lower()

    if is_cross_sensor:
        reasons.append(f"Cross-sensor observation: {obs_earlier.sensor} -> {obs_later.sensor}")
    if is_cross_platform:
        reasons.append(f"Cross-platform observation: {obs_earlier.platform} -> {obs_later.platform}")

    # 1. Check chronological order
    if delta_sec < 0:
        return overlap, PairCompatibility(
            is_compatible=False,
            status=PairCompatibilityStatus.INVALID_TEMPORAL_ORDER,
            reasons=[f"Later observation timestamp ({obs_later.acquisition_time.isoformat()}) is earlier than T1 ({obs_earlier.acquisition_time.isoformat()})"],
            is_cross_sensor=is_cross_sensor,
            is_cross_platform=is_cross_platform,
        )

    if delta_sec == 0:
        return overlap, PairCompatibility(
            is_compatible=False,
            status=PairCompatibilityStatus.IDENTICAL_TIMESTAMPS,
            reasons=["Observations have identical acquisition timestamps (zero temporal separation)"],
            is_cross_sensor=is_cross_sensor,
            is_cross_platform=is_cross_platform,
        )

    # 2. Check minimum temporal separation
    if delta_sec < config.min_temporal_separation_seconds:
        return overlap, PairCompatibility(
            is_compatible=False,
            status=PairCompatibilityStatus.BELOW_MIN_INTERVAL,
            reasons=[f"Separation ({delta_sec:.1f}s) is below configured minimum ({config.min_temporal_separation_seconds:.1f}s)"],
            is_cross_sensor=is_cross_sensor,
            is_cross_platform=is_cross_platform,
        )

    # 3. Check maximum temporal separation
    if config.max_temporal_separation_seconds is not None and delta_sec > config.max_temporal_separation_seconds:
        return overlap, PairCompatibility(
            is_compatible=False,
            status=PairCompatibilityStatus.EXCEEDS_MAX_INTERVAL,
            reasons=[f"Separation ({delta_sec:.1f}s) exceeds configured maximum ({config.max_temporal_separation_seconds:.1f}s)"],
            is_cross_sensor=is_cross_sensor,
            is_cross_platform=is_cross_platform,
        )

    # 4. Check spatial overlap threshold
    metric_map = {
        "iou": overlap.overlap_ratio_iou,
        "min": overlap.overlap_ratio_min,
        "earlier": overlap.overlap_ratio_earlier,
        "later": overlap.overlap_ratio_later,
    }
    selected_ratio = metric_map.get(config.overlap_metric.lower(), overlap.overlap_ratio_iou)

    if not overlap.is_overlapping or selected_ratio < config.min_spatial_overlap_ratio:
        return overlap, PairCompatibility(
            is_compatible=False,
            status=PairCompatibilityStatus.INSUFFICIENT_OVERLAP,
            reasons=[
                f"Spatial overlap ratio ({selected_ratio:.4f} via '{config.overlap_metric}') "
                f"is below required minimum ({config.min_spatial_overlap_ratio:.4f})"
            ],
            is_cross_sensor=is_cross_sensor,
            is_cross_platform=is_cross_platform,
        )

    # 5. Check sensor requirement
    if config.require_same_sensor and is_cross_sensor:
        return overlap, PairCompatibility(
            is_compatible=False,
            status=PairCompatibilityStatus.INCOMPATIBLE_SENSOR,
            reasons=[f"Strict same-sensor requirement failed: {obs_earlier.sensor} != {obs_later.sensor}"],
            is_cross_sensor=is_cross_sensor,
            is_cross_platform=is_cross_platform,
        )

    # 6. Check platform requirement
    if config.require_same_platform and is_cross_platform:
        return overlap, PairCompatibility(
            is_compatible=False,
            status=PairCompatibilityStatus.INCOMPATIBLE_PLATFORM,
            reasons=[f"Strict same-platform requirement failed: {obs_earlier.platform} != {obs_later.platform}"],
            is_cross_sensor=is_cross_sensor,
            is_cross_platform=is_cross_platform,
        )

    # All checks passed
    return overlap, PairCompatibility(
        is_compatible=True,
        status=PairCompatibilityStatus.COMPATIBLE,
        reasons=reasons if reasons else ["Observations are temporally and spatially compatible"],
        is_cross_sensor=is_cross_sensor,
        is_cross_platform=is_cross_platform,
    )


def create_scene_pair(
    obs_earlier: TemporalObservation,
    obs_later: TemporalObservation,
    config: Optional[PairingConfig] = None,
    pairing_method: str = "exact_tile_identity",
) -> ScenePair:
    """Creates a deterministic ScenePair record for two observations."""
    cfg = config or PairingConfig()
    overlap, compat = evaluate_pair_compatibility(obs_earlier, obs_later, cfg)

    delta_sec = (obs_later.acquisition_time - obs_earlier.acquisition_time).total_seconds()
    pair_id = create_deterministic_pair_id(obs_earlier, obs_later, pairing_method)

    return ScenePair(
        pair_id=pair_id,
        earlier_observation=obs_earlier,
        later_observation=obs_later,
        temporal_separation_seconds=round(max(0.0, delta_sec), 2),
        temporal_separation_days=round(max(0.0, delta_sec) / 86400.0, 4),
        spatial_overlap=overlap,
        pairing_method=pairing_method,
        compatibility=compat,
        provenance_reference=obs_later.provenance_reference or obs_earlier.provenance_reference,
    )


def pair_observations(
    observations: List[TemporalObservation],
    config: Optional[PairingConfig] = None,
    mode: str = "adjacent",
) -> List[ScenePair]:
    """Deterministically pairs a list of observations.

    Args:
        observations: List of observations to pair.
        config: Pairing constraints and thresholds.
        mode: Pairing strategy:
            - 'adjacent': Pairs chronological neighbors (T1-T2, T2-T3, ...).
            - 'all_pairwise': Evaluates all combinations (T1-T2, T1-T3, T2-T3, ...).

    Returns:
        List of deterministically ordered ScenePair instances.
    """
    cfg = config or PairingConfig()
    if len(observations) < 2:
        return []

    # Sort strictly chronologically, tie-break by observation_id
    sorted_obs = sorted(observations, key=lambda o: (o.acquisition_time, o.observation_id))
    pairs: List[ScenePair] = []

    if mode == "adjacent":
        for i in range(len(sorted_obs) - 1):
            pair = create_scene_pair(sorted_obs[i], sorted_obs[i + 1], cfg, pairing_method="adjacent_chronological")
            pairs.append(pair)
    elif mode == "all_pairwise":
        for i in range(len(sorted_obs)):
            for j in range(i + 1, len(sorted_obs)):
                pair = create_scene_pair(sorted_obs[i], sorted_obs[j], cfg, pairing_method="all_pairwise")
                pairs.append(pair)
    else:
        raise ValueError(f"Unknown pairing mode '{mode}'. Choose 'adjacent' or 'all_pairwise'.")

    # Deterministic sorting of resulting pairs by earlier time, later time, and pair_id
    return sorted(
        pairs,
        key=lambda p: (
            p.earlier_observation.acquisition_time,
            p.later_observation.acquisition_time,
            p.pair_id,
        ),
    )
