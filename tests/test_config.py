"""Automated tests for configuration management and offline enforcement."""

import os
from pathlib import Path
from backend.config import Settings, settings


def test_default_config_offline_mode():
    """Verifies that offline mode is enabled by default adhering to Rule 1."""
    assert settings.ASTRA_OFFLINE_MODE is True


def test_config_paths_exist_as_path_objects():
    """Verifies that all storage directories are defined as Path objects."""
    assert isinstance(settings.ASTRA_DATA_DIR, Path)
    assert isinstance(settings.ASTRA_RAW_DIR, Path)
    assert isinstance(settings.ASTRA_PROCESSED_DIR, Path)
    assert isinstance(settings.ASTRA_MANIFESTS_DIR, Path)
    assert isinstance(settings.ASTRA_BENCHMARK_DIR, Path)
    assert isinstance(settings.ASTRA_MODELS_CACHE_DIR, Path)


def test_cors_origins_parsing():
    """Verifies that comma-delimited strings are parsed into a list of origins."""
    custom_settings = Settings(
        ASTRA_CORS_ORIGINS="http://localhost:3000, http://example.local",
    )
    assert custom_settings.ASTRA_CORS_ORIGINS == ["http://localhost:3000", "http://example.local"]


def test_env_override(monkeypatch):
    """Verifies that environment variables correctly override configuration."""
    monkeypatch.setenv("ASTRA_ENV", "testing")
    monkeypatch.setenv("ASTRA_PORT", "9090")
    test_settings = Settings()
    assert test_settings.ASTRA_ENV == "testing"
    assert test_settings.ASTRA_PORT == 9090
