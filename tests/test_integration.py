"""Integration tests — end-to-end flows with mocked external services.

These tests verify the full pipeline works without real API calls.
"""

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _make_pubsub_payload(history_id: int) -> dict:
    """Build a Gmail Pub/Sub push notification payload."""
    data = json.dumps({"historyId": history_id})
    data_b64 = base64.urlsafe_b64encode(data.encode()).decode()
    return {"message": {"data": data_b64}}


class TestGmailWebhookIntegration:
    """Test the full Gmail webhook → classify → transition → reply pipeline."""

    def test_gmail_push_no_data(self, client):
        resp = client.post("/webhooks/gmail", json={"message": {}})
        assert resp.status_code == 200
        assert resp.json()["status"] == "no_data"

    def test_gmail_push_duplicate(self, client):
        """Same historyId should be deduplicated."""
        import app.routers.gmail_webhook as gw
        gw._last_history_id = 999
        payload = _make_pubsub_payload(999)
        resp = client.post("/webhooks/gmail", json=payload)
        assert resp.json()["status"] == "duplicate"
        gw._last_history_id = 0  # reset

    @patch("app.services.gmail_service.get_history", return_value=[])
    def test_gmail_push_no_messages(self, mock_history, client):
        """Push with no new messages should return processed=0."""
        import app.routers.gmail_webhook as gw
        gw._last_history_id = 0
        payload = _make_pubsub_payload(100)
        resp = client.post("/webhooks/gmail", json=payload)
        data = resp.json()
        assert data["status"] == "ok"
        assert data["processed"] == 0

    def test_follow_ups_endpoint(self, client):
        """Follow-ups endpoint should work even with empty sheets."""
        with patch("app.services.sheets_service.get_stale_leads", return_value=[]):
            resp = client.post("/webhooks/follow-ups")
            assert resp.status_code == 200
            assert resp.json()["follow_ups_sent"] == 0


class TestTelegramWebhookIntegration:
    """Test Telegram webhook with mocked bot."""

    def test_telegram_no_message(self, client):
        with patch("app.services.telegram_service.bot"):
            resp = client.post("/webhooks/telegram", json={"update_id": 1})
            assert resp.status_code == 200

    def test_telegram_webhook_secret_validation(self, client):
        """If secret is configured, requests without it should be rejected."""
        import app.config as cfg
        original = cfg.settings.TELEGRAM_WEBHOOK_SECRET
        cfg.settings.TELEGRAM_WEBHOOK_SECRET = "my-secret"
        try:
            resp = client.post(
                "/webhooks/telegram",
                json={
                    "update_id": 1,
                    "message": {
                        "text": "hi",
                        "chat": {"id": 1, "type": "private"},
                        "from": {"id": 1, "is_bot": False, "first_name": "Test"},
                        "date": 0,
                        "message_id": 1,
                    },
                },
            )
            assert resp.json().get("status") == "unauthorized"
        finally:
            cfg.settings.TELEGRAM_WEBHOOK_SECRET = original


class TestDashboard:
    """Test the analytics dashboard."""

    def test_dashboard_returns_html(self, client):
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Email Agent Dashboard" in resp.text


class TestDailySummary:
    """Test daily summary endpoint."""

    @patch("app.services.telegram_service.notify_manager_daily_summary", new_callable=AsyncMock)
    @patch("app.services.analytics_service.generate_summary_text", new_callable=AsyncMock, return_value="Test summary")
    def test_daily_summary_endpoint(self, mock_summary, mock_notify, client):
        resp = client.post("/webhooks/daily-summary")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
