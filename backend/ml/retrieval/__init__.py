"""ASTRA Semantic Retrieval Engine (Phase 2B).

Offline, modular satellite imagery semantic retrieval subsystem providing:
- Foundation model embedding services (RemoteCLIP, CLIP, Reference)
- Exact NumPy cosine vector indexing with deterministic ranking
- Persistent SQLite metadata store with spatial AOI & attribute pre-filtering
- High-level RetrievalService orchestrating search and provenance linkage
"""

from backend.ml.retrieval.embedding_service import EmbeddingService
from backend.ml.retrieval.metadata_store import MetadataStore
from backend.ml.retrieval.vector_index import NumpyCosineVectorIndex, VectorIndex
from backend.ml.retrieval.retrieval_service import RetrievalService
from backend.ml.retrieval.types import (
    EmbeddingRecord,
    ImageRetrievalRequest,
    RetrievalFilter,
    RetrievalHealthResponse,
    RetrievalResponse,
    RetrievalResultItem,
    TextRetrievalRequest,
)

__all__ = [
    "EmbeddingService",
    "VectorIndex",
    "NumpyCosineVectorIndex",
    "MetadataStore",
    "RetrievalService",
    "RetrievalFilter",
    "TextRetrievalRequest",
    "ImageRetrievalRequest",
    "RetrievalResultItem",
    "RetrievalResponse",
    "RetrievalHealthResponse",
    "EmbeddingRecord",
]
