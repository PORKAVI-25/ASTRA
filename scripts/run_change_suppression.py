"""ASTRA CLI: False-Alarm Suppression Engine (Phase M4D).

Screens candidate change regions against atmospheric, geometric, and radiometric
false-alarm artifacts. Produces an auditable SuppressionResult and a tri-state
filtered change mask GeoTIFF conforming to ASTRA-DC-v0.1.

Usage:
    python scripts/run_change_suppression.py --evidence-id evi_...
    python scripts/run_change_suppression.py --evidence-id evi_... --classification-id cls_...
    python scripts/run_change_suppression.py --evidence-file path/to/evidence.json
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
from backend.ml.change_classification import (
    ChangeClassificationEvidenceService,
    ChangeClassificationResult,
    ChangeEvidence,
)
from backend.ml.change_suppression import (
    ChangeSuppressionService,
    SuppressionConfig,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ASTRA False-Alarm Suppression Engine (Phase M4D)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--evidence-id",
        type=str,
        default=None,
        help="Identifier of existing M4C-A ChangeEvidence document (e.g. evi_...)",
    )
    parser.add_argument(
        "--classification-id",
        type=str,
        default=None,
        help="Optional identifier of M4C-B ChangeClassificationResult document (e.g. cls_...)",
    )
    parser.add_argument(
        "--evidence-file",
        type=str,
        default=None,
        help="Path to direct M4C-A ChangeEvidence JSON file",
    )
    parser.add_argument(
        "--classification-file",
        type=str,
        default=None,
        help="Path to direct M4C-B ChangeClassificationResult JSON file",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(settings.ASTRA_CHANGE_SUPPRESSION_DIR),
        help="Root directory for suppression artifacts",
    )
    parser.add_argument(
        "--provenance-dir",
        type=str,
        default=str(settings.ASTRA_MANIFESTS_DIR / "provenance"),
        help="Directory for immutable provenance records",
    )
    # Configuration overrides
    parser.add_argument(
        "--min-area",
        type=int,
        default=10,
        help="Minimum region pixel area to evaluate",
    )
    parser.add_argument(
        "--suppression-threshold",
        type=float,
        default=0.70,
        help="Composite risk threshold for flagging high-risk candidates",
    )
    parser.add_argument(
        "--flag-threshold",
        type=float,
        default=0.35,
        help="Composite risk threshold for flagging moderate-risk candidates",
    )
    parser.add_argument(
        "--cloud-min-reflectance",
        type=float,
        default=0.35,
        help="Minimum visible reflectance for cloud candidate",
    )
    parser.add_argument(
        "--cloud-whiteness-threshold",
        type=float,
        default=0.15,
        help="Maximum visible band deviation for cloud whiteness",
    )
    parser.add_argument(
        "--cloud-cirrus-threshold",
        type=float,
        default=0.015,
        help="Minimum Cirrus band reflectance for cloud confirmation",
    )
    parser.add_argument(
        "--snow-min-ndsi",
        type=float,
        default=0.40,
        help="Minimum NDSI index for snow/ice confirmation",
    )
    parser.add_argument(
        "--shadow-max-vis",
        type=float,
        default=0.10,
        help="Maximum visible reflectance for cloud shadow candidate",
    )
    parser.add_argument(
        "--shadow-max-nir",
        type=float,
        default=0.12,
        help="Maximum NIR reflectance for cloud shadow candidate",
    )
    parser.add_argument(
        "--edge-shear-gradient-threshold",
        type=float,
        default=0.15,
        help="Static edge gradient threshold for registration shear",
    )
    parser.add_argument(
        "--edge-shear-overlap-ratio",
        type=float,
        default=0.70,
        help="Minimum ratio of region overlapping high-gradient static edges",
    )
    parser.add_argument(
        "--edge-shear-max-width",
        type=float,
        default=2.0,
        help="Maximum minor axis width in pixels to qualify as edge shear",
    )
    parser.add_argument(
        "--local-contrast-margin",
        type=float,
        default=0.15,
        help="Local contrast margin protecting genuine change from soft penalty",
    )
    parser.add_argument(
        "--solar-azimuth",
        type=float,
        default=None,
        help="Optional solar azimuth in degrees for shadow directional validation",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw SuppressionResult JSON to stdout",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Enforce offline integrity: reject any remote URLs
    for path_str in (args.evidence_file, args.classification_file):
        if path_str and (path_str.startswith("http://") or path_str.startswith("https://")):
            print(f"Error: Remote URLs forbidden in offline mode: {path_str}", file=sys.stderr)
            sys.exit(1)

    evidence: ChangeEvidence = None
    classification: ChangeClassificationResult = None

    # Load ChangeEvidence
    if args.evidence_file:
        evi_path = Path(args.evidence_file)
        if not evi_path.exists():
            print(f"Error: Evidence file '{args.evidence_file}' not found.", file=sys.stderr)
            sys.exit(1)
        try:
            with open(evi_path, "r", encoding="utf-8") as f:
                evidence = ChangeEvidence.model_validate_json(f.read())
        except Exception as e:
            print(f"Error: Failed to parse evidence file '{args.evidence_file}': {e}", file=sys.stderr)
            sys.exit(1)
    elif args.evidence_id:
        evi_service = ChangeClassificationEvidenceService(
            output_dir=settings.ASTRA_CHANGE_CLASSIFICATION_DIR,
            provenance_dir=settings.ASTRA_MANIFESTS_DIR / "provenance",
        )
        evidence = evi_service.get_evidence(args.evidence_id)
        if evidence is None:
            print(f"Error: Evidence ID '{args.evidence_id}' not found in classification store.", file=sys.stderr)
            sys.exit(1)
    else:
        print("Error: Must specify either --evidence-id or --evidence-file.", file=sys.stderr)
        sys.exit(1)

    # Load ChangeClassificationResult (optional)
    if args.classification_file:
        cls_path = Path(args.classification_file)
        if not cls_path.exists():
            print(f"Error: Classification file '{args.classification_file}' not found.", file=sys.stderr)
            sys.exit(1)
        try:
            with open(cls_path, "r", encoding="utf-8") as f:
                classification = ChangeClassificationResult.model_validate_json(f.read())
        except Exception as e:
            print(f"Error: Failed to parse classification file '{args.classification_file}': {e}", file=sys.stderr)
            sys.exit(1)
    elif args.classification_id:
        evi_service = ChangeClassificationEvidenceService(
            output_dir=settings.ASTRA_CHANGE_CLASSIFICATION_DIR,
            provenance_dir=settings.ASTRA_MANIFESTS_DIR / "provenance",
        )
        classification = evi_service.get_classification(args.classification_id)
        if classification is None:
            print(f"Warning: Classification ID '{args.classification_id}' not found; proceeding without prior classifications.", file=sys.stderr)

    # Build configuration overrides
    config = SuppressionConfig(
        min_evaluation_area_px=args.min_area,
        suppression_threshold=args.suppression_threshold,
        flag_threshold=args.flag_threshold,
        cloud_min_reflectance=args.cloud_min_reflectance,
        cloud_whiteness_threshold=args.cloud_whiteness_threshold,
        cloud_cirrus_threshold=args.cloud_cirrus_threshold,
        snow_min_ndsi=args.snow_min_ndsi,
        shadow_max_vis_reflectance=args.shadow_max_vis,
        shadow_max_nir_reflectance=args.shadow_max_nir,
        edge_shear_gradient_threshold=args.edge_shear_gradient_threshold,
        edge_shear_overlap_ratio=args.edge_shear_overlap_ratio,
        edge_shear_max_width_px=args.edge_shear_max_width,
        local_contrast_retention_margin=args.local_contrast_margin,
    )

    auxiliary_data = {}
    if args.solar_azimuth is not None:
        auxiliary_data["solar_azimuth"] = args.solar_azimuth

    # Run false-alarm screening service
    suppression_service = ChangeSuppressionService(
        output_dir=Path(args.output_dir),
        provenance_dir=Path(args.provenance_dir),
    )

    try:
        result = suppression_service.suppress_false_alarms(
            evidence=evidence,
            classification=classification,
            config=config,
            auxiliary_data=auxiliary_data,
        )
    except Exception as e:
        print(f"Error during false-alarm screening execution: {e}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(result.model_dump_json(indent=2))
        return

    # Formatted terminal report
    print("\n" + "=" * 76)
    print("ASTRA False-Alarm Suppression Engine: Quality Assurance Layer (Phase M4D)")
    print("=" * 76)
    print(f"Suppression Result ID:  {result.suppression_id}")
    print(f"Evidence ID:            {result.evidence_id}")
    print(f"Classification ID:      {result.classification_id or 'None'}")
    print(f"Scene Pair ID:          {result.scene_pair_id}")
    print(f"Change Result ID:       {result.change_detection_result_id}")
    print(f"Suppressor ID:          {result.suppressor_id} (v{result.suppressor_version})")
    print(f"Provenance Record:      {result.provenance_id}")
    print(f"Filtered Change Mask:   {result.filtered_change_mask_path}")
    print("-" * 76)
    m = result.metrics
    print(f"Total Input Regions:    {m.total_input_regions}")
    print(f"Retained Regions:       {m.retained_count} ({m.retained_count / max(1, m.total_input_regions):.1%}) [Continues Downstream]")
    print(f"Flagged Regions:        {m.flagged_count} ({m.flagged_count / max(1, m.total_input_regions):.1%}) [Analyst Review]")
    print(f"Suppressed Regions:     {m.suppressed_count} ({m.suppression_rate:.1%}) [Filtered Artifacts]")
    print(f"Insufficient Evidence:  {m.insufficient_evidence_count} ({m.insufficient_evidence_count / max(1, m.total_input_regions):.1%}) [Data Limitations]")
    print(f"Total Area:             {m.total_area_px} px")
    print(f"  - Retained Area:      {m.retained_area_px} px")
    print(f"  - Flagged Area:       {m.flagged_area_px} px")
    print(f"  - Suppressed Area:    {m.suppressed_area_px} px")
    print("-" * 76)

    print("Artifact Breakdown (Primary Attribution):")
    if m.artifact_counts:
        for art_name, cnt in sorted(m.artifact_counts.items(), key=lambda x: x[1], reverse=True):
            bar = "#" * cnt
            print(f"  - {art_name:<30}: {cnt:>3} {bar}")
    else:
        print("  - None detected")
    print("-" * 76)

    print("Region Evaluation Summary:")
    for idx, reg in enumerate(result.regions, start=1):
        dec_tag = f"[{reg.decision.value.upper()}]"
        hard_tag = " (HARD GATED)" if reg.hard_triggered else ""
        print(f"[{idx:02d}] Region: {reg.region_id:<12} {dec_tag:<14}{hard_tag}")
        print(f"     Risk Index:       {reg.artifact_risk_score:.2f} ({reg.artifact_risk_interpretation})")
        print(f"     Basis:            {reg.decision_basis}")
        print(f"     Category:         {reg.original_category} -> {reg.retained_category} (Tier: {reg.confidence_tier_adjusted})")
        if reg.primary_attribution:
            print(f"     Primary Artifact: {reg.primary_attribution.value}")
        if reg.decision_reasons:
            print(f"     Reasons:          {'; '.join(reg.decision_reasons[:2])}")
        if reg.data_limitations:
            print(f"     Limitations:      {'; '.join(reg.data_limitations)}")
        print()

    print("=" * 76)
    print("NOTE: RETAINED does NOT mean verified ground truth;")
    print("      it means no sufficient false-alarm evidence detected.")
    print(f"Suppression artifacts persisted to: {Path(args.output_dir) / result.suppression_id}\n")


if __name__ == "__main__":
    main()
