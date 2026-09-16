"""Deterministic retrieval and evaluation metrics for satellite embedding benchmarks.

Provides mathematical implementations for cosine similarity, Top-K precision,
Mean Reciprocal Rank (MRR), Mean Average Precision (mAP), and intra/inter-class
separation distances for image-to-image and text-to-image retrieval.
"""

from typing import Any, Dict, List, Sequence, Tuple
import numpy as np


def normalize_vector(v: np.ndarray) -> np.ndarray:
    """Normalizes an embedding vector to unit L2 norm."""
    norm = np.linalg.norm(v)
    if norm < 1e-12:
        return np.zeros_like(v)
    return v / norm


def normalize_matrix(M: np.ndarray) -> np.ndarray:
    """Row-normalizes a 2D embedding matrix to unit L2 norm."""
    norms = np.linalg.norm(M, axis=1, keepdims=True)
    norms[norms < 1e-12] = 1.0
    return M / norms


def cosine_similarity(u: np.ndarray, v: np.ndarray) -> float:
    """Calculates cosine similarity between two 1D embedding vectors."""
    u_norm = np.linalg.norm(u)
    v_norm = np.linalg.norm(v)
    if u_norm < 1e-12 or v_norm < 1e-12:
        return 0.0
    return float(np.dot(u, v) / (u_norm * v_norm))


