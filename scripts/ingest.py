"""ASTRA Development CLI Tool - Ingest Satellite Raster.

Usage:
    python scripts/ingest.py <path_to_raster> [--tile-size 512] [--force]
"""

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# Ensure UTF-8 output on Windows consoles
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from backend.ingestion.service import ingestion_service


def main():
    parser = argparse.ArgumentParser(
        description="A.S.T.R.A. Geospatial Ingestion CLI - Ingest GeoTIFF or COG rasters."
    )
    parser.add_argument("raster_path", type=str, help="Local path to GeoTIFF or COG raster")
    parser.add_argument("--tile-size", type=int, default=512, help="Square tile chip size in pixels (default: 512)")
    parser.add_argument("--force", action="store_true", help="Force reprocessing even if scene was previously ingested")

    args = parser.parse_args()
    raster_file = Path(args.raster_path)

    print("==================================================")
    print("A.S.T.R.A. Geospatial Ingestion Pipeline (Phase 1)")
    print("==================================================")
    print(f"Target Raster : {raster_file}")
    print(f"Tile Size     : {args.tile_size}x{args.tile_size}")
    print(f"Force Reprocess: {args.force}")
    print("--------------------------------------------------")

    response = ingestion_service.ingest_raster(
        file_path=str(raster_file),
        tile_size=args.tile_size,
        force_reprocess=args.force,
    )

    if response.status == "failed":
        print(f"[INGESTION FAILED]: {response.message}")
        sys.exit(1)

    scene = response.scene
    print(f"Scene ID          : {scene.scene_id}")
    print(f"Format            : {'Cloud Optimized GeoTIFF (COG)' if scene.is_cog else 'Standard GeoTIFF'}")
    print(f"CRS               : {scene.crs}")
    print(f"Bounds (WGS84)    : Lon [{scene.bounds_wgs84.min_lon}, {scene.bounds_wgs84.max_lon}] | Lat [{scene.bounds_wgs84.min_lat}, {scene.bounds_wgs84.max_lat}]")
    print(f"Acquisition       : {scene.acquisition_time.isoformat() if scene.acquisition_time else 'None (Unavailable)'}")
    print(f"Sensor            : {scene.sensor} (Platform: {scene.platform})")
    print(f"Dimensions        : {scene.quality_info.get('width', 'N/A')} x {scene.quality_info.get('height', 'N/A')} (Bands: {scene.quality_info.get('bands_count', 'N/A')})")
    print(f"Bands             : {', '.join(scene.bands)}")
    print(f"Tile Count        : {scene.tile_count} chips")
    print(f"Provenance Status : Recorded ({response.provenance_id})")
    print(f"Ingestion Status  : {response.status.upper()} - {response.message}")
    print(f"Synthetic Data    : {scene.is_synthetic}")
    print("==================================================")
    print("[SUCCESS] Ingestion slice completed successfully.")


if __name__ == "__main__":
    main()
