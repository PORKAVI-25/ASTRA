"""ASTRA Semantic Retrieval Orchestration Service.

Coordinates query vectorization, metadata and spatial pre-filtering,
deterministic vector similarity ranking, and provenance linkage.
"""

from pathlib import Path
import time
from typing import List, Optional, Union

from backend.ml.retrieval.embedding_service import EmbeddingService
from backend.ml.retrieval.metadata_store import MetadataStore
from backend.ml.retrieval.vector_index import VectorIndex
from backend.ml.retrieval.types import (
    RetrievalFilter,
    RetrievalHealthResponse,
    RetrievalResponse,
    RetrievalResultItem,
)


class RetrievalService:
    """High-level semantic search service for satellite imagery."""

    def __init__(
        self,
        embedding_service: EmbeddingService,
        vector_index: VectorIndex,
        metadata_store: MetadataStore,
    ):
        self.embedding_service = embedding_service
        self.vector_index = vector_index
        self.metadata_store = metadata_store

    def text_to_image(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[RetrievalFilter] = None,
    ) -> RetrievalResponse:
        """Executes zero-shot natural language text query against satellite tile index."""
        t0 = time.perf_counter()

        # Generate normalized text embedding
        query_vec = self.embedding_service.embed_text(query)

        total_indexed = self.vector_index.size()

        # Apply metadata pre-filtering
        if filters is not None:
            candidate_ids = self.metadata_store.filter_tile_ids(filters)
            filtered_count = len(candidate_ids)
        else:
            candidate_ids = None
            filtered_count = total_indexed

        # Vector similarity search
        matches = self.vector_index.search(
            query_vec, top_k=top_k, candidate_ids=candidate_ids
        )

        if candidate_ids is not None:
            scored_count = len([cid for cid in candidate_ids if self.vector_index.contains(cid)])
        else:
            scored_count = total_indexed

        # Enrich results with metadata and provenance
        items = self._enrich_results(matches)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        return RetrievalResponse(
            query=query,
            query_type="text",
            total_indexed_tiles=total_indexed,
            filtered_candidates_count=filtered_count,
            scored_candidates_count=scored_count,
            total_candidates_searched=scored_count,
            returned_count=len(items),
            results=items,
            filters_applied=filters,
            execution_time_ms=round(elapsed_ms, 2),
        )

    def image_to_image(
        self,
        image_input: Union[Path, str],
        top_k: int = 10,
        filters: Optional[RetrievalFilter] = None,
        tile_id: Optional[str] = None,
        exclude_self: bool = False,
    ) -> RetrievalResponse:
        """Executes visual similarity search using a query tile or local image."""
        t0 = time.perf_counter()

        # Handle tile_id query vs explicit image path
        if tile_id and not image_input:
            existing_vec = self.vector_index.get_vector(tile_id)
            if existing_vec is not None:
                query_vec = existing_vec
            else:
                tile_meta = self.metadata_store.get_tile(tile_id)
                if not tile_meta:
                    raise KeyError(f"Tile ID '{tile_id}' not found in metadata store")
                query_vec = self.embedding_service.embed_image(tile_meta["file_path"])
            query_label = f"tile:{tile_id}"
            query_tile_id = tile_id
        else:
            p = Path(image_input)
            if not p.exists():
                raise FileNotFoundError(f"Query image not found on local filesystem: {p}")
            query_vec = self.embedding_service.embed_image(p)
            query_label = str(p.as_posix())
            query_tile_id = tile_id

        total_indexed = self.vector_index.size()

        # Apply metadata pre-filtering
        if filters is not None:
            candidate_ids = self.metadata_store.filter_tile_ids(filters)
            filtered_count = len(candidate_ids)
        else:
            candidate_ids = None
            filtered_count = total_indexed

        # Optionally exclude query tile itself
        if exclude_self and query_tile_id:
            if candidate_ids is not None:
                candidate_ids = candidate_ids - {query_tile_id}
                filtered_count = len(candidate_ids)
            else:
                all_ids = set(self.metadata_store.list_all_tile_ids()) - {query_tile_id}
                candidate_ids = all_ids
                filtered_count = len(candidate_ids)

        # Search index
        matches = self.vector_index.search(
            query_vec, top_k=top_k, candidate_ids=candidate_ids
        )

        if candidate_ids is not None:
            scored_count = len([cid for cid in candidate_ids if self.vector_index.contains(cid)])
        else:
            scored_count = total_indexed

        items = self._enrich_results(matches)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        return RetrievalResponse(
            query=query_label,
            query_type="image",
            total_indexed_tiles=total_indexed,
            filtered_candidates_count=filtered_count,
            scored_candidates_count=scored_count,
            total_candidates_searched=scored_count,
            returned_count=len(items),
            results=items,
            filters_applied=filters,
            execution_time_ms=round(elapsed_ms, 2),
        )

    def _enrich_results(self, matches: List) -> List[RetrievalResultItem]:
        items: List[RetrievalResultItem] = []
        for rank, (t_id, score) in enumerate(matches, start=1):
            tile_meta = self.metadata_store.get_tile(t_id)
            if not tile_meta:
                continue
            emb_rec = self.metadata_store.get_embedding_record(t_id)

            item = RetrievalResultItem(
                tile_id=t_id,
                scene_id=tile_meta["source_scene_id"],
                score=round(float(score), 4),
                rank=rank,
                acquisition_time=tile_meta.get("acquisition_time"),
                sensor=tile_meta.get("sensor", "unknown"),
                platform=tile_meta.get("platform", "unknown"),
                bounds_wgs84=tile_meta["bounds_wgs84"],
                provenance_id=emb_rec.provenance_reference if emb_rec else None,
                embedding_model_id=self.embedding_service.model_id,
                embedding_model_version=self.embedding_service.model_version,
                file_path=tile_meta.get("file_path"),
            )
            items.append(item)
        return items

    def get_health(self) -> RetrievalHealthResponse:
        """Returns runtime status and index telemetry."""
        return RetrievalHealthResponse(
            index_size=self.vector_index.size(),
            active_embedding_model=self.embedding_service.model_id,
            embedding_dimension=self.embedding_service.embedding_dimension,
            offline_status=True,
            backend_type="exact_numpy_cosine",
            indexed_scenes_count=self.metadata_store.count_scenes(),
        )
