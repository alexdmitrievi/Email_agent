"""Tests for middleware — request ID and rate limiting."""

from fastapi.testclient import TestClient

from app.main import app


def test_request_id_header():
    """Response should contain X-Request-ID header."""
    client = TestClient(app)
    resp = client.get("/health")
    assert "X-Request-ID" in resp.headers


def test_custom_request_id():
    """Custom X-Request-ID should be echoed back."""
    client = TestClient(app)
    resp = client.get("/health", headers={"X-Request-ID": "my-test-id"})
    assert resp.headers["X-Request-ID"] == "my-test-id"


def test_rate_limit_not_triggered_on_health():
    """Health endpoint should not be rate limited."""
    client = TestClient(app)
    for _ in range(50):
        resp = client.get("/health")
        assert resp.status_code == 200
