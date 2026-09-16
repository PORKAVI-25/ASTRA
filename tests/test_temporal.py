"""ASTRA Phase M4A: Comprehensive Temporal Model & Scene Pairing Tests.

Covers:
1. Observation contract validation
2. Missing acquisition date handling
3. Invalid acquisition date handling
4. Chronological ordering
5. Earlier/later enforcement
6. Same-tile temporal pairing
7. Spatial overlap calculation
8. No-overlap rejection
9. Partial-overlap handling
10. Temporal separation calculation
11. Same-sensor compatibility
12. Cross-sensor compatibility representation
13. Deterministic pair IDs
14. Deterministic pair ordering
15. Multiple observations forming a temporal series
16. Malformed manifest handling
17. Empty catalog handling
18. Duplicate observation handling
19. Provenance linkage
20. CLI smoke test
"""

import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest
from pydantic import ValidationError

from geospatial.contracts import GeoBoundingBox, SceneManifest, TileManifest
from backend.ml.change.types import (
    PairCompatibility,
    PairCompatibilityStatus,
    PairingConfig,
    ScenePair,
    SpatialOverlap,
    TemporalObservation,
    TemporalSeries,
)
from backend.ml.change.scene_pairing import (
    compute_spatial_overlap,
    create_deterministic_pair_id,
    create_scene_pair,
    evaluate_pair_compatibility,
    pair_observations,
)
from backend.ml.change.temporal_catalog import (
    CatalogDiscoveryResult,
    TemporalCatalog,
)


def make_obs(
    obs_id: str,
    scene_id: str = "scene_001",
    tile_id: str = "tile_001",
    timestamp: datetime = datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc),
    sensor: str = "Sentinel-2A MSI",
    platform: str = "Sentinel-2",
    min_lon: float = 76.0,
    min_lat: float = 12.0,
    max_lon: float = 76.1,
    max_lat: float = 12.1,
    source_hash: str = "abcdef0123456789abcdef0123456789",
    prov_ref: str = "prov_ing_001",
) -> TemporalObservation:
    """Helper to construct valid TemporalObservation fixtures."""
    return TemporalObservation(
        observation_id=obs_id,
        scene_id=scene_id,
        tile_id=tile_id,
        acquisition_time=timestamp,
        sensor=sensor,
        platform=platform,
        crs="EPSG:32643",
        bounds_wgs84=GeoBoundingBox(
            min_lon=min_lon, min_lat=min_lat, max_lon=max_lon, max_lat=max_lat
        ),
        source_hash=source_hash,
        file_path=f"data/tiles/{tile_id}.png",
        provenance_reference=prov_ref,
    )


# 1. Observation contract validation
def test_01_temporal_observation_contract():
    obs = make_obs("obs_test_1")
    assert obs.observation_id == "obs_test_1"
    assert obs.acquisition_time.tzinfo == timezone.utc
    assert obs.bounds_wgs84.min_lon == 76.0
    assert obs.sensor == "Sentinel-2A MSI"


# 2. Missing acquisition date handling
def test_02_missing_acquisition_date_handling(tmp_path):
    catalog = TemporalCatalog()
    tiles_dir = tmp_path / "tiles"
    tiles_dir.mkdir()

    # Create tile with missing acquisition_time
    tile_data = [{
        "tile_id": "tile_no_date",
        "source_scene_id": "scene_unknown",
        "tile_col": 0,
        "tile_row": 0,
        "zoom_level": 14,
        "crs": "EPSG:32643",
        "bounds_wgs84": {"min_lon": 76.0, "min_lat": 12.0, "max_lon": 76.1, "max_lat": 12.1},
        "acquisition_time": None,
        "file_path": "tile.png",
        "sha256_hash": "a" * 64,
    }]
    (tiles_dir / "scene_unknown.json").write_text(json.dumps(tile_data), encoding="utf-8")

    res = catalog.discover_manifests(tiles_dir=tiles_dir, scenes_dir=tmp_path / "scenes")
    assert res.valid_observations == 0
    assert res.invalid_observations == 1
    assert any("missing required acquisition_time" in d for d in res.diagnostics)


