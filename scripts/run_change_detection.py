"""ASTRA CLI: Run Temporal Change Detection.

Executes reproducible offline change detection between two satellite rasters
or an M4A scene pair, outputs quantitative change statistics, and persists
lineage-backed artifacts (continuous score map, binary mask, and result JSON).

Usage:
    python scripts/run_change_detection.py --earlier path/to/t1.tif --later path/to/t2.tif
    python scripts/run_change_detection.py --earlier path/to/t1.tif --later path/to/t2.tif --threshold-method statistical --threshold-std 2.5
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
from backend.ml.change_detection import (
    ASTRAPixelDifferenceDetector,
    ChangeDetectionConfig,
    ChangeDetectionService,
    NormalizationMethod,
    ThresholdMethod,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ASTRA Reproducible Temporal Change Detection Engine (M4B)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--earlier",
        type=str,
        required=True,
        help="Path to earlier (T1) GeoTIFF or image chip",
    )
    parser.add_argument(
        "--later",
        type=str,
        required=True,
        help="Path to later (T2) GeoTIFF or image chip",
    )
    parser.add_argument(
        "--threshold-method",
        type=str,
        choices=["statistical", "fixed", "percentile"],
        default="statistical",
        help="Threshold algorithm ('statistical', 'fixed', 'percentile')",
    )
    parser.add_argument(
        "--threshold-std",
        type=float,
        default=2.0,
        help="Multiplier k for statistical threshold (mean + k * std)",
    )
    parser.add_argument(
        "--fixed-threshold",
        type=float,
        default=0.2,
        help="Cutoff score for fixed thresholding in [0.0, 1.0]",
    )
    parser.add_argument(
        "--threshold-percentile",
        type=float,
        default=95.0,
        help="Percentile cutoff when threshold-method is percentile",
    )
    parser.add_argument(
        "--min-region-area",
        type=int,
        default=20,
        help="Minimum pixel area for connected change regions",
    )
    parser.add_argument(
        "--connectivity",
        type=int,
        choices=[4, 8],
        default=8,
        help="Pixel neighborhood connectivity (4 or 8)",
    )
    parser.add_argument(
        "--normalization",
        type=str,
        choices=["robust_percentile", "min_max", "none"],
        default="robust_percentile",
        help="Radiometric normalization method",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Custom output directory (defaults to data/change_results)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print complete result in raw JSON format",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    earlier_path = Path(args.earlier)
    later_path = Path(args.later)

    if not earlier_path.exists():
        print(f"Error: Earlier raster does not exist: {earlier_path}", file=sys.stderr)
        return 1
    if not later_path.exists():
        print(f"Error: Later raster does not exist: {later_path}", file=sys.stderr)
        return 1

    config = ChangeDetectionConfig(
        threshold_method=ThresholdMethod(args.threshold_method),
        threshold_std_multiplier=args.threshold_std,
        fixed_threshold=args.fixed_threshold,
        threshold_percentile=args.threshold_percentile,
        minimum_region_area=args.min_region_area,
        connectivity=args.connectivity,
        normalization_method=NormalizationMethod(args.normalization),
    )

    out_dir = Path(args.output_dir) if args.output_dir else settings.ASTRA_CHANGE_RESULTS_DIR
    service = ChangeDetectionService(output_dir=out_dir)

    if not args.json:
        print("=" * 70)
        print("ASTRA Temporal Change Detection Engine (M4B)")
        print("=" * 70)
        print(f"Earlier (T1)       : {earlier_path}")
        print(f"Later (T2)         : {later_path}")
        print(f"Threshold Method   : {config.threshold_method.value}")
        print(f"Normalization      : {config.normalization_method.value}")
        print(f"Min Region Area    : {config.minimum_region_area} px (connectivity={config.connectivity})")
        print("-" * 70)

    try:
        result = service.run_detection(
            earlier_input=earlier_path,
            later_input=later_path,
            config=config,
        )
    except Exception as e:
        print(f"Change detection failed: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(result.model_dump_json(indent=2))
        return 0

    m = result.metrics
    print("\nQuantitative Change Summary:")
    print(f"  Result ID        : {result.result_id}")
    print(f"  Provenance ID    : {result.provenance_id}")
    print(f"  Total Pixels     : {m.total_pixels:,}")
    print(f"  Valid Pixels     : {m.valid_pixels:,} ({100.0 * m.valid_pixels / max(1, m.total_pixels):.1f}%)")
    print(f"  Invalid / Nodata : {m.invalid_pixels:,}")
    print(f"  Changed Pixels   : {m.changed_pixels:,}")
    print(f"  Changed Ratio    : {m.changed_fraction * 100.0:.2f}%")
    print(f"  Threshold Used   : {m.threshold_used:.4f} ({m.threshold_method})")
    print(f"  Mean Change Mag  : {m.mean_change_score:.4f}")
    print(f"  Max Change Mag   : {m.max_change_score:.4f}")
    print(f"  Discrete Regions : {m.number_of_regions}")

    if result.regions:
        print("\nTop Detected Change Regions:")
        print(f"  {'ID':<10} {'Area (px)':<12} {'Mean Score':<12} {'Max Score':<12} {'Centroid (r, c)':<18}")
        print("  " + "-" * 66)
        for r in result.regions[:10]:
            print(
                f"  {r.region_id:<10} {r.pixel_count:<12} {r.mean_change_score:<12.4f} "
                f"{r.max_change_score:<12.4f} {str(r.centroid_px):<18}"
            )
        if len(result.regions) > 10:
            print(f"  ... and {len(result.regions) - 10} additional regions")

    print("\nGenerated Artifacts:")
    print(f"  Change Mask PNG  : {result.mask_path}")
    print(f"  Score Map NPY    : {result.score_path}")
    print(f"  Result JSON      : {out_dir / result.result_id / 'result.json'}")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
