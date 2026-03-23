"""
Google Drive service — file sharing from conversations.

Allows sending Drive links instead of (or in addition to) attachments.
"""

import logging

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from googleapiclient.discovery import build

from app.config import settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

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
    _service = build("drive", "v3", credentials=creds)
    return _service


def get_shareable_link(file_id: str) -> str:
    """Get a shareable web link for a Drive file."""
    service = _get_service()
    file_meta = service.files().get(
        fileId=file_id,
        fields="webViewLink",
    ).execute()
    link = file_meta.get("webViewLink", "")
    logger.info("Got shareable link for file %s: %s", file_id, link)
    return link


def list_folder(folder_id: str) -> list[dict]:
    """List files in a Drive folder.

    Returns list of dicts: [{"id": "...", "name": "...", "mimeType": "...", "webViewLink": "..."}, ...]
    """
    service = _get_service()
    results = (
        service.files()
        .list(
            q=f"'{folder_id}' in parents and trashed = false",
            fields="files(id, name, mimeType, webViewLink, size)",
            orderBy="name",
        )
        .execute()
    )
    files = results.get("files", [])
    logger.info("Listed %d files in folder %s", len(files), folder_id)
    return files


def get_file_metadata(file_id: str) -> dict:
    """Get metadata for a single file."""
    service = _get_service()
    return (
        service.files()
        .get(fileId=file_id, fields="id, name, mimeType, webViewLink, size")
        .execute()
    )
