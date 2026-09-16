"""Ingestion orchestration and incremental catalog service."""

import json
from pathlib import Path
from typing import List, Optional
from backend.config import settings
from geospatial.contracts import (
    IngestionResponse,
    SceneManifest,
    TileManifest,
)
from backend.ingestion.validator import validate_raster
from backend.ingestion.extractor import extract_scene_metadata
from backend.ingestion.tiler import generate_tiles_for_scene
from backend.provenance.service import provenance_service


class IngestionService:
    """Manages scene ingestion, validation, tiling, and incremental cataloging."""

    def __init__(self, manifests_dir: Optional[Path] = None):
        self.manifests_dir = manifests_dir or settings.ASTRA_MANIFESTS_DIR
        self.scenes_dir = self.manifests_dir / "scenes"
        self.tiles_dir = self.manifests_dir / "tiles"

        self.scenes_dir.mkdir(parents=True, exist_ok=True)
        self.tiles_dir.mkdir(parents=True, exist_ok=True)

    def find_existing_by_hash(self, file_hash: str) -> Optional[SceneManifest]:
        """Finds already ingested scene matching source file SHA-256 hash."""
        if not file_hash:
            return None
        for scene_file in self.scenes_dir.glob("*.json"):
            try:
                with open(scene_file, "r", encoding="utf-8") as f:
                    scene = SceneManifest.model_validate_json(f.read())
                    if scene.file_hash == file_hash:
                        return scene
            except Exception:
                continue
        return None

    def get_scene(self, scene_id: str) -> Optional[SceneManifest]:
        """Loads scene manifest by ID."""
        manifest_file = self.scenes_dir / f"{scene_id}.json"
        if not manifest_file.exists():
            return None
        with open(manifest_file, "r", encoding="utf-8") as f:
            return SceneManifest.model_validate_json(f.read())

    def list_scenes(self) -> List[SceneManifest]:
        """Lists all ingested scene manifests."""
        scenes = []
        for scene_file in self.scenes_dir.glob("*.json"):
            try:
                with open(scene_file, "r", encoding="utf-8") as f:
                    scenes.append(SceneManifest.model_validate_json(f.read()))
            except Exception:
                continue
        return sorted(scenes, key=lambda x: x.created_at, reverse=True)

    def get_scene_tiles(self, scene_id: str) -> List[TileManifest]:
        """Retrieves all tile manifests for a specific scene."""
        tile_file = self.tiles_dir / f"{scene_id}.json"
        if not tile_file.exists():
            return []
        with open(tile_file, "r", encoding="utf-8") as f:
            data = json.loads(f.read())
            return [TileManifest.model_validate(item) for item in data]

    def ingest_raster(
        self,
        file_path: str,
        tile_size: int = 512,
        force_reprocess: bool = False,
    ) -> IngestionResponse:
        """Executes the complete ingestion vertical slice for a local raster file.

        Args:
            file_path: Path to the GeoTIFF or COG raster.
            tile_size: Pixel dimension for square chipped tiles.
            force_reprocess: If True, bypasses incremental cache and re-tiles.

        Returns:
            IngestionResponse with operational status and metadata.
        """
        path = Path(file_path)

        # 1. Validation
        val = validate_raster(path)
        if not val.is_valid:
            return IngestionResponse(
                status="failed",
                message=f"Validation failed: {val.error_message}",
                tile_count=0,
            )

        # 2. Extract Metadata & Compute Hash
        scene = extract_scene_metadata(path, is_cog=val.is_cog)
        if val.warnings:
            scene.processing_warnings.extend(val.warnings)

        # 3. Incremental Ingestion & Duplicate Detection
        if not force_reprocess:
            existing = self.find_existing_by_hash(scene.file_hash)
            if existing is not None:
                # Retrieve existing provenance if available
                prov_records = provenance_service.list_provenance_for_scene(existing.scene_id)
                prov_id = prov_records[-1].provenance_id if prov_records else None
                return IngestionResponse(
                    status="already_ingested",
                    message="Scene has already been ingested. Preserving existing catalog and provenance.",
                    scene=existing,
                    tile_count=existing.tile_count,
                    provenance_id=prov_id,
                )

        # 4. Deterministic Tiling
        try:
            tiles = generate_tiles_for_scene(
                scene=scene,
                tile_size=tile_size,
            )
            scene.tile_count = len(tiles)
        except Exception as e:
            return IngestionResponse(
                status="failed",
                message=f"Tiling generation failed: {str(e)}",
                tile_count=0,
            )

        # 5. Persist Scene Manifest
        scene_manifest_file = self.scenes_dir / f"{scene.scene_id}.json"
        with open(scene_manifest_file, "w", encoding="utf-8") as f:
            f.write(scene.model_dump_json(indent=2))

        # 6. Persist Tile Manifests
        tile_manifest_file = self.tiles_dir / f"{scene.scene_id}.json"
        with open(tile_manifest_file, "w", encoding="utf-8") as f:
            tiles_json = [tile.model_dump(mode="json") for tile in tiles]
            json.dump(tiles_json, f, indent=2)

        # 7. Record Provenance
        prov = provenance_service.record_ingestion(
            source_scene_id=scene.scene_id,
            parameters={
                "tile_size": tile_size,
                "tile_count": scene.tile_count,
                "file_hash": scene.file_hash,
                "format": val.format_name,
                "is_cog": val.is_cog,
                "crs": scene.crs,
            },
        )

        return IngestionResponse(
            status="ingested",
            message=f"Successfully ingested scene '{scene.scene_id}' ({val.format_name}) into {scene.tile_count} tiles.",
            scene=scene,
            tile_count=scene.tile_count,
            provenance_id=prov.provenance_id,
        )


# Singleton
ingestion_service = IngestionService()
