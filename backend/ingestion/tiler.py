"""Deterministic windowed raster tiling engine."""

import hashlib
from pathlib import Path
from typing import List, Tuple
import numpy as np
import rasterio
from rasterio.windows import Window
import rasterio.warp
from PIL import Image

from backend.config import settings
from geospatial.contracts import (
    GeoBoundingBox,
    SceneManifest,
    TileDimensions,
    TileManifest,
)


def compute_tile_bounds(
    ds: rasterio.DatasetReader, window: Window
) -> Tuple[GeoBoundingBox, Tuple[float, float, float, float]]:
    """Calculates geographic WGS84 bounding box and projected bounds for a window."""
    window_transform = rasterio.windows.transform(window, ds.transform)
    left = window_transform.c
    top = window_transform.f
    right = left + window.width * window_transform.a
    bottom = top + window.height * window_transform.e

    # Ensure min/max ordering
    proj_left, proj_right = min(left, right), max(left, right)
    proj_bottom, proj_top = min(bottom, top), max(bottom, top)
    projected_bounds = (proj_left, proj_bottom, proj_right, proj_top)

    if ds.crs and ds.crs.to_string() != "EPSG:4326":
        try:
            wgs = rasterio.warp.transform_bounds(
                ds.crs, "EPSG:4326", proj_left, proj_bottom, proj_right, proj_top
            )
            bounds_wgs84 = GeoBoundingBox(
                min_lon=round(wgs[0], 6),
                min_lat=round(wgs[1], 6),
                max_lon=round(wgs[2], 6),
                max_lat=round(wgs[3], 6),
            )
        except Exception:
            bounds_wgs84 = GeoBoundingBox(
                min_lon=round(proj_left, 6),
                min_lat=round(proj_bottom, 6),
                max_lon=round(proj_right, 6),
                max_lat=round(proj_top, 6),
            )
    else:
        bounds_wgs84 = GeoBoundingBox(
            min_lon=round(proj_left, 6),
            min_lat=round(proj_bottom, 6),
            max_lon=round(proj_right, 6),
            max_lat=round(proj_top, 6),
        )

    return bounds_wgs84, projected_bounds


def generate_tiles_for_scene(
    scene: SceneManifest,
    tile_size: int = 512,
    zoom_level: int = 14,
    output_dir: Path = None,
) -> List[TileManifest]:
    """Generates deterministic, georeferenced chipped tiles using windowed reads.

    Args:
        scene: Ingested SceneManifest.
        tile_size: Square tile dimension in pixels.
        zoom_level: Tiling pyramid level.
        output_dir: Directory where chips are saved.

    Returns:
        List of generated TileManifest instances.
    """
    source_path = Path(scene.source_file_path)
    if output_dir is None:
        output_dir = settings.ASTRA_PROCESSED_DIR / "tiles" / scene.scene_id
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    tile_manifests: List[TileManifest] = []

    with rasterio.open(source_path) as ds:
        width = ds.width
        height = ds.height
        nodata = ds.nodata

        # Grid generation
        cols = int(np.ceil(width / tile_size))
        rows = int(np.ceil(height / tile_size))

        for row_idx in range(rows):
            for col_idx in range(cols):
                col_off = col_idx * tile_size
                row_off = row_idx * tile_size

                # Window boundaries (bounded by dataset dimensions)
                w_width = min(tile_size, width - col_off)
                w_height = min(tile_size, height - row_off)

                window = Window(
                    col_off=col_off,
                    row_off=row_off,
                    width=w_width,
                    height=w_height,
                )

                # Memory-safe windowed read
                tile_data = ds.read(window=window)  # shape: (bands, height, width)

                # Calculate nodata metrics
                nodata_count = 0
                valid_ratio = 1.0
                total_pixels = w_width * w_height
                if nodata is not None:
                    nodata_mask = np.isclose(tile_data[0], nodata)
                    nodata_count = int(np.sum(nodata_mask))
                    valid_ratio = round(float(1.0 - (nodata_count / total_pixels)), 4)

                # Pad to standard tile_size if edge chip
                if w_width != tile_size or w_height != tile_size:
                    padded_data = np.zeros((ds.count, tile_size, tile_size), dtype=tile_data.dtype)
                    if nodata is not None:
                        padded_data.fill(nodata)
                    padded_data[:, :w_height, :w_width] = tile_data
                    tile_data = padded_data

                # Compute stable content hash
                tile_bytes = tile_data.tobytes()
                sha256_hash = hashlib.sha256(tile_bytes).hexdigest()

                # Deterministic tile_id
                tile_id = f"tile_{scene.scene_id}_c{col_idx:04d}_r{row_idx:04d}_z{zoom_level:02d}"

                # Calculate spatial bounds
                bounds_wgs84, _ = compute_tile_bounds(ds, window)

                # Save chip as PNG representation for downstream visual display
                tile_file = output_dir / f"{tile_id}.png"

                # Normalize 1st to 3rd bands for RGB PNG
                try:
                    if tile_data.shape[0] >= 3:
                        rgb = tile_data[:3, :, :].transpose(1, 2, 0)
                    elif tile_data.shape[0] == 1:
                        rgb = np.repeat(tile_data[0, :, :, np.newaxis], 3, axis=2)
                    else:
                        rgb = np.zeros((tile_size, tile_size, 3), dtype=np.uint8)

                    # Simple 8-bit normalization for PNG export
                    if rgb.dtype != np.uint8:
                        p_min, p_max = float(np.min(rgb)), float(np.max(rgb))
                        if p_max > p_min:
                            rgb_norm = ((rgb - p_min) / (p_max - p_min) * 255.0).astype(np.uint8)
                        else:
                            rgb_norm = np.zeros_like(rgb, dtype=np.uint8)
                    else:
                        rgb_norm = rgb

                    img = Image.fromarray(rgb_norm)
                    img.save(tile_file, format="PNG")
                except Exception:
                    # If image export fails, write raw bytes
                    tile_file.write_bytes(tile_bytes[:1024])

                tile_manifest = TileManifest(
                    tile_id=tile_id,
                    source_scene_id=scene.scene_id,
                    tile_col=col_idx,
                    tile_row=row_idx,
                    zoom_level=zoom_level,
                    dimensions=TileDimensions(
                        width_px=tile_size,
                        height_px=tile_size,
                        channels=ds.count,
                    ),
                    crs=scene.crs,
                    bounds_wgs84=bounds_wgs84,
                    acquisition_time=scene.acquisition_time,
                    sensor=scene.sensor,
                    file_path=str(tile_file.as_posix()),
                    sha256_hash=sha256_hash,
                    nodata_pixel_count=nodata_count,
                    valid_pixel_ratio=valid_ratio,
                    is_synthetic=scene.is_synthetic,
                )

                tile_manifests.append(tile_manifest)

    return tile_manifests
