"""ASTRA Configuration Management.

Provides centralized, validated configuration with strict offline enforcement.
"""

from pathlib import Path
from typing import List, Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """System settings for ASTRA."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server environment
    ASTRA_ENV: str = Field(default="development", description="Environment mode (development/testing/production)")

    # Strict offline mode
    ASTRA_OFFLINE_MODE: bool = Field(
        default=True,
        description="Enforces zero runtime external network or API calls",
    )

    # Network binding
    ASTRA_HOST: str = Field(default="127.0.0.1", description="Backend host address")
    ASTRA_PORT: int = Field(default=8000, description="Backend HTTP port")
    ASTRA_API_PREFIX: str = Field(default="/api/v1", description="Prefix for API routes")

    # CORS configuration
    ASTRA_CORS_ORIGINS: Union[List[str], str] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"],
        description="Allowed CORS origins for the frontend",
    )

    # Logging
    ASTRA_LOG_LEVEL: str = Field(default="INFO", description="Application logging level")

    # Local storage paths
    ASTRA_DATA_DIR: Path = Field(default=Path("data"), description="Root data directory")
    ASTRA_RAW_DIR: Path = Field(default=Path("data/raw"), description="Raw satellite scenes")
    ASTRA_PROCESSED_DIR: Path = Field(default=Path("data/processed"), description="Processed tile chips")
    ASTRA_MANIFESTS_DIR: Path = Field(default=Path("data/manifests"), description="Metadata manifests")
    ASTRA_BENCHMARK_DIR: Path = Field(default=Path("data/benchmark"), description="Ground truth benchmark data")
    ASTRA_MODELS_CACHE_DIR: Path = Field(default=Path("models/staged"), description="Staged model weights cache")

    @field_validator("ASTRA_CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v


# Singleton instance
settings = Settings()
