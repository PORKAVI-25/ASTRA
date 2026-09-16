"""Raster format validation and COG recognition."""

from pathlib import Path
from typing import List, Optional
import rasterio
from rasterio.errors import RasterioIOError
from pydantic import BaseModel, Field


class RasterValidationResult(BaseModel):
    """Result of raster validation checks."""

    is_valid: bool = Field(..., description="Whether file is a valid geospatial raster")
    format_name: str = Field(default="Unknown", description="Human-readable format descriptor")
    driver: str = Field(default="", description="GDAL driver code (e.g. GTiff)")
    is_cog: bool = Field(default=False, description="Whether raster adheres to COG layout")
    error_message: Optional[str] = Field(default=None, description="Detailed error if invalid")
    warnings: List[str] = Field(default_factory=list, description="Non-fatal warnings")


def validate_raster(file_path: Path) -> RasterValidationResult:
    """Safely validates a local raster file and detects GeoTIFF / COG compliance.

    Args:
        file_path: Local filesystem Path.

    Returns:
        RasterValidationResult with validation flags and format diagnostics.
    """
    path = Path(file_path)

    if not path.exists():
        return RasterValidationResult(
            is_valid=False,
            error_message=f"File not found: {path}",
        )

    if not path.is_file():
        return RasterValidationResult(
            is_valid=False,
            error_message=f"Path is not a regular file: {path}",
        )

    if path.stat().st_size == 0:
        return RasterValidationResult(
            is_valid=False,
            error_message=f"File is empty (0 bytes): {path}",
        )

    warnings: List[str] = []

    try:
        with rasterio.open(path) as ds:
            driver = ds.driver
            if driver != "GTiff":
                return RasterValidationResult(
                    is_valid=False,
                    driver=driver,
                    error_message=f"Unsupported raster format: driver '{driver}'. Only GeoTIFF/COG supported.",
                )

            if ds.crs is None:
                warnings.append("Raster does not define a Coordinate Reference System (CRS).")

            # Check for Cloud Optimized GeoTIFF (COG) characteristics:
            # 1. Internal tiling (blockxsize and blockysize are square, typically 256 or 512, and < width)
            # 2. Presence of internal overviews on band 1
            is_tiled = False
            try:
                block_shapes = ds.block_shapes
                if block_shapes and len(block_shapes) > 0:
                    bx, by = block_shapes[0]
                    if bx == by and 16 <= bx < ds.width:
                        is_tiled = True
            except Exception:
                is_tiled = False

            has_overviews = False
            try:
                if ds.count > 0 and len(ds.overviews(1)) > 0:
                    has_overviews = True
            except Exception:
                has_overviews = False

            is_cog = is_tiled and has_overviews
            format_name = "Cloud Optimized GeoTIFF (COG)" if is_cog else "Standard GeoTIFF"

            return RasterValidationResult(
                is_valid=True,
                format_name=format_name,
                driver=driver,
                is_cog=is_cog,
                warnings=warnings,
            )

    except RasterioIOError as e:
        return RasterValidationResult(
            is_valid=False,
            error_message=f"Corrupt or invalid geospatial raster: {str(e)}",
        )
    except Exception as e:
        return RasterValidationResult(
            is_valid=False,
            error_message=f"Unexpected error opening raster: {str(e)}",
        )
