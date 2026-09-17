"""ASTRA Phase M4E: Trajectory, Category Evolution & Onset Reasoner.

Assembles chronological timeline nodes, determines earliest supporting observation,
evaluates total supporting persistence counts, bounds onset intervals strictly as half-open,
and audits category continuity without modifying upstream classifications.
"""

from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

from backend.ml.change_classification.types import ChangeCategory
from backend.ml.temporal_evidence.types import (
    CandidateRegionRef,
    TemporalCategoryEvolution,
    TemporalConfidenceTier,
    TemporalEvidenceConfig,
    TemporalEvidenceMetrics,
    TemporalEvidenceNode,
    TemporalIntervalType,
    TemporalNodeStatus,
    TemporalOnsetEstimate,
    TemporalSupportStatus,
)


def analyze_category_evolution(
    timeline_nodes: List[TemporalEvidenceNode],
    default_category: ChangeCategory = ChangeCategory.UNKNOWN,
) -> TemporalCategoryEvolution:
    """Audits semantic category progression across chronological timeline nodes.

    M4E NEVER classifies imagery; it inspects upstream M4C-B categories.
    Valid transitions:
    - 'unknown' -> known category (early disturbance precedes morphology)
    - 'clearance' -> 'construction' (site preparation precedes structure)
    - identical categories (persistent)
    Contradictory persistent categories (e.g. water vs road) flag TEMPORALLY_AMBIGUOUS.
    """
    categories_observed: List[Tuple[datetime, ChangeCategory]] = []
    for node in timeline_nodes:
        if (
            node.node_status in (TemporalNodeStatus.EARLIEST_SUPPORTING, TemporalNodeStatus.PERSISTENT_SUPPORT, TemporalNodeStatus.FLAGGED_SUPPORT)
            and node.category_observed is not None
        ):
            categories_observed.append((node.acquisition_time, node.category_observed))

    if not categories_observed:
        return TemporalCategoryEvolution(
            earliest_observed_category=None,
            latest_observed_category=None,
            primary_category=default_category,
            is_evolution_valid=True,
            is_conflicted=False,
            evolution_trajectory=[],
            audit_notes=["No semantic change categories observed in supporting nodes."],
        )

    earliest_cat = categories_observed[0][1]
    latest_cat = categories_observed[-1][1]

    trajectory: List[str] = [cat.value for _, cat in categories_observed]

    # Category frequency
    counts: Dict[ChangeCategory, int] = {}
    for _, cat in categories_observed:
        counts[cat] = counts.get(cat, 0) + 1

    # Dominant category
    primary_cat = max(counts.keys(), key=lambda c: counts[c])

    # Check for valid physical transitions
    distinct_cats = list(dict.fromkeys(trajectory))
    is_valid = True
    is_conflicted = False
    notes: List[str] = []

    if len(distinct_cats) > 1:
        notes.append(f"Category progression observed: {' -> '.join(distinct_cats)}.")
        for i in range(len(distinct_cats) - 1):
            c1 = distinct_cats[i]
            c2 = distinct_cats[i + 1]

            if c1 == "unknown":
                notes.append(f"Valid evolution: surface disturbance detected before {c2} structural features emerged.")
            elif c1 == "clearance" and c2 == "construction":
                notes.append("Valid evolution: vegetation clearance followed by building construction.")
            elif (c1 == "water_extent_change" and c2 in ("construction", "road_development")) or (
                c2 == "water_extent_change" and c1 in ("construction", "road_development")
            ):
                is_conflicted = True
                is_valid = False
                notes.append(f"Conflicting persistent categories '{c1}' and '{c2}' co-occur on the same spatial footprint.")
            else:
                notes.append(f"Logged category transition from '{c1}' to '{c2}'.")

    return TemporalCategoryEvolution(
        earliest_observed_category=earliest_cat,
        latest_observed_category=latest_cat,
        primary_category=primary_cat,
        is_evolution_valid=is_valid,
        is_conflicted=is_conflicted,
        evolution_trajectory=trajectory,
        audit_notes=notes,
    )


