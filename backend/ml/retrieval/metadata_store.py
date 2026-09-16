"""ASTRA SQLite Metadata Store for Semantic Retrieval.

Provides ACID-compliant, persistent local metadata and geospatial index storage
enabling rapid multi-attribute filtering (AOI bounding box, acquisition time,
sensor, platform) and embedding lineage tracking with zero server dependencies.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from geospatial.contracts import GeoBoundingBox, TileManifest
from backend.ml.retrieval.types import EmbeddingRecord, RetrievalFilter


class MetadataStore:
    """Persistent SQLite store for tile metadata, spatial boundaries, and embedding records."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or "data/indices/metadata_store.sqlite3")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            # Tiles table with spatial and temporal indexes
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tiles (
                    tile_id TEXT PRIMARY KEY,
                    source_scene_id TEXT NOT NULL,
                    sensor TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    acquisition_time TEXT,
                    crs TEXT NOT NULL,
                    min_lon REAL NOT NULL,
                    min_lat REAL NOT NULL,
                    max_lon REAL NOT NULL,
                    max_lat REAL NOT NULL,
                    file_path TEXT NOT NULL,
                    sha256_hash TEXT NOT NULL,
                    is_synthetic INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
            # Embeddings records table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS embeddings (
                    tile_id TEXT PRIMARY KEY,
                    scene_id TEXT NOT NULL,
                    embedding_model_id TEXT NOT NULL,
                    embedding_model_version TEXT NOT NULL,
                    embedding_dimension INTEGER NOT NULL,
                    preprocessing_version TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    vector_index_reference TEXT NOT NULL,
                    provenance_reference TEXT NOT NULL,
                    FOREIGN KEY (tile_id) REFERENCES tiles (tile_id) ON DELETE CASCADE
                )
                """
            )
            # Indexes for accelerated querying
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tiles_scene ON tiles(source_scene_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tiles_sensor ON tiles(sensor)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tiles_platform ON tiles(platform)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tiles_time ON tiles(acquisition_time)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tiles_spatial ON tiles(min_lon, max_lon, min_lat, max_lat)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_embeddings_model ON embeddings(embedding_model_id)")
            conn.commit()

    def store_tile(self, tile: TileManifest, platform: str = "unknown") -> None:
        """Stores or updates a tile manifest record."""
        acq_str = tile.acquisition_time.isoformat() if tile.acquisition_time else None
        now_str = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO tiles (
                    tile_id, source_scene_id, sensor, platform, acquisition_time,
                    crs, min_lon, min_lat, max_lon, max_lat, file_path,
                    sha256_hash, is_synthetic, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tile.tile_id,
                    tile.source_scene_id,
                    tile.sensor,
                    platform,
                    acq_str,
                    tile.crs,
                    tile.bounds_wgs84.min_lon,
                    tile.bounds_wgs84.min_lat,
                    tile.bounds_wgs84.max_lon,
                    tile.bounds_wgs84.max_lat,
                    tile.file_path,
                    tile.sha256_hash,
                    1 if tile.is_synthetic else 0,
                    now_str,
                ),
            )
            conn.commit()

    def store_embedding_record(self, record: EmbeddingRecord) -> None:
        """Stores or updates an embedding generation record."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO embeddings (
                    tile_id, scene_id, embedding_model_id, embedding_model_version,
                    embedding_dimension, preprocessing_version, source_sha256,
                    created_at, vector_index_reference, provenance_reference
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.tile_id,
                    record.scene_id,
                    record.embedding_model_id,
                    record.embedding_model_version,
                    record.embedding_dimension,
                    record.preprocessing_version,
                    record.source_sha256,
                    record.created_at.isoformat(),
                    record.vector_index_reference,
                    record.provenance_reference,
                ),
            )
            conn.commit()

    def get_tile(self, tile_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves raw tile record dictionary."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM tiles WHERE tile_id = ?", (tile_id,))
            row = cursor.fetchone()
            if not row:
                return None
            res = dict(row)
            if res.get("acquisition_time"):
                res["acquisition_time"] = datetime.fromisoformat(res["acquisition_time"])
            res["bounds_wgs84"] = GeoBoundingBox(
                min_lon=res["min_lon"],
                min_lat=res["min_lat"],
                max_lon=res["max_lon"],
                max_lat=res["max_lat"],
            )
            return res

    def get_embedding_record(self, tile_id: str) -> Optional[EmbeddingRecord]:
        """Retrieves embedding lineage record for a tile."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM embeddings WHERE tile_id = ?", (tile_id,))
            row = cursor.fetchone()
            if not row:
                return None
            d = dict(row)
            d["created_at"] = datetime.fromisoformat(d["created_at"])
            return EmbeddingRecord(**d)

    def is_tile_stale(
        self,
        tile_id: str,
        current_sha256: str,
        model_id: str,
        preprocessing_version: str,
    ) -> bool:
        """Determines if a tile embedding must be recomputed."""
        rec = self.get_embedding_record(tile_id)
        if not rec:
            return True
        if rec.source_sha256 != current_sha256:
            return True
        if rec.embedding_model_id != model_id:
            return True
        if rec.preprocessing_version != preprocessing_version:
            return True
        return False

    def filter_tile_ids(self, filters: Optional[RetrievalFilter] = None) -> Set[str]:
        """Filters tile IDs matching specified metadata and spatial criteria."""
        if not filters:
            with self._get_connection() as conn:
                cursor = conn.execute("SELECT tile_id FROM tiles")
                return {row["tile_id"] for row in cursor.fetchall()}

        query = "SELECT tile_id FROM tiles WHERE 1=1"
        params: List[Any] = []

        if filters.scene_id:
            query += " AND source_scene_id = ?"
            params.append(filters.scene_id)

        if filters.sensor:
            query += " AND LOWER(sensor) = LOWER(?)"
            params.append(filters.sensor)

        if filters.platform:
            query += " AND LOWER(platform) = LOWER(?)"
            params.append(filters.platform)

        if filters.date_from:
            query += " AND acquisition_time >= ?"
            params.append(filters.date_from.isoformat())

        if filters.date_to:
            query += " AND acquisition_time <= ?"
            params.append(filters.date_to.isoformat())

        # Exact 2D bounding box intersection:
        # Box A intersects Box B iff (A.min_x <= B.max_x AND A.max_x >= B.min_x AND A.min_y <= B.max_y AND A.max_y >= B.min_y)
        if filters.aoi:
            query += " AND min_lon <= ? AND max_lon >= ? AND min_lat <= ? AND max_lat >= ?"
            params.extend([
                filters.aoi.max_lon,
                filters.aoi.min_lon,
                filters.aoi.max_lat,
                filters.aoi.min_lat,
            ])

        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return {row["tile_id"] for row in cursor.fetchall()}

    def list_all_tile_ids(self) -> List[str]:
        """Returns sorted list of all indexed tile IDs."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT tile_id FROM tiles ORDER BY tile_id ASC")
            return [row["tile_id"] for row in cursor.fetchall()]

    def count_tiles(self) -> int:
        """Returns total count of registered tiles."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) AS c FROM tiles")
            return int(cursor.fetchone()["c"])

    def count_scenes(self) -> int:
        """Returns total count of unique scenes represented."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(DISTINCT source_scene_id) AS c FROM tiles")
            return int(cursor.fetchone()["c"])

    def delete_tile(self, tile_id: str) -> bool:
        """Deletes a tile and its cascaded embedding record."""
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM tiles WHERE tile_id = ?", (tile_id,))
            conn.commit()
            return cursor.rowcount > 0
