"""Avito Messenger API client — OAuth2 auth, read/send messages."""

import logging
import time
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_token: Optional[str] = None
_token_expires_at: float = 0.0

BASE_URL = "https://api.avito.ru"


async def _ensure_token() -> str:
    """Get a valid OAuth2 access token, refreshing if needed."""
    global _token, _token_expires_at

    if _token and time.time() < _token_expires_at - 60:
        return _token

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/token",
            data={
                "grant_type": "client_credentials",
                "client_id": settings.AVITO_CLIENT_ID,
                "client_secret": settings.AVITO_CLIENT_SECRET,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    _token = data["access_token"]
    _token_expires_at = time.time() + data.get("expires_in", 3600)
    logger.info("Avito token refreshed, expires in %ds", data.get("expires_in", 3600))
    return _token


async def _request(method: str, path: str, **kwargs) -> dict:
    """Make an authenticated request to Avito API."""
    token = await _ensure_token()
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url=BASE_URL, headers=headers, timeout=30) as client:
        resp = await client.request(method, path, **kwargs)
        resp.raise_for_status()
        return resp.json()


async def get_chats(unread_only: bool = True) -> list[dict]:
    """Get list of messenger chats."""
    user_id = settings.AVITO_USER_ID
    params = {}
    if unread_only:
        params["unread_only"] = "true"
    data = await _request("GET", f"/messenger/v2/accounts/{user_id}/chats", params=params)
    return data.get("chats", [])


async def get_messages(chat_id: str, limit: int = 20) -> list[dict]:
    """Get messages in a chat."""
    user_id = settings.AVITO_USER_ID
    data = await _request(
        "GET",
        f"/messenger/v3/accounts/{user_id}/chats/{chat_id}/messages/",
        params={"limit": limit},
    )
    return data.get("messages", [])


async def send_message(chat_id: str, text: str) -> dict:
    """Send a text message in a chat."""
    user_id = settings.AVITO_USER_ID
    data = await _request(
        "POST",
        f"/messenger/v1/accounts/{user_id}/chats/{chat_id}/messages",
        json={"message": {"text": text}, "type": "text"},
    )
    logger.info("Sent Avito message to chat %s (%d chars)", chat_id, len(text))
    return data


async def mark_chat_read(chat_id: str) -> None:
    """Mark a chat as read."""
    user_id = settings.AVITO_USER_ID
    try:
        await _request(
            "POST",
            f"/messenger/v1/accounts/{user_id}/chats/{chat_id}/read",
        )
    except Exception as e:
        logger.warning("Failed to mark chat %s as read: %s", chat_id, e)
