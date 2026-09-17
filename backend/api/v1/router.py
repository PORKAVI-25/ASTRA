"""ASTRA API v1 Router Aggregator."""

from fastapi import APIRouter
from backend.api.v1.endpoints import (
    change_classification,
    change_detection,
    change_suppression,
    health,
    ingestion,
    pipeline,
    retrieval,
    temporal,
    temporal_evidence,
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

# False-alarm suppression & quality assurance
api_router.include_router(change_suppression.router, tags=["Change Suppression"])

# Temporal evidence reasoning & earliest support
api_router.include_router(temporal_evidence.router, tags=["Temporal Evidence"])

# Temporal series & scene pairs discovery
api_router.include_router(temporal.router, tags=["Temporal Series & Pairs"])

# End-to-end pipeline orchestration
api_router.include_router(pipeline.router, tags=["Pipeline Orchestration"])
