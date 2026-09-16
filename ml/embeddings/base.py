"""Base interface for embedding model adapters.

Enforces decoupling between retrieval pipelines and underlying foundation models
in accordance with Critical Architectural Rule 6 & 7.
"""

from abc import ABC, abstractmethod
from typing import Any, List, Optional
import numpy as np


class BaseEmbeddingAdapter(ABC):
    """Abstract base class for multi-modal Earth Observation embedding adapters."""

    def __init__(self, model_id: str, weights_path: Optional[str] = None):
        self.model_id = model_id
        self.weights_path = weights_path
        self._is_loaded = False

    @property
    def is_loaded(self) -> bool:
        """Returns whether model weights have been loaded into memory."""
        return self._is_loaded

    @abstractmethod
    def load(self) -> None:
        """Loads model weights from local storage. Must not perform online downloads."""
        pass

    @abstractmethod
    def encode_text(self, text: str) -> np.ndarray:
        """Generates a normalized embedding vector for a natural language prompt.

        Args:
            text: Query description.

        Returns:
            np.ndarray of shape (embedding_dim,)
        """
        pass

    @abstractmethod
    def encode_image(self, image: Any) -> np.ndarray:
        """Generates a normalized embedding vector for an imagery tile.

        Args:
            image: Image data as NumPy array or PIL Image.

        Returns:
            np.ndarray of shape (embedding_dim,)
        """
        pass

    @abstractmethod
    def batch_encode_images(self, images: List[Any]) -> np.ndarray:
        """Batch encodes multiple imagery tiles.

        Args:
            images: List of images.

        Returns:
            np.ndarray of shape (N, embedding_dim)
        """
        pass
