"""ASTRA Phase M4E: Chronological Ordering & Multi-Pair Timeline Alignment.

Enforces strict temporal ordering conforming to ASTRA-DC-v0.1.
Rejects tie-breaking for identical acquisition timestamps and maps
pairwise pipeline evidence to chronological observation nodes.
"""

from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

from backend.ml.change.types import TemporalObservation, TemporalSeries
from backend.ml.temporal_evidence.types import (
    CandidateRegionRef,
    PairwiseTemporalEvidenceInput,
    TemporalEvidenceConfig,
)


def order_and_validate_observations(
    observations: List[TemporalObservation],
) -> Tuple[List[TemporalObservation], Set[str], List[str]]:
    """Validates chronological ordering and identifies simultaneous observations.

    Strictly conforms to M4A strict chronology:
    - Sorts observations by acquisition_time.
    - Does NOT tie-break identical timestamps for ordered intervals.
    - Retains simultaneous observations for audit but marks their observation IDs.
    Returns: (sorted_observations, simultaneous_observation_ids, validation_warnings)
    """
    if not observations:
        return [], set(), ["Temporal series contains zero observations."]

    # Sort observations chronologically by UTC acquisition time
    sorted_obs = sorted(observations, key=lambda o: o.acquisition_time)

    simultaneous_ids: Set[str] = set()
    warnings: List[str] = []

    # Detect duplicate acquisition timestamps
    seen_timestamps: Dict[datetime, List[str]] = {}
    for obs in sorted_obs:
        t = obs.acquisition_time
        if t not in seen_timestamps:
            seen_timestamps[t] = []
        seen_timestamps[t].append(obs.observation_id)

    for t, obs_ids in seen_timestamps.items():
        if len(obs_ids) > 1:
            warnings.append(
                f"Identical acquisition timestamp {t.isoformat()} detected for observations: {', '.join(obs_ids)}. "
                f"Simultaneous observations cannot establish an ordered temporal interval and are marked SIMULTANEOUS_CO_TEMPORAL."
            )
            # Retain the first as ordered node, mark subsequent as simultaneous co-temporal
            for co_id in obs_ids[1:]:
                simultaneous_ids.add(co_id)

    return sorted_obs, simultaneous_ids, warnings


