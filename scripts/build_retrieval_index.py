"""ASTRA Retrieval Index Construction CLI Script.

Discovers ingested Phase 1 tile manifests, performs incremental embedding generation
with RemoteCLIP (or specified local adapter), creates immutable provenance records,
and persists vectors and metadata with strict offline enforcement.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Dict, List, Optional

# Ensure UTF-8 output on Windows consoles
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure repository root is in python path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from backend.config import settings
from backend.ml.retrieval.embedding_service import EmbeddingService
from backend.ml.retrieval.metadata_store import MetadataStore
from backend.ml.retrieval.types import EmbeddingRecord
from backend.ml.retrieval.vector_index import NumpyCosineVectorIndex
from backend.provenance.service import provenance_service
from geospatial.contracts import ProvenanceRecord, SceneManifest, TileManifest


def print_banner():
    print("=" * 80)
    print("ASTRA PHASE 2B: LOCAL SEMANTIC RETRIEVAL INDEX BUILDER")
    print("Offline Incremental Vector Index & Metadata Ingestion Engine")
    print("=" * 80)


def load_scene_manifests(scenes_dir: Path) -> Dict[str, SceneManifest]:
    """Loads all scene manifests into a lookup map by scene_id."""
    manifests: Dict[str, SceneManifest] = {}
    if not scenes_dir.exists():
        return manifests

    for scene_file in scenes_dir.glob("*.json"):
        try:
            with open(scene_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                sm = SceneManifest.model_validate(data)
                manifests[sm.scene_id] = sm
        except Exception as e:
            print(f"  [WARN] Failed to parse scene manifest {scene_file}: {e}")
    return manifests


def discover_tile_manifests(tiles_dir: Path) -> List[TileManifest]:
    """Discovers all valid Phase 1 tile manifests."""
    tiles: List[TileManifest] = []
    if not tiles_dir.exists():
        return tiles

    for tile_file in sorted(tiles_dir.glob("*.json")):
        try:
            with open(tile_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        tiles.append(TileManifest.model_validate(item))
                elif isinstance(data, dict):
                    tiles.append(TileManifest.model_validate(data))
        except Exception as e:
            print(f"  [WARN] Failed to load tile manifest {tile_file}: {e}")
    return tiles


def build_index(
    manifests_dir: Path,
    scenes_dir: Path,
    indices_dir: Path,
    model_id: str = "remoteclip-vit-b-32",
    device: str = "cpu",
    force_reindex: bool = False,
) -> None:
    """Executes the incremental index build pipeline."""
    print(f"\n[1/4] Discovering manifests:")
    print(f"      Tiles Directory  : {manifests_dir}")
    print(f"      Scenes Directory : {scenes_dir}")

    scene_map = load_scene_manifests(scenes_dir)
    tiles = discover_tile_manifests(manifests_dir)

    print(f"      Found {len(scene_map)} scene manifests")
    print(f"      Found {len(tiles)} chipped tile manifests")

    if not tiles:
        print("\n[NOTICE]: No tile manifests found. Run Phase 1 ingestion first.")
        return

    # Initialize Embedding Service (fails clearly if weights are missing)
    print(f"\n[2/4] Initializing Embedding Engine:")
    print(f"      Target Model     : {model_id}")
    print(f"      Device           : {device.upper()}")
    try:
        embedding_service = EmbeddingService(model_id=model_id, device=device)
        print(f"      Model Name       : {embedding_service.model_name}")
        print(f"      Dimension        : {embedding_service.embedding_dimension}")
        print(f"      Preprocessing    : {embedding_service.preprocessing_version}")
    except RuntimeError as re:
        print(f"\n[FATAL ERROR]: Could not initialize embedding model '{model_id}':")
        print(f"  {re}")
        print("\nEnsure local weights are staged prior to indexing. Zero network downloads allowed.")
        sys.exit(1)

    # Initialize Vector Index and Metadata Store
    indices_dir.mkdir(parents=True, exist_ok=True)
    vec_path = indices_dir / "vector_index.npz"
    db_path = indices_dir / "metadata_store.sqlite3"

    vector_index = NumpyCosineVectorIndex(
        dimension=embedding_service.embedding_dimension,
        storage_path=vec_path,
    )
    metadata_store = MetadataStore(db_path=db_path)

    print(f"\n[3/4] Processing tiles (Incremental Check & Embedding Generation):")
    t0 = time.perf_counter()

    indexed_count = 0
    skipped_count = 0
    replaced_count = 0

    for idx, tile in enumerate(tiles, start=1):
        tile_file = Path(tile.file_path)

        # Fallback path check if relative path
        if not tile_file.is_absolute() and not tile_file.exists():
            resolved = root_dir / tile_file
            if resolved.exists():
                tile_file = resolved

        if not tile_file.exists():
            print(f"  [WARN] Tile image binary missing for {tile.tile_id} at {tile.file_path}; skipping.")
            continue

        # Check for incremental staleness
        is_stale = metadata_store.is_tile_stale(
            tile_id=tile.tile_id,
            current_sha256=tile.sha256_hash,
            model_id=embedding_service.model_id,
            preprocessing_version=embedding_service.preprocessing_version,
        )

        was_in_index = vector_index.contains(tile.tile_id)
        already_indexed = was_in_index and not is_stale

        if already_indexed and not force_reindex:
            skipped_count += 1
            continue

        # Resolve platform from scene manifest if present
        scene_manifest = scene_map.get(tile.source_scene_id)
        platform = scene_manifest.platform if scene_manifest else "unknown"

        # Generate embedding
        vector = embedding_service.embed_image(tile_file)

        # Record provenance
        now = datetime.now(timezone.utc)
        seed = f"{tile.tile_id}:{embedding_service.model_id}:{now.isoformat()}"
        prov_id = f"prov_emb_{abs(hash(seed)) % (10**16):016x}"

        prov_record = ProvenanceRecord(
            provenance_id=prov_id,
            target_tile_id=tile.tile_id,
            source_scene_id=tile.source_scene_id,
            processing_stage="semantic_embedding_generation",
            pipeline_version="0.2.0",
            parameters={
                "embedding_model_id": embedding_service.model_id,
                "embedding_model_version": embedding_service.model_version,
                "embedding_dimension": embedding_service.embedding_dimension,
                "preprocessing_version": embedding_service.preprocessing_version,
                "source_tile_sha256": tile.sha256_hash,
            },
            executed_by="astra.retrieval.indexer",
            timestamp=now,
        )

        # Save provenance record
        prov_file = settings.ASTRA_MANIFESTS_DIR / "provenance" / f"{prov_id}.json"
        prov_file.parent.mkdir(parents=True, exist_ok=True)
        prov_file.write_text(prov_record.model_dump_json(indent=2), encoding="utf-8")

        # Create EmbeddingRecord
        emb_record = EmbeddingRecord(
            tile_id=tile.tile_id,
            scene_id=tile.source_scene_id,
            embedding_model_id=embedding_service.model_id,
            embedding_model_version=embedding_service.model_version,
            embedding_dimension=embedding_service.embedding_dimension,
            preprocessing_version=embedding_service.preprocessing_version,
            source_sha256=tile.sha256_hash,
            created_at=now,
            vector_index_reference=f"idx_{tile.tile_id}",
            provenance_reference=prov_id,
        )

        # Upsert into vector index and metadata store
        vector_index.upsert(tile.tile_id, vector)
        metadata_store.store_tile(tile, platform=platform)
        metadata_store.store_embedding_record(emb_record)

        if was_in_index:
            replaced_count += 1
        else:
            indexed_count += 1

        if idx % 10 == 0 or idx == len(tiles):
            print(f"  Processed {idx}/{len(tiles)} tiles...")

    # Persist vector index
    vector_index.save()
    elapsed = time.perf_counter() - t0

    print(f"\n[4/4] Build Complete:")
    print("=" * 80)
    print("INDEX BUILD SUMMARY REPORT:")
    print(f"  Discovered Tiles    : {len(tiles)}")
    print(f"  Newly Indexed       : {indexed_count}")
    print(f"  Stale Replaced      : {replaced_count}")
    print(f"  Unchanged Skipped   : {skipped_count}")
    print(f"  Total Index Size    : {vector_index.size()} vectors")
    print(f"  Storage Location    : {vec_path} & {db_path}")
    print(f"  Processing Time     : {elapsed:.2f} seconds")
    print("=" * 80)


def main():
    print_banner()

    parser = argparse.ArgumentParser(description="ASTRA Retrieval Index Construction CLI")
    parser.add_argument(
        "--manifests-dir",
        type=str,
        default=str(settings.ASTRA_MANIFESTS_DIR / "tiles"),
        help="Path to tile manifests directory",
    )
    parser.add_argument(
        "--scenes-dir",
        type=str,
        default=str(settings.ASTRA_MANIFESTS_DIR / "scenes"),
        help="Path to scene manifests directory",
    )
    parser.add_argument(
        "--indices-dir",
        type=str,
        default=str(settings.ASTRA_INDICES_DIR),
        help="Path to output indices directory",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="remoteclip-vit-b-32",
        help="Embedding candidate model ID (default: remoteclip-vit-b-32)",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="cpu",
        help="Execution device ('cpu' or 'cuda')",
    )
    parser.add_argument(
        "--force-reindex",
        action="store_true",
        help="Force recomputation of all embeddings even if unchanged",
    )

    args = parser.parse_args()

    build_index(
        manifests_dir=Path(args.manifests_dir),
        scenes_dir=Path(args.scenes_dir),
        indices_dir=Path(args.indices_dir),
        model_id=args.model,
        device=args.device,
        force_reindex=args.force_reindex,
    )


if __name__ == "__main__":
    main()
