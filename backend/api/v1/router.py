"""ASTRA API v1 Router Aggregator."""

from fastapi import APIRouter
from backend.api.v1.endpoints import health, ingestion

api_router = APIRouter()

# Health and diagnostics
api_router.include_router(health.router, tags=["Health & Telemetry"])

# Ingestion and scene catalog
api_router.include_router(ingestion.router, tags=["Ingestion & Catalog"])
