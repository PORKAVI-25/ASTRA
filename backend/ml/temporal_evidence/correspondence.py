"""ASTRA Phase M4E: Spatial Correspondence & Metric-Projected Bbox IoU.

Provides deterministic geometric and topological correspondence evaluation
between candidate change regions and observation footprints/regions.
Guarantees metric area computation without degree-space distortion.
"""

import math
from typing import Any, Dict, List, Optional, Tuple

from geospatial.contracts import GeoBoundingBox
from backend.ml.change_detection.types import ChangeRegion
from backend.ml.temporal_evidence.types import (
    CorrespondenceRelationship,
    SpatialCorrespondence,
    SpatialCorrespondenceStatus,
)

try:
    from rasterio.warp import transform_bounds
    HAS_RASTERIO_WARP = True
except ImportError:
    HAS_RASTERIO_WARP = False


def compute_geodesic_distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Calculates great-circle distance between two points in meters using Haversine formula."""
    r_earth = 6371000.0  # Mean radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(r_earth * c, 2)


def project_wgs84_bbox_to_metric(
    bbox: GeoBoundingBox, target_crs: Optional[str] = None
) -> Tuple[float, float, float, float]:
    """Reprojects a WGS84 axis-aligned GeoBoundingBox into a local metric projection (x_min, y_min, x_max, y_max).

    Guarantees that area calculations occur strictly in square meters, never in angular degree space.
    """
    center_lon = (bbox.min_lon + bbox.max_lon) / 2.0
    center_lat = (bbox.min_lat + bbox.max_lat) / 2.0

    # Determine UTM zone EPSG if target_crs is not explicitly provided
    if target_crs and target_crs.upper().startswith("EPSG:") and target_crs.upper() != "EPSG:4326":
        epsg_code = target_crs.upper()
    else:
        zone = int((center_lon + 180.0) / 6.0) + 1
        epsg_code = f"EPSG:{32600 + zone}" if center_lat >= 0 else f"EPSG:{32700 + zone}"

    if HAS_RASTERIO_WARP:
        try:
            min_x, min_y, max_x, max_y = transform_bounds(
                "EPSG:4326", epsg_code, bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat
            )
            return min_x, min_y, max_x, max_y
        except Exception:
            pass  # Fallback to local planar projection below

    # Deterministic local planar metric projection centered on bbox centroid
    # 1 deg lat ~= 110540 m, 1 deg lon ~= 111320 * cos(lat) m
    lat_rad = math.radians(center_lat)
    m_per_deg_lat = 110540.0
    m_per_deg_lon = 111320.0 * max(0.01, math.cos(lat_rad))

    min_x = (bbox.min_lon - center_lon) * m_per_deg_lon
    max_x = (bbox.max_lon - center_lon) * m_per_deg_lon
    min_y = (bbox.min_lat - center_lat) * m_per_deg_lat
    max_y = (bbox.max_lat - center_lat) * m_per_deg_lat

    return min_x, min_y, max_x, max_y


def compute_metric_bbox_iou(
    box_a: GeoBoundingBox, box_b: GeoBoundingBox, target_crs: Optional[str] = None
) -> float:
    """Computes axis-aligned bounding-box Intersection-over-Union in metric coordinates (m^2).

    Retains the field concept 'iou_wgs84' while strictly computing areas in metric units.
    This remains BBOX IoU, not polygon IoU and not raster-mask IoU.
    """
    min_x_a, min_y_a, max_x_a, max_y_a = project_wgs84_bbox_to_metric(box_a, target_crs=target_crs)
    min_x_b, min_y_b, max_x_b, max_y_b = project_wgs84_bbox_to_metric(box_b, target_crs=target_crs)

    int_min_x = max(min_x_a, min_x_b)
    int_max_x = min(max_x_a, max_x_b)
    int_min_y = max(min_y_a, min_y_b)
    int_max_y = min(max_y_a, max_y_b)

    if int_min_x >= int_max_x or int_min_y >= int_max_y:
        return 0.0

    int_area = (int_max_x - int_min_x) * (int_max_y - int_min_y)
    area_a = max(1e-6, (max_x_a - min_x_a) * (max_y_a - min_y_a))
    area_b = max(1e-6, (max_x_b - min_x_b) * (max_y_b - min_y_b))
    union_area = area_a + area_b - int_area

    if union_area <= 0.0:
        return 0.0

    return round(min(1.0, max(0.0, int_area / union_area)), 4)


def verify_pixel_grid_compatibility(
    cand_crs: Optional[str],
    obs_crs: Optional[str],
    cand_gsd_m: Optional[float] = None,
    obs_gsd_m: Optional[float] = None,
    cand_transform: Optional[Tuple[float, ...]] = None,
    obs_transform: Optional[Tuple[float, ...]] = None,
) -> Tuple[bool, bool, bool]:
    """Strictly evaluates whether candidate and observation share an identical pixel grid.

    Requires:
    1. Exact CRS string equality
    2. GSD matching within 1.0%
    3. Grid transform alignment (origin and orientation)
    Returns: (is_grid_compatible, crs_match, gsd_match)
    """
    if not cand_crs or not obs_crs:
        return False, False, False

    crs_match = cand_crs.strip().upper() == obs_crs.strip().upper()

    gsd_match = True
    if cand_gsd_m is not None and obs_gsd_m is not None:
        denom = max(cand_gsd_m, obs_gsd_m)
        if denom > 0:
            gsd_match = (abs(cand_gsd_m - obs_gsd_m) / denom) <= 0.01
        else:
            gsd_match = False

    transform_match = True
    if cand_transform is not None and obs_transform is not None:
        if len(cand_transform) >= 6 and len(obs_transform) >= 6:
            # Check pixel size and origin alignment
            pixel_size_match = (
                abs(cand_transform[1] - obs_transform[1]) < 1e-4
                and abs(cand_transform[5] - obs_transform[5]) < 1e-4
            )
            origin_match = (
                abs(cand_transform[0] - obs_transform[0]) < 1e-2
                and abs(cand_transform[3] - obs_transform[3]) < 1e-2
            )
            transform_match = pixel_size_match and origin_match

    is_grid_compatible = crs_match and gsd_match and transform_match
    return is_grid_compatible, crs_match, gsd_match


def evaluate_spatial_correspondence(
    candidate_bbox_wgs84: Optional[GeoBoundingBox],
    candidate_centroid_wgs84: Optional[List[float]],
    candidate_bbox_px: Optional[List[int]],
    candidate_centroid_px: Optional[List[float]],
    candidate_crs: Optional[str],
    target_bbox_wgs84: Optional[GeoBoundingBox],
    target_centroid_wgs84: Optional[List[float]],
    target_bbox_px: Optional[List[int]],
    target_centroid_px: Optional[List[float]],
    target_crs: Optional[str],
    cand_gsd_m: Optional[float] = None,
    target_gsd_m: Optional[float] = None,
    cand_transform: Optional[Tuple[float, ...]] = None,
    target_transform: Optional[Tuple[float, ...]] = None,
    min_bbox_iou_threshold: float = 0.30,
    max_centroid_distance_m: float = 60.0,
    matching_relationship: CorrespondenceRelationship = CorrespondenceRelationship.MATCHED,
) -> SpatialCorrespondence:
    """Evaluates spatial correspondence between candidate region and a target observation or region.

    Decouples HOW geometry was compared (SpatialCorrespondenceStatus) from
    WHAT topological relationship was observed (CorrespondenceRelationship).
    """
    # 1. Evaluate pixel-grid compatibility
    is_grid_compat, crs_match, gsd_match = verify_pixel_grid_compatibility(
        cand_crs=candidate_crs,
        obs_crs=target_crs,
        cand_gsd_m=cand_gsd_m,
        obs_gsd_m=target_gsd_m,
        cand_transform=cand_transform,
        obs_transform=target_transform,
    )

    centroid_dist_px: Optional[float] = None
    if is_grid_compat and candidate_centroid_px and target_centroid_px:
        dr = candidate_centroid_px[0] - target_centroid_px[0]
        dc = candidate_centroid_px[1] - target_centroid_px[1]
        centroid_dist_px = round(math.sqrt(dr * dr + dc * dc), 2)

    # 2. Evaluate metric georeferenced correspondence
    iou_wgs84 = 0.0
    if candidate_bbox_wgs84 and target_bbox_wgs84:
        iou_wgs84 = compute_metric_bbox_iou(candidate_bbox_wgs84, target_bbox_wgs84, target_crs=candidate_crs)

    centroid_dist_m: Optional[float] = None
    if candidate_centroid_wgs84 and target_centroid_wgs84:
        centroid_dist_m = compute_geodesic_distance_m(
            candidate_centroid_wgs84[0],
            candidate_centroid_wgs84[1],
            target_centroid_wgs84[0],
            target_centroid_wgs84[1],
        )

    # 3. Determine SpatialCorrespondenceStatus (HOW geometry was compared)
    if is_grid_compat and centroid_dist_px is not None:
        status = SpatialCorrespondenceStatus.EXACT_PIXEL_GRID
    elif candidate_bbox_wgs84 is not None and target_bbox_wgs84 is not None:
        status = SpatialCorrespondenceStatus.GEOREFERENCED_BBOX
    elif centroid_dist_m is not None:
        status = SpatialCorrespondenceStatus.GEOREFERENCED_CENTROID_ONLY
    elif candidate_bbox_wgs84 is None and candidate_centroid_wgs84 is None:
        status = SpatialCorrespondenceStatus.INSUFFICIENT_METADATA
    else:
        status = SpatialCorrespondenceStatus.DISJOINT

    # 4. Check spatial compatibility
    is_spatially_compatible = False
    if iou_wgs84 >= min_bbox_iou_threshold:
        is_spatially_compatible = True
    elif centroid_dist_m is not None and centroid_dist_m <= max_centroid_distance_m:
        is_spatially_compatible = True

    if not is_spatially_compatible and (centroid_dist_m is not None and centroid_dist_m > max_centroid_distance_m * 2):
        status = SpatialCorrespondenceStatus.DISJOINT

    # 5. Handle topological relationship default
    rel = matching_relationship
    if not is_spatially_compatible and iou_wgs84 == 0.0:
        rel = CorrespondenceRelationship.NONE

    return SpatialCorrespondence(
        status=status,
        relationship=rel,
        is_spatially_compatible=is_spatially_compatible,
        iou_wgs84=iou_wgs84,
        centroid_distance_m=centroid_dist_m,
        centroid_distance_px=centroid_dist_px,
        crs_match=crs_match,
        gsd_match=gsd_match,
    )
