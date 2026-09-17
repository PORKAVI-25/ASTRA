"""ASTRA Temporal Catalog.

Discovers existing Phase 1 scene and tile manifests, validates acquisition timestamps,
constructs chronological temporal series, and generates deterministic scene/tile pairs.
Conforms strictly to offline requirements and never alters Phase 1 data.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field
from geospatial.contracts import GeoBoundingBox, SceneManifest, TileManifest
from .scene_pairing import pair_observations
from .types import (
    PairingConfig,
    ScenePair,
    TemporalObservation,
    TemporalSeries,
)


class CatalogDiscoveryResult(BaseModel):
    """Metrics and diagnostic logs from manifest discovery."""

    scenes_discovered: int = 0
    valid_observations: int = 0
    invalid_observations: int = 0
    temporal_series_count: int = 0
    diagnostics: List[str] = Field(default_factory=list)


class TemporalCatalog:
    """In-memory temporal catalog for satellite observation discovery and pairing."""

    def __init__(self):
        self._observations: Dict[str, TemporalObservation] = {}
        self._series: Dict[str, TemporalSeries] = {}
        self._diagnostics: List[str] = []

    @property
    def observations(self) -> List[TemporalObservation]:
        """Returns all registered observations sorted chronologically."""
        return sorted(
            self._observations.values(),
            key=lambda o: (o.acquisition_time, o.observation_id),
        )

    def add_observation(self, obs: TemporalObservation) -> bool:
        """Adds an observation to the catalog. Returns True if added, False if duplicate."""
        if obs.observation_id in self._observations:
            return False
        self._observations[obs.observation_id] = obs
        return True

    def get_observation(self, observation_id: str) -> Optional[TemporalObservation]:
        """Retrieves observation by its deterministic identifier."""
        return self._observations.get(observation_id)

    def count_observations(self) -> int:
        """Returns total valid registered observations."""
        return len(self._observations)

    def discover_manifests(
        self,
        tiles_dir: Optional[Path] = None,
        scenes_dir: Optional[Path] = None,
    ) -> CatalogDiscoveryResult:
        """Discovers and validates existing Phase 1 scene and tile manifests."""
        scenes_discovered = 0
        valid_count = 0
        invalid_count = 0
        diagnostics: List[str] = []

        scene_map: Dict[str, SceneManifest] = {}

        # 1. Discover scenes
        if scenes_dir and scenes_dir.exists():
            for s_file in sorted(scenes_dir.glob("*.json")):
                try:
                    with open(s_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    sm = SceneManifest.model_validate(data)
                    scene_map[sm.scene_id] = sm
                    scenes_discovered += 1
                except Exception as e:
                    diagnostics.append(f"Malformed scene manifest {s_file.name}: {e}")
                    invalid_count += 1

        # 2. Discover tiles
        if tiles_dir and tiles_dir.exists():
            for t_file in sorted(tiles_dir.glob("*.json")):
                try:
                    with open(t_file, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    raw_tiles: List[Any] = data if isinstance(data, list) else [data]
                    for raw_tile in raw_tiles:
                        # Extract and validate required metadata
                        try:
                            tm = TileManifest.model_validate(raw_tile)
                        except Exception as e:
                            diagnostics.append(f"Invalid tile schema in {t_file.name}: {e}")
                            invalid_count += 1
                            continue

                        # Strict validation: acquisition timestamp is required
                        if tm.acquisition_time is None:
                            # Attempt resolution from parent scene manifest
                            parent_scene = scene_map.get(tm.source_scene_id)
                            if parent_scene and parent_scene.acquisition_time:
                                acq_time = parent_scene.acquisition_time
                            else:
                                diagnostics.append(
                                    f"Tile '{tm.tile_id}' missing required acquisition_time; rejected from temporal catalog."
                                )
                                invalid_count += 1
                                continue
                        else:
                            acq_time = tm.acquisition_time

                        # Ensure UTC normalization
                        if acq_time.tzinfo is None:
                            acq_time = acq_time.replace(tzinfo=timezone.utc)
                        else:
                            acq_time = acq_time.astimezone(timezone.utc)

                        # Resolve platform & sensor
                        parent_scene = scene_map.get(tm.source_scene_id)
                        platform = parent_scene.platform if parent_scene else "unknown"
                        sensor = tm.sensor if tm.sensor != "unknown" else (parent_scene.sensor if parent_scene else "unknown")

                        # Deterministic observation ID
                        obs_id = f"obs_{tm.tile_id}_{tm.sha256_hash[:8]}"

                        obs = TemporalObservation(
                            observation_id=obs_id,
                            scene_id=tm.source_scene_id,
                            tile_id=tm.tile_id,
                            acquisition_time=acq_time,
                            sensor=sensor,
                            platform=platform,
                            crs=tm.crs,
                            bounds_wgs84=tm.bounds_wgs84,
                            source_hash=tm.sha256_hash,
                            file_path=tm.file_path,
                            is_synthetic=tm.is_synthetic,
                            metadata={
                                "tile_col": tm.tile_col,
                                "tile_row": tm.tile_row,
                                "zoom_level": tm.zoom_level,
                                "valid_pixel_ratio": tm.valid_pixel_ratio if tm.valid_pixel_ratio is not None else 1.0,
                                "cloud_cover_percentage": parent_scene.cloud_cover_percentage if parent_scene else None,
                                "cloud_fraction": (
                                    (parent_scene.cloud_cover_percentage / 100.0)
                                    if (parent_scene and parent_scene.cloud_cover_percentage is not None)
                                    else 0.0
                                ),
                            },
                        )

                        if self.add_observation(obs):
                            valid_count += 1
                        else:
                            # Duplicate observation
                            diagnostics.append(f"Skipped duplicate observation: {obs_id}")

                except Exception as e:
                    diagnostics.append(f"Failed to read tile manifest file {t_file.name}: {e}")
                    invalid_count += 1

        self._diagnostics.extend(diagnostics)
        series_dict = self.build_series()

        return CatalogDiscoveryResult(
            scenes_discovered=scenes_discovered,
            valid_observations=valid_count,
            invalid_observations=invalid_count,
            temporal_series_count=len(series_dict),
            diagnostics=diagnostics,
        )

    def _extract_grid_key(self, obs: TemporalObservation) -> str:
        """Derives a stable geographic grid anchor key for grouping observations into a series."""
        b = obs.bounds_wgs84
        center_lon = round((b.min_lon + b.max_lon) / 2.0, 2)
        center_lat = round((b.min_lat + b.max_lat) / 2.0, 2)

        # 1. Check tile col/row in metadata
        col = obs.metadata.get("tile_col")
        row = obs.metadata.get("tile_row")
        zoom = obs.metadata.get("zoom_level", 14)
        if col is not None and row is not None:
            return f"grid_lon{center_lon:.2f}_lat{center_lat:.2f}_c{int(col):04d}_r{int(row):04d}_z{int(zoom)}"

        # 2. Try parsing col/row from tile_id
        if obs.tile_id:
            m = re.search(r"c(\d+)_r(\d+)_z(\d+)", obs.tile_id)
            if m:
                return f"grid_lon{center_lon:.2f}_lat{center_lat:.2f}_c{int(m.group(1)):04d}_r{int(m.group(2)):04d}_z{int(m.group(3))}"

        # 3. Fallback to geographic bbox center
        center_lon_4 = round((b.min_lon + b.max_lon) / 2.0, 4)
        center_lat_4 = round((b.min_lat + b.max_lat) / 2.0, 4)
        return f"geo_lon{center_lon_4}_lat{center_lat_4}"

    def build_series(self) -> Dict[str, TemporalSeries]:
        """Groups observations by geographic footprint and sorts chronologically."""
        grouped: Dict[str, List[TemporalObservation]] = {}
        for obs in self._observations.values():
            key = self._extract_grid_key(obs)
            grouped.setdefault(key, []).append(obs)

        series_dict: Dict[str, TemporalSeries] = {}
        for target_id, obs_list in grouped.items():
            # Sort chronologically, tie-break by observation_id
            sorted_obs = sorted(obs_list, key=lambda o: (o.acquisition_time, o.observation_id))

            # Compute covering bounds
            min_lon = min(o.bounds_wgs84.min_lon for o in sorted_obs)
            min_lat = min(o.bounds_wgs84.min_lat for o in sorted_obs)
            max_lon = max(o.bounds_wgs84.max_lon for o in sorted_obs)
            max_lat = max(o.bounds_wgs84.max_lat for o in sorted_obs)

            series_id = f"series_{target_id}"
            series_dict[series_id] = TemporalSeries(
                series_id=series_id,
                target_id=target_id,
                bounds_wgs84=GeoBoundingBox(
                    min_lon=min_lon, min_lat=min_lat, max_lon=max_lon, max_lat=max_lat
                ),
                observations=sorted_obs,
                observation_count=len(sorted_obs),
                earliest_date=sorted_obs[0].acquisition_time,
                latest_date=sorted_obs[-1].acquisition_time,
            )

        self._series = series_dict
        return series_dict

    def get_series(self, series_id: str) -> Optional[TemporalSeries]:
        """Retrieves a specific temporal series by its series_id."""
        return self._series.get(series_id)

    def list_series(self) -> List[TemporalSeries]:
        """Returns all temporal series sorted by series_id."""
        return sorted(self._series.values(), key=lambda s: s.series_id)

    def generate_pairs(
        self,
        config: Optional[PairingConfig] = None,
        mode: str = "adjacent",
    ) -> Tuple[List[ScenePair], List[ScenePair]]:
        """Generates all pairs across all temporal series.

        Returns:
            Tuple of (valid_pairs, rejected_pairs).
        """
        cfg = config or PairingConfig()
        if not self._series:
            self.build_series()

        valid_pairs: List[ScenePair] = []
        rejected_pairs: List[ScenePair] = []

        for series in self._series.values():
            if series.observation_count < 2:
                continue

            pairs = pair_observations(series.observations, config=cfg, mode=mode)
            for p in pairs:
                if p.compatibility.is_compatible:
                    valid_pairs.append(p)
                else:
                    rejected_pairs.append(p)

        # Deterministic sorting
        sort_key = lambda p: (
            p.earlier_observation.acquisition_time,
            p.later_observation.acquisition_time,
            p.pair_id,
        )
        return sorted(valid_pairs, key=sort_key), sorted(rejected_pairs, key=sort_key)
