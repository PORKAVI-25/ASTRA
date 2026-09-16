"""ASTRA Semantic Retrieval API Endpoints.

Provides REST endpoints for text-to-image semantic search, image-to-image
similarity search, and retrieval index telemetry with strict offline enforcement.
"""

from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status

from backend.config import settings
from backend.ml.retrieval.embedding_service import EmbeddingService
from backend.ml.retrieval.metadata_store import MetadataStore
from backend.ml.retrieval.retrieval_service import RetrievalService
from backend.ml.retrieval.vector_index import NumpyCosineVectorIndex
from backend.ml.retrieval.types import (
    ImageRetrievalRequest,
    RetrievalHealthResponse,
    RetrievalResponse,
    TextRetrievalRequest,
)

router = APIRouter(prefix="/retrieval")

# Global singleton instance, configurable via dependency injection
_retrieval_service: Optional[RetrievalService] = None


def get_retrieval_service() -> RetrievalService:
    """Provides the active RetrievalService instance."""
    global _retrieval_service
    if _retrieval_service is None:
        idx_dir = settings.ASTRA_INDICES_DIR
        vec_path = idx_dir / "vector_index.npz"
        db_path = idx_dir / "metadata_store.sqlite3"

        vec_index = NumpyCosineVectorIndex(dimension=512, storage_path=vec_path)
        meta_store = MetadataStore(db_path=db_path)

        # Load the explicitly configured retrieval model (defaults to remoteclip-vit-b-32)
        model_id = settings.ASTRA_RETRIEVAL_MODEL_ID
        try:
            emb_service = EmbeddingService(model_id=model_id, device="cpu")
        except RuntimeError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Configured embedding model '{model_id}' is unavailable: {str(e)}",
            )

        _retrieval_service = RetrievalService(
            embedding_service=emb_service,
            vector_index=vec_index,
            metadata_store=meta_store,
        )
    return _retrieval_service


def set_retrieval_service(service: Optional[RetrievalService]) -> None:
    """Overrides the active RetrievalService instance (useful for testing/isolation)."""
    global _retrieval_service
    _retrieval_service = service


@router.post(
    "/text",
    response_model=RetrievalResponse,
    status_code=status.HTTP_200_OK,
    summary="Zero-shot text-to-image semantic search",
)
async def text_search(
    request: TextRetrievalRequest,
    service: RetrievalService = Depends(get_retrieval_service),
):
    """Searches indexed satellite imagery tiles using a natural language text query."""
    if not request.query or not request.query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Search query cannot be empty or whitespace.",
        )

    try:
        response = service.text_to_image(
            query=request.query,
            top_k=request.top_k,
            filters=request.filters,
        )
        return response
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Text retrieval failed: {str(e)}",
        )


@router.post(
    "/image",
    response_model=RetrievalResponse,
    status_code=status.HTTP_200_OK,
    summary="Visual similarity image-to-image search",
)
async def image_search(
    request: ImageRetrievalRequest,
    service: RetrievalService = Depends(get_retrieval_service),
):
    """Searches indexed satellite imagery tiles using a query tile or local image."""
    # Strict offline safety: reject remote URLs
    if request.file_path:
        lowered = request.file_path.lower()
        if lowered.startswith(("http://", "https://", "ftp://", "s3://")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Remote URLs are strictly prohibited under ASTRA Offline Policy. Provide a local file path.",
            )

        p = Path(request.file_path)
        if not p.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Query image file not found on local filesystem: {request.file_path}",
            )

    try:
        response = service.image_to_image(
            image_input=request.file_path or "",
            top_k=request.top_k,
            filters=request.filters,
            tile_id=request.tile_id,
            exclude_self=request.exclude_query_tile,
        )
        return response
    except FileNotFoundError as fnf:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(fnf))
    except KeyError as ke:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ke))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Image retrieval failed: {str(e)}",
        )


@router.get(
    "/health",
    response_model=RetrievalHealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieval subsystem health and index telemetry",
)
async def retrieval_health(
    service: RetrievalService = Depends(get_retrieval_service),
):
    """Returns retrieval index statistics, model configuration, and offline status."""
    return service.get_health()
