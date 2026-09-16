"""Geospatial and sensor metadata extraction from raster datasets."""

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import rasterio
import rasterio.warp
from geospatial.contracts import GeoBoundingBox, SceneManifest


def compute_file_sha256(path: Path, chunk_size: int = 65536) -> str:
    """Computes SHA-256 checksum of a file."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def parse_acquisition_datetime(meta_tags: Dict[str, str], stem: str) -> Optional[datetime]:
    """Extracts UTC acquisition timestamp from metadata tags or filename.

    Does NOT fabricate timestamps; returns None if not present.
    """
    # 1. Check TIFF / GDAL standard datetime tags
    for tag_key in ["TIFFTAG_DATETIME", "DATETIME", "ACQUISITION_DATETIME", "acquisition_time"]:
        val = meta_tags.get(tag_key)
        if val:
            # Common formats: "YYYY:MM:DD HH:MM:SS" or ISO format
            for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
                try:
                    dt = datetime.strptime(val.strip(), fmt)
                    return dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue

    # 2. Check filename for standard ISO date pattern: YYYYMMDD or YYYY-MM-DD
    match = re.search(r"(\d{4})[_-]?(\d{2})[_-]?(\d{2})(?:[T_](\d{2})(\d{2})(\d{2}))?", stem)
    if match:
        groups = match.groups()
        try:
            year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
            hour = int(groups[3]) if groups[3] is not None else 0
            minute = int(groups[4]) if groups[4] is not None else 0
            second = int(groups[5]) if groups[5] is not None else 0
            if 1970 <= year <= 2050 and 1 <= month <= 12 and 1 <= day <= 31:
                return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
        except Exception:
            pass

    return None


def detect_sensor_and_platform(meta_tags: Dict[str, str], stem: str) -> Tuple[str, str]:
    """Detects sensor instrument and platform from metadata tags or filename pattern.

    Defaults explicitly to ('unknown', 'unknown') without fabricating data.
    """
    stem_upper = stem.upper()
    tags_upper = {k.upper(): str(v) for k, v in meta_tags.items()}

    # Check tags
    sensor = tags_upper.get("SENSOR", tags_upper.get("INSTRUMENT", ""))
    platform = tags_upper.get("PLATFORM", tags_upper.get("SATELLITE", ""))

    if sensor or platform:
        return (sensor or "unknown", platform or "unknown")

    # Check filename conventions
    if "S2A" in stem_upper or "SENTINEL-2A" in stem_upper:
        return ("Sentinel-2A MSI", "Sentinel-2")
    if "S2B" in stem_upper or "SENTINEL-2B" in stem_upper:
        return ("Sentinel-2B MSI", "Sentinel-2")
    if "LC08" in stem_upper or "LANDSAT_8" in stem_upper or "LANDSAT8" in stem_upper:
        return ("Landsat-8 OLI/TIRS", "Landsat-8")
    if "LC09" in stem_upper or "LANDSAT_9" in stem_upper or "LANDSAT9" in stem_upper:
        return ("Landsat-9 OLI-2/TIRS-2", "Landsat-9")

    return ("unknown", "unknown")


def extract_scene_metadata(file_path: Path, is_cog: bool = False) -> SceneManifest:
    """Safely extracts full scene metadata and returns a validated SceneManifest."""
    path = Path(file_path)
    file_hash = compute_file_sha256(path)

    with rasterio.open(path) as ds:
        tags = ds.tags()
        stem = path.stem

        # Extract CRS
        if ds.crs:
            crs_str = ds.crs.to_string()
        else:
            crs_str = "EPSG:4326"  # Unprojected fallback

        # Extract Geographic bounds in WGS84
        left, bottom, right, top = ds.bounds.left, ds.bounds.bottom, ds.bounds.right, ds.bounds.top
        try:
            if ds.crs and ds.crs.to_string() != "EPSG:4326":
                wgs_bounds = rasterio.warp.transform_bounds(ds.crs, "EPSG:4326", left, bottom, right, top)
                bounds_wgs84 = GeoBoundingBox(
                    min_lon=round(wgs_bounds[0], 6),
                    min_lat=round(wgs_bounds[1], 6),
                    max_lon=round(wgs_bounds[2], 6),
                    max_lat=round(wgs_bounds[3], 6),
                )
            else:
                bounds_wgs84 = GeoBoundingBox(
                    min_lon=round(left, 6),
                    min_lat=round(bottom, 6),
                    max_lon=round(right, 6),
                    max_lat=round(top, 6),
                )
        except Exception:
            # Fallback for unprojected coordinates
            bounds_wgs84 = GeoBoundingBox(
                min_lon=max(-180.0, min(180.0, left)),
                min_lat=max(-90.0, min(90.0, bottom)),
                max_lon=max(-180.0, min(180.0, right)),
                max_lat=max(-90.0, min(90.0, top)),
            )

        # Resolution (meters or pixel units)
        res_x, res_y = ds.res
        spatial_resolution = round(float(abs(res_x)), 4) if res_x else None

        # Band descriptions or indices
        bands = []
        for b_idx in range(1, ds.count + 1):
            desc = ds.descriptions[b_idx - 1] if ds.descriptions and ds.descriptions[b_idx - 1] else f"B{b_idx}"
            bands.append(desc)

        # Acquisition time and sensor
        acq_time = parse_acquisition_datetime(tags, stem)
        sensor, platform = detect_sensor_and_platform(tags, stem)

        # Quality & Nodata foundation
        nodata = float(ds.nodata) if ds.nodata is not None else None
        quality_info = {
            "driver": ds.driver,
            "dtype": str(ds.dtypes[0]) if ds.dtypes else "unknown",
            "width": ds.width,
            "height": ds.height,
            "bands_count": ds.count,
            "nodata": nodata,
            "is_tiled": ds.profile.get("tiled", False),
        }

        # Stable source_scene_id: clean alphanumeric stem with deterministic hash suffix
        clean_stem = re.sub(r"[^a-zA-Z0-9_-]", "_", stem)
        scene_id = f"{clean_stem}_{file_hash[:8]}"

        # Synthetic check
        is_synthetic = (
            "synthetic" in stem.lower()
            or "demo" in stem.lower()
            or tags.get("IS_SYNTHETIC", "").lower() in ["true", "1"]
        )

        return SceneManifest(
            scene_id=scene_id,
            sensor=sensor,
            platform=platform,
            acquisition_time=acq_time,
            crs=crs_str,
            bounds_wgs84=bounds_wgs84,
            spatial_resolution_m=spatial_resolution,
            bands=bands,
            source_file_path=str(path.as_posix()),
            is_cog=is_cog,
            tile_count=0,
            nodata_value=nodata,
            quality_info=quality_info,
            file_hash=file_hash,
            is_synthetic=is_synthetic,
        )
