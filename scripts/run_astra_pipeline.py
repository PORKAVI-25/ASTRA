"""ASTRA End-to-End Pipeline Investigation Runner (Phase M4F-C/D).

Executes a deterministic, fully offline multi-epoch satellite change investigation
through the integrated ASTRA pipeline orchestrator. Produces an analyst investigation
dossier conforming to ASTRA-DC-v0.1 with terminal reporting.

Usage:
    # Auto-detect or generate demo dataset and run with baseline pairing:
    python scripts/run_astra_pipeline.py

    # Specify explicit canonical entities and pairing strategy:
    python scripts/run_astra_pipeline.py \\
        --series-id series_grid_lon77.33_lat13.08_c0000_r0000_z14 \\
        --discovery-pair-id pair_obs_tile_...__obs_tile_... \\
        --candidate-region-id reg_0001 \\
        --pairing-strategy baseline

    # Run with adjacent pairing:
    python scripts/run_astra_pipeline.py --pairing-strategy adjacent
"""

import argparse
import json
from pathlib import Path
import sys
from typing import Optional

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import settings
from backend.ml.change.temporal_catalog import TemporalCatalog
from backend.ml.change_classification.types import EvidenceConfig
from backend.ml.change_detection.service import ChangeDetectionService
from backend.orchestrator.service import ASTRAPipelineOrchestrator
from backend.orchestrator.types import InvestigationDossier, InvestigationRequest
from scripts.generate_demo_dataset import generate_and_ingest_demo_dataset


