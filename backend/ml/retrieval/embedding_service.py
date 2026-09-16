"""ASTRA Embedding Service.

Provides a unified interface for generating image and text embeddings for retrieval,
wrapping existing Phase 2A foundation model adapters (RemoteCLIP, CLIP, Reference)
with strict offline enforcement and zero network dependencies.
"""

from pathlib import Path
from typing import List, Optional, Sequence, Union
import numpy as np

from backend.ml.benchmark.candidates import (
    EmbeddingModelAdapter,
    RemoteCLIPAdapter,
    ReferenceSpectralSpatialAdapter,
    registry,
)


class EmbeddingService:
    """Service wrapping offline embedding model adapters for semantic retrieval."""

    def __init__(
        self,
        adapter: Optional[EmbeddingModelAdapter] = None,
        model_id: str = "remoteclip-vit-b-32",
        device: str = "cpu",
    ):
        """Initializes the embedding service with an adapter.

        Args:
            adapter: Explicit EmbeddingModelAdapter instance. If None, resolves from registry.
            model_id: Registry identifier (e.g. 'remoteclip-vit-b-32', 'reference-spectral-spatial').
            device: Computing device ('cpu' or 'cuda').
        """
        self._device = device
        self._model_id = model_id

        if adapter is not None:
            self._adapter = adapter
        else:
            cand = registry.get(model_id)
            if cand is None:
                raise ValueError(f"Unknown embedding model candidate: '{model_id}'")
            self._adapter = cand

        # Validate offline readiness
        avail, reason = self._adapter.is_available()
        if not avail:
            raise RuntimeError(
                f"Embedding model '{model_id}' cannot be loaded: {reason}. "
                "Local weights must be staged offline prior to evaluation/retrieval."
            )

        # Load weights into memory
        self._adapter.load(device=self._device)
        self._meta = self._adapter.metadata()

    @property
    def model_id(self) -> str:
        """Unique identifier of the underlying model."""
        return self._meta.candidate_id

    @property
    def model_name(self) -> str:
        """Human-readable display name of the model."""
        return self._meta.display_name

    @property
    def model_version(self) -> str:
        """Architecture and model version."""
        return "1.0.0"

    @property
    def embedding_dimension(self) -> int:
        """Dimensionality of produced feature vectors."""
        return self._meta.embedding_dimension

    @property
    def preprocessing_version(self) -> str:
        """Version tag of the preprocessing pipeline."""
        if "clip" in self._meta.candidate_id.lower():
            return "v1.0.0-clip-bicubic-norm"
        return "v1.0.0-spectral-spatial-norm"

    def embed_image(self, image_input: Union[Path, str, np.ndarray]) -> np.ndarray:
        """Generates a unit-normalized 1D embedding vector for a single image.

        Args:
            image_input: File path to image or numpy image array.

        Returns:
            Normalized 1D float32 array of shape (embedding_dimension,).
        """
        if isinstance(image_input, (str, Path)):
            p = Path(image_input)
            if not p.exists():
                raise FileNotFoundError(f"Image tile not found at path: {p}")

        feat = self._adapter.encode_image(image_input)
        feat = feat.astype(np.float32)

        # Ensure strict unit L2 norm
        norm = np.linalg.norm(feat)
        if norm > 1e-12:
            feat = feat / norm
        return feat

    def embed_text(self, query: str) -> np.ndarray:
        """Generates a unit-normalized 1D embedding vector for a text query.

        Args:
            query: Search query text.

        Returns:
            Normalized 1D float32 array of shape (embedding_dimension,).

        Raises:
            ValueError: If the model does not support text encoding.
        """
        if not query or not query.strip():
            raise ValueError("Text query cannot be empty or whitespace")

        feat = self._adapter.encode_text(query.strip())
        if feat is None:
            raise ValueError(
                f"Active model '{self.model_name}' does not support natural language text queries."
            )

        feat = feat.astype(np.float32)
        norm = np.linalg.norm(feat)
        if norm > 1e-12:
            feat = feat / norm
        return feat

    def batch_embed_images(
        self, image_inputs: Sequence[Union[Path, str, np.ndarray]]
    ) -> np.ndarray:
        """Generates unit-normalized embeddings for a batch of images.

        Args:
            image_inputs: Sequence of file paths or numpy arrays.

        Returns:
            Normalized 2D float32 array of shape (N, embedding_dimension).
        """
        if not image_inputs:
            return np.empty((0, self.embedding_dimension), dtype=np.float32)

        feats = [self.embed_image(inp) for inp in image_inputs]
        matrix = np.stack(feats, axis=0).astype(np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms < 1e-12] = 1.0
        return matrix / norms
