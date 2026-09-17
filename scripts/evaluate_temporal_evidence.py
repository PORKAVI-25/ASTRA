"""ASTRA CLI: Temporal Evidence Reasoner (Phase M4E).

Evaluates candidate change support, persistence, and onset intervals across
multi-temporal satellite observations and upstream M4A/M4B/M4C/M4D artifact chains.

Usage:
    python scripts/evaluate_temporal_evidence.py --help
    python scripts/evaluate_temporal_evidence.py \
        --change-detection-id res_0001 \
        --scene-pair-id pair_0001 \
        --region-id reg_0001 \
        --series-file path/to/series.json \
        --discovery-suppression-file path/to/discovery_sup.json
"""

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

# Ensure repository root is in python path
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from backend.config import settings
from backend.ml.change.types import TemporalSeries
from backend.ml.change_suppression.service import ChangeSuppressionService
from backend.ml.change_suppression.types import SuppressionResult
from backend.ml.temporal_evidence import (
    CandidateRegionRef,
    PairwiseTemporalEvidenceInput,
    TemporalEvidenceConfig,
    TemporalEvidenceService,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ASTRA Temporal Evidence Reasoner Engine (Phase M4E)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Candidate Lineage Anchor
    parser.add_argument(
        "--change-detection-id",
        type=str,
        default=None,
        help="M4B ChangeDetectionResult ID where candidate was discovered (e.g. res_...)",
    )
    parser.add_argument(
        "--scene-pair-id",
        type=str,
        default=None,
        help="M4A ScenePair ID of discovery pair (e.g. pair_...)",
    )
    parser.add_argument(
        "--region-id",
        type=str,
        default=None,
        help="Locally unique region ID within M4B result (e.g. reg_0001)",
    )

    # TemporalSeries Inputs
    parser.add_argument(
        "--series-id",
        type=str,
        default=None,
        help="Identifier of existing TemporalSeries",
    )
    parser.add_argument(
        "--series-file",
        type=str,
        default=None,
        help="Path to direct TemporalSeries JSON file",
    )

    # Discovery Pair Evidence Inputs
    parser.add_argument(
        "--discovery-suppression-id",
        type=str,
        default=None,
        help="M4D SuppressionResult ID for discovery pair",
    )
    parser.add_argument(
        "--discovery-suppression-file",
        type=str,
        default=None,
        help="Path to direct discovery M4D SuppressionResult JSON file",
    )

    # Subsequent Pairwise Evidence Inputs
    parser.add_argument(
        "--pairwise-suppression-ids",
        nargs="*",
        default=[],
        help="List of M4D SuppressionResult IDs for subsequent evaluated scene pairs",
    )
    parser.add_argument(
        "--pairwise-suppression-files",
        nargs="*",
        default=[],
        help="List of paths to subsequent M4D SuppressionResult JSON files",
    )

    # Structured Manifest Bundle
    parser.add_argument(
        "--manifest",
        type=str,
        default=None,
        help="Path to JSON manifest containing complete multi-pair bundle and candidate ref",
    )

    # Output & Provenance Directories
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(settings.ASTRA_TEMPORAL_EVIDENCE_DIR),
        help="Directory to persist TemporalEvidenceResult JSON",
    )
    parser.add_argument(
        "--provenance-dir",
        type=str,
        default=str(settings.ASTRA_MANIFESTS_DIR / "provenance"),
        help="Directory to persist immutable ProvenanceRecord JSON",
    )

    # Configuration Hyperparameters
    parser.add_argument(
        "--min-persistent",
        type=int,
        default=2,
        help="Total supporting observations required for STRONG_TEMPORAL_SUPPORT",
    )
    parser.add_argument(
        "--min-support-threshold",
        type=float,
        default=0.45,
        help="Minimum M4E heuristic support score to assign support",
    )
    parser.add_argument(
        "--min-bbox-iou",
        type=float,
        default=0.30,
        help="Minimum metric-projected bbox IoU for spatial correspondence",
    )
    parser.add_argument(
        "--max-gap-days",
        type=float,
        default=90.0,
        help="Threshold in days triggering wide temporal gap warnings",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("================================================================================")
    print("           ASTRA TEMPORAL EVIDENCE REASONER CLI (Phase M4E)                     ")
    print("================================================================================")

    out_dir = Path(args.output_dir)
    prov_dir = Path(args.provenance_dir)
    service = TemporalEvidenceService(output_dir=out_dir, provenance_dir=prov_dir)
    supp_service = ChangeSuppressionService(
        output_dir=settings.ASTRA_CHANGE_SUPPRESSION_DIR,
        provenance_dir=prov_dir,
    )

    # 1. Parse manifest if provided
    if args.manifest:
        manifest_path = Path(args.manifest)
        if not manifest_path.exists():
            print(f"[ERROR] Manifest file not found: {manifest_path}", file=sys.stderr)
            return 1
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        candidate_ref = CandidateRegionRef.model_validate(data["candidate_ref"])
        series = TemporalSeries.model_validate(data["series"])
        discovery_pair = PairwiseTemporalEvidenceInput.model_validate(data["discovery_pair_evidence"])
        pairwise_list = [
            PairwiseTemporalEvidenceInput.model_validate(p)
            for p in data.get("pairwise_evidence", [])
        ]
    else:
        # Validate CLI parameters
        if not args.change_detection_id or not args.scene_pair_id or not args.region_id:
            print("[ERROR] Candidate reference (--change-detection-id, --scene-pair-id, --region-id) is required.", file=sys.stderr)
            return 1

        candidate_ref = CandidateRegionRef(
            change_detection_result_id=args.change_detection_id,
            scene_pair_id=args.scene_pair_id,
            region_id=args.region_id,
        )

        # Load TemporalSeries
        if args.series_file:
            sf_path = Path(args.series_file)
            if not sf_path.exists():
                print(f"[ERROR] Series file not found: {sf_path}", file=sys.stderr)
                return 1
            series = TemporalSeries.model_validate(json.loads(sf_path.read_text(encoding="utf-8")))
        else:
            print("[ERROR] Either --series-file or --manifest must be provided.", file=sys.stderr)
            return 1

        # Load Discovery Suppression Result
        disc_supp: Optional[SuppressionResult] = None
        if args.discovery_suppression_file:
            ds_path = Path(args.discovery_suppression_file)
            if not ds_path.exists():
                print(f"[ERROR] Discovery suppression file not found: {ds_path}", file=sys.stderr)
                return 1
            disc_supp = SuppressionResult.model_validate(json.loads(ds_path.read_text(encoding="utf-8")))
        elif args.discovery_suppression_id:
            disc_supp = supp_service.get_suppression_result(args.discovery_suppression_id)
            if disc_supp is None:
                print(f"[ERROR] Discovery SuppressionResult '{args.discovery_suppression_id}' not found in storage.", file=sys.stderr)
                return 1
        else:
            print("[ERROR] Either --discovery-suppression-id or --discovery-suppression-file is required.", file=sys.stderr)
            return 1

        discovery_pair = PairwiseTemporalEvidenceInput(
            scene_pair_id=disc_supp.scene_pair_id,
            change_detection_result_id=disc_supp.change_detection_result_id,
            evidence_id=disc_supp.evidence_id,
            classification_id=disc_supp.classification_id,
            suppression_id=disc_supp.suppression_id,
            suppression_result=disc_supp,
        )

        # Load Subsequent Pairwise Evidence
        pairwise_list = []
        for pf in args.pairwise_suppression_files:
            pf_path = Path(pf)
            if pf_path.exists():
                ps = SuppressionResult.model_validate(json.loads(pf_path.read_text(encoding="utf-8")))
                pairwise_list.append(
                    PairwiseTemporalEvidenceInput(
                        scene_pair_id=ps.scene_pair_id,
                        change_detection_result_id=ps.change_detection_result_id,
                        evidence_id=ps.evidence_id,
                        classification_id=ps.classification_id,
                        suppression_id=ps.suppression_id,
                        suppression_result=ps,
                    )
                )

        for pid in args.pairwise_suppression_ids:
            ps = supp_service.get_suppression_result(pid)
            if ps:
                pairwise_list.append(
                    PairwiseTemporalEvidenceInput(
                        scene_pair_id=ps.scene_pair_id,
                        change_detection_result_id=ps.change_detection_result_id,
                        evidence_id=ps.evidence_id,
                        classification_id=ps.classification_id,
                        suppression_id=ps.suppression_id,
                        suppression_result=ps,
                    )
                )

    config = TemporalEvidenceConfig(
        min_persistent_observations=args.min_persistent,
        min_support_score_threshold=args.min_support_threshold,
        min_bbox_iou_threshold=args.min_bbox_iou,
        max_temporal_gap_days=args.max_gap_days,
    )

    print(f"[*] Candidate Region   : {candidate_ref.canonical_id} (Discovery: {candidate_ref.scene_pair_id})")
    print(f"[*] Temporal Series    : {series.series_id} ({len(series.observations)} observations)")
    print(f"[*] Evaluated Pairs    : {1 + len(pairwise_list)} pair(s)")
    print(f"[*] Min Persistence    : {config.min_persistent_observations} supporting observations")
    print("[*] Executing offline temporal evidence evaluation...")

    try:
        result = service.evaluate_temporal_evidence(
            candidate_ref=candidate_ref,
            series=series,
            discovery_pair_evidence=discovery_pair,
            pairwise_evidence=pairwise_list,
            config=config,
        )
    except Exception as e:
        print(f"[ERROR] Temporal evidence evaluation failed: {str(e)}", file=sys.stderr)
        return 1

    print("\n--------------------------------------------------------------------------------")
    print(f"  Result ID            : {result.temporal_evidence_id}")
    print(f"  Provenance ID        : {result.provenance_id}")
    print(f"  Support Status       : {result.temporal_support_status.value}")
    print(f"  Confidence Tier      : {result.confidence_tier.value}")
    print(f"  Total Supporting Obs : {result.metrics.supporting_nodes_count} / {len(result.timeline_nodes)}")
    print(f"  Primary Category     : {result.category_evolution.primary_category.value}")
    print(f"  Category Evolution   : {' -> '.join(result.category_evolution.evolution_trajectory) or 'N/A'}")
    print(f"  Onset Interval Type  : {result.onset_estimate.interval_type.value}")
    if result.onset_estimate.physical_onset_interval:
        print(f"  Physical Onset       : {result.onset_estimate.physical_onset_interval}")
        print(f"  Observation Span     : {result.onset_estimate.display_bounding_span}")
        print(f"  Interval Days        : {result.onset_estimate.interval_days} days")
    print("--------------------------------------------------------------------------------\n")

    print("[Timeline Summary]")
    for n in result.timeline_nodes:
        print(f"  Epoch {n.acquisition_time.date().isoformat()} [{n.observation_id}] -> {n.node_status.value} (score={n.heuristic_support_score:.4f}, eligible={n.eligible_for_earliest_support})")

    print(f"\n[OK] TemporalEvidenceResult persisted to: {out_dir / result.temporal_evidence_id / 'temporal_evidence.json'}")
    print(f"[OK] ProvenanceRecord persisted to: {prov_dir / f'{result.provenance_id}.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