def render_terminal_dossier(dossier: InvestigationDossier) -> None:
    """Renders a structured terminal report for the investigation dossier."""
    te = dossier.temporal_evidence
    if not te:
        print(f"[ERROR] Dossier {dossier.investigation_id} contains no temporal evidence result.")
        return

    onset = te.onset_estimate
    cat_evo = te.category_evolution
    metrics = te.metrics
    lineage = dossier.lineage

    print("\n" + "=" * 78)
    print("                      ASTRA ANALYST INVESTIGATION DOSSIER                      ")
    print("         Conforming to ASTRA-DC-v0.1 | Full-Provenance Multi-Temporal         ")
    print("=" * 78)

    # 1. Executive Summary
    print("\n" + "-" * 78)
    print(" 1. EXECUTIVE INVESTIGATION SUMMARY")
    print("-" * 78)
    print(f"  Investigation ID       : {dossier.investigation_id}")
    print(f"  Investigation Status   : {dossier.status}")
    print(f"  Temporal Support Status: {te.temporal_support_status.value}")
    print(f"  Confidence Tier        : {te.confidence_tier.value.upper()}")
    print(f"  Target Series ID       : {dossier.series_id}")
    print(f"  Pairing Strategy       : {dossier.request.pairing_strategy}")
    print(f"  Deterministic Timestamp: {dossier.created_at.isoformat()}")
    print(f"  Dossier Content Hash   : {dossier.content_hash}")
    print(f"  Provenance Record ID   : {dossier.provenance_id}")

    # 2. Target Candidate Profile
    print("\n" + "-" * 78)
    print(" 2. TARGET CANDIDATE PROFILE")
    print("-" * 78)
    print(f"  Candidate Region ID    : {dossier.candidate_region_id}")
    print(f"  Discovery Pair ID      : {dossier.discovery_pair_id}")
    print(f"  Primary Category       : {cat_evo.primary_category.value}")
    print(f"  Trajectory Validation  : {'VALID' if cat_evo.is_evolution_valid else 'INVALID'}")
    print(f"  Conflicted Status      : {'CONFLICTED' if cat_evo.is_conflicted else 'NONE'}")
    if cat_evo.evolution_trajectory:
        print(f"  Evolution Sequence     : {' -> '.join(cat_evo.evolution_trajectory)}")

    # 3. Spatial Correspondence Tracking
    print("\n" + "-" * 78)
    print(" 3. MULTI-EPOCH SPATIAL CORRESPONDENCE TRACKING")
    print("-" * 78)
    if lineage.candidate_correspondence:
        for pair_id, c_data in lineage.candidate_correspondence.items():
            matched_id = c_data.get("matched_region_id") or "NONE"
            status = c_data.get("status", "UNKNOWN")
            rel = c_data.get("relationship", "UNKNOWN")
            iou = c_data.get("metric_iou")
            dist = c_data.get("centroid_distance_m")
            iou_str = f"{iou:.3f}" if iou is not None else "N/A"
            dist_str = f"{dist:.2f}m" if dist is not None else "N/A"
            print(f"  Subsequent Pair: {pair_id[:48]}...")
            print(f"    - Matched Region ID : {matched_id}")
            print(f"    - Geometry Status   : {status}")
            print(f"    - Relationship      : {rel}")
            print(f"    - Metric IoU / Dist : IoU={iou_str}, Dist={dist_str}")
            if c_data.get("resolution_notes"):
                print(f"    - Notes             : {c_data['resolution_notes']}")
    else:
        print("  (No subsequent pairs evaluated)")

    # 4. Chronological Timeline Nodes
    print("\n" + "-" * 78)
    print(" 4. CHRONOLOGICAL TIMELINE NODES")
    print("-" * 78)
    header = f"  {'Idx':<4} {'Date':<11} {'Observation ID':<36} {'Status':<22} {'M4D':<10} {'Category':<14}"
    print(header)
    print("  " + "-" * 74)
    for idx, node in enumerate(te.timeline_nodes, start=1):
        d_str = node.acquisition_time.strftime("%Y-%m-%d")
        obs_trunc = node.observation_id[:34] + ".." if len(node.observation_id) > 36 else node.observation_id
        st_str = node.node_status.value
        m4d_str = node.m4d_decision.value if node.m4d_decision else "N/A"
        cat_str = node.category_observed.value if node.category_observed else "N/A"
        print(f"  {idx:<4} {d_str:<11} {obs_trunc:<36} {st_str:<22} {m4d_str:<10} {cat_str:<14}")
        for r in node.decision_reasons:
            print(f"       * Reason: {r}")

    # 5. Temporal Onset & Evolution Estimate
    print("\n" + "-" * 78)
    print(" 5. TEMPORAL ONSET & EVOLUTION ESTIMATE")
    print("-" * 78)
    t_earliest = onset.earliest_support_date.strftime("%Y-%m-%d %H:%M UTC") if onset.earliest_support_date else "None"
    t_pre = onset.pre_change_date.strftime("%Y-%m-%d %H:%M UTC") if onset.pre_change_date else "None"
    span_str = f"{onset.interval_days:.1f} days" if onset.interval_days is not None else "N/A"
    print(f"  Onset Interval Type    : {onset.interval_type.value}")
    print(f"  Pre-Change Absence     : {t_pre}")
    print(f"    - Observation ID     : {onset.pre_change_observation_id or 'None'}")
    print(f"  Earliest Supporting Obs: {t_earliest}")
    print(f"    - Observation ID     : {onset.earliest_support_observation_id or 'None'}")
    print(f"  Sampling Interval Span : {span_str}")
    print(f"  Supporting Nodes Count : {metrics.supporting_nodes_count} / {metrics.evaluated_nodes_count}")
    print(f"  Flagged Nodes Count    : {metrics.flagged_nodes_count}")
    print(f"  Suppressed Nodes Count : {metrics.suppressed_nodes_count}")
    print(f"  Absence Nodes Count    : {metrics.absence_nodes_count}")
    print(f"  Total In Series        : {metrics.total_observations_in_series}")

    # 6. Upstream Lineage & Provenance Chain
    print("\n" + "-" * 78)
    print(" 6. UPSTREAM LINEAGE & PROVENANCE CHAIN")
    print("-" * 78)
    print(f"  Evaluated Scene Pairs  : {len(lineage.scene_pair_ids)}")
    for i, pair_id in enumerate(lineage.scene_pair_ids):
        cd_id = lineage.change_detection_result_ids[i] if i < len(lineage.change_detection_result_ids) else "N/A"
        ev_id = lineage.evidence_ids[i] if i < len(lineage.evidence_ids) else "N/A"
        cl_id = lineage.classification_ids[i] if i < len(lineage.classification_ids) else "N/A"
        sp_id = lineage.suppression_ids[i] if i < len(lineage.suppression_ids) else "N/A"
        print(f"  [Pair {i+1}] {pair_id}")
        print(f"    |-- M4B Change Detection : {cd_id}")
        print(f"    |-- M4C-A Evidence       : {ev_id}")
        print(f"    |-- M4C-B Classification : {cl_id}")
        print(f"    \\-- M4D Suppression      : {sp_id}")
    print(f"  [Final] M4E Temporal Reasoner: {lineage.temporal_evidence_id}")
    print(f"  Upstream Input Hashes Tracked: {len(lineage.upstream_hashes)} hashes")

    # 7. Overall Decision Reasons & Limitations
    print("\n" + "-" * 78)
    print(" 7. REASONING AUDIT TRAIL & LIMITATIONS")
    print("-" * 78)
    print("  Decision Reasons:")
    for dr in te.decision_reasons:
        print(f"    [+] {dr}")
    if te.evidence_limitations:
        print("  Limitations / Quality Notes:")
        for lm in te.evidence_limitations:
            print(f"    [!] {lm}")

    # 8. Saved Artifacts
    print("\n" + "-" * 78)
    print(" 8. SAVED DOSSIER ARTIFACTS")
    print("-" * 78)
    print(f"  Dossier JSON Path      : {dossier.dossier_path}")
    print(f"  Content Verification   : SHA256({dossier.content_hash})")
    print("=" * 78 + "\n")


