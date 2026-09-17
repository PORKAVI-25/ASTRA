"""ASTRA Change Evidence Extractor (Phase M4C-A).

Implements deterministic, explainable feature and evidence extraction across
spatial morphology, geometry, temporal progression, spectral response,
and local neighborhood context.
"""

from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
from PIL import Image

try:
    import rasterio
except ImportError:  # pragma: no cover
    rasterio = None

from backend.ml.change.types import ScenePair, TemporalObservation
from backend.ml.change_classification.types import (
    ChangeEvidence,
    ChangeRegionFeatures,
    ContextEvidence,
    EvidenceConfig,
    EvidenceFeature,
    SpatialEvidence,
    SpectralEvidence,
    TemporalEvidence,
)
from backend.ml.change_detection.types import ChangeDetectionResult, ChangeRegion


def _load_raster_bands(
    raster_input: Union[str, Path, np.ndarray, Any]
) -> Tuple[np.ndarray, List[str], Dict[str, Any]]:
    """Loads imagery array as (C, H, W) float32, extracting band names and metadata."""
    if isinstance(raster_input, (str, Path)):
        path = Path(raster_input)
        if not path.exists():
            raise FileNotFoundError(f"Imagery file not found: {path}")

        if rasterio is not None:
            try:
                with rasterio.open(path) as src:
                    arr = src.read().astype(np.float32)
                    band_names = [f"Band_{i}" for i in range(1, arr.shape[0] + 1)]
                    if src.descriptions and any(src.descriptions):
                        band_names = [
                            desc if desc else f"Band_{i}"
                            for i, desc in enumerate(src.descriptions, start=1)
                        ]
                    meta = {"crs": str(src.crs), "nodata": src.nodata}
                    return arr, band_names, meta
            except Exception:
                pass

        with Image.open(path) as img:
            arr = np.array(img).astype(np.float32)
            if arr.ndim == 2:
                data = arr[np.newaxis, :, :]
                band_names = ["Band_1"]
            elif arr.ndim == 3:
                data = np.transpose(arr, (2, 0, 1))
                if data.shape[0] == 3:
                    band_names = ["Red", "Green", "Blue"]
                elif data.shape[0] == 4:
                    band_names = ["Red", "Green", "Blue", "Alpha"]
                else:
                    band_names = [f"Band_{i}" for i in range(1, data.shape[0] + 1)]
            else:
                raise ValueError(f"Unsupported image array dimensions: {arr.shape}")
            return data, band_names, {}

    if isinstance(raster_input, np.ndarray):
        arr = raster_input.astype(np.float32)
        if arr.ndim == 2:
            data = arr[np.newaxis, :, :]
            band_names = ["Band_1"]
        elif arr.ndim == 3:
            if arr.shape[2] <= 16 and arr.shape[0] > 16:
                data = np.transpose(arr, (2, 0, 1))
            else:
                data = arr
            band_names = [f"Band_{i}" for i in range(1, data.shape[0] + 1)]
        else:
            raise ValueError(f"NumPy array must be 2D or 3D, got ndim={arr.ndim}")
        return data, band_names, {}

    raise TypeError(f"Unsupported raster input type: {type(raster_input)}")


