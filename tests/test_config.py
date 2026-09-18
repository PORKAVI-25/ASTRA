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


def test_default_cors_origins_include_port_5176():
    """Verifies that default origins include development port 5176 and regex matches."""
    import re
    assert "http://127.0.0.1:5176" in settings.ASTRA_CORS_ORIGINS
    assert "http://localhost:5176" in settings.ASTRA_CORS_ORIGINS
    assert settings.ASTRA_CORS_ORIGIN_REGEX is not None
    pattern = re.compile(settings.ASTRA_CORS_ORIGIN_REGEX)
    assert pattern.fullmatch("http://127.0.0.1:5176") is not None
    assert pattern.fullmatch("http://localhost:5176") is not None
    assert pattern.fullmatch("https://external-domain.com") is None