def align_pairwise_evidence_to_observations(
    observations: List[TemporalObservation],
    discovery_pair_evidence: PairwiseTemporalEvidenceInput,
    pairwise_evidence: List[PairwiseTemporalEvidenceInput],
    candidate_ref: CandidateRegionRef,
) -> Tuple[Dict[str, PairwiseTemporalEvidenceInput], Optional[str], Optional[str], List[str]]:
    """Maps pairwise evidence inputs to observation IDs along the timeline.

    The discovery candidate belongs to the later observation of the discovery pair.
    Subsequent persistence evidence belongs to the later observation of each subsequent pair.

    Returns:
        (obs_id_to_pairwise_map, discovery_earlier_obs_id, discovery_later_obs_id, validation_errors)
    """
    errors: List[str] = []

    # 1. Enforce discovery pair consistency with candidate reference
    if discovery_pair_evidence.scene_pair_id != candidate_ref.scene_pair_id:
        errors.append(
            f"Discovery pair ID mismatch: discovery_pair_evidence.scene_pair_id "
            f"'{discovery_pair_evidence.scene_pair_id}' != candidate_ref.scene_pair_id '{candidate_ref.scene_pair_id}'."
        )

    if discovery_pair_evidence.change_detection_result_id != candidate_ref.change_detection_result_id:
        errors.append(
            f"Discovery change detection result ID mismatch: discovery_pair_evidence.change_detection_result_id "
            f"'{discovery_pair_evidence.change_detection_result_id}' != candidate_ref.change_detection_result_id "
            f"'{candidate_ref.change_detection_result_id}'."
        )

    # 2. Index observations by ID
    obs_map = {obs.observation_id: obs for obs in observations}

    # 3. Align discovery pair
    discovery_earlier_obs_id: Optional[str] = None
    discovery_later_obs_id: Optional[str] = None

    obs_id_to_pairwise_map: Dict[str, PairwiseTemporalEvidenceInput] = {}

    all_pairs = [discovery_pair_evidence] + list(pairwise_evidence)
    seen_pair_ids: Set[str] = set()

    for p in all_pairs:
        if p.scene_pair_id in seen_pair_ids:
            errors.append(f"Duplicate scene_pair_id detected in evaluation inputs: '{p.scene_pair_id}'.")
        seen_pair_ids.add(p.scene_pair_id)

    # Resolve discovery endpoints from M4D/M4A if available
    disc_m4d = discovery_pair_evidence.suppression_result
    disc_cdr = discovery_pair_evidence.change_detection_result

    # Try resolving observation IDs from suppression or detection metadata
    # 1. Match discovery pair using explicit evidence timestamps if available
    if discovery_pair_evidence.evidence and discovery_pair_evidence.evidence.temporal:
        t_earlier = discovery_pair_evidence.evidence.temporal.earlier_acquisition_time
        t_later = discovery_pair_evidence.evidence.temporal.later_acquisition_time
        for obs in observations:
            if abs((obs.acquisition_time - t_earlier).total_seconds()) < 1.0:
                discovery_earlier_obs_id = obs.observation_id
            elif abs((obs.acquisition_time - t_later).total_seconds()) < 1.0:
                discovery_later_obs_id = obs.observation_id

    # 2. Try matching observation IDs encoded within scene_pair_id
    if discovery_earlier_obs_id is None or discovery_later_obs_id is None:
        if "__" in discovery_pair_evidence.scene_pair_id:
            earlier_part, later_part = discovery_pair_evidence.scene_pair_id.split("__", 1)
            for obs in observations:
                if obs.observation_id in earlier_part:
                    discovery_earlier_obs_id = obs.observation_id
                if obs.observation_id in later_part:
                    discovery_later_obs_id = obs.observation_id
        else:
            for obs in observations:
                if obs.observation_id in discovery_pair_evidence.scene_pair_id:
                    if discovery_earlier_obs_id is None:
                        discovery_earlier_obs_id = obs.observation_id
                    elif discovery_later_obs_id is None:
                        discovery_later_obs_id = obs.observation_id

    # 3. Fallback based on series length
    if discovery_earlier_obs_id is None or discovery_later_obs_id is None:
        if len(observations) == 1:
            discovery_later_obs_id = observations[0].observation_id
        elif len(observations) >= 2:
            if discovery_earlier_obs_id is not None and discovery_later_obs_id is None:
                for obs in observations:
                    if obs.observation_id != discovery_earlier_obs_id:
                        discovery_later_obs_id = obs.observation_id
                        break
            elif discovery_later_obs_id is not None and discovery_earlier_obs_id is None:
                for obs in observations:
                    if obs.observation_id != discovery_later_obs_id:
                        discovery_earlier_obs_id = obs.observation_id
                        break
            elif discovery_earlier_obs_id is None and discovery_later_obs_id is None:
                discovery_earlier_obs_id = observations[0].observation_id
                discovery_later_obs_id = observations[1].observation_id

    if discovery_later_obs_id:
        obs_id_to_pairwise_map[discovery_later_obs_id] = discovery_pair_evidence

    # Map subsequent pairwise evidence
    for p in pairwise_evidence:
        matched_later_id: Optional[str] = None

        # A. Try matching by timestamp
        if p.evidence and p.evidence.temporal:
            t_later = p.evidence.temporal.later_acquisition_time
            for obs in observations:
                if abs((obs.acquisition_time - t_later).total_seconds()) < 1.0:
                    matched_later_id = obs.observation_id
                    break

        # B. Try matching by observation ID in scene_pair_id
        if matched_later_id is None:
            if "__" in p.scene_pair_id:
                _, later_part = p.scene_pair_id.split("__", 1)
                for obs in observations:
                    if obs.observation_id in later_part:
                        matched_later_id = obs.observation_id
                        break
            if matched_later_id is None:
                for obs in observations:
                    if obs.observation_id != discovery_earlier_obs_id and obs.observation_id in p.scene_pair_id:
                        matched_later_id = obs.observation_id
                        break

        # C. Fallback: match by chronological index
        if matched_later_id is None:
            for obs in observations:
                if obs.observation_id not in obs_id_to_pairwise_map and obs.observation_id != discovery_earlier_obs_id:
                    matched_later_id = obs.observation_id
                    break

        if matched_later_id:
            obs_id_to_pairwise_map[matched_later_id] = p
        else:
            errors.append(
                f"Could not map pairwise evidence for scene_pair_id '{p.scene_pair_id}' to any observation in series."
            )

    return obs_id_to_pairwise_map, discovery_earlier_obs_id, discovery_later_obs_id, errors


def check_temporal_gaps(
    sorted_observations: List[TemporalObservation],
    max_gap_days: float = 90.0,
) -> List[str]:
    """Inspects adjacent observations and emits limitation notices for gaps exceeding max_gap_days."""
    limitations: List[str] = []
    if len(sorted_observations) < 2:
        return limitations

    for i in range(len(sorted_observations) - 1):
        o1 = sorted_observations[i]
        o2 = sorted_observations[i + 1]
        delta_sec = (o2.acquisition_time - o1.acquisition_time).total_seconds()
        delta_days = round(delta_sec / 86400.0, 1)

        if delta_days > max_gap_days:
            limitations.append(
                f"Wide temporal gap of {delta_days} days detected between observation '{o1.observation_id}' "
                f"({o1.acquisition_time.date().isoformat()}) and '{o2.observation_id}' "
                f"({o2.acquisition_time.date().isoformat()}). Onset precision is constrained by observation cadence."
            )

    return limitations