# 3. Invalid acquisition date handling
def test_03_invalid_acquisition_date_handling():
    # Direct model validation rejects non-datetime or unparseable date
    with pytest.raises(ValidationError):
        TemporalObservation(
            observation_id="obs_bad_date",
            scene_id="scene_001",
            acquisition_time="not-a-date",  # Invalid type
            sensor="MSI",
            platform="S2",
            crs="EPSG:4326",
            bounds_wgs84=GeoBoundingBox(min_lon=0, min_lat=0, max_lon=1, max_lat=1),
            source_hash="h" * 16,
        )


# 4. Chronological ordering
def test_04_chronological_ordering():
    t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2026, 2, 1, tzinfo=timezone.utc)
    t3 = datetime(2026, 3, 1, tzinfo=timezone.utc)

    o1 = make_obs("obs_1", timestamp=t1)
    o2 = make_obs("obs_2", timestamp=t2)
    o3 = make_obs("obs_3", timestamp=t3)

    # Insert out of order
    catalog = TemporalCatalog()
    catalog.add_observation(o3)
    catalog.add_observation(o1)
    catalog.add_observation(o2)

    series_map = catalog.build_series()
    assert len(series_map) == 1
    series = list(series_map.values())[0]

    timestamps = [o.acquisition_time for o in series.observations]
    assert timestamps == [t1, t2, t3]


# 5. Earlier/later enforcement
def test_05_earlier_later_enforcement():
    t_early = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t_late = datetime(2026, 2, 1, tzinfo=timezone.utc)

    obs_early = make_obs("obs_early", timestamp=t_early)
    obs_late = make_obs("obs_late", timestamp=t_late)

    # Valid order: early -> late
    pair = create_scene_pair(obs_early, obs_late)
    assert pair.compatibility.is_compatible is True
    assert pair.temporal_separation_seconds > 0.0
    assert pair.temporal_separation_days > 0.0

    # Inverted order: late -> early must raise validation error in ScenePair contract
    with pytest.raises(ValidationError):
        ScenePair(
            pair_id="pair_inverted",
            earlier_observation=obs_late,
            later_observation=obs_early,
            temporal_separation_seconds=0.0,
            temporal_separation_days=0.0,
            spatial_overlap=compute_spatial_overlap(obs_late.bounds_wgs84, obs_early.bounds_wgs84),
            compatibility=evaluate_pair_compatibility(obs_late, obs_early, PairingConfig())[1],
        )

    # Same timestamp: identical acquisition times can NEVER form a valid pair
    obs_same_time_1 = make_obs("obs_time_a", timestamp=t_early)
    obs_same_time_2 = make_obs("obs_time_b", timestamp=t_early)

    pair_same = create_scene_pair(obs_same_time_1, obs_same_time_2, config=PairingConfig(min_temporal_separation_seconds=0.0))
    assert pair_same.compatibility.is_compatible is False
    assert pair_same.compatibility.status == PairCompatibilityStatus.IDENTICAL_TIMESTAMPS
    assert pair_same.temporal_separation_seconds == 0.0
    assert any("identical acquisition timestamps" in r.lower() for r in pair_same.compatibility.reasons)

    # Directly creating a ScenePair with is_compatible=True and identical timestamps must raise ValidationError
    with pytest.raises(ValidationError):
        ScenePair(
            pair_id="pair_same_time_invalid",
            earlier_observation=obs_same_time_1,
            later_observation=obs_same_time_2,
            temporal_separation_seconds=0.0,
            temporal_separation_days=0.0,
            spatial_overlap=compute_spatial_overlap(obs_same_time_1.bounds_wgs84, obs_same_time_2.bounds_wgs84),
            compatibility=PairCompatibility(
                is_compatible=True,  # Forged compatible flag on zero time gap
                status=PairCompatibilityStatus.COMPATIBLE,
                reasons=["Forged compatibility"],
            ),
        )


