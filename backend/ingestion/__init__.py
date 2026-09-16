"""ASTRA Ingestion Subsystem.

Responsible for ingesting satellite scenes, parsing geospatial headers,
tiling into chips, and writing deterministic tile manifests.
"""

from .service import ingestion_service, IngestionService
from .validator import validate_raster
from .extractor import extract_scene_metadata
from .tiler import generate_tiles_for_scene


def get_ingestion_status() -> str:
    """Returns readiness status of ingestion subsystem."""
    return "ready"



__all__ = [
    "ingestion_service",
    "IngestionService",
    "validate_raster",
    "extract_scene_metadata",
    "generate_tiles_for_scene",
    "get_ingestion_status",
]
