"""ASTRA CLI: Extract Change Evidence (Phase M4C-A).

Extracts deterministic, explainable evidence across spatial morphology,
geometry, temporal progression, spectral response, and local neighborhood context.
Does NOT classify or label change types.

Usage:
    python scripts/extract_change_evidence.py --result-id res_chg_... --earlier data/t1.tif --later data/t2.tif
"""

import argparse
import json
from pathlib import Path
import sys

# Ensure repository root is in python path
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from backend.config import settings
from backend.ml.change.types import (
    PairCompatibility,
    PairCompatibilityStatus,
    ScenePair,
    SpatialOverlap,
    TemporalObservation,
)
from backend.ml.change_classification import (
    ChangeClassificationEvidenceService,
    EvidenceConfig,
)
from backend.ml.change_detection import ChangeDetectionService
from geospatial.contracts import GeoBoundingBox


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ASTRA Change Evidence Extractor (Phase M4C-A)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--result-id",
        type=str,
        required=True,
        help="Identifier of M4B ChangeDetectionResult (e.g. res_chg_...)",
    )
    parser.add_argument(
        "--pair-id",
        type=str,
        default=None,
        help="Optional identifier of M4A ScenePair",
    )
    parser.add_argument(
        "--earlier",
        type=str,
        default=None,
        help="Path to earlier (T1) raster image",
    )
    parser.add_argument(
        "--later",
        type=str,
        default=None,
        help="Path to later (T2) raster image",
    )
    parser.add_argument(
        "--change-results-dir",
        type=str,
        default=None,
        help="Optional custom directory containing M4B change results",
    )
    parser.add_argument(
        "--neighborhood-buffer",
        type=int,
        default=15,
        help="Neighborhood context buffer radius in pixels",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Directory to persist evidence documents",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON document only",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # Resolve ChangeDetectionResult
    cd_dir = Path(args.change_results_dir) if args.change_results_dir else settings.ASTRA_CHANGE_RESULTS_DIR
    cd_service = ChangeDetectionService(output_dir=cd_dir)
    change_result = cd_service.get_result(args.result_id)
    if change_result is None:
        print(f"Error: Change detection result '{args.result_id}' not found in {cd_dir}.", file=sys.stderr)
        return 1

    # Resolve or create synthetic ScenePair wrapper if ad-hoc
    from datetime import datetime, timezone

    p_id = args.pair_id or change_result.scene_pair_id or "pair_cli_adhoc"
    earlier_path = args.earlier
    later_path = args.later

    obs1 = TemporalObservation(
        observation_id=f"{p_id}_t1",
        scene_id=f"{p_id}_scene_t1",
        acquisition_time=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        crs="EPSG:4326",
        bounds_wgs84=GeoBoundingBox(min_lon=0.0, min_lat=0.0, max_lon=1.0, max_lat=1.0),
        source_hash="0" * 64,
        file_path=earlier_path,
        is_synthetic=True,
    )
    obs2 = TemporalObservation(
        observation_id=f"{p_id}_t2",
        scene_id=f"{p_id}_scene_t2",
        acquisition_time=datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc),
        crs="EPSG:4326",
        bounds_wgs84=GeoBoundingBox(min_lon=0.0, min_lat=0.0, max_lon=1.0, max_lat=1.0),
        source_hash="0" * 64,
        file_path=later_path,
        is_synthetic=True,
    )

    pair = ScenePair(
        pair_id=p_id,
        earlier_observation=obs1,
        later_observation=obs2,
        temporal_separation_seconds=31 * 86400.0,
        temporal_separation_days=31.0,
        spatial_overlap=SpatialOverlap(
            intersection_bounds=None,
            earlier_area_deg2=1.0,
            later_area_deg2=1.0,
            is_overlapping=True,
        ),
        compatibility=PairCompatibility(
            is_compatible=True,
            status=PairCompatibilityStatus.COMPATIBLE,
        ),
    )

    config = EvidenceConfig(neighborhood_buffer_px=args.neighborhood_buffer)
    out_dir = Path(args.output_dir) if args.output_dir else settings.ASTRA_CHANGE_CLASSIFICATION_DIR
    service = ChangeClassificationEvidenceService(output_dir=out_dir)

    try:
        evidence = service.extract_evidence(
            scene_pair=pair,
            change_result=change_result,
            earlier_image=earlier_path,
            later_image=later_path,
            config=config,
        )
    except Exception as e:
        print(f"Evidence extraction failed: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(evidence.model_dump_json(indent=2))
        return 0

    print("=" * 72)
    print("ASTRA Change Classification: Evidence Extraction Layer (M4C-A)")
    print("=" * 72)
    print(f"Evidence ID       : {evidence.evidence_id}")
    print(f"Scene Pair ID     : {evidence.scene_pair_id}")
    print(f"Change Result ID  : {evidence.change_detection_result_id}")
    print(f"Provenance ID     : {evidence.provenance_id}")
    print(f"Temporal Delta    : {evidence.temporal.temporal_separation_days:.1f} days ({evidence.temporal.temporal_separation_hours:.1f} hours)")
    print(f"Regions Evaluated : {len(evidence.regions)}")
    print("-" * 72)

    # Feature family availability
    has_spectral = any(r.spectral.available for r in evidence.regions) if evidence.regions else False
    has_context = any(r.context.available for r in evidence.regions) if evidence.regions else False

    print("Feature Families Status:")
    print("  [+] Spatial Morphology & Geometry : AVAILABLE")
    print("  [+] Temporal Progression          : AVAILABLE")
    print(f"  [{'+' if has_spectral else '-'}] Spectral Reflectance & Color   : {'AVAILABLE' if has_spectral else 'UNAVAILABLE (Imagery not supplied or unreadable)'}")
    print(f"  [{'+' if has_context else '-'}] Local Background Context        : {'AVAILABLE' if has_context else 'UNAVAILABLE (Insufficient background pixels)'}")

    if evidence.regions:
        print("\nRegional Morphology & Evidence Summary:")
        header = f"  {'Region ID':<10} {'Area(px)':<10} {'Aspect':<8} {'Compact':<9} {'Linearity':<10} {'Perim(px)':<10}"
        print(header)
        print("  " + "-" * (len(header) - 2))
        for r in evidence.regions[:8]:
            sp = r.spatial
            print(
                f"  {r.region_id:<10} {sp.area_px:<10} {sp.aspect_ratio:<8.2f} "
                f"{sp.compactness:<9.3f} {sp.linearity_score:<10.3f} {sp.perimeter_px:<10.1f}"
            )
        if len(evidence.regions) > 8:
            print(f"  ... and {len(evidence.regions) - 8} additional regions")

    print("\nPersisted Artifacts:")
    print(f"  Evidence Document : {out_dir / evidence.evidence_id / 'evidence.json'}")
    print("=" * 72)
    print("[NOTE]: M4C-A extracts measurable evidence only; no change classification performed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
