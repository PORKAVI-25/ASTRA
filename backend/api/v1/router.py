"""ASTRA API v1 Router Aggregator."""

from fastapi import APIRouter
from backend.api.v1.endpoints import (
    change_classification,
    change_detection,
    health,
    ingestion,
    retrieval,
)

api_router = APIRouter()

# Health and diagnostics
api_router.include_router(health.router, tags=["Health & Telemetry"])

# Ingestion and scene catalog
api_router.include_router(ingestion.router, tags=["Ingestion & Catalog"])

# Semantic retrieval and vector search
api_router.include_router(retrieval.router, tags=["Semantic Retrieval"])

# Temporal change detection
api_router.include_router(change_detection.router, tags=["Change Detection"])

# Temporal change classification & evidence extraction
api_router.include_router(change_classification.router, tags=["Change Classification"])
