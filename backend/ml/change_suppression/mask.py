"""ASTRA Filtered Change Mask Generation (Phase M4D).

Serializes the tri-state suppression raster:
0 = background / suppressed
1 = retained (candidate continues downstream; NOT verified ground truth)
2 = flagged / insufficient evidence (requires analyst review)

Outputs standard GeoTIFF format preserving spatial georeferencing metadata.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import rasterio
from rasterio.transform import Affine

from backend.ml.change_detection.types import ChangeRegion
from backend.ml.change_suppression.types import RegionSuppression, SuppressionDecision


def generate_filtered_change_mask(
    regions_suppression: List[RegionSuppression],
    target_path: Union[str, Path],
    change_mask: Optional[np.ndarray] = None,
    change_regions: Optional[List[ChangeRegion]] = None,
    shape: Optional[Tuple[int, int]] = None,
    crs: Optional[Any] = None,
    transform: Optional[Affine] = None,
) -> Path:
    """Renders and serializes the tri-state filtered change mask as a GeoTIFF.

    Args:
        regions_suppression: Evaluated suppression decisions per region.
        target_path: Destination path for filtered_change_mask.tif.
        change_mask: Optional raw binary change mask from M4B (values 0 and 255 or 0 and 1).
        change_regions: Optional list of M4B ChangeRegions with bounding boxes.
        shape: Optional (height, width) if change_mask is not provided.
        crs: Coordinate Reference System (e.g. EPSG:32643).
        transform: Affine geotransform matrix.

    Returns:
        Path to serialized filtered_change_mask.tif.
    """
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    # Determine canvas dimensions
    if change_mask is not None:
        height, width = change_mask.shape[:2]
    elif shape is not None:
        height, width = shape
    elif change_regions and len(change_regions) > 0:
        max_r = max(reg.bbox_px[2] for reg in change_regions)
        max_c = max(reg.bbox_px[3] for reg in change_regions)
        height = max(100, max_r + 10)
        width = max(100, max_c + 10)
    else:
        height, width = 100, 100

    # Initialize tri-state canvas: 0 = background
    filtered_mask = np.zeros((height, width), dtype=np.uint8)

    # Map region_id -> SuppressionDecision
    dec_map: Dict[str, SuppressionDecision] = {r.region_id: r.decision for r in regions_suppression}

    # If ChangeRegions with bounding boxes are available, paint each region
    if change_regions and len(change_regions) > 0:
        for reg in change_regions:
            decision = dec_map.get(reg.region_id, SuppressionDecision.RETAINED)
            if decision == SuppressionDecision.SUPPRESSED:
                val = 0
            elif decision == SuppressionDecision.RETAINED:
                val = 1
            else:  # FLAGGED or INSUFFICIENT_EVIDENCE
                val = 2

            r_min, c_min, r_max, c_max = reg.bbox_px
            # Clip bounds
            r_min, r_max = max(0, r_min), min(height, r_max)
            c_min, c_max = max(0, c_min), min(width, c_max)

            if change_mask is not None:
                # Mask within bbox where change_mask is non-zero
                sub_mask = (change_mask[r_min:r_max, c_min:c_max] > 0)
                filtered_mask[r_min:r_max, c_min:c_max][sub_mask] = val
            else:
                filtered_mask[r_min:r_max, c_min:c_max] = val
    elif change_mask is not None:
        # If no discrete region bounding boxes provided, treat all changed pixels by primary decision
        # Default: if any suppressed, paint retained
        primary_val = 1
        if len(regions_suppression) == 1:
            dec = regions_suppression[0].decision
            if dec == SuppressionDecision.SUPPRESSED:
                primary_val = 0
            elif dec == SuppressionDecision.RETAINED:
                primary_val = 1
            else:
                primary_val = 2
        filtered_mask[change_mask > 0] = primary_val

    # Validate output values
    unique_vals = set(np.unique(filtered_mask))
    valid_vals = {0, 1, 2}
    if not unique_vals.issubset(valid_vals):
        raise ValueError(f"Filtered change mask contains invalid pixel values: {unique_vals - valid_vals}")

    # Write GeoTIFF
    out_transform = transform or Affine.identity()
    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": 1,
        "dtype": rasterio.uint8,
        "crs": crs,
        "transform": out_transform,
        "nodata": None,
    }

    with rasterio.open(target, "w", **profile) as dst:
        dst.write(filtered_mask, 1)

    return target
