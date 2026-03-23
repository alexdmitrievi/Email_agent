"""Tests for Google Calendar service (mocked)."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.config_loader import get_config


@pytest.fixture
def mock_calendar_service():
    with patch("app.services.calendar_service._get_service") as mock:
        yield mock


def test_calendar_config_loaded():
    config = get_config()
    assert config.calendar is not None
    # Test fixture has calendar.enabled = False
    assert config.calendar.enabled is False


def test_get_free_slots_when_disabled(mock_calendar_service):
    """When calendar is disabled, should return empty list."""
    from app.services.calendar_service import get_free_slots

    result = get_free_slots(datetime(2026, 3, 25, 10, 0))
    assert result == []
    # Should not call the API when disabled
    mock_calendar_service.assert_not_called()


def test_create_meeting_when_disabled(mock_calendar_service):
    """When calendar is disabled, should raise RuntimeError."""
    from app.services.calendar_service import create_meeting

    with pytest.raises(RuntimeError, match="not enabled"):
        create_meeting(
            attendee_email="test@example.com",
            attendee_name="Test",
            start_datetime="2026-03-25T10:00:00",
        )


def test_get_free_slots_with_enabled_calendar(mock_calendar_service):
    """Test slot generation with mocked freebusy API when calendar is enabled."""
    import app.config_loader as cl

    # Temporarily enable calendar in test config
    original = cl._config.calendar.enabled
    cl._config.calendar.enabled = True

    try:
        from app.services.calendar_service import get_free_slots

        # Mock freebusy response
        mock_service = MagicMock()
        mock_calendar_service.return_value = mock_service
        mock_service.freebusy().query().execute.return_value = {
            "calendars": {
                "primary": {
                    "busy": [
                        {"start": "2026-03-25T10:00:00+03:00", "end": "2026-03-25T11:00:00+03:00"}
                    ]
                }
            }
        }

        slots = get_free_slots(datetime(2026, 3, 25, 9, 0))
        assert isinstance(slots, list)
    finally:
        cl._config.calendar.enabled = original


def test_create_meeting_with_enabled_calendar(mock_calendar_service):
    """Test meeting creation with mocked insert API."""
    import app.config_loader as cl

    original = cl._config.calendar.enabled
    cl._config.calendar.enabled = True

    try:
        from app.services.calendar_service import create_meeting

        mock_service = MagicMock()
        mock_calendar_service.return_value = mock_service
        mock_service.events().insert().execute.return_value = {
            "id": "test-event-id",
            "htmlLink": "https://calendar.google.com/event?eid=test",
        }

        result = create_meeting(
            attendee_email="client@example.com",
            attendee_name="Иван Иванов",
            start_datetime="2026-03-25T10:00:00",
        )

        assert result["id"] == "test-event-id"
    finally:
        cl._config.calendar.enabled = original
