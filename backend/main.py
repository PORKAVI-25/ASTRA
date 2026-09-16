"""ASTRA FastAPI Application Entry Point.

Automated Semantic Tracking and Retrieval Architecture.
SIH 2026 Problem Statement: SIH26227 / PS227.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.config import settings
from backend.api.v1.router import api_router
from backend.api.v1.endpoints.health import check_health

app = FastAPI(
    title="A.S.T.R.A. API",
    description=(
        "Automated Semantic Tracking and Retrieval Architecture. "
        "High-performance, offline-ready satellite imagery retrieval and change analysis."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ASTRA_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root endpoint
@app.get("/", tags=["Root"])
async def root():
    return {
        "project": "A.S.T.R.A.",
        "full_name": "Automated Semantic Tracking and Retrieval Architecture",
        "challenge": "SIH 2026 (SIH26227 / PS227)",
        "phase": "Phase 0 - Foundation",
        "status": "operational",
        "offline_mode": settings.ASTRA_OFFLINE_MODE,
        "api_docs": "/docs",
        "health_check": f"{settings.ASTRA_API_PREFIX}/health",
    }


# Direct /health alias
app.add_api_route("/health", check_health, methods=["GET"], tags=["Health & Telemetry"], include_in_schema=False)

# Mount API v1 routes
app.include_router(api_router, prefix=settings.ASTRA_API_PREFIX)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=settings.ASTRA_HOST,
        port=settings.ASTRA_PORT,
        reload=True,
    )
