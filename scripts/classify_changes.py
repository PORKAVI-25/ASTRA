"""ASTRA CLI: Change-Type Classifier (Phase M4C-B).

Consumes M4C-A ChangeEvidence and executes deterministic, explainable
change-type classification into semantic categories:
construction, clearance, water_extent_change, road_development, and unknown.
Conforms to ASTRA-DC-v0.1.

Usage:
    python scripts/classify_changes.py --evidence-id evi_...
    python scripts/classify_changes.py --result-id res_chg_... --earlier data/t1.tif --later data/t2.tif
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
    ClassifierConfig,
    EvidenceConfig,
)
from backend.ml.change_detection import ChangeDetectionService
from geospatial.contracts import GeoBoundingBox


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ASTRA Change-Type Classifier (Phase M4C-B)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--evidence-id",
        type=str,
        default=None,
        help="Identifier of existing M4C-A ChangeEvidence document (e.g. evi_...)",
    )
    parser.add_argument(
        "--result-id",
        type=str,
        default=None,
        help="Identifier of M4B ChangeDetectionResult if extracting evidence first",
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
        "--output-dir",
        type=str,
        default=str(settings.ASTRA_CHANGE_CLASSIFICATION_DIR),
        help="Root directory for classification artifacts",
    )
    parser.add_argument(
        "--provenance-dir",
        type=str,
        default=str(settings.ASTRA_MANIFESTS_DIR / "provenance"),
        help="Directory for immutable provenance records",
    )
    parser.add_argument(
        "--min-area",
        type=int,
        default=10,
        help="Minimum region pixel count to classify",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.45,
        help="Minimum evidence score threshold",
    )
    parser.add_argument(
        "--margin",
        type=float,
        default=0.15,
        help="Ambiguity margin threshold between top candidates",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw classification JSON to stdout",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Security check: Prohibit remote URLs
    for path_str in (args.earlier, args.later):
        if path_str and (path_str.startswith("http://") or path_str.startswith("https://")):
            print(f"Error: Remote URLs forbidden in offline mode: {path_str}", file=sys.stderr)
            sys.exit(1)

    service = ChangeClassificationEvidenceService(
        output_dir=Path(args.output_dir),
        provenance_dir=Path(args.provenance_dir),
    )

    evidence = None

    if args.evidence_id:
        evidence = service.get_evidence(args.evidence_id)
        if evidence is None:
            print(f"Error: Change evidence '{args.evidence_id}' not found in {args.output_dir}", file=sys.stderr)
            sys.exit(1)
    elif args.result_id:
        cd_service = ChangeDetectionService()
        change_res = cd_service.get_result(args.result_id)
        if change_res is None:
            print(f"Error: Change detection result '{args.result_id}' not found.", file=sys.stderr)
            sys.exit(1)

        # Mock minimal scene pair if not provided
        t1_time = change_res.created_at
        t2_time = change_res.created_at
        obs1 = TemporalObservation(
            observation_id=f"obs_earlier_{args.result_id}",
            scene_id="earlier_scene",
            acquisition_time=t1_time,
            sensor="unknown",
            platform="unknown",
            crs="EPSG:4326",
            bounds_wgs84=GeoBoundingBox(min_lon=0.0, min_lat=0.0, max_lon=1.0, max_lat=1.0),
            source_hash="0" * 64,
            is_synthetic=True,
        )
        obs2 = TemporalObservation(
            observation_id=f"obs_later_{args.result_id}",
            scene_id="later_scene",
            acquisition_time=t2_time,
            sensor="unknown",
            platform="unknown",
            crs="EPSG:4326",
            bounds_wgs84=GeoBoundingBox(min_lon=0.0, min_lat=0.0, max_lon=1.0, max_lat=1.0),
            source_hash="0" * 64,
            is_synthetic=True,
        )
        pair = ScenePair(
            pair_id=change_res.scene_pair_id,
            earlier_observation=obs1,
            later_observation=obs2,
            temporal_separation_seconds=1.0,
            temporal_separation_days=1.0 / 86400.0,
            spatial_overlap=SpatialOverlap(intersection_bounds=None, earlier_area_deg2=1.0, later_area_deg2=1.0, is_overlapping=True),
            compatibility=PairCompatibility(is_compatible=True, status=PairCompatibilityStatus.COMPATIBLE),
        )

        evidence = service.extract_evidence(
            scene_pair=pair,
            change_result=change_res,
            earlier_image=args.earlier,
            later_image=args.later,
        )
    else:
        print("Error: Must specify either --evidence-id or --result-id.", file=sys.stderr)
        sys.exit(1)

    # Classify evidence
    config = ClassifierConfig(
        min_classification_area_px=args.min_area,
        min_evidence_score_threshold=args.min_score,
        ambiguity_margin_threshold=args.margin,
    )

    classification = service.classify_evidence(evidence, config=config)

    if args.json:
        print(classification.model_dump_json(indent=2))
        return

    # Formatted terminal report
    print("\n" + "=" * 70)
    print("ASTRA Change-Type Classification: Semantic Decision Layer (M4C-B)")
    print("=" * 70)
    print(f"Classification ID:   {classification.classification_id}")
    print(f"Evidence ID:         {classification.evidence_id}")
    print(f"Scene Pair ID:       {classification.scene_pair_id}")
    print(f"Change Result ID:    {classification.change_detection_result_id}")
    print(f"Classifier:          {classification.classifier_id} (v{classification.classifier_version})")
    print(f"Provenance ID:       {classification.provenance_id}")
    print("-" * 70)
    m = classification.metrics
    print(f"Total Regions:       {m.total_regions}")
    print(f"High Confidence:     {m.high_confidence_count}")
    print(f"Ambiguous Regions:   {m.ambiguous_count}")
    print(f"Unknown Fraction:    {m.unclassified_unknown_fraction:.1%}")
    print("\nCategory Distribution:")
    for cat_name, cnt in m.category_counts.items():
        bar = "#" * cnt
        print(f"  - {cat_name:<20}: {cnt:>3} {bar}")
    print("-" * 70)

    print("\nRegional Semantic Classifications:")
    for idx, reg_cls in enumerate(classification.classifications, start=1):
        ambig_flag = " [AMBIGUOUS]" if reg_cls.is_ambiguous else ""
        print(f"[{idx:02d}] Region: {reg_cls.region_id}")
        print(f"     Category:     {reg_cls.category.value.upper()}{ambig_flag}")
        print(f"     Confidence:   {reg_cls.confidence_tier.value.upper()}")
        print(f"     Score:        {reg_cls.evidence_score:.2f}")
        print(f"     Reason:       {reg_cls.decision_reason}")
        if reg_cls.conflicting_categories:
            print(f"     Conflicts:    {', '.join(reg_cls.conflicting_categories)}")
        if reg_cls.data_limitations:
            print(f"     Limitations:  {'; '.join(reg_cls.data_limitations)}")
        print()
    print("=" * 70)
    print(f"Result saved to: {Path(args.output_dir) / classification.classification_id / 'classification.json'}\n")


if __name__ == "__main__":
    main()
