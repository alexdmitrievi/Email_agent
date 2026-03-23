"""Tests for admin API endpoints."""

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


def test_admin_stats_no_auth(client):
    """Without ADMIN_SECRET configured, should return 403."""
    resp = client.get("/admin/stats")
    assert resp.status_code in (401, 403)


def test_admin_stats_wrong_token(client):
    resp = client.get("/admin/stats", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code in (401, 403)


def test_admin_config_with_auth(client):
    """With correct secret, should return config."""
    with patch("app.routers.admin.settings") as mock_settings:
        mock_settings.ADMIN_SECRET = "test-secret"
        mock_settings.BUSINESS_CONFIG_PATH = "tests/fixtures/test_business.yaml"
        mock_settings.GMAIL_DAILY_SEND_LIMIT = 230
        resp = client.get(
            "/admin/config",
            headers={"Authorization": "Bearer test-secret"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "business" in data


def test_admin_rate_limits_with_auth(client):
    with patch("app.routers.admin.settings") as mock_settings:
        mock_settings.ADMIN_SECRET = "test-secret"
        mock_settings.GMAIL_DAILY_SEND_LIMIT = 230
        resp = client.get(
            "/admin/rate-limits",
            headers={"Authorization": "Bearer test-secret"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "daily_max" in data