# 6. Same-tile temporal pairing
def test_06_same_tile_temporal_pairing():
    t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2026, 2, 1, tzinfo=timezone.utc)

    o1 = make_obs("obs_t1", tile_id="tile_A", timestamp=t1)
    o2 = make_obs("obs_t2", tile_id="tile_A", timestamp=t2)

    pairs = pair_observations([o1, o2])
    assert len(pairs) == 1
    p = pairs[0]
    assert p.earlier_observation.tile_id == "tile_A"
    assert p.later_observation.tile_id == "tile_A"
    assert p.compatibility.is_compatible is True
    assert p.spatial_overlap.overlap_ratio_iou == 1.0


# 7. Spatial overlap calculation
def test_07_spatial_overlap_calculation():
    # Box A: [0, 0, 2, 2] -> Area = 4
    # Box B: [1, 1, 3, 3] -> Area = 4
    # Intersection: [1, 1, 2, 2] -> Area = 1
    # Union = 4 + 4 - 1 = 7
    # IoU = 1/7 = 0.1429
    box_a = GeoBoundingBox(min_lon=0.0, min_lat=0.0, max_lon=2.0, max_lat=2.0)
    box_b = GeoBoundingBox(min_lon=1.0, min_lat=1.0, max_lon=3.0, max_lat=3.0)

    overlap = compute_spatial_overlap(box_a, box_b)
    assert overlap.is_overlapping is True
    assert overlap.intersection_bounds is not None
    assert overlap.intersection_bounds.min_lon == 1.0
    assert overlap.intersection_bounds.max_lat == 2.0
    assert round(overlap.intersection_area_deg2, 2) == 1.0
    assert round(overlap.overlap_ratio_iou, 4) == round(1.0 / 7.0, 4)
    assert overlap.overlap_ratio_earlier == 0.25
    assert overlap.overlap_ratio_later == 0.25


# 8. No-overlap rejection
def test_08_no_overlap_rejection():
    # Disjoint boxes
    box_a = GeoBoundingBox(min_lon=0.0, min_lat=0.0, max_lon=1.0, max_lat=1.0)
    box_b = GeoBoundingBox(min_lon=2.0, min_lat=2.0, max_lon=3.0, max_lat=3.0)

    overlap = compute_spatial_overlap(box_a, box_b)
    assert overlap.is_overlapping is False
    assert overlap.intersection_bounds is None
    assert overlap.intersection_area_deg2 == 0.0
    assert overlap.overlap_ratio_iou == 0.0

    obs_1 = make_obs("obs_1", min_lon=0.0, min_lat=0.0, max_lon=1.0, max_lat=1.0, timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc))
    obs_2 = make_obs("obs_2", min_lon=2.0, min_lat=2.0, max_lon=3.0, max_lat=3.0, timestamp=datetime(2026, 2, 1, tzinfo=timezone.utc))

    pair = create_scene_pair(obs_1, obs_2, PairingConfig(min_spatial_overlap_ratio=0.5))
    assert pair.compatibility.is_compatible is False
    assert pair.compatibility.status == PairCompatibilityStatus.INSUFFICIENT_OVERLAP


# 9. Partial-overlap handling
def test_09_partial_overlap_handling():
    # Overlap IoU is 1/7 (~0.1429)
    obs_1 = make_obs("obs_1", min_lon=0.0, min_lat=0.0, max_lon=2.0, max_lat=2.0, timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc))
    obs_2 = make_obs("obs_2", min_lon=1.0, min_lat=1.0, max_lon=3.0, max_lat=3.0, timestamp=datetime(2026, 2, 1, tzinfo=timezone.utc))

    # Reject with high threshold (0.5)
    pair_reject = create_scene_pair(obs_1, obs_2, PairingConfig(min_spatial_overlap_ratio=0.5))
    assert pair_reject.compatibility.is_compatible is False
    assert pair_reject.compatibility.status == PairCompatibilityStatus.INSUFFICIENT_OVERLAP

    # Accept with low threshold (0.1)
    pair_accept = create_scene_pair(obs_1, obs_2, PairingConfig(min_spatial_overlap_ratio=0.1))
    assert pair_accept.compatibility.is_compatible is True