def assemble_timeline_and_trajectory(
    nodes: List[TemporalEvidenceNode],
    candidate_ref: CandidateRegionRef,
    config: TemporalEvidenceConfig,
    total_series_observations: int,
) -> Tuple[
    List[TemporalEvidenceNode],
    TemporalSupportStatus,
    TemporalConfidenceTier,
    TemporalOnsetEstimate,
    TemporalCategoryEvolution,
    TemporalEvidenceMetrics,
    List[str],
    List[str],
]:
    """Assembles chronological timeline, determines earliest support, onset interval, and metrics."""
    decision_reasons: List[str] = []
    limitations: List[str] = []

    # Sort nodes chronologically
    sorted_nodes = sorted(nodes, key=lambda n: n.acquisition_time)

    # 1. Select chronologically earliest eligible supporting node
    earliest_node: Optional[TemporalEvidenceNode] = None
    earliest_idx: Optional[int] = None

    for i, node in enumerate(sorted_nodes):
        if node.eligible_for_earliest_support:
            earliest_node = node
            earliest_idx = i
            break

    # Reclassify nodes relative to earliest supporting node
    if earliest_node is not None and earliest_idx is not None:
        earliest_node.node_status = TemporalNodeStatus.EARLIEST_SUPPORTING
        decision_reasons.append(
            f"Observation '{earliest_node.observation_id}' ({earliest_node.acquisition_time.date().isoformat()}) "
            f"establishes earliest supporting evidence (M4D RETAINED, score={earliest_node.heuristic_support_score:.4f})."
        )

        # Subsequent nodes that satisfy support threshold become PERSISTENT_SUPPORT
        for j in range(earliest_idx + 1, len(sorted_nodes)):
            sub_node = sorted_nodes[j]
            if sub_node.eligible_for_earliest_support:
                sub_node.node_status = TemporalNodeStatus.PERSISTENT_SUPPORT
            elif sub_node.node_status == TemporalNodeStatus.EARLIEST_SUPPORTING:
                sub_node.node_status = TemporalNodeStatus.PERSISTENT_SUPPORT

    # 2. Compute total supporting observations
    supporting_nodes = [
        n for n in sorted_nodes
        if n.node_status in (TemporalNodeStatus.EARLIEST_SUPPORTING, TemporalNodeStatus.PERSISTENT_SUPPORT)
    ]
    n_support = len(supporting_nodes)

    # 3. Category evolution analysis
    cat_evolution = analyze_category_evolution(sorted_nodes)
    if cat_evolution.is_conflicted:
        decision_reasons.append("Conflicting persistent semantic categories co-occur on the candidate footprint.")

    # 4. Determine overall TemporalSupportStatus
    if cat_evolution.is_conflicted:
        support_status = TemporalSupportStatus.TEMPORALLY_AMBIGUOUS
    elif n_support >= config.min_persistent_observations:
        support_status = TemporalSupportStatus.STRONG_TEMPORAL_SUPPORT
        decision_reasons.append(
            f"Candidate confirmed with STRONG_TEMPORAL_SUPPORT across {n_support} supporting observations "
            f"(threshold={config.min_persistent_observations})."
        )
    elif n_support == 1:
        support_status = TemporalSupportStatus.SINGLE_OBSERVATION_SUPPORT
        decision_reasons.append(
            "Candidate supported at only 1 observation (earliest supporting) with no persistent subsequent support."
        )
    else:
        # Check if any FLAGGED nodes exist
        flagged_nodes = [n for n in sorted_nodes if n.node_status == TemporalNodeStatus.FLAGGED_SUPPORT]
        if flagged_nodes:
            support_status = TemporalSupportStatus.FLAGGED_PENDING_REVIEW
            decision_reasons.append(
                f"Earliest potential evidence carries M4D FLAGGED status across {len(flagged_nodes)} observation(s); "
                f"unresolved artifact risk requires analyst review."
            )
        else:
            insufficient_nodes = [n for n in sorted_nodes if n.node_status == TemporalNodeStatus.INSUFFICIENT_DATA]
            if len(insufficient_nodes) == len(sorted_nodes):
                support_status = TemporalSupportStatus.INSUFFICIENT_DATA
                decision_reasons.append("Series contains insufficient usable data across all evaluated observations.")
            else:
                support_status = TemporalSupportStatus.NO_SUPPORT
                decision_reasons.append("Zero observations in the series provide valid supporting evidence.")

    # 5. Onset interval estimation (BOUNDED_HALF_OPEN)
    pre_node: Optional[TemporalEvidenceNode] = None
    if earliest_idx is not None:
        # Search backwards for latest confirmed PRE_CHANGE_ABSENCE node
        for k in range(earliest_idx - 1, -1, -1):
            cand_pre = sorted_nodes[k]
            if cand_pre.node_status == TemporalNodeStatus.PRE_CHANGE_ABSENCE:
                pre_node = cand_pre
                break

    # Check for provisional flagged nodes preceding earliest support
    provisional_flagged_id: Optional[str] = None
    provisional_flagged_date: Optional[datetime] = None
    if earliest_idx is not None:
        for k in range(earliest_idx):
            if sorted_nodes[k].node_status == TemporalNodeStatus.FLAGGED_SUPPORT:
                provisional_flagged_id = sorted_nodes[k].observation_id
                provisional_flagged_date = sorted_nodes[k].acquisition_time
                limitations.append(
                    f"Observation '{provisional_flagged_id}' preceded earliest support with FLAGGED status. "
                    f"Earliest support deferred to '{earliest_node.observation_id}'."
                )
                break

    if earliest_node is not None:
        t_earliest = earliest_node.acquisition_time
        earliest_id = earliest_node.observation_id

        if pre_node is not None:
            t_pre = pre_node.acquisition_time
            pre_id = pre_node.observation_id
            delta_days = round((t_earliest - t_pre).total_seconds() / 86400.0, 2)
            onset_estimate = TemporalOnsetEstimate(
                pre_change_observation_id=pre_id,
                pre_change_date=t_pre,
                earliest_support_observation_id=earliest_id,
                earliest_support_date=t_earliest,
                interval_days=delta_days,
                provisional_flagged_observation_id=provisional_flagged_id,
                provisional_flagged_date=provisional_flagged_date,
                interval_type=TemporalIntervalType.BOUNDED_HALF_OPEN,
                display_bounding_span=f"[{t_pre.date().isoformat()}, {t_earliest.date().isoformat()}]",
                physical_onset_interval=f"({t_pre.date().isoformat()}, {t_earliest.date().isoformat()}]",
            )
            decision_reasons.append(
                f"Onset interval bounded to ({t_pre.date().isoformat()}, {t_earliest.date().isoformat()}] "
                f"({delta_days} days span)."
            )
        else:
            onset_estimate = TemporalOnsetEstimate(
                pre_change_observation_id=None,
                pre_change_date=None,
                earliest_support_observation_id=earliest_id,
                earliest_support_date=t_earliest,
                interval_days=None,
                provisional_flagged_observation_id=provisional_flagged_id,
                provisional_flagged_date=provisional_flagged_date,
                interval_type=TemporalIntervalType.LEFT_UNBOUNDED,
                display_bounding_span=f"[None, {t_earliest.date().isoformat()}]",
                physical_onset_interval=f"(-infinity, {t_earliest.date().isoformat()}]",
            )
            decision_reasons.append(
                f"Onset interval is LEFT_UNBOUNDED: earliest support at {t_earliest.date().isoformat()} "
                f"with no preceding verified absence."
            )
    else:
        onset_estimate = TemporalOnsetEstimate(
            pre_change_observation_id=pre_node.observation_id if pre_node else None,
            pre_change_date=pre_node.acquisition_time if pre_node else None,
            earliest_support_observation_id=None,
            earliest_support_date=None,
            interval_days=None,
            provisional_flagged_observation_id=provisional_flagged_id,
            provisional_flagged_date=provisional_flagged_date,
            interval_type=TemporalIntervalType.UNRESOLVED,
            display_bounding_span=None,
            physical_onset_interval=None,
        )

    # 6. Stratified confidence tier assignment
    has_cross_sensor = any(n.is_cross_sensor for n in sorted_nodes)
    if support_status == TemporalSupportStatus.STRONG_TEMPORAL_SUPPORT:
        if has_cross_sensor:
            confidence_tier = TemporalConfidenceTier.MEDIUM
            limitations.append("Confidence tier capped at 'medium' due to uncalibrated cross-sensor pairings.")
        elif pre_node is None:
            confidence_tier = TemporalConfidenceTier.MEDIUM
            limitations.append("Confidence tier set to 'medium': pre-change absence unverified.")
        elif onset_estimate.interval_days is not None and onset_estimate.interval_days > config.max_temporal_gap_days:
            confidence_tier = TemporalConfidenceTier.MEDIUM
            limitations.append("Confidence tier set to 'medium': bounding interval exceeds gap threshold.")
        else:
            confidence_tier = TemporalConfidenceTier.HIGH
    elif support_status == TemporalSupportStatus.SINGLE_OBSERVATION_SUPPORT:
        confidence_tier = TemporalConfidenceTier.LOW
    elif support_status in (TemporalSupportStatus.FLAGGED_PENDING_REVIEW, TemporalSupportStatus.TEMPORALLY_AMBIGUOUS):
        confidence_tier = TemporalConfidenceTier.UNCERTAIN
    else:
        confidence_tier = TemporalConfidenceTier.UNCERTAIN

    # 7. Aggregate summary metrics
    metrics = TemporalEvidenceMetrics(
        total_observations_in_series=total_series_observations,
        evaluated_nodes_count=len(sorted_nodes),
        supporting_nodes_count=n_support,
        flagged_nodes_count=sum(1 for n in sorted_nodes if n.node_status == TemporalNodeStatus.FLAGGED_SUPPORT),
        suppressed_nodes_count=sum(1 for n in sorted_nodes if n.node_status == TemporalNodeStatus.SUPPRESSED_ARTIFACT),
        absence_nodes_count=sum(1 for n in sorted_nodes if n.node_status == TemporalNodeStatus.PRE_CHANGE_ABSENCE),
        insufficient_data_nodes_count=sum(1 for n in sorted_nodes if n.node_status == TemporalNodeStatus.INSUFFICIENT_DATA),
        simultaneous_nodes_count=sum(1 for n in sorted_nodes if n.node_status == TemporalNodeStatus.SIMULTANEOUS_CO_TEMPORAL),
        cross_sensor_nodes_count=sum(1 for n in sorted_nodes if n.is_cross_sensor),
    )

    return (
        sorted_nodes,
        support_status,
        confidence_tier,
        onset_estimate,
        cat_evolution,
        metrics,
        decision_reasons,
        limitations,
    )
