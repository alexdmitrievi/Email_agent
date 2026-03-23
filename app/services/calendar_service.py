"""
Google Calendar service — meeting booking from email/Telegram conversations.

Uses the same Google Service Account as Gmail/Sheets.
"""

import logging
from datetime import datetime, timedelta

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from googleapiclient.discovery import build

from app.config import settings
from app.config_loader import get_config

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]

_service = None


def _get_service():
    global _service
    if _service is not None:
        return _service

    creds = service_account.Credentials.from_service_account_file(
        settings.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    creds = creds.with_subject(settings.GOOGLE_DELEGATED_EMAIL)
    creds.refresh(Request())
    _service = build("calendar", "v3", credentials=creds)
    return _service


def get_free_slots(date: datetime, duration_minutes: int | None = None) -> list[dict]:
    """Get available meeting slots for a given date.

    Returns list of dicts: [{"start": "10:00", "end": "10:30"}, ...]
    """
    config = get_config()
    cal_config = config.calendar
    if not cal_config.enabled:
        return []

    duration = duration_minutes or cal_config.slot_duration_minutes
    service = _get_service()

    # Query busy times for the day
    wh = cal_config.working_hours
    day_start = date.replace(
        hour=int(wh.start.split(":")[0]),
        minute=int(wh.start.split(":")[1]),
        second=0,
        microsecond=0,
    )
    day_end = date.replace(
        hour=int(wh.end.split(":")[0]),
        minute=int(wh.end.split(":")[1]),
        second=0,
        microsecond=0,
    )

    body = {
        "timeMin": day_start.isoformat(),
        "timeMax": day_end.isoformat(),
        "timeZone": cal_config.timezone,
        "items": [{"id": cal_config.calendar_id}],
    }

    result = service.freebusy().query(body=body).execute()
    busy_periods = result.get("calendars", {}).get(cal_config.calendar_id, {}).get("busy", [])

    # Convert busy to datetime pairs (strip timezone for comparison with naive datetimes)
    busy = []
    for period in busy_periods:
        b_start = datetime.fromisoformat(period["start"])
        b_end = datetime.fromisoformat(period["end"])
        # Make naive for comparison (we work in the configured timezone)
        if b_start.tzinfo is not None:
            b_start = b_start.replace(tzinfo=None)
        if b_end.tzinfo is not None:
            b_end = b_end.replace(tzinfo=None)
        busy.append((b_start, b_end))

    # Generate slots
    slots = []
    current = day_start
    while current + timedelta(minutes=duration) <= day_end:
        slot_end = current + timedelta(minutes=duration)
        is_free = all(
            slot_end <= b_start or current >= b_end
            for b_start, b_end in busy
        )
        if is_free:
            slots.append({
                "start": current.strftime("%H:%M"),
                "end": slot_end.strftime("%H:%M"),
                "datetime_start": current.isoformat(),
                "datetime_end": slot_end.isoformat(),
            })
        current += timedelta(minutes=duration)

    logger.info("Found %d free slots on %s", len(slots), date.strftime("%Y-%m-%d"))
    return slots


def create_meeting(
    attendee_email: str,
    attendee_name: str,
    start_datetime: str,
    duration_minutes: int | None = None,
    summary: str | None = None,
) -> dict:
    """Create a calendar meeting and send invite to the attendee.

    Args:
        attendee_email: Client's email
        attendee_name: Client's name
        start_datetime: ISO format datetime string
        duration_minutes: Meeting duration (default from config)
        summary: Event title (default: "Встреча с {company_name}")
    """
    config = get_config()
    cal_config = config.calendar
    if not cal_config.enabled:
        raise RuntimeError("Calendar is not enabled in business config")

    duration = duration_minutes or cal_config.slot_duration_minutes
    service = _get_service()

    start = datetime.fromisoformat(start_datetime)
    end = start + timedelta(minutes=duration)

    event_summary = summary or f"Встреча: {config.business.name} — {attendee_name}"

    event = {
        "summary": event_summary,
        "start": {
            "dateTime": start.isoformat(),
            "timeZone": cal_config.timezone,
        },
        "end": {
            "dateTime": end.isoformat(),
            "timeZone": cal_config.timezone,
        },
        "attendees": [
            {"email": attendee_email, "displayName": attendee_name},
        ],
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "email", "minutes": 60},
                {"method": "popup", "minutes": 15},
            ],
        },
    }

    result = (
        service.events()
        .insert(
            calendarId=cal_config.calendar_id,
            body=event,
            sendUpdates="all",
        )
        .execute()
    )

    logger.info(
        "Created meeting: %s at %s for %s (event_id=%s)",
        event_summary, start.isoformat(), attendee_email, result.get("id"),
    )
    return result
