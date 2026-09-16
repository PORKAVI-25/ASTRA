"""Generates deterministic synthetic GeoTIFF and COG test rasters for automated tests.

Adheres strictly to Critical Rule 9:
- Clearly marked as synthetic
- Never mixed with benchmark/public imagery
- is_synthetic = True
"""

from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.enums import Resampling


def create_synthetic_geotiff(
    output_path: Path,
    width: int = 1024,
    height: int = 1024,
    crs: str = "EPSG:32643",
    res: float = 10.0,
    nodata: float = -9999.0,
) -> Path:
    """Creates a deterministic synthetic 3-band GeoTIFF with UTM projection."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Origin coordinates in UTM zone 43N (Bengaluru/Mysuru region)
    west = 700000.0
    north = 1400000.0
    transform = from_origin(west, north, res, res)

    # Deterministic gradient pattern across bands
    band1 = np.linspace(100, 2000, width, dtype=np.uint16)
    band1 = np.tile(band1, (height, 1))

    band2 = np.linspace(200, 3000, height, dtype=np.uint16)
    band2 = np.tile(band2[:, np.newaxis], (1, width))

    band3 = ((band1.astype(np.float32) + band2.astype(np.float32)) / 2).astype(np.uint16)

    # Introduce known nodata region in top-left 32x32 pixels
    band1[:32, :32] = int(nodata) if nodata >= 0 else 0

    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": 3,
        "dtype": "uint16",
        "crs": crs,
        "transform": transform,
        "nodata": nodata if nodata >= 0 else None,
    }

    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(band1, 1)
        dst.write(band2, 2)
        dst.write(band3, 3)
        dst.set_band_description(1, "B02_Blue")
        dst.set_band_description(2, "B03_Green")
        dst.set_band_description(3, "B04_Red")
        dst.update_tags(
            TIFFTAG_DATETIME="2026:03:15 05:20:21",
            SENSOR="Sentinel-2A MSI",
            PLATFORM="Sentinel-2",
            IS_SYNTHETIC="true",
        )

    return output_path


def create_synthetic_cog(
    output_path: Path,
    width: int = 512,
    height: int = 512,
    crs: str = "EPSG:4326",
) -> Path:
    """Creates a deterministic synthetic Cloud Optimized GeoTIFF (tiled with overviews)."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # WGS84 coordinates
    west, north = 77.5, 13.0
    res = 0.001
    transform = from_origin(west, north, res, res)

    data = np.zeros((3, height, width), dtype=np.uint8)
    # Generate distinct concentric squares
    for i in range(height):
        for j in range(width):
            data[0, i, j] = (i + j) % 256
            data[1, i, j] = (i * 2) % 256
            data[2, i, j] = (j * 2) % 256

    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": 3,
        "dtype": "uint8",
        "crs": crs,
        "transform": transform,
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
    }

    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(data)
        dst.set_band_description(1, "Red")
        dst.set_band_description(2, "Green")
        dst.set_band_description(3, "Blue")
        dst.update_tags(
            TIFFTAG_DATETIME="2026:06:21 10:00:00",
            SENSOR="SyntheticSensor",
            PLATFORM="SyntheticPlatform",
            IS_SYNTHETIC="true",
        )
        # Build overviews for COG compliance
        dst.build_overviews([2, 4], Resampling.nearest)

    return output_path


if __name__ == "__main__":
    test_dir = Path("data/raw/synthetic")
    p1 = create_synthetic_geotiff(test_dir / "synthetic_S2A_20260315_utm.tif")
    p2 = create_synthetic_cog(test_dir / "synthetic_cog_wgs84.tif")
    print(f"Generated test GeoTIFF: {p1}")
    print(f"Generated test COG    : {p2}")