def run_investigation_pipeline(
    series_id: Optional[str] = None,
    discovery_pair_id: Optional[str] = None,
    candidate_region_id: Optional[str] = None,
    output_dir: Optional[str] = None,
    pairing_strategy: str = "baseline",
    band_mapping: Optional[dict] = None,
    manifests_dir: Optional[Path] = None,
    force_generate: bool = False,
) -> InvestigationDossier:
    """Resolves inputs, executes the orchestrator, and returns the dossier."""
    manifests_path = manifests_dir or settings.ASTRA_MANIFESTS_DIR
    catalog = TemporalCatalog()
    disc = catalog.discover_manifests(
        tiles_dir=manifests_path / "tiles",
        scenes_dir=manifests_path / "scenes",
    )

    # If demo dataset is missing or regeneration requested, run generator
    demo_series_candidates = [
        s for s in catalog.list_series()
        if s.observation_count >= 4 and any("demo_synthetic" in obs.scene_id for obs in s.observations)
    ]

    if force_generate or not demo_series_candidates:
        print("[INFO] Demo dataset not found or regeneration requested. Generating demo dataset...")
        demo_info = generate_and_ingest_demo_dataset(
            output_dir=settings.ASTRA_RAW_DIR / "demo",
            manifests_dir=manifests_path,
            processed_dir=settings.ASTRA_PROCESSED_DIR,
            force=True,
        )
        # Rediscover
        catalog = TemporalCatalog()
        catalog.discover_manifests(
            tiles_dir=manifests_path / "tiles",
            scenes_dir=manifests_path / "scenes",
        )
        if not series_id:
            series_id = demo_info["series_id"]
        if not discovery_pair_id:
            discovery_pair_id = demo_info["discovery_pair_id"]
        if not candidate_region_id:
            candidate_region_id = demo_info["candidate_region_id"]

    # If series_id still not provided, pick first available series
    if not series_id:
        series_candidates = [
            s for s in catalog.list_series()
            if s.observation_count >= 4 and any("demo_synthetic" in obs.scene_id for obs in s.observations)
        ]
        if not series_candidates:
            series_candidates = [s for s in catalog.list_series() if s.observation_count >= 2]
        if not series_candidates:
            raise RuntimeError("No valid TemporalSeries found in catalog.")
        series = series_candidates[0]
        series_id = series.series_id
    else:
        series = catalog.get_series(series_id)
        if not series:
            raise ValueError(f"Requested series '{series_id}' not found in catalog.")

    # Resolve discovery pair and candidate region if not provided
    if not discovery_pair_id or not candidate_region_id:
        valid_pairs, _ = catalog.generate_pairs(mode="all_pairwise")
        series_obs_ids = {obs.observation_id for obs in series.observations}
        series_pairs = [
            p for p in valid_pairs
            if p.earlier_observation.observation_id in series_obs_ids
            and p.later_observation.observation_id in series_obs_ids
        ]
        if not series_pairs:
            raise RuntimeError(f"No valid pairs could be generated for series '{series_id}'.")

        # Pick earliest pair (T1 -> T2)
        disc_pair = series_pairs[0]
        if not discovery_pair_id:
            discovery_pair_id = disc_pair.pair_id

        if not candidate_region_id:
            cd_service = ChangeDetectionService(
                output_dir=settings.ASTRA_CHANGE_RESULTS_DIR,
                provenance_dir=manifests_path / "provenance",
            )
            cdr = cd_service.run_detection(pair=disc_pair)
            if not cdr.regions:
                raise RuntimeError(f"No change regions detected in discovery pair '{discovery_pair_id}'.")
            # Pick construction candidate region around (200, 200) if present, else first region
            target_reg = next(
                (r for r in cdr.regions if 190 <= r.bbox_px[0] <= 210 and 190 <= r.bbox_px[1] <= 210),
                cdr.regions[0],
            )
            candidate_region_id = target_reg.region_id

    evidence_cfg = None
    if band_mapping:
        evidence_cfg = EvidenceConfig(band_mapping=band_mapping)
    else:
        # Default Sentinel-2 RGB band index mapping for chipped tiles
        evidence_cfg = EvidenceConfig(band_mapping={"red": 0, "green": 1, "blue": 2})

    request = InvestigationRequest(
        series_id=series_id,
        discovery_pair_id=discovery_pair_id,
        candidate_region_id=candidate_region_id,
        output_dir=output_dir,
        pairing_strategy=pairing_strategy,
        evidence_config=evidence_cfg,
    )

    orchestrator = ASTRAPipelineOrchestrator(
        catalog=catalog,
        output_dir=Path(output_dir) if output_dir else settings.ASTRA_PROCESSED_DIR / "investigations",
        provenance_dir=manifests_path / "provenance",
    )

    dossier = orchestrator.run_investigation(request)
    return dossier


