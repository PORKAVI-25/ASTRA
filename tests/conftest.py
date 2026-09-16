"""Pytest configuration and shared fixtures for ASTRA tests."""

import pytest
from starlette.testclient import TestClient
from backend.main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    """Provides a TestClient instance for testing API endpoints."""
    return TestClient(app)