def pairwise_cosine_similarity(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """Computes full pairwise cosine similarity matrix between two sets of embeddings.

    Args:
        A: Array of shape (N, D)
        B: Array of shape (M, D)

    Returns:
        Similarity matrix of shape (N, M) with values bounded in [-1.0, 1.0]
    """
    if A.ndim == 1:
        A = A.reshape(1, -1)
    if B.ndim == 1:
        B = B.reshape(1, -1)

    A_norm = normalize_matrix(A)
    B_norm = normalize_matrix(B)
    sim = np.matmul(A_norm, B_norm.T)
    return np.clip(sim, -1.0, 1.0)


def compute_retrieval_metrics(
    query_embeddings: np.ndarray,
    query_labels: Sequence[str],
    gallery_embeddings: np.ndarray,
    gallery_labels: Sequence[str],
    top_k_ranks: Sequence[int] = (1, 3, 5),
) -> Dict[str, Any]:
    """Computes comprehensive retrieval metrics for image-to-image ranking.

    Args:
        query_embeddings: (N_q, D) array of query representations
        query_labels: Ground-truth class labels for each query
        gallery_embeddings: (N_g, D) array of gallery representations
        gallery_labels: Ground-truth class labels for each gallery item
        top_k_ranks: K values for Top-K evaluation

    Returns:
        Dictionary containing Top-1, Top-K, MRR, mAP, and intra/inter-class distances
    """
    if len(query_labels) == 0 or len(gallery_labels) == 0:
        return {
            "top_1_accuracy": 0.0,
            "top_k_accuracy": {k: 0.0 for k in top_k_ranks},
            "mean_reciprocal_rank": 0.0,
            "mean_average_precision": 0.0,
            "intra_class_similarity_mean": 0.0,
            "inter_class_similarity_mean": 0.0,
            "separation_ratio": 0.0,
            "query_count": 0,
            "gallery_count": 0,
        }

    sim_matrix = pairwise_cosine_similarity(query_embeddings, gallery_embeddings)
    n_queries, n_gallery = sim_matrix.shape

    top_1_hits = 0
    top_k_hits = {k: 0 for k in top_k_ranks}
    reciprocal_ranks: List[float] = []
    average_precisions: List[float] = []

    intra_similarities: List[float] = []
    inter_similarities: List[float] = []

    for i in range(n_queries):
        target_label = query_labels[i]
        sims = sim_matrix[i]

        # Sort descending by similarity
        ranked_indices = np.argsort(sims)[::-1]
        ranked_labels = [gallery_labels[idx] for idx in ranked_indices]

        # Calculate intra- and inter-class similarity samples
        for j, g_idx in enumerate(ranked_indices):
            if gallery_labels[g_idx] == target_label:
                intra_similarities.append(float(sims[g_idx]))
            else:
                inter_similarities.append(float(sims[g_idx]))

        # Top-1 accuracy
        if len(ranked_labels) > 0 and ranked_labels[0] == target_label:
            top_1_hits += 1

        # Top-K accuracies
        for k in top_k_ranks:
            k_clamped = min(k, len(ranked_labels))
            if any(lbl == target_label for lbl in ranked_labels[:k_clamped]):
                top_k_hits[k] += 1

        # Reciprocal rank (rank of first relevant item, 1-indexed)
        rr = 0.0
        for rank_1idx, lbl in enumerate(ranked_labels, start=1):
            if lbl == target_label:
                rr = 1.0 / rank_1idx
                break
        reciprocal_ranks.append(rr)

        # Average precision (AP)
        num_relevant = 0
        precisions_sum = 0.0
        for rank_1idx, lbl in enumerate(ranked_labels, start=1):
            if lbl == target_label:
                num_relevant += 1
                precisions_sum += num_relevant / rank_1idx
        total_relevant = sum(1 for gl in gallery_labels if gl == target_label)
        ap = (precisions_sum / total_relevant) if total_relevant > 0 else 0.0
        average_precisions.append(ap)

    top_1_acc = round(top_1_hits / n_queries, 4)
    top_k_acc = {k: round(top_k_hits[k] / n_queries, 4) for k in top_k_ranks}
    mrr = round(float(np.mean(reciprocal_ranks)) if reciprocal_ranks else 0.0, 4)
    map_score = round(float(np.mean(average_precisions)) if average_precisions else 0.0, 4)

    intra_mean = round(float(np.mean(intra_similarities)) if intra_similarities else 0.0, 4)
    inter_mean = round(float(np.mean(inter_similarities)) if inter_similarities else 0.0, 4)
    separation_ratio = round(intra_mean / max(inter_mean, 1e-6), 4) if inter_mean > 0 else 1.0

    return {
        "top_1_accuracy": top_1_acc,
        "top_k_accuracy": top_k_acc,
        "mean_reciprocal_rank": mrr,
        "mean_average_precision": map_score,
        "intra_class_similarity_mean": intra_mean,
        "inter_class_similarity_mean": inter_mean,
        "separation_ratio": separation_ratio,
        "query_count": n_queries,
        "gallery_count": n_gallery,
    }


def compute_text_image_retrieval_metrics(
    text_embeddings: np.ndarray,
    text_labels: Sequence[str],
    image_embeddings: np.ndarray,
    image_labels: Sequence[str],
    top_k_ranks: Sequence[int] = (1, 3, 5),
) -> Dict[str, Any]:
    """Computes cross-modal retrieval metrics for text query to image candidate retrieval."""
    return compute_retrieval_metrics(
        query_embeddings=text_embeddings,
        query_labels=text_labels,
        gallery_embeddings=image_embeddings,
        gallery_labels=image_labels,
        top_k_ranks=top_k_ranks,
    )


def compute_latency_statistics(latencies_ms: Sequence[float]) -> Dict[str, float]:
    """Computes statistical distribution metrics from a sequence of execution timings."""
    if not latencies_ms:
        return {
            "mean_latency_ms": 0.0,
            "median_latency_ms": 0.0,
            "p95_latency_ms": 0.0,
            "min_latency_ms": 0.0,
            "max_latency_ms": 0.0,
            "throughput_fps": 0.0,
        }

    arr = np.array(latencies_ms, dtype=np.float64)
    mean_lat = float(np.mean(arr))
    throughput = (1000.0 / mean_lat) if mean_lat > 1e-6 else 0.0

    return {
        "mean_latency_ms": round(mean_lat, 2),
        "median_latency_ms": round(float(np.median(arr)), 2),
        "p95_latency_ms": round(float(np.percentile(arr, 95)), 2),
        "min_latency_ms": round(float(np.min(arr)), 2),
        "max_latency_ms": round(float(np.max(arr)), 2),
        "throughput_fps": round(throughput, 2),
    }
