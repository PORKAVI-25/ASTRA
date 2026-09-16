"""ASTRA Vector Index Abstraction and Exact NumPy Cosine Backend.

Provides high-performance, deterministic offline vector similarity search
with support for persistent storage, incremental upsert, candidate filtering,
and deterministic tie-breaking without external cloud or C++ dependencies.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple
import numpy as np


class VectorIndex(ABC):
    """Abstract decoupled vector index interface."""

    @abstractmethod
    def add(self, id: str, vector: np.ndarray) -> None:
        """Adds a new vector to the index. Raises ValueError if id already exists."""
        raise NotImplementedError

    @abstractmethod
    def upsert(self, id: str, vector: np.ndarray) -> None:
        """Adds or updates a vector in the index."""
        raise NotImplementedError

    @abstractmethod
    def remove(self, id: str) -> bool:
        """Removes a vector by id. Returns True if removed, False if not present."""
        raise NotImplementedError

    @abstractmethod
    def contains(self, id: str) -> bool:
        """Checks whether the index contains a vector for the given id."""
        raise NotImplementedError

    @abstractmethod
    def get_vector(self, id: str) -> Optional[np.ndarray]:
        """Retrieves the stored normalized vector for the given id, or None."""
        raise NotImplementedError

    @abstractmethod
    def search(
        self,
        vector: np.ndarray,
        top_k: int = 10,
        candidate_ids: Optional[Set[str]] = None,
    ) -> List[Tuple[str, float]]:
        """Searches for nearest neighbors using cosine similarity.

        Args:
            vector: Query vector of shape (dimension,).
            top_k: Maximum number of results to return.
            candidate_ids: Optional set of pre-filtered IDs to restrict search to.

        Returns:
            List of (id, similarity_score) sorted descending by score with deterministic tie-breaking.
        """
        raise NotImplementedError

    @abstractmethod
    def size(self) -> int:
        """Returns total number of indexed vectors."""
        raise NotImplementedError

    @abstractmethod
    def save(self, path: Optional[Path] = None) -> None:
        """Persists index to disk."""
        raise NotImplementedError

    @abstractmethod
    def load(self, path: Optional[Path] = None) -> None:
        """Loads index from disk."""
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> None:
        """Clears all vectors from the index."""
        raise NotImplementedError


class NumpyCosineVectorIndex(VectorIndex):
    """Exact local NumPy-based vector index utilizing normalized inner product.

    Features:
    - Cosine similarity via inner product on L2-normalized vectors
    - Deterministic tie-breaking on (score descending, id ascending)
    - Instant candidate mask pre-filtering
    - Compressed .npz persistent disk serialization
    - Zero external C++ or server dependencies
    """

    def __init__(self, dimension: int = 512, storage_path: Optional[Path] = None):
        self.dimension = dimension
        self.storage_path = Path(storage_path) if storage_path else None

        self._ids: List[str] = []
        self._id_to_idx: Dict[str, int] = {}
        self._matrix: np.ndarray = np.empty((0, dimension), dtype=np.float32)

        if self.storage_path and self.storage_path.exists():
            self.load()

    def _normalize(self, v: np.ndarray) -> np.ndarray:
        v = np.asarray(v, dtype=np.float32).ravel()
        if v.shape[0] != self.dimension:
            raise ValueError(
                f"Vector dimension mismatch: expected {self.dimension}, got {v.shape[0]}"
            )
        norm = np.linalg.norm(v)
        if norm > 1e-12:
            return v / norm
        return v

    def add(self, id: str, vector: np.ndarray) -> None:
        if id in self._id_to_idx:
            raise ValueError(f"Vector ID '{id}' already exists in index. Use upsert() instead.")
        norm_v = self._normalize(vector)

        idx = len(self._ids)
        self._ids.append(id)
        self._id_to_idx[id] = idx

        if self._matrix.shape[0] == 0:
            self._matrix = norm_v.reshape(1, self.dimension)
        else:
            self._matrix = np.vstack([self._matrix, norm_v])

    def upsert(self, id: str, vector: np.ndarray) -> None:
        norm_v = self._normalize(vector)
        if id in self._id_to_idx:
            idx = self._id_to_idx[id]
            self._matrix[idx] = norm_v
        else:
            idx = len(self._ids)
            self._ids.append(id)
            self._id_to_idx[id] = idx
            if self._matrix.shape[0] == 0:
                self._matrix = norm_v.reshape(1, self.dimension)
            else:
                self._matrix = np.vstack([self._matrix, norm_v])

    def remove(self, id: str) -> bool:
        if id not in self._id_to_idx:
            return False

        idx_to_remove = self._id_to_idx[id]
        n = len(self._ids)

        if idx_to_remove == n - 1:
            # Last element, simply pop
            self._ids.pop()
            del self._id_to_idx[id]
            self._matrix = self._matrix[:-1]
        else:
            # Swap with last element for O(1) removal
            last_id = self._ids[-1]
            self._ids[idx_to_remove] = last_id
            self._id_to_idx[last_id] = idx_to_remove
            self._matrix[idx_to_remove] = self._matrix[-1]

            self._ids.pop()
            del self._id_to_idx[id]
            self._matrix = self._matrix[:-1]

        return True

    def contains(self, id: str) -> bool:
        return id in self._id_to_idx

    def get_vector(self, id: str) -> Optional[np.ndarray]:
        if id not in self._id_to_idx:
            return None
        idx = self._id_to_idx[id]
        return self._matrix[idx].copy()

    def size(self) -> int:
        return len(self._ids)

    def search(
        self,
        vector: np.ndarray,
        top_k: int = 10,
        candidate_ids: Optional[Set[str]] = None,
    ) -> List[Tuple[str, float]]:
        if self.size() == 0 or top_k <= 0:
            return []

        q = self._normalize(vector)

        if candidate_ids is not None:
            # Restrict search strictly to candidate subset
            matched_indices = [
                self._id_to_idx[cid] for cid in candidate_ids if cid in self._id_to_idx
            ]
            if not matched_indices:
                return []
            sub_matrix = self._matrix[matched_indices]
            scores = sub_matrix.dot(q)
            id_subset = [self._ids[idx] for idx in matched_indices]
        else:
            scores = self._matrix.dot(q)
            id_subset = self._ids

        # Pair scores with IDs
        scored_pairs = list(zip(id_subset, scores.tolist()))

        # Deterministic ranking: sort primarily by score descending, secondarily by id ascending
        scored_pairs.sort(key=lambda item: (-round(float(item[1]), 6), item[0]))

        return [(item[0], float(item[1])) for item in scored_pairs[:top_k]]

    def save(self, path: Optional[Path] = None) -> None:
        target_path = Path(path or self.storage_path)
        if not target_path:
            raise ValueError("No storage path provided to save index.")

        target_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            target_path,
            ids=np.array(self._ids, dtype=object),
            vectors=self._matrix,
            dimension=np.array([self.dimension], dtype=np.int32),
        )

    def load(self, path: Optional[Path] = None) -> None:
        target_path = Path(path or self.storage_path)
        if not target_path or not target_path.exists():
            raise FileNotFoundError(f"Index storage file not found at: {target_path}")

        data = np.load(target_path, allow_pickle=True)
        self._ids = [str(x) for x in data["ids"].tolist()]
        self._matrix = data["vectors"].astype(np.float32)
        self.dimension = int(data["dimension"][0])
        self._id_to_idx = {id_: idx for idx, id_ in enumerate(self._ids)}

    def clear(self) -> None:
        self._ids = []
        self._id_to_idx = {}
        self._matrix = np.empty((0, self.dimension), dtype=np.float32)
