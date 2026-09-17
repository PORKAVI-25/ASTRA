"""ASTRA Multi-Epoch Synthetic Demo Dataset Generator (Phase M4F-C).

Generates a deterministic 4-epoch synthetic satellite-style temporal dataset,
ingests it through the Phase 1 Ingestion Service, validates catalog discovery,
and outputs all canonical identifiers for downstream investigation orchestration.

Adheres strictly to ASTRA Determinism & Offline Policies:
- Zero external network requests or remote APIs
- 100% deterministic pixel synthesis (no random seeds)
- Explicit synthetic provenance (is_synthetic=True)
- Spatially corresponding regions with differing local M4B region IDs across epochs
"""

import argparse
from pathlib import Path
import sys
from typing import Dict, List, Tuple

import numpy as np
import rasterio
from rasterio.transform import from_origin

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import settings
from backend.ingestion.service import IngestionService
from backend.ml.change.temporal_catalog import TemporalCatalog
from backend.ml.change_detection.service import ChangeDetectionService


def create_synthetic_epoch_rasters(
    output_dir: Path,
    width: int = 512,
    height: int = 512,
    res: float = 10.0,
    crs: str = "EPSG:32643",
) -> List[Tuple[int, str, Path]]:
    """Synthesizes deterministic 4-epoch GeoTIFF scenes with calibrated target features.

    Bands:
      1: B02_Blue
      2: B03_Green
      3: B04_Red
      4: B08_NIR
      5: B11_SWIR

    Epoch layout:
      T1: 2026-01-15T10:00:00Z (Baseline)
      T2: 2026-02-15T10:00:00Z (Construction appears at [200:230, 200:230], clearance at [60:85, 60:85], cloud at [350:375, 350:375])
      T3: 2026-03-15T10:00:00Z (Construction persists at [200:230, 200:230], unrelated change at [420:445, 420:445])
      T4: 2026-04-15T10:00:00Z (Construction persists at [200:230, 200:230], unrelated changes at [30:50, 30:50] and [100:120, 100:120])
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    west = 750000.0
    north = 1450000.0
    transform = from_origin(west, north, res, res)

    # Deterministic background gradient and texture
    y, x = np.mgrid[0:height, 0:width]
    base_blue = 800 + ((x * 3 + y * 2) % 200)
    base_green = 1200 + ((x * 2 + y * 3) % 250)
    base_red = 1100 + ((x * 4 + y * 1) % 200)
    base_nir = 2500 + ((x * 1 + y * 4) % 300)
    base_swir = 1400 + ((x * 2 + y * 2) % 200)

    epochs_meta = [
        (1, "2026:01:15 10:00:00", "2026-01-15"),
        (2, "2026:02:15 10:00:00", "2026-02-15"),
        (3, "2026:03:15 10:00:00", "2026-03-15"),
        (4, "2026:04:15 10:00:00", "2026-04-15"),
    ]

    generated_rasters: List[Tuple[int, str, Path]] = []

    for epoch_idx, acq_tag, date_slug in epochs_meta:
        b_blue = base_blue.copy()
        b_green = base_green.copy()
        b_red = base_red.copy()
        b_nir = base_nir.copy()
        b_swir = base_swir.copy()

        # Fixed calibration reference anchor in corner (0,0 to 0,1)
        # Guarantees identical PNG normalization across all epochs
        b_blue[0, 0] = 0
        b_blue[0, 1] = 9000
        b_green[0, 0] = 0
        b_green[0, 1] = 9000
        b_red[0, 0] = 0
        b_red[0, 1] = 9000
        b_nir[0, 0] = 0
        b_nir[0, 1] = 9000
        b_swir[0, 0] = 0
        b_swir[0, 1] = 9000

        if epoch_idx == 1:
            # T1: Baseline
            # Vegetated patch at [40:80, 40:80]
            b_nir[40:80, 40:80] = 4500
            b_red[40:80, 40:80] = 700

        elif epoch_idx == 2:
            # T2: Construction emergence
            # 1. Unrelated clearance at [40:80, 40:80] (Area 1600px > 900px -> M4B reg_0001)
            b_nir[40:80, 40:80] = 1200
            b_red[40:80, 40:80] = 2400

            # 2. Genuine construction candidate at [200:230, 200:230] (Area 900px -> M4B reg_0002)
            # Terracotta / brick reflectance: high red, moderate green/blue (whiteness > 0.20, not cloud)
            b_blue[200:230, 200:230] = 3000
            b_green[200:230, 200:230] = 4200
            b_red[200:230, 200:230] = 6800
            b_nir[200:230, 200:230] = 5500
            b_swir[200:230, 200:230] = 6500

            # 3. Artifact (Cloud contamination blob) at [350:375, 350:375] (Area 316px -> M4B reg_0003)
            # High visible brightness, low SWIR (triggers swir_drop / cloud contamination in M4D)
            yy, xx = np.mgrid[350:375, 350:375]
            dist_sq = ((yy - 362.5) / 10.0) ** 2 + ((xx - 362.5) / 10.0) ** 2
            cloud_mask = dist_sq <= 1.0
            b_blue[350:375, 350:375][cloud_mask] = 8500
            b_green[350:375, 350:375][cloud_mask] = 8500
            b_red[350:375, 350:375][cloud_mask] = 8500
            b_nir[350:375, 350:375][cloud_mask] = 8500
            b_swir[350:375, 350:375][cloud_mask] = 1000

        elif epoch_idx == 3:
            # T3: Construction persists at [200:230, 200:230] (Area 900px -> M4B reg_0001)
            b_blue[200:230, 200:230] = 3000
            b_green[200:230, 200:230] = 4200
            b_red[200:230, 200:230] = 6800
            b_nir[200:230, 200:230] = 5500
            b_swir[200:230, 200:230] = 6500

            # Clearance regrown to baseline vegetative state
            b_nir[40:80, 40:80] = 4500
            b_red[40:80, 40:80] = 700

            # Unrelated change at bottom [420:445, 420:445] (Area 625px < 900px -> M4B reg_0002)
            # Result: in T1 vs T3 change detection, target construction at row 200 is reg_0001!
            b_blue[420:445, 420:445] = 3000
            b_green[420:445, 420:445] = 3200
            b_red[420:445, 420:445] = 3400

        elif epoch_idx == 4:
            # T4: Construction persists at [200:230, 200:230] (Area 900px -> M4B reg_0003)
            b_blue[200:230, 200:230] = 3000
            b_green[200:230, 200:230] = 4200
            b_red[200:230, 200:230] = 6800
            b_nir[200:230, 200:230] = 5500
            b_swir[200:230, 200:230] = 6500

            # Clearance remains regrown
            b_nir[40:80, 40:80] = 4500
            b_red[40:80, 40:80] = 700

            # Two unrelated changes larger than target construction:
            # Change 1: at [60:100, 60:100] (Area 1600px -> M4B reg_0001)
            b_blue[60:100, 60:100] = 3000
            b_green[60:100, 60:100] = 4000
            b_red[60:100, 60:100] = 6000

            # Change 2: at [320:355, 320:355] (Area 1225px -> M4B reg_0002)
            b_blue[320:355, 320:355] = 3000
            b_green[320:355, 320:355] = 4000
            b_red[320:355, 320:355] = 6000
            # Result: in T1 vs T4 change detection, target construction is reg_0003!

        raster_filename = f"demo_synthetic_epoch{epoch_idx}_{date_slug.replace('-', '')}.tif"
        out_path = output_dir / raster_filename

        profile = {
            "driver": "GTiff",
            "height": height,
            "width": width,
            "count": 5,
            "dtype": "uint16",
            "crs": crs,
            "transform": transform,
            "nodata": None,
        }

        with rasterio.open(out_path, "w", **profile) as dst:
            dst.write(b_blue.astype(np.uint16), 1)
            dst.write(b_green.astype(np.uint16), 2)
            dst.write(b_red.astype(np.uint16), 3)
            dst.write(b_nir.astype(np.uint16), 4)
            dst.write(b_swir.astype(np.uint16), 5)
            dst.set_band_description(1, "B02_Blue")
            dst.set_band_description(2, "B03_Green")
            dst.set_band_description(3, "B04_Red")
            dst.set_band_description(4, "B08_NIR")
            dst.set_band_description(5, "B11_SWIR")
            dst.update_tags(
                TIFFTAG_DATETIME=acq_tag,
                SENSOR="Sentinel-2A MSI",
                PLATFORM="Sentinel-2",
                IS_SYNTHETIC="true",
                CLOUD_COVER="0.0",
            )

        generated_rasters.append((epoch_idx, acq_tag, out_path))

    return generated_rasters


def generate_and_ingest_demo_dataset(
    output_dir: Path,
    manifests_dir: Path,
    processed_dir: Path,
    tile_size: int = 512,
    force: bool = False,
) -> Dict[str, str]:
    """Generates the 4 synthetic scenes, ingests them, and discovers catalog entities."""
    print("=" * 70)
    print("ASTRA MULTI-EPOCH DEMO DATASET GENERATOR (PHASE M4F-C)")
    print("=" * 70)
    print(f"Target Output Directory   : {output_dir}")
    print(f"Target Manifests Directory: {manifests_dir}")
    print(f"Target Processed Directory: {processed_dir}")
    print(f"Tile Size                 : {tile_size}x{tile_size}")
    print(f"Force Reprocess           : {force}")
    print("-" * 70)

    if force:
        # Clean previous demo artifacts to avoid conflicting runs
        for clean_dir in [
            manifests_dir / "scenes",
            manifests_dir / "tiles",
            processed_dir / "tiles",
            output_dir,
        ]:
            if clean_dir.exists():
                for f in clean_dir.glob("demo_synthetic*"):
                    try:
                        f.unlink()
                    except OSError:
                        pass

    # Step 1: Generate GeoTIFF files
    print("\n[1/4] Synthesizing 4-Epoch Multi-Spectral Satellite Rasters...")
    rasters = create_synthetic_epoch_rasters(output_dir=output_dir)
    for ep, tag, p in rasters:
        print(f"      Epoch {ep}: {p.name} ({tag})")

    # Step 2: Ingest Rasters
    print("\n[2/4] Ingesting GeoTIFFs through Ingestion Pipeline...")
    ingest_service = IngestionService(manifests_dir=manifests_dir)
    ingested_scenes = []
    for ep, tag, p in rasters:
        resp = ingest_service.ingest_raster(str(p), tile_size=tile_size, force_reprocess=force)
        if resp.status == "failed":
            raise RuntimeError(f"Ingestion failed for {p.name}: {resp.message}")
        ingested_scenes.append(resp.scene)
        print(f"      Ingested {p.name} -> Scene ID: {resp.scene.scene_id} ({resp.status})")

    # Step 3: Discover Catalog
    print("\n[3/4] Discovering Ingested Scenes & Building Temporal Series...")
    catalog = TemporalCatalog()
    disc = catalog.discover_manifests(
        tiles_dir=manifests_dir / "tiles",
        scenes_dir=manifests_dir / "scenes",
    )
    print(f"      Discovered Scenes : {disc.scenes_discovered}")
    print(f"      Valid Observations: {disc.valid_observations}")
    print(f"      Formed Series     : {disc.temporal_series_count}")

    series_list = catalog.list_series()
    ingested_scene_ids = {sc.scene_id for sc in ingested_scenes}
    series_candidates = [
        s for s in series_list
        if set(obs.scene_id for obs in s.observations) == ingested_scene_ids
    ]
    if not series_candidates:
        series_candidates = [
            s for s in series_list
            if s.observation_count == 4 and any("demo_synthetic" in obs.scene_id for obs in s.observations)
        ]
    if not series_candidates:
        raise RuntimeError("No temporal series could be formed from ingested demo dataset.")
    series = series_candidates[0]
    print(f"      Active Series ID  : {series.series_id} ({series.observation_count} epochs)")

    # Step 4: Generate Pairs & Identify Discovery Pair + Candidate Region
    print("\n[4/4] Evaluating Scene Pairs & Resolving Discovery Candidate...")
    valid_pairs, _ = catalog.generate_pairs(mode="all_pairwise")
    demo_obs_ids = {obs.observation_id for obs in series.observations}
    pairs = [
        p for p in valid_pairs
        if p.earlier_observation.observation_id in demo_obs_ids
        and p.later_observation.observation_id in demo_obs_ids
    ]
    # Discovery pair is T1 -> T2
    discovery_pair = next(
        p for p in pairs
        if p.earlier_observation.acquisition_time.month == 1
        and p.later_observation.acquisition_time.month == 2
    )

    # Run change detection on discovery pair to obtain exact candidate_region_id
    cd_service = ChangeDetectionService(
        output_dir=settings.ASTRA_CHANGE_RESULTS_DIR,
        provenance_dir=manifests_dir / "provenance",
    )
    cdr = cd_service.run_detection(pair=discovery_pair)

    # Find the target construction region at [200:230, 200:230]
    candidate_reg = next(
        (r for r in cdr.regions if 190 <= r.bbox_px[0] <= 210 and 190 <= r.bbox_px[1] <= 210),
        cdr.regions[0] if cdr.regions else None,
    )
    if candidate_reg is None:
        raise RuntimeError("Could not resolve construction candidate region in discovery pair.")

    candidate_region_id = candidate_reg.region_id

    print("\n" + "=" * 70)
    print("DEMO DATASET GENERATION SUMMARY & IDENTIFIERS")
    print("=" * 70)
    print(f"Series ID            : {series.series_id}")
    print(f"Discovery Pair ID    : {discovery_pair.pair_id}")
    print(f"Candidate Region ID  : {candidate_region_id}")
    print(f"Observations Count   : {len(series.observations)}")
    print(f"Pair Count           : {len(pairs)}")
    print("-" * 70)
    print("Canonical Observation IDs:")
    for obs in series.observations:
        print(f"  - {obs.acquisition_time.date()}: {obs.observation_id}")
    print("-" * 70)
    print("Detected Regions in Discovery Pair:")
    for reg in cdr.regions:
        is_target = " [TARGET CANDIDATE]" if reg.region_id == candidate_region_id else ""
        print(f"  - {reg.region_id}: bbox={reg.bbox_px}, area={reg.area_px}px{is_target}")
    print("=" * 70)
    print("[SUCCESS] Demo dataset generation and cataloging completed successfully.\n")

    return {
        "series_id": series.series_id,
        "discovery_pair_id": discovery_pair.pair_id,
        "candidate_region_id": candidate_region_id,
    }


def main():
    parser = argparse.ArgumentParser(
        description="ASTRA Multi-Epoch Demo Dataset Generator (Phase M4F-C)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(settings.ASTRA_RAW_DIR / "demo"),
        help="Directory to save raw synthetic GeoTIFF rasters (default: data/raw/demo)",
    )
    parser.add_argument(
        "--manifests-dir",
        type=str,
        default=str(settings.ASTRA_MANIFESTS_DIR),
        help="Manifests root directory (default: data/manifests)",
    )
    parser.add_argument(
        "--processed-dir",
        type=str,
        default=str(settings.ASTRA_PROCESSED_DIR),
        help="Processed root directory (default: data/processed)",
    )
    parser.add_argument(
        "--tile-size",
        type=int,
        default=512,
        help="Chipping tile size in pixels (default: 512)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force regeneration and re-ingestion of rasters",
    )

    args = parser.parse_args()

    generate_and_ingest_demo_dataset(
        output_dir=Path(args.output_dir),
        manifests_dir=Path(args.manifests_dir),
        processed_dir=Path(args.processed_dir),
        tile_size=args.tile_size,
        force=args.force,
    )


if __name__ == "__main__":
    main()
