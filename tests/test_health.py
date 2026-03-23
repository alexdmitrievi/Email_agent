"""Tests for health check endpoint."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_returns_status(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert data["status"] in ("ok", "degraded")
    assert "config" in data
    assert "database" in data
    assert "redis" in data
    assert "gmail" in data


def test_health_config_loaded(client):
    resp = client.get("/health")
    data = resp.json()
    assert data["config"] == "ok"