def main():
    parser = argparse.ArgumentParser(
        description="ASTRA End-to-End Pipeline Investigation Runner (Phase M4F-C/D)"
    )
    parser.add_argument(
        "--series-id",
        type=str,
        default=None,
        help="Canonical TemporalSeries identifier (auto-detected if omitted)",
    )
    parser.add_argument(
        "--discovery-pair-id",
        type=str,
        default=None,
        help="Canonical ScenePair identifier for discovery epoch (auto-detected if omitted)",
    )
    parser.add_argument(
        "--candidate-region-id",
        type=str,
        default=None,
        help="Candidate change region identifier (e.g. reg_0001, auto-detected if omitted)",
    )
    parser.add_argument(
        "--pairing-strategy",
        type=str,
        choices=["baseline", "adjacent"],
        default="baseline",
        help="Pairing strategy for subsequent observations: 'baseline' (recommended for persistence) or 'adjacent'",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(settings.ASTRA_PROCESSED_DIR / "investigations"),
        help="Directory to persist investigation dossier artifacts",
    )
    parser.add_argument(
        "--band-mapping",
        type=str,
        default=None,
        help='JSON string specifying semantic band indices (e.g. \'{"red": 0, "green": 1, "blue": 2}\')',
    )
    parser.add_argument(
        "--manifests-dir",
        type=str,
        default=str(settings.ASTRA_MANIFESTS_DIR),
        help="Manifests root directory (default: data/manifests)",
    )
    parser.add_argument(
        "--force-generate",
        action="store_true",
        help="Force regeneration of demo dataset before running investigation",
    )

    args = parser.parse_args()

    band_map = None
    if args.band_mapping:
        band_map = json.loads(args.band_mapping)

    dossier = run_investigation_pipeline(
        series_id=args.series_id,
        discovery_pair_id=args.discovery_pair_id,
        candidate_region_id=args.candidate_region_id,
        output_dir=args.output_dir,
        pairing_strategy=args.pairing_strategy,
        band_mapping=band_map,
        manifests_dir=Path(args.manifests_dir),
        force_generate=args.force_generate,
    )

    render_terminal_dossier(dossier)


if __name__ == "__main__":
    main()
