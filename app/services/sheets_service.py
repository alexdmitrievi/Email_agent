import logging
from datetime import datetime, timezone

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from googleapiclient.discovery import build

from app.config import settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SHEET_NAME = "Leads"

# Column mapping (0-indexed)
COL_EMAIL = 0
COL_NAME = 1
COL_COMPANY = 2
COL_STAGE = 3
COL_LAST_CONTACT = 4
COL_NOTES = 5
COL_TELEGRAM = 6
COL_THREAD_ID = 7
COL_FOLLOW_UP_COUNT = 8

HEADERS = [
    "Email",
    "Name",
    "Company",
    "Stage",
    "Last Contact",
    "Notes",
    "Telegram",
    "Thread ID",
    "Follow-up Count",
]

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
    _service = build("sheets", "v4", credentials=creds)
    return _service


def _get_all_rows() -> list[list[str]]:
    service = _get_service()
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=settings.GOOGLE_SHEET_ID, range=f"{SHEET_NAME}!A:I")
        .execute()
    )
    return result.get("values", [])


def find_lead_by_email(email: str) -> dict | None:
    """Find a lead row by email address. Returns dict or None."""
    rows = _get_all_rows()
    for i, row in enumerate(rows):
        if i == 0:  # skip header
            continue
        if len(row) > COL_EMAIL and row[COL_EMAIL].lower() == email.lower():
            return _row_to_dict(row, i + 1)  # 1-indexed row number
    return None


def find_lead_by_thread_id(thread_id: str) -> dict | None:
    """Find a lead row by Gmail thread ID."""
    rows = _get_all_rows()
    for i, row in enumerate(rows):
        if i == 0:
            continue
        if len(row) > COL_THREAD_ID and row[COL_THREAD_ID] == thread_id:
            return _row_to_dict(row, i + 1)
    return None


def create_lead(
    email: str,
    name: str = "",
    company: str = "",
    stage: str = "NEW_REPLY",
    thread_id: str = "",
) -> dict:
    """Create a new lead row."""
    service = _get_service()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    row = [email, name, company, stage, now, "", "", thread_id, "0"]
    service.spreadsheets().values().append(
        spreadsheetId=settings.GOOGLE_SHEET_ID,
        range=f"{SHEET_NAME}!A:I",
        valueInputOption="RAW",
        body={"values": [row]},
    ).execute()
    logger.info("Created lead: %s", email)
    # Fetch back to get row number
    return find_lead_by_email(email)


def update_lead(row_number: int, updates: dict) -> None:
    """Update specific fields for a lead. updates keys: stage, notes, telegram, last_contact, follow_up_count."""
    service = _get_service()
    field_map = {
        "stage": COL_STAGE,
        "last_contact": COL_LAST_CONTACT,
        "notes": COL_NOTES,
        "telegram": COL_TELEGRAM,
        "thread_id": COL_THREAD_ID,
        "follow_up_count": COL_FOLLOW_UP_COUNT,
    }

    for key, value in updates.items():
        col_idx = field_map.get(key)
        if col_idx is None:
            continue
        col_letter = chr(ord("A") + col_idx)
        cell = f"{SHEET_NAME}!{col_letter}{row_number}"
        service.spreadsheets().values().update(
            spreadsheetId=settings.GOOGLE_SHEET_ID,
            range=cell,
            valueInputOption="RAW",
            body={"values": [[str(value)]]},
        ).execute()

    logger.info("Updated lead row %d: %s", row_number, updates)


def get_stale_leads(days: int) -> list[dict]:
    """Get leads that haven't been contacted in `days` days and are eligible for follow-up."""
    from datetime import timedelta

    rows = _get_all_rows()
    stale = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    for i, row in enumerate(rows):
        if i == 0:
            continue
        lead = _row_to_dict(row, i + 1)
        if lead["stage"] not in ("PORTFOLIO_SENT", "IN_DISCUSSION"):
            continue
        follow_up_count = int(lead.get("follow_up_count") or "0")
        if follow_up_count >= settings.MAX_FOLLOW_UPS:
            continue
        try:
            last = datetime.strptime(lead["last_contact"], "%Y-%m-%d %H:%M").replace(
                tzinfo=timezone.utc
            )
            if last < cutoff:
                stale.append(lead)
        except (ValueError, KeyError):
            continue

    return stale


def _row_to_dict(row: list[str], row_number: int) -> dict:
    """Convert a sheet row to a dict."""

    def safe_get(idx):
        return row[idx] if len(row) > idx else ""

    return {
        "row_number": row_number,
        "email": safe_get(COL_EMAIL),
        "name": safe_get(COL_NAME),
        "company": safe_get(COL_COMPANY),
        "stage": safe_get(COL_STAGE),
        "last_contact": safe_get(COL_LAST_CONTACT),
        "notes": safe_get(COL_NOTES),
        "telegram": safe_get(COL_TELEGRAM),
        "thread_id": safe_get(COL_THREAD_ID),
        "follow_up_count": safe_get(COL_FOLLOW_UP_COUNT),
    }
