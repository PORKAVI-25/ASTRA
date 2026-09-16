"""ASTRA Baseline Pixel Difference Change Detector.

Implements a deterministic, reproducible, fully offline change detection engine
calculating normalized band-averaged radiometric difference, statistical and percentile thresholding,
pure-Python/NumPy connected component labeling, and spatial change region metrics.
"""

from collections import deque
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import numpy as np
from PIL import Image

try:
    import rasterio
    import rasterio.warp
    from rasterio.transform import xy as transform_xy
except ImportError:  # pragma: no cover
    rasterio = None

from backend.ml.change.types import TemporalObservation
from backend.ml.change_detection.base import ChangeDetector
from backend.ml.change_detection.types import (
    ChangeDetectionConfig,
    ChangeDetectionResult,
    ChangeMetrics,
    ChangeRegion,
    NormalizationMethod,
    ThresholdMethod,
)
from geospatial.contracts import GeoBoundingBox


class ASTRAPixelDifferenceDetector(ChangeDetector):
    """Deterministic, band-averaged pixel difference change detector."""

    algorithm_id: str = "pixel_difference"
    algorithm_version: str = "1.0.0"

    def _load_raster(
        self, raster_input: Union[str, Path, np.ndarray, Any]
    ) -> Tuple[np.ndarray, Optional[float], Optional[Any], Optional[Any]]:
        """Loads raster imagery and returns (bands, H, W) float array, nodata, transform, crs.

        Supports GeoTIFF via rasterio, standard image formats via Pillow, and direct NumPy arrays.
        """
        if isinstance(raster_input, (str, Path)):
            path = Path(raster_input)
            if not path.exists():
                raise FileNotFoundError(f"Raster file not found: {path}")

            if rasterio is not None:
                try:
                    with rasterio.open(path) as src:
                        data = src.read().astype(np.float32)
                        nodata = src.nodata
                        transform = src.transform
                        crs = src.crs
                        return data, nodata, transform, crs
                except Exception:
                    # Fallback to PIL for non-georeferenced images
                    pass

            with Image.open(path) as img:
                arr = np.array(img).astype(np.float32)
                if arr.ndim == 2:
                    data = arr[np.newaxis, :, :]
                elif arr.ndim == 3:
                    # PIL (H, W, C) -> (C, H, W)
                    data = np.transpose(arr, (2, 0, 1))
                else:
                    raise ValueError(f"Unsupported image array dimensions: {arr.shape}")
                return data, None, None, None

        if isinstance(raster_input, np.ndarray):
            arr = raster_input.astype(np.float32)
            if arr.ndim == 2:
                data = arr[np.newaxis, :, :]
            elif arr.ndim == 3:
                # If shape is (H, W, C) where C <= 16 and H > 16, transpose to (C, H, W)
                if arr.shape[2] <= 16 and arr.shape[0] > 16:
                    data = np.transpose(arr, (2, 0, 1))
                else:
                    data = arr
            else:
                raise ValueError(f"NumPy array must be 2D or 3D, got ndim={arr.ndim}")
            return data, None, None, None

        raise TypeError(f"Unsupported raster input type: {type(raster_input)}")

    def _normalize_band(
        self,
        band: np.ndarray,
        valid_mask: np.ndarray,
        method: NormalizationMethod,
        p_low: float = 2.0,
        p_high: float = 98.0,
    ) -> np.ndarray:
        """Normalizes a single 2D raster band to [0.0, 1.0] over valid pixels."""
        norm = np.zeros_like(band, dtype=np.float32)
        valid_vals = band[valid_mask]

        if valid_vals.size == 0:
            return norm

        if method == NormalizationMethod.ROBUST_PERCENTILE:
            low_val = float(np.percentile(valid_vals, p_low))
            high_val = float(np.percentile(valid_vals, p_high))
            if high_val > low_val:
                norm[valid_mask] = np.clip((valid_vals - low_val) / (high_val - low_val), 0.0, 1.0)
            else:
                norm[valid_mask] = 0.0
        elif method == NormalizationMethod.MIN_MAX:
            min_val = float(np.min(valid_vals))
            max_val = float(np.max(valid_vals))
            if max_val > min_val:
                norm[valid_mask] = (valid_vals - min_val) / (max_val - min_val)
            else:
                norm[valid_mask] = 0.0
        elif method == NormalizationMethod.NONE:
            norm[valid_mask] = np.clip(valid_vals, 0.0, 1.0)

        return norm

    def _connected_components(
        self, binary_mask: np.ndarray, connectivity: int = 8, min_area: int = 20
    ) -> Tuple[np.ndarray, List[List[Tuple[int, int]]]]:
        """Extracts connected components and filters by minimum area using pure-Python BFS.

        Returns:
            Tuple of:
                - filtered_mask: uint8 array with 255 for retained components, 0 elsewhere.
                - components: list of lists containing (row, col) pixel coordinates of retained components.
        """
        h, w = binary_mask.shape
        visited = np.zeros((h, w), dtype=bool)
        filtered_mask = np.zeros((h, w), dtype=np.uint8)
        retained_components: List[List[Tuple[int, int]]] = []

        if connectivity == 4:
            neighbors = ((-1, 0), (1, 0), (0, -1), (0, 1))
        else:
            neighbors = (
                (-1, -1), (-1, 0), (-1, 1),
                (0, -1),           (0, 1),
                (1, -1),  (1, 0),  (1, 1),
            )

        # Iterate over changed pixels
        changed_rows, changed_cols = np.where(binary_mask)
        for start_r, start_c in zip(changed_rows, changed_cols):
            if visited[start_r, start_c]:
                continue

            # BFS to gather component
            queue = deque([(start_r, start_c)])
            visited[start_r, start_c] = True
            component: List[Tuple[int, int]] = []

            while queue:
                curr_r, curr_c = queue.popleft()
                component.append((curr_r, curr_c))

                for dr, dc in neighbors:
                    nr, nc = curr_r + dr, curr_c + dc
                    if 0 <= nr < h and 0 <= nc < w:
                        if binary_mask[nr, nc] and not visited[nr, nc]:
                            visited[nr, nc] = True
                            queue.append((nr, nc))

            if len(component) >= min_area:
                retained_components.append(component)
                for r, c in component:
                    filtered_mask[r, c] = 255

        # Sort retained components deterministically: descending by area, then ascending by min_row, min_col
        retained_components.sort(
            key=lambda comp: (-len(comp), min(r for r, _ in comp), min(c for _, c in comp))
        )

        return filtered_mask, retained_components

    def _pixel_to_wgs84(
        self,
        row: float,
        col: float,
        h: int,
        w: int,
        transform: Optional[Any] = None,
        crs: Optional[Any] = None,
        bounds_wgs84: Optional[GeoBoundingBox] = None,
        offset: str = "center",
    ) -> Optional[Tuple[float, float]]:
        """Converts pixel coordinate (row, col) to WGS84 [lon, lat]."""
        if transform is not None and crs is not None and rasterio is not None:
            try:
                x, y = transform_xy(transform, row, col, offset=offset)
                if hasattr(crs, "to_epsg") and crs.to_epsg() == 4326:
                    return float(x), float(y)
                if crs == "EPSG:4326" or str(crs).upper() == "EPSG:4326":
                    return float(x), float(y)
                # Warp to EPSG:4326
                xs, ys = rasterio.warp.transform(crs, "EPSG:4326", [x], [y])
                return float(xs[0]), float(ys[0])
            except Exception:
                pass

        if bounds_wgs84 is not None:
            # Linear interpolation across observation bounds
            if offset == "ul":
                frac_x = col / float(w)
                frac_y = row / float(h)
            elif offset == "lr":
                frac_x = (col + 1.0) / float(w)
                frac_y = (row + 1.0) / float(h)
            else:  # "center"
                frac_x = (col + 0.5) / float(w)
                frac_y = (row + 0.5) / float(h)

            lon = bounds_wgs84.min_lon + frac_x * (bounds_wgs84.max_lon - bounds_wgs84.min_lon)
            lat = bounds_wgs84.max_lat - frac_y * (bounds_wgs84.max_lat - bounds_wgs84.min_lat)
            return float(lon), float(lat)

        return None

    def detect(
        self,
        earlier_raster: Union[str, Path, np.ndarray, Any],
        later_raster: Union[str, Path, np.ndarray, Any],
        earlier_obs: Optional[TemporalObservation] = None,
        later_obs: Optional[TemporalObservation] = None,
        config: Optional[ChangeDetectionConfig] = None,
        pair_id: Optional[str] = None,
    ) -> Tuple[ChangeDetectionResult, np.ndarray, np.ndarray]:
        """Executes pixel difference change detection and extracts discrete change regions."""
        if config is None:
            config = ChangeDetectionConfig()

        # 1. Load rasters
        earlier_arr, earlier_nodata, earlier_transform, earlier_crs = self._load_raster(earlier_raster)
        later_arr, later_nodata, later_transform, later_crs = self._load_raster(later_raster)

        # 2. Dimensional validation
        if earlier_arr.shape[1:] != later_arr.shape[1:]:
            raise ValueError(
                f"Spatial dimension mismatch: earlier has {earlier_arr.shape[1:]} (H, W), "
                f"later has {later_arr.shape[1:]} (H, W)"
            )

        # Band selection / alignment
        if config.bands is not None:
            for b in config.bands:
                if b < 0 or b >= earlier_arr.shape[0] or b >= later_arr.shape[0]:
                    raise ValueError(f"Requested band index {b} out of range for inputs")
            earlier_arr = earlier_arr[config.bands]
            later_arr = later_arr[config.bands]
        elif earlier_arr.shape[0] != later_arr.shape[0]:
            raise ValueError(
                f"Band count mismatch: earlier has {earlier_arr.shape[0]} bands, "
                f"later has {later_arr.shape[0]} bands"
            )

        num_bands, height, width = earlier_arr.shape
        total_pixels = height * width

        # 3. Nodata and invalid pixel isolation
        valid_mask = np.ones((height, width), dtype=bool)

        # NaN / Inf filtering
        valid_mask &= ~np.isnan(earlier_arr).any(axis=0)
        valid_mask &= ~np.isinf(earlier_arr).any(axis=0)
        valid_mask &= ~np.isnan(later_arr).any(axis=0)
        valid_mask &= ~np.isinf(later_arr).any(axis=0)

        # Explicit nodata filtering
        if config.quality_mask:
            if config.nodata_value is not None:
                valid_mask &= ~(earlier_arr == config.nodata_value).any(axis=0)
                valid_mask &= ~(later_arr == config.nodata_value).any(axis=0)
            if earlier_nodata is not None:
                valid_mask &= ~(earlier_arr == earlier_nodata).any(axis=0)
            if later_nodata is not None:
                valid_mask &= ~(later_arr == later_nodata).any(axis=0)

        valid_pixels = int(np.sum(valid_mask))
        invalid_pixels = total_pixels - valid_pixels

        # 4. Radiometric normalization & absolute difference
        diff_accum = np.zeros((height, width), dtype=np.float32)

        if valid_pixels > 0:
            for c in range(num_bands):
                norm_earlier = self._normalize_band(
                    earlier_arr[c],
                    valid_mask,
                    config.normalization_method,
                    config.percentile_lower,
                    config.percentile_upper,
                )
                norm_later = self._normalize_band(
                    later_arr[c],
                    valid_mask,
                    config.normalization_method,
                    config.percentile_lower,
                    config.percentile_upper,
                )
                diff_accum += np.abs(norm_later - norm_earlier)

            score_map = diff_accum / float(num_bands)
            score_map[~valid_mask] = 0.0
            score_map = np.clip(score_map, 0.0, 1.0)
        else:
            score_map = np.zeros((height, width), dtype=np.float32)

        # 5. Thresholding
        threshold_used = 0.0
        if valid_pixels > 0:
            valid_scores = score_map[valid_mask]
            max_valid_score = float(np.max(valid_scores)) if valid_scores.size > 0 else 0.0

            if max_valid_score == 0.0:
                # Zero change across all valid pixels
                threshold_used = 0.0
                raw_binary_mask = np.zeros((height, width), dtype=bool)
            else:
                if config.threshold_method == ThresholdMethod.FIXED:
                    threshold_used = float(config.fixed_threshold if config.fixed_threshold is not None else 0.2)
                elif config.threshold_method == ThresholdMethod.STATISTICAL:
                    mean_score = float(np.mean(valid_scores))
                    std_score = float(np.std(valid_scores))
                    if std_score == 0.0:
                        threshold_used = mean_score
                    else:
                        threshold_used = float(mean_score + config.threshold_std_multiplier * std_score)
                elif config.threshold_method == ThresholdMethod.PERCENTILE:
                    threshold_used = float(np.percentile(valid_scores, config.threshold_percentile))

                threshold_used = float(np.clip(threshold_used, 0.0, 1.0))
                # Only pixels with non-zero change meeting or exceeding threshold are considered changed
                raw_binary_mask = (score_map >= threshold_used) & (score_map > 0.0) & valid_mask
        else:
            raw_binary_mask = np.zeros((height, width), dtype=bool)

        # 6. Connected Component Labeling & Noise Filtering
        change_mask, components = self._connected_components(
            raw_binary_mask,
            connectivity=config.connectivity,
            min_area=config.minimum_region_area,
        )

        # 7. Extract Discrete Regions & Geo Coordinates
        bounds_ref = None
        if earlier_obs is not None:
            bounds_ref = earlier_obs.bounds_wgs84
        elif later_obs is not None:
            bounds_ref = later_obs.bounds_wgs84

        active_transform = earlier_transform or later_transform
        active_crs = earlier_crs or later_crs

        # Ground resolution estimation
        pixel_res_m = None
        if earlier_obs is not None and "spatial_resolution_m" in earlier_obs.metadata:
            pixel_res_m = float(earlier_obs.metadata["spatial_resolution_m"])
        elif later_obs is not None and "spatial_resolution_m" in later_obs.metadata:
            pixel_res_m = float(later_obs.metadata["spatial_resolution_m"])
        elif active_transform is not None:
            # If transform uses meters
            try:
                res_x = abs(float(active_transform.a))
                res_y = abs(float(active_transform.e))
                if res_x > 0.1:  # reasonable metric resolution
                    pixel_res_m = (res_x + res_y) / 2.0
            except Exception:
                pass

        regions: List[ChangeRegion] = []
        for idx, comp in enumerate(components, start=1):
            region_id = f"reg_{idx:04d}"
            px_count = len(comp)
            rows = [r for r, c in comp]
            cols = [c for r, c in comp]
            min_r, max_r = min(rows), max(rows)
            min_c, max_c = min(cols), max(cols)
            bbox_px = [min_r, min_c, max_r, max_c]

            centroid_r = float(np.mean(rows))
            centroid_c = float(np.mean(cols))
            centroid_px = [round(centroid_r, 2), round(centroid_c, 2)]

            comp_scores = score_map[rows, cols]
            mean_score = float(np.mean(comp_scores))
            max_score = float(np.max(comp_scores))

            # Geographic bbox and centroid
            bbox_wgs84 = None
            centroid_wgs84 = None
            geometry = None

            c_geo = self._pixel_to_wgs84(
                centroid_r, centroid_c, height, width, active_transform, active_crs, bounds_ref, offset="center"
            )
            if c_geo is not None:
                centroid_wgs84 = [round(c_geo[0], 6), round(c_geo[1], 6)]

            p_top_left = self._pixel_to_wgs84(
                min_r, min_c, height, width, active_transform, active_crs, bounds_ref, offset="ul"
            )
            p_bottom_right = self._pixel_to_wgs84(
                max_r, max_c, height, width, active_transform, active_crs, bounds_ref, offset="lr"
            )

            if p_top_left is not None and p_bottom_right is not None:
                min_lon = min(p_top_left[0], p_bottom_right[0])
                max_lon = max(p_top_left[0], p_bottom_right[0])
                min_lat = min(p_top_left[1], p_bottom_right[1])
                max_lat = max(p_top_left[1], p_bottom_right[1])
                bbox_wgs84 = GeoBoundingBox(
                    min_lon=round(min_lon, 6),
                    min_lat=round(min_lat, 6),
                    max_lon=round(max_lon, 6),
                    max_lat=round(max_lat, 6),
                )
                geometry = {
                    "type": "Polygon",
                    "coordinates": [[
                        [round(min_lon, 6), round(min_lat, 6)],
                        [round(max_lon, 6), round(min_lat, 6)],
                        [round(max_lon, 6), round(max_lat, 6)],
                        [round(min_lon, 6), round(max_lat, 6)],
                        [round(min_lon, 6), round(min_lat, 6)],
                    ]],
                }

            area_m2 = None
            if pixel_res_m is not None:
                area_m2 = round(px_count * (pixel_res_m ** 2), 2)

            regions.append(
                ChangeRegion(
                    region_id=region_id,
                    pixel_count=px_count,
                    area_px=px_count,
                    area_m2=area_m2,
                    bbox_px=bbox_px,
                    bbox_wgs84=bbox_wgs84,
                    centroid_px=centroid_px,
                    centroid_wgs84=centroid_wgs84,
                    mean_change_score=round(mean_score, 4),
                    max_change_score=round(max_score, 4),
                    geometry=geometry,
                )
            )

        # 8. Aggregate Metrics
        changed_pixels = int(np.sum(change_mask == 255))
        changed_fraction = float(changed_pixels / valid_pixels) if valid_pixels > 0 else 0.0

        if changed_pixels > 0:
            changed_scores = score_map[change_mask == 255]
            overall_mean_change = float(np.mean(changed_scores))
            overall_max_change = float(np.max(changed_scores))
        else:
            overall_mean_change = 0.0
            overall_max_change = 0.0

        total_changed_m2 = None
        if pixel_res_m is not None:
            total_changed_m2 = round(changed_pixels * (pixel_res_m ** 2), 2)

        metrics = ChangeMetrics(
            total_pixels=total_pixels,
            valid_pixels=valid_pixels,
            invalid_pixels=invalid_pixels,
            changed_pixels=changed_pixels,
            changed_fraction=round(changed_fraction, 4),
            number_of_regions=len(regions),
            changed_area_px=changed_pixels,
            changed_area_m2=total_changed_m2,
            mean_change_score=round(overall_mean_change, 4),
            max_change_score=round(overall_max_change, 4),
            threshold_used=round(threshold_used, 4),
            threshold_method=config.threshold_method.value,
        )

        # 9. Deterministic IDs
        earlier_ref = (
            earlier_obs.observation_id
            if earlier_obs
            else (str(earlier_raster) if isinstance(earlier_raster, (str, Path)) else "e_arr")
        )
        later_ref = (
            later_obs.observation_id
            if later_obs
            else (str(later_raster) if isinstance(later_raster, (str, Path)) else "l_arr")
        )
        seed_data = (
            f"{pair_id or 'ad_hoc'}:"
            f"{earlier_ref}:"
            f"{later_ref}:"
            f"{metrics.changed_pixels}:{metrics.threshold_used}:"
            f"{config.algorithm_id}:{config.algorithm_version}"
        )
        content_hash = hashlib.sha256(seed_data.encode("utf-8")).hexdigest()[:16]
        result_id = f"res_chg_{content_hash}"
        provenance_id = f"prov_chg_{content_hash}"

        result = ChangeDetectionResult(
            result_id=result_id,
            scene_pair_id=pair_id or (f"pair_{content_hash}"),
            algorithm_id=self.algorithm_id,
            algorithm_version=self.algorithm_version,
            config=config,
            metrics=metrics,
            regions=regions,
            mask_path=None,
            score_path=None,
            provenance_id=provenance_id,
            created_at=datetime.now(timezone.utc),
        )

        return result, score_map, change_mask
