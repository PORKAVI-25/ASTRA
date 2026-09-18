"""Automated tests for health check and root endpoints."""

from starlette.testclient import TestClient


def test_root_endpoint(client: TestClient):
    """Verifies that root endpoint returns operational metadata."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["project"] == "A.S.T.R.A."
    assert data["status"] == "operational"
    assert "offline_mode" in data
    assert "health_check" in data


def test_api_v1_health_endpoint(client: TestClient):
    """Verifies that /api/v1/health returns healthy status, version, and module diagnostic states."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()

    # Core health contract verification
    assert data["status"] == "healthy"
    assert data["version"] == "0.1.0"
    assert data["service"] == "ASTRA Backend API"
    assert data["offline_mode"] is True
    assert "timestamp" in data
    assert "environment" in data

    # Subsystem module readiness verification
    modules = data["modules"]
    expected_modules = ["api", "ingestion", "retrieval", "change_analysis", "provenance", "evaluation"]
    for mod in expected_modules:
        assert mod in modules, f"Module '{mod}' missing from health diagnostic response"
        assert modules[mod] in ["healthy", "ready"], f"Module '{mod}' in unexpected state: {modules[mod]}"


def test_direct_health_alias(client: TestClient):
    """Verifies that direct /health alias operates identically to /api/v1/health."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == "0.1.0"


def test_cors_origin_port_5176(client: TestClient):
    """Verifies that local frontend origin http://127.0.0.1:5176 is allowed by CORS."""
    response = client.get(
        "/api/v1/health",
        headers={"Origin": "http://127.0.0.1:5176"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://127.0.0.1:5176"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_rejected_external_origin(client: TestClient):
    """Verifies that external non-local origins do not receive CORS allow headers."""
    response = client.get(
        "/api/v1/health",
        headers={"Origin": "https://external-site.com"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") is None