# 10. Temporal separation calculation
def test_10_temporal_separation_calculation():
    t1 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 11, 12, 0, 0, tzinfo=timezone.utc)  # 10.5 days = 907,200 seconds

    obs_1 = make_obs("obs_1", timestamp=t1)
    obs_2 = make_obs("obs_2", timestamp=t2)

    pair = create_scene_pair(obs_1, obs_2)
    assert pair.temporal_separation_seconds == 907200.0
    assert pair.temporal_separation_days == 10.5


# 11. Same-sensor compatibility
def test_11_same_sensor_compatibility():
    obs_1 = make_obs("obs_1", sensor="Sentinel-2A MSI", timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc))
    obs_2 = make_obs("obs_2", sensor="Sentinel-2A MSI", timestamp=datetime(2026, 2, 1, tzinfo=timezone.utc))

    config = PairingConfig(require_same_sensor=True)
    pair = create_scene_pair(obs_1, obs_2, config)
    assert pair.compatibility.is_compatible is True
    assert pair.compatibility.is_cross_sensor is False


# 12. Cross-sensor compatibility representation
def test_12_cross_sensor_compatibility_representation():
    obs_1 = make_obs("obs_1", sensor="Sentinel-2A MSI", timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc))
    obs_2 = make_obs("obs_2", sensor="Landsat-8 OLI", timestamp=datetime(2026, 2, 1, tzinfo=timezone.utc))

    # Allowed by default
    pair_allowed = create_scene_pair(obs_1, obs_2, PairingConfig(require_same_sensor=False))
    assert pair_allowed.compatibility.is_compatible is True
    assert pair_allowed.compatibility.is_cross_sensor is True
    assert any("Cross-sensor" in r for r in pair_allowed.compatibility.reasons)

    # Rejected when strict
    pair_rejected = create_scene_pair(obs_1, obs_2, PairingConfig(require_same_sensor=True))
    assert pair_rejected.compatibility.is_compatible is False
    assert pair_rejected.compatibility.status == PairCompatibilityStatus.INCOMPATIBLE_SENSOR


# 13. Deterministic pair IDs
def test_13_deterministic_pair_ids():
    obs_1 = make_obs("obs_alpha", timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc))
    obs_2 = make_obs("obs_beta", timestamp=datetime(2026, 2, 1, tzinfo=timezone.utc))

    id1 = create_deterministic_pair_id(obs_1, obs_2)
    id2 = create_deterministic_pair_id(obs_1, obs_2)
    assert id1 == id2
    assert id1 == "pair_obs_alpha__obs_beta"


# 14. Deterministic pair ordering
def test_14_deterministic_pair_ordering():
    t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2026, 2, 1, tzinfo=timezone.utc)
    t3 = datetime(2026, 3, 1, tzinfo=timezone.utc)

    obs = [
        make_obs("obs_3", timestamp=t3),
        make_obs("obs_1", timestamp=t1),
        make_obs("obs_2", timestamp=t2),
    ]

    pairs1 = pair_observations(obs, mode="all_pairwise")
    pairs2 = pair_observations(list(reversed(obs)), mode="all_pairwise")

    assert [p.pair_id for p in pairs1] == [p.pair_id for p in pairs2]
    assert [p.pair_id for p in pairs1] == [
        "pair_obs_1__obs_2",
        "pair_obs_1__obs_3",
        "pair_obs_2__obs_3",
    ]


# 15. Multiple observations forming a temporal series
def test_15_multiple_observations_forming_series():
    catalog = TemporalCatalog()
    for i in range(5):
        t = datetime(2026, 1, 1 + i, tzinfo=timezone.utc)
        obs = make_obs(f"obs_{i}", tile_id="tile_grid_0", timestamp=t)
        catalog.add_observation(obs)

    series_map = catalog.build_series()
    assert len(series_map) == 1
    series = list(series_map.values())[0]
    assert series.observation_count == 5
    assert series.earliest_date == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert series.latest_date == datetime(2026, 1, 5, tzinfo=timezone.utc)