class ChangeEvidenceExtractor:
    """Extracts deterministic, explainable evidence and features for change regions."""

    def __init__(self, config: Optional[EvidenceConfig] = None):
        self.config = config or EvidenceConfig()

    def _extract_spatial_evidence(
        self,
        region: ChangeRegion,
        region_mask: np.ndarray,
        height: int,
        width: int,
        other_regions: List[ChangeRegion],
    ) -> Tuple[SpatialEvidence, Dict[str, EvidenceFeature]]:
        """Calculates geometric, morphological, and spatial features for a single change region."""
        features: Dict[str, EvidenceFeature] = {}
        reg_id = region.region_id

        # Basic dimensions
        min_r, min_c, max_r, max_c = region.bbox_px
        w_px = max_c - min_c + 1
        h_px = max_r - min_r + 1
        area_px = region.pixel_count
        aspect_ratio = max(float(w_px), float(h_px)) / max(1.0, min(float(w_px), float(h_px)))

        # Submask for region
        sub_mask = region_mask[min_r : max_r + 1, min_c : max_c + 1]

        # Perimeter calculation (count pixels in sub_mask with at least one 4-neighbor outside)
        sh, sw = sub_mask.shape
        perimeter_count = 0
        boundary_pixels: List[Tuple[int, int]] = []
        for r in range(sh):
            for c in range(sw):
                if sub_mask[r, c]:
                    is_boundary = False
                    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        nr, nc = r + dr, c + dc
                        if nr < 0 or nr >= sh or nc < 0 or nc >= sw or not sub_mask[nr, nc]:
                            is_boundary = True
                            break
                    if is_boundary:
                        perimeter_count += 1
                        boundary_pixels.append((r + min_r, c + min_c))

        perimeter_px = float(max(1, perimeter_count))

        # Compactness: 4 * pi * area / perimeter^2
        compactness = (4.0 * math.pi * float(area_px)) / (perimeter_px ** 2)
        compactness = min(1.0, max(0.0, compactness))

        # Rectangularity: area / (width * height)
        bbox_area = float(w_px * h_px)
        rectangularity = float(area_px) / max(1.0, bbox_area)
        rectangularity = min(1.0, max(0.0, rectangularity))

        # 2D Central Moments for Linearity proxy, Principal Axes, Orientation
        changed_coords = np.argwhere(sub_mask)  # relative (r, c)
        if len(changed_coords) > 1:
            mean_r = float(np.mean(changed_coords[:, 0]))
            mean_c = float(np.mean(changed_coords[:, 1]))
            # Cartesian coordinates: x is horizontal (col), y is vertical (row inverted, pointing North)
            x = changed_coords[:, 1] - mean_c
            y = -(changed_coords[:, 0] - mean_r)

            mu_xx = float(np.mean(x ** 2))
            mu_yy = float(np.mean(y ** 2))
            mu_xy = float(np.mean(x * y))

            delta = math.sqrt((mu_xx - mu_yy) ** 2 + 4.0 * (mu_xy ** 2))
            lambda1 = max(0.0, ((mu_xx + mu_yy) + delta) / 2.0)
            lambda2 = max(0.0, ((mu_xx + mu_yy) - delta) / 2.0)

            major_axis = 4.0 * math.sqrt(lambda1)
            minor_axis = 4.0 * math.sqrt(lambda2)
            axis_ratio = major_axis / max(1e-6, minor_axis)

            # Linearity score: (lambda1 - lambda2) / (lambda1 + lambda2)
            denom = lambda1 + lambda2
            linearity = (lambda1 - lambda2) / denom if denom > 1e-6 else 0.0
            linearity = min(1.0, max(0.0, linearity))

            # Orientation angle in degrees relative to horizontal axis [-90.0, 90.0]
            orientation = 0.5 * math.atan2(2.0 * mu_xy, mu_xx - mu_yy) * (180.0 / math.pi)
        else:
            major_axis = float(max(w_px, h_px))
            minor_axis = float(min(w_px, h_px))
            axis_ratio = 1.0
            linearity = 0.0
            orientation = 0.0

        elongation = axis_ratio
        component_density = rectangularity

        # Shape regularity: compare perimeter to circle of equivalent area
        circle_perimeter = 2.0 * math.sqrt(math.pi * float(area_px))
        shape_regularity = min(1.0, circle_perimeter / max(1e-6, perimeter_px))

        # Fragmentation proxy: perimeter / sqrt(area)
        fragmentation = perimeter_px / math.sqrt(float(area_px))

        # Neighboring regions within buffer
        buf = self.config.neighborhood_buffer_px
        neighbor_count = 0
        for other in other_regions:
            if other.region_id != reg_id:
                o_min_r, o_min_c, o_max_r, o_max_c = other.bbox_px
                # Check bounding box distance
                d_r = max(0, max(min_r - o_max_r, o_min_r - max_r))
                d_c = max(0, max(min_c - o_max_c, o_min_c - max_c))
                if max(d_r, d_c) <= buf:
                    neighbor_count += 1

        # Distance to scene boundary
        d_top = min_r
        d_bottom = height - 1 - max_r
        d_left = min_c
        d_right = width - 1 - max_c
        dist_to_boundary = float(min(d_top, d_bottom, d_left, d_right))

        spatial = SpatialEvidence(
            area_px=area_px,
            pixel_count=area_px,
            width_px=w_px,
            height_px=h_px,
            aspect_ratio=round(aspect_ratio, 4),
            perimeter_px=round(perimeter_px, 2),
            compactness=round(compactness, 4),
            rectangularity=round(rectangularity, 4),
            elongation=round(elongation, 4),
            major_axis_length=round(major_axis, 2),
            minor_axis_length=round(minor_axis, 2),
            axis_ratio=round(axis_ratio, 4),
            linearity_score=round(linearity, 4),
            orientation_degrees=round(orientation, 2),
            component_density=round(component_density, 4),
            shape_regularity=round(shape_regularity, 4),
            fragmentation=round(fragmentation, 4),
            neighboring_changed_regions_count=neighbor_count,
            centroid_wgs84=region.centroid_wgs84,
            bbox_wgs84=region.bbox_wgs84,
            area_m2=region.area_m2,
            distance_to_boundary_px=round(dist_to_boundary, 1),
        )

        # Build individual atomic features
        for f_name, val, unit, meth in [
            ("area_px", float(area_px), "px", "pixel_count"),
            ("width_px", float(w_px), "px", "bbox_width"),
            ("height_px", float(h_px), "px", "bbox_height"),
            ("aspect_ratio", aspect_ratio, None, "max_dim_over_min_dim"),
            ("perimeter_px", perimeter_px, "px", "contour_pixel_count"),
            ("compactness", compactness, None, "isoperimetric_quotient"),
            ("rectangularity", rectangularity, None, "area_over_bbox"),
            ("elongation", elongation, None, "principal_axis_ratio"),
            ("linearity_score", linearity, None, "moment_inertia_ratio"),
            ("orientation_degrees", orientation, "deg", "principal_moment_angle"),
            ("component_density", component_density, None, "pixel_density"),
            ("shape_regularity", shape_regularity, None, "circle_perimeter_ratio"),
            ("fragmentation", fragmentation, None, "perimeter_over_sqrt_area"),
        ]:
            feat_id = f"feat_{reg_id}_{f_name}"
            features[f_name] = EvidenceFeature(
                feature_id=feat_id,
                feature_name=f_name,
                value=round(val, 4),
                unit=unit,
                available=True,
                source="geometry" if "px" in f_name or "ratio" in f_name else "morphology",
                method=meth,
            )

        return spatial, features

    def _extract_spectral_evidence(
        self,
        reg_id: str,
        region_mask: np.ndarray,
        earlier_arr: Optional[np.ndarray],
        later_arr: Optional[np.ndarray],
        band_names: List[str],
        band_mapping: Optional[Dict[str, int]],
        metadata: Dict[str, Any],
    ) -> Tuple[SpectralEvidence, Dict[str, EvidenceFeature]]:
        """Calculates regional spectral statistics and physical indices if supported."""
        features: Dict[str, EvidenceFeature] = {}

        if earlier_arr is None or later_arr is None:
            spectral = SpectralEvidence(
                available=False,
                unavailability_reason="Imagery arrays not provided or could not be loaded",
                band_names=band_names,
            )
            return spectral, features

        # Pixel extraction
        coords = np.where(region_mask)
        if len(coords[0]) == 0:
            spectral = SpectralEvidence(
                available=False,
                unavailability_reason="Zero changed pixels inside region mask",
                band_names=band_names,
            )
            return spectral, features

        earlier_pixels = earlier_arr[:, coords[0], coords[1]]  # (C, N)
        later_pixels = later_arr[:, coords[0], coords[1]]

        # Exclude NaNs / Infs and optional nodata values
        valid_px_mask = (
            ~np.isnan(earlier_pixels).any(axis=0)
            & ~np.isinf(earlier_pixels).any(axis=0)
            & ~np.isnan(later_pixels).any(axis=0)
            & ~np.isinf(later_pixels).any(axis=0)
        )
        nodata_val = metadata.get("nodata")
        if nodata_val is not None:
            valid_px_mask &= ~(earlier_pixels == nodata_val).any(axis=0)
            valid_px_mask &= ~(later_pixels == nodata_val).any(axis=0)

        if not np.any(valid_px_mask):
            spectral = SpectralEvidence(
                available=False,
                unavailability_reason="All regional pixels are NaN, Inf, or nodata",
                band_names=band_names,
            )
            return spectral, features

        earlier_valid = earlier_pixels[:, valid_px_mask]
        later_valid = later_pixels[:, valid_px_mask]

        earlier_means: Dict[str, float] = {}
        later_means: Dict[str, float] = {}
        deltas: Dict[str, float] = {}
        abs_deltas: Dict[str, float] = {}

        for b_idx, b_name in enumerate(band_names[: earlier_valid.shape[0]]):
            e_m = float(np.mean(earlier_valid[b_idx]))
            l_m = float(np.mean(later_valid[b_idx]))
            d = l_m - e_m
            earlier_means[b_name] = round(e_m, 4)
            later_means[b_name] = round(l_m, 4)
            deltas[b_name] = round(d, 4)
            abs_deltas[b_name] = round(abs(d), 4)

        if band_mapping:
            for sem_name, idx in band_mapping.items():
                if idx < earlier_valid.shape[0]:
                    e_m = float(np.mean(earlier_valid[idx]))
                    l_m = float(np.mean(later_valid[idx]))
                    earlier_means[sem_name] = round(e_m, 4)
                    later_means[sem_name] = round(l_m, 4)
                    deltas[sem_name] = round(l_m - e_m, 4)
                    abs_deltas[sem_name] = round(abs(l_m - e_m), 4)

        for b_name, d in list(deltas.items()):
            # Atomic features per band
            f_key = f"delta_{b_name.lower()}"
            features[f_key] = EvidenceFeature(
                feature_id=f"feat_{reg_id}_{f_key}",
                feature_name=f_key,
                value=round(d, 4),
                available=True,
                source="spectral",
                method="mean_difference",
            )

        # Check explicit wavelength metadata
        has_wavelength_meta = bool(band_mapping is not None and len(band_mapping) > 0)
        ndvi_feat: Optional[EvidenceFeature] = None
        ndwi_feat: Optional[EvidenceFeature] = None
        water_criterion_feat: Optional[EvidenceFeature] = None
        veg_delta_feat: Optional[EvidenceFeature] = None

        # Physical Index: NDVI (requires explicitly identified NIR and Red)
        if band_mapping and "nir" in band_mapping and "red" in band_mapping:
            nir_idx = band_mapping["nir"]
            red_idx = band_mapping["red"]
            if nir_idx < earlier_valid.shape[0] and red_idx < earlier_valid.shape[0]:
                e_nir = earlier_valid[nir_idx]
                e_red = earlier_valid[red_idx]
                l_nir = later_valid[nir_idx]
                l_red = later_valid[red_idx]

                e_ndvi = (e_nir - e_red) / np.maximum(1e-6, e_nir + e_red)
                l_ndvi = (l_nir - l_red) / np.maximum(1e-6, l_nir + l_red)

                mean_l_ndvi = float(np.mean(l_ndvi))
                delta_ndvi = float(np.mean(l_ndvi - e_ndvi))

                ndvi_feat = EvidenceFeature(
                    feature_id=f"feat_{reg_id}_ndvi_mean",
                    feature_name="ndvi_mean",
                    value=round(mean_l_ndvi, 4),
                    unit="index_score",
                    available=True,
                    source="spectral",
                    method="(nir - red) / (nir + red)",
                    metadata={"earlier_ndvi_mean": round(float(np.mean(e_ndvi)), 4)},
                )
                veg_delta_feat = EvidenceFeature(
                    feature_id=f"feat_{reg_id}_vegetation_proxy_delta",
                    feature_name="vegetation_proxy_delta",
                    value=round(delta_ndvi, 4),
                    unit="index_delta",
                    available=True,
                    source="spectral",
                    method="delta_ndvi",
                )
        if ndvi_feat is None:
            ndvi_feat = EvidenceFeature(
                feature_id=f"feat_{reg_id}_ndvi_mean",
                feature_name="ndvi_mean",
                available=False,
                unavailability_reason="NIR and Red bands not explicitly identified in metadata or configuration",
                source="spectral",
            )
            veg_delta_feat = EvidenceFeature(
                feature_id=f"feat_{reg_id}_vegetation_proxy_delta",
                feature_name="vegetation_proxy_delta",
                available=False,
                unavailability_reason="Requires valid NDVI band mapping",
                source="spectral",
            )

        # Physical Index: NDWI (requires Green and NIR)
        if band_mapping and "green" in band_mapping and "nir" in band_mapping:
            green_idx = band_mapping["green"]
            nir_idx = band_mapping["nir"]
            if green_idx < earlier_valid.shape[0] and nir_idx < earlier_valid.shape[0]:
                e_green = earlier_valid[green_idx]
                e_nir = earlier_valid[nir_idx]
                l_green = later_valid[green_idx]
                l_nir = later_valid[nir_idx]

                l_ndwi = (l_green - l_nir) / np.maximum(1e-6, l_green + l_nir)
                mean_l_ndwi = float(np.mean(l_ndwi))

                ndwi_feat = EvidenceFeature(
                    feature_id=f"feat_{reg_id}_ndwi_mean",
                    feature_name="ndwi_mean",
                    value=round(mean_l_ndwi, 4),
                    unit="index_score",
                    available=True,
                    source="spectral",
                    method="(green - nir) / (green + nir)",
                )

                # Measurable water spectral criterion fraction
                thresh = self.config.water_criterion_threshold
                water_px_fraction = float(np.mean(l_ndwi > thresh))
                water_criterion_feat = EvidenceFeature(
                    feature_id=f"feat_{reg_id}_water_spectral_criterion_fraction",
                    feature_name="water_spectral_criterion_fraction",
                    value=round(water_px_fraction, 4),
                    unit="fraction",
                    available=True,
                    source="spectral",
                    method="fraction_ndwi_gt_threshold",
                    metadata={
                        "threshold": thresh,
                        "bands_used": ["green", "nir"],
                        "config_version": self.config.extractor_version,
                    },
                )
        if ndwi_feat is None:
            ndwi_feat = EvidenceFeature(
                feature_id=f"feat_{reg_id}_ndwi_mean",
                feature_name="ndwi_mean",
                available=False,
                unavailability_reason="Green and NIR bands not explicitly identified in metadata or configuration",
                source="spectral",
            )
            water_criterion_feat = EvidenceFeature(
                feature_id=f"feat_{reg_id}_water_spectral_criterion_fraction",
                feature_name="water_spectral_criterion_fraction",
                available=False,
                unavailability_reason="Requires Green and NIR bands for water-like spectral response criterion",
                source="spectral",
            )

        # Brightness delta (average visible delta)
        vis_deltas = [
            deltas[b]
            for b in band_names
            if any(term in b.lower() for term in ("red", "green", "blue", "band_1", "band_2", "band_3"))
            and b in deltas
        ]
        if vis_deltas:
            mean_vis_delta = float(np.mean(vis_deltas))
            brightness_feat = EvidenceFeature(
                feature_id=f"feat_{reg_id}_brightness_delta",
                feature_name="brightness_delta",
                value=round(mean_vis_delta, 4),
                available=True,
                source="spectral",
                method="mean_visible_band_delta",
            )
        else:
            brightness_feat = EvidenceFeature(
                feature_id=f"feat_{reg_id}_brightness_delta",
                feature_name="brightness_delta",
                value=round(float(np.mean(list(deltas.values()))), 4) if deltas else 0.0,
                available=True,
                source="spectral",
                method="mean_band_delta",
            )

        features["ndvi_mean"] = ndvi_feat
        features["ndwi_mean"] = ndwi_feat
        features["water_spectral_criterion_fraction"] = water_criterion_feat
        features["vegetation_proxy_delta"] = veg_delta_feat
        features["brightness_delta"] = brightness_feat

        spectral = SpectralEvidence(
            available=True,
            earlier_mean_per_band=earlier_means,
            later_mean_per_band=later_means,
            delta_per_band=deltas,
            abs_delta_per_band=abs_deltas,
            band_names=band_names,
            has_wavelength_metadata=has_wavelength_meta,
            ndvi_mean=ndvi_feat if ndvi_feat.available else None,
            ndwi_mean=ndwi_feat if ndwi_feat.available else None,
            water_spectral_criterion_fraction=water_criterion_feat if water_criterion_feat.available else None,
            vegetation_proxy_delta=veg_delta_feat if veg_delta_feat.available else None,
            brightness_delta=brightness_feat,
        )

        return spectral, features

    def _extract_context_evidence(
        self,
        reg_id: str,
        region: ChangeRegion,
        change_mask: np.ndarray,
        score_map: Optional[np.ndarray],
        earlier_arr: Optional[np.ndarray],
        later_arr: Optional[np.ndarray],
        band_names: List[str],
    ) -> Tuple[ContextEvidence, Dict[str, EvidenceFeature]]:
        """Calculates local neighborhood contrast and background statistics around the region."""
        features: Dict[str, EvidenceFeature] = {}
        h, w = change_mask.shape
        min_r, min_c, max_r, max_c = region.bbox_px
        buf = self.config.neighborhood_buffer_px

        # Buffer window
        r0 = max(0, min_r - buf)
        r1 = min(h, max_r + 1 + buf)
        c0 = max(0, min_c - buf)
        c1 = min(w, max_c + 1 + buf)

        # Background mask: within window, unchanged pixels (change_mask == 0)
        window_mask = np.zeros((h, w), dtype=bool)
        window_mask[r0:r1, c0:c1] = True
        bg_mask = window_mask & (change_mask == 0)

        # Exclude non-finite pixels in background if score_map or imagery is provided
        valid_bg_mask = bg_mask.copy()
        if score_map is not None:
            valid_bg_mask &= np.isfinite(score_map)
        if later_arr is not None:
            valid_bg_mask &= (
                ~np.isnan(later_arr).any(axis=0)
                & ~np.isinf(later_arr).any(axis=0)
            )

        valid_bg_count = int(np.sum(valid_bg_mask))
        if valid_bg_count < self.config.min_valid_context_pixels:
            ctx = ContextEvidence(
                available=False,
                unavailability_reason=(
                    f"Insufficient unchanged background pixels in {buf}px buffer "
                    f"({valid_bg_count} found, minimum {self.config.min_valid_context_pixels} required)"
                ),
                neighborhood_buffer_px=buf,
            )
            feat = EvidenceFeature(
                feature_id=f"feat_{reg_id}_region_to_background_contrast",
                feature_name="region_to_background_contrast",
                available=False,
                unavailability_reason=ctx.unavailability_reason,
                source="context",
            )
            features["region_to_background_contrast"] = feat
            return ctx, features

        surrounding_change = None
        contrast = None
        if score_map is not None:
            bg_scores = score_map[valid_bg_mask]
            surrounding_change = float(np.mean(bg_scores))
            contrast = abs(region.mean_change_score - surrounding_change)

            feat = EvidenceFeature(
                feature_id=f"feat_{reg_id}_region_to_background_contrast",
                feature_name="region_to_background_contrast",
                value=round(contrast, 4),
                available=True,
                source="context",
                method="abs(region_score - background_score)",
            )
            features["region_to_background_contrast"] = feat

        bg_means: Dict[str, float] = {}
        if later_arr is not None:
            bg_pixels = later_arr[:, valid_bg_mask]
            for b_idx, b_name in enumerate(band_names[: bg_pixels.shape[0]]):
                bg_means[b_name] = round(float(np.mean(bg_pixels[b_idx])), 4)

        ctx = ContextEvidence(
            available=True,
            neighborhood_buffer_px=buf,
            surrounding_mean_change=round(surrounding_change, 4) if surrounding_change is not None else None,
            region_to_background_contrast=round(contrast, 4) if contrast is not None else None,
            local_background_mean_per_band=bg_means,
        )

        return ctx, features

    def extract(
        self,
        scene_pair: ScenePair,
        change_result: ChangeDetectionResult,
        earlier_image: Optional[Union[str, Path, np.ndarray]] = None,
        later_image: Optional[Union[str, Path, np.ndarray]] = None,
        score_map: Optional[np.ndarray] = None,
        change_mask: Optional[np.ndarray] = None,
        config: Optional[EvidenceConfig] = None,
    ) -> ChangeEvidence:
        """Executes full evidence extraction across all regions and evidence families."""
        if config is not None:
            self.config = config

        # 1. Temporal Evidence
        t_earlier = scene_pair.earlier_observation.acquisition_time
        t_later = scene_pair.later_observation.acquisition_time
        sec_delta = scene_pair.temporal_separation_seconds
        days_delta = scene_pair.temporal_separation_days
        hours_delta = sec_delta / 3600.0

        temporal = TemporalEvidence(
            earlier_acquisition_time=t_earlier,
            later_acquisition_time=t_later,
            temporal_separation_seconds=sec_delta,
            temporal_separation_days=days_delta,
            temporal_separation_hours=round(hours_delta, 2),
            earlier_scene_id=scene_pair.earlier_observation.scene_id,
            later_scene_id=scene_pair.later_observation.scene_id,
            earlier_tile_id=scene_pair.earlier_observation.tile_id,
            later_tile_id=scene_pair.later_observation.tile_id,
            earlier_sensor=scene_pair.earlier_observation.sensor,
            later_sensor=scene_pair.later_observation.sensor,
            is_cross_sensor=scene_pair.compatibility.is_cross_sensor,
        )

        # 2. Load Imagery and Masks
        earlier_arr = None
        later_arr = None
        band_names: List[str] = []
        meta: Dict[str, Any] = {}

        if earlier_image is not None:
            earlier_arr, band_names, meta = _load_raster_bands(earlier_image)
        elif scene_pair.earlier_observation.file_path:
            p = Path(scene_pair.earlier_observation.file_path)
            if p.exists():
                earlier_arr, band_names, meta = _load_raster_bands(p)

        if later_image is not None:
            later_arr, _, _ = _load_raster_bands(later_image)
        elif scene_pair.later_observation.file_path:
            p = Path(scene_pair.later_observation.file_path)
            if p.exists():
                later_arr, _, _ = _load_raster_bands(p)

        # Fallback mask & score map loading from change_result
        if change_mask is None and change_result.mask_path:
            mp = Path(change_result.mask_path)
            if mp.exists():
                with Image.open(mp) as img:
                    change_mask = np.array(img)

        if score_map is None and change_result.score_path:
            sp = Path(change_result.score_path)
            if sp.exists():
                score_map = np.load(sp)

        # If mask is still None, construct from dimensions
        if change_mask is None:
            if earlier_arr is not None:
                change_mask = np.zeros((earlier_arr.shape[1], earlier_arr.shape[2]), dtype=np.uint8)
            else:
                change_mask = np.zeros((512, 512), dtype=np.uint8)

        height, width = change_mask.shape

        # Band mapping discovery from config or observation metadata
        band_mapping = self.config.band_mapping
        if band_mapping is None and "band_mapping" in scene_pair.earlier_observation.metadata:
            band_mapping = scene_pair.earlier_observation.metadata["band_mapping"]

        # 3. Extract per-region evidence
        region_features_list: List[ChangeRegionFeatures] = []

        for region in change_result.regions:
            reg_id = region.region_id
            min_r, min_c, max_r, max_c = region.bbox_px

            # Isolate pixels belonging to this specific region
            region_mask = np.zeros((height, width), dtype=bool)
            sub_chg = change_mask[min_r : max_r + 1, min_c : max_c + 1] > 0
            if int(np.sum(sub_chg)) == region.pixel_count:
                region_mask[min_r : max_r + 1, min_c : max_c + 1] = sub_chg
            else:
                # Disambiguate overlapping bounding boxes by finding component matching region centroid
                sub_h, sub_w = sub_chg.shape
                c_row = region.centroid_px[0] - min_r
                c_col = region.centroid_px[1] - min_c
                visited = np.zeros((sub_h, sub_w), dtype=bool)
                best_comp = []
                best_dist = float("inf")

                for r in range(sub_h):
                    for c in range(sub_w):
                        if sub_chg[r, c] and not visited[r, c]:
                            comp = []
                            queue = [(r, c)]
                            visited[r, c] = True
                            while queue:
                                curr_r, curr_c = queue.pop()
                                comp.append((curr_r, curr_c))
                                for dr, dc in ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)):
                                    nr, nc = curr_r + dr, curr_c + dc
                                    if 0 <= nr < sub_h and 0 <= nc < sub_w and sub_chg[nr, nc] and not visited[nr, nc]:
                                        visited[nr, nc] = True
                                        queue.append((nr, nc))

                            comp_mean_r = sum(p[0] for p in comp) / len(comp)
                            comp_mean_c = sum(p[1] for p in comp) / len(comp)
                            dist = (comp_mean_r - c_row) ** 2 + (comp_mean_c - c_col) ** 2
                            size_diff = abs(len(comp) - region.pixel_count)
                            total_cost = dist + size_diff * 0.1
                            if total_cost < best_dist:
                                best_dist = total_cost
                                best_comp = comp

                if best_comp:
                    for r, c in best_comp:
                        region_mask[min_r + r, min_c + c] = True
                else:
                    region_mask[min_r : max_r + 1, min_c : max_c + 1] = sub_chg

            # Spatial evidence
            spatial, s_feats = self._extract_spatial_evidence(
                region, region_mask, height, width, change_result.regions
            )

            # Spectral evidence
            spectral, spec_feats = self._extract_spectral_evidence(
                reg_id, region_mask, earlier_arr, later_arr, band_names, band_mapping, meta
            )

            # Context evidence
            context, ctx_feats = self._extract_context_evidence(
                reg_id, region, change_mask, score_map, earlier_arr, later_arr, band_names
            )

            # Change score magnitude metrics
            c_scores = {}
            if score_map is not None and np.any(region_mask):
                reg_scores = score_map[region_mask]
                c_scores = {
                    "mean_change_score": round(float(np.mean(reg_scores)), 4),
                    "max_change_score": round(float(np.max(reg_scores)), 4),
                    "score_std": round(float(np.std(reg_scores)), 4),
                    "changed_fraction": round(float(region.pixel_count / max(1, change_result.metrics.valid_pixels)), 4),
                }
            else:
                c_scores = {
                    "mean_change_score": region.mean_change_score,
                    "max_change_score": region.max_change_score,
                    "score_std": 0.0,
                    "changed_fraction": 0.0,
                }

            # Merge all atomic features
            all_feats = {}
            all_feats.update(s_feats)
            all_feats.update(spec_feats)
            all_feats.update(ctx_feats)

            region_features_list.append(
                ChangeRegionFeatures(
                    region_id=reg_id,
                    spatial=spatial,
                    spectral=spectral,
                    context=context,
                    change_score=c_scores,
                    features=all_feats,
                )
            )

        # 4. Deterministic Identity and Provenance
        seed = (
            f"{scene_pair.pair_id}:"
            f"{change_result.result_id}:"
            f"{self.config.extractor_id}:{self.config.extractor_version}:"
            f"{len(region_features_list)}"
        )
        content_hash = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
        evidence_id = f"evi_{content_hash}"
        provenance_id = f"prov_evi_{content_hash}"

        hashes = {}
        if scene_pair.earlier_observation.source_hash:
            hashes["earlier"] = scene_pair.earlier_observation.source_hash
        if scene_pair.later_observation.source_hash:
            hashes["later"] = scene_pair.later_observation.source_hash

        return ChangeEvidence(
            evidence_id=evidence_id,
            scene_pair_id=scene_pair.pair_id,
            change_detection_result_id=change_result.result_id,
            extractor_id=self.config.extractor_id,
            extractor_version=self.config.extractor_version,
            temporal=temporal,
            regions=region_features_list,
            config=self.config,
            source_hashes=hashes,
            provenance_id=provenance_id,
            created_at=datetime.now(timezone.utc),
        )
