"""ASTRA Machine Learning Embedding Benchmark Module.

Provides model adapter abstractions, candidate registry, deterministic evaluation
datasets, metrics calculation, and benchmark suites for satellite imagery representation models.
"""

from .candidates import (
    CandidateMetadata,
    CandidateRegistry,
    EmbeddingModelAdapter,
    registry,
)
from .metrics import (
    compute_retrieval_metrics,
    compute_text_image_retrieval_metrics,
    cosine_similarity,
    pairwise_cosine_similarity,
)
from .benchmark import (
    BenchmarkDataset,
    BenchmarkResult,
    EmbeddingBenchmarkRunner,
)

__all__ = [
    "EmbeddingModelAdapter",
    "CandidateMetadata",
    "CandidateRegistry",
    "registry",
    "cosine_similarity",
    "pairwise_cosine_similarity",
    "compute_retrieval_metrics",
    "compute_text_image_retrieval_metrics",
    "BenchmarkDataset",
    "BenchmarkResult",
    "EmbeddingBenchmarkRunner",
]
