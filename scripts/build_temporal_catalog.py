"""ASTRA Phase M4A: Temporal Catalog & Scene Pairing CLI.

Discovers local Phase 1 scene and tile manifests, constructs chronological
temporal series, evaluates candidate pairs under configurable spatial and temporal
constraints, and prints an operational summary report.
"""

import argparse
import sys
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import settings
from backend.ml.change import (
    PairingConfig,
    TemporalCatalog,
)


def print_banner():
    print("=" * 80)
    print("ASTRA PHASE M4A: TEMPORAL OBSERVATION CATALOG & SCENE PAIRING")
    print("Deterministic Multi-Temporal Satellite Scene Association Engine")
    print("=" * 80)


def build_catalog(
    manifests_dir: Path,
    scenes_dir: Path,
    min_overlap: float = 0.5,
    min_days: float = 0.0,
    max_days: float = None,
    require_same_sensor: bool = False,
    require_same_platform: bool = False,
    mode: str = "adjacent",
    verbose: bool = False,
) -> int:
    """Discovers manifests, creates catalog, evaluates pairs, and reports metrics."""
    t0 = time.perf_counter()

    print(f"\n[1/3] Scanning Local Manifests:")
    print(f"      Scenes Directory : {scenes_dir}")
    print(f"      Tiles Directory  : {manifests_dir}")

    catalog = TemporalCatalog()
    result = catalog.discover_manifests(tiles_dir=manifests_dir, scenes_dir=scenes_dir)

    print(f"      Scenes Discovered   : {result.scenes_discovered}")
    print(f"      Valid Observations  : {result.valid_observations}")
    print(f"      Invalid/Skipped     : {result.invalid_observations}")
    if verbose and result.diagnostics:
        print("\n      [Diagnostics]:")
        for d in result.diagnostics[:10]:
            print(f"        - {d}")
        if len(result.diagnostics) > 10:
            print(f"        ... and {len(result.diagnostics) - 10} more.")

    print(f"\n[2/3] Constructing Temporal Series:")
    series_list = catalog.list_series()
    print(f"      Formed {len(series_list)} distinct geographic temporal series")
    for s in series_list[:5]:
        print(f"        Series '{s.series_id}': {s.observation_count} observations ({s.earliest_date.strftime('%Y-%m-%d')} to {s.latest_date.strftime('%Y-%m-%d')})")
    if len(series_list) > 5:
        print(f"        ... and {len(series_list) - 5} more series")

    print(f"\n[3/3] Evaluating Temporal Pairs (Constraints Enforcement):")
    config = PairingConfig(
        min_spatial_overlap_ratio=min_overlap,
        min_temporal_separation_seconds=min_days * 86400.0,
        max_temporal_separation_seconds=max_days * 86400.0 if max_days is not None else None,
        require_same_sensor=require_same_sensor,
        require_same_platform=require_same_platform,
    )
    print(f"      Strategy            : {mode}")
    min_sep_str = (
        f"{min_days:.1f} days (strictly positive; requires T2 > T1)"
        if min_days == 0.0
        else f"{min_days:.1f} days"
    )
    print(f"      Min Separation      : {min_sep_str}")
    print(f"      Max Separation      : {'Unbounded' if max_days is None else f'{max_days:.1f} days'}")
    print(f"      Same-Sensor Enforced: {require_same_sensor}")
    print(f"      Same-Platform Enforced: {require_same_platform}")

    valid_pairs, rejected_pairs = catalog.generate_pairs(config=config, mode=mode)
    candidate_pairs_count = len(valid_pairs) + len(rejected_pairs)

    elapsed = time.perf_counter() - t0

    print("\n" + "=" * 80)
    print("TEMPORAL CATALOG & SCENE PAIRING SUMMARY REPORT:")
    print(f"  Scenes discovered   : {result.scenes_discovered}")
    print(f"  Valid observations  : {result.valid_observations}")
    print(f"  Invalid observations: {result.invalid_observations}")
    print(f"  Temporal series     : {len(series_list)}")
    print(f"  Candidate pairs     : {candidate_pairs_count}")
    print(f"  Valid pairs         : {len(valid_pairs)}")
    print(f"  Rejected pairs      : {len(rejected_pairs)}")
    print(f"  Processing Time     : {elapsed:.2f} seconds")
    print("=" * 80)

    if valid_pairs:
        print("\nSample Valid Pairs:")
        for vp in valid_pairs[:3]:
            print(f"  - {vp.pair_id}:")
            print(f"      T1: {vp.earlier_observation.acquisition_time.isoformat()} ({vp.earlier_observation.sensor})")
            print(f"      T2: {vp.later_observation.acquisition_time.isoformat()} ({vp.later_observation.sensor})")
            print(f"      Separation: {vp.temporal_separation_days:.2f} days | Overlap IoU: {vp.spatial_overlap.overlap_ratio_iou:.3f}")
    elif candidate_pairs_count == 0 and result.valid_observations > 0:
        print("\n[NOTE]: Catalog contains observations from a single acquisition timestamp.")
        print("        Multiple multi-temporal scene acquisitions are required to form temporal pairs.")

    return 0


def main():
    print_banner()

    parser = argparse.ArgumentParser(description="ASTRA Temporal Catalog & Scene Pairing CLI")
    parser.add_argument(
        "--manifests-dir",
        type=str,
        default=str(settings.ASTRA_MANIFESTS_DIR / "tiles"),
        help="Path to tile manifests directory (default: data/manifests/tiles)",
    )
    parser.add_argument(
        "--scenes-dir",
        type=str,
        default=str(settings.ASTRA_MANIFESTS_DIR / "scenes"),
        help="Path to scene manifests directory (default: data/manifests/scenes)",
    )
    parser.add_argument(
        "--min-overlap",
        type=float,
        default=0.5,
        help="Minimum spatial overlap IoU ratio (default: 0.5)",
    )
    parser.add_argument(
        "--min-days",
        type=float,
        default=0.0,
        help="Minimum temporal separation in days (default: 0.0)",
    )
    parser.add_argument(
        "--max-days",
        type=float,
        default=None,
        help="Maximum temporal separation in days (default: None / unbounded)",
    )
    parser.add_argument(
        "--require-same-sensor",
        action="store_true",
        help="Reject cross-sensor observation pairs",
    )
    parser.add_argument(
        "--require-same-platform",
        action="store_true",
        help="Reject cross-platform observation pairs",
    )
    parser.add_argument(
        "--mode",
        choices=["adjacent", "all_pairwise"],
        default="adjacent",
        help="Pairing mode: 'adjacent' (default) or 'all_pairwise'",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Display detailed diagnostic logs",
    )

    args = parser.parse_args()

    sys.exit(
        build_catalog(
            manifests_dir=Path(args.manifests_dir),
            scenes_dir=Path(args.scenes_dir),
            min_overlap=args.min_overlap,
            min_days=args.min_days,
            max_days=args.max_days,
            require_same_sensor=args.require_same_sensor,
            require_same_platform=args.require_same_platform,
            mode=args.mode,
            verbose=args.verbose,
        )
    )


if __name__ == "__main__":
    main()