# 16. Malformed manifest handling
def test_16_malformed_manifest_handling(tmp_path):
    catalog = TemporalCatalog()
    scenes_dir = tmp_path / "scenes"
    scenes_dir.mkdir()

    (scenes_dir / "bad_json.json").write_text("NOT_VALID_JSON{", encoding="utf-8")
    (scenes_dir / "invalid_schema.json").write_text(json.dumps({"wrong": "data"}), encoding="utf-8")

    res = catalog.discover_manifests(scenes_dir=scenes_dir)
    assert res.scenes_discovered == 0
    assert res.invalid_observations == 2
    assert len(res.diagnostics) == 2


# 17. Empty catalog handling
def test_17_empty_catalog_handling(tmp_path):
    catalog = TemporalCatalog()
    res = catalog.discover_manifests(tiles_dir=tmp_path / "empty_tiles", scenes_dir=tmp_path / "empty_scenes")
    assert res.scenes_discovered == 0
    assert res.valid_observations == 0
    assert res.temporal_series_count == 0

    valid, rejected = catalog.generate_pairs()
    assert len(valid) == 0
    assert len(rejected) == 0


# 18. Duplicate observation handling
def test_18_duplicate_observation_handling():
    catalog = TemporalCatalog()
    obs1 = make_obs("obs_duplicate")
    obs2 = make_obs("obs_duplicate")  # Same ID

    assert catalog.add_observation(obs1) is True
    assert catalog.add_observation(obs2) is False
    assert catalog.count_observations() == 1


# 19. Provenance linkage
def test_19_provenance_linkage():
    obs1 = make_obs("obs_1", prov_ref="prov_ing_123456", timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc))
    obs2 = make_obs("obs_2", prov_ref="prov_ing_789012", timestamp=datetime(2026, 2, 1, tzinfo=timezone.utc))

    pair = create_scene_pair(obs1, obs2)
    assert pair.provenance_reference is not None
    assert pair.provenance_reference == "prov_ing_789012"
    assert pair.earlier_observation.provenance_reference == "prov_ing_123456"
    assert pair.later_observation.provenance_reference == "prov_ing_789012"


# 20. CLI smoke test
def test_20_cli_smoke_test():
    cmd = [
        sys.executable,
        "scripts/build_temporal_catalog.py",
        "--min-overlap", "0.5",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0
    assert "TEMPORAL CATALOG & SCENE PAIRING SUMMARY REPORT:" in proc.stdout
    assert "Scenes discovered" in proc.stdout
    assert "Valid observations" in proc.stdout


# 21. Same-timestamp observations rejected from valid pairs in catalog
def test_21_same_timestamp_rejection_in_catalog():
    catalog = TemporalCatalog()
    same_time = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)

    # Two observations on the same tile footprint with the exact same acquisition timestamp
    obs1 = make_obs("obs_s1", tile_id="tile_X", timestamp=same_time, source_hash="11111111111111111111111111111111")
    obs2 = make_obs("obs_s2", tile_id="tile_X", timestamp=same_time, source_hash="22222222222222222222222222222222")

    assert catalog.add_observation(obs1) is True
    assert catalog.add_observation(obs2) is True
    assert catalog.count_observations() == 2

    # Even with min_temporal_separation_seconds=0.0 (no additional minimum gap),
    # identical timestamps must NEVER form valid before/after pairs
    valid_pairs, rejected_pairs = catalog.generate_pairs(
        config=PairingConfig(min_temporal_separation_seconds=0.0)
    )

    assert len(valid_pairs) == 0, "Same-timestamp observations must NEVER produce valid pairs!"
    assert len(rejected_pairs) == 1
    rejected = rejected_pairs[0]
    assert rejected.compatibility.is_compatible is False
    assert rejected.compatibility.status == PairCompatibilityStatus.IDENTICAL_TIMESTAMPS
    assert rejected.temporal_separation_seconds == 0.0
