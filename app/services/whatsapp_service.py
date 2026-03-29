"""
WhatsApp service via Green API — агент пишет с реального номера WhatsApp.

Green API позволяет подключить обычный WhatsApp-номер через QR-код
и работать с ним через HTTP REST API.

Настройка (один раз):
  1. Зарегистрироваться на greenapi.com
  2. Создать инстанс, отсканировать QR с телефона
  3. Получить idInstance и apiTokenInstance
  4. Указать webhook URL: https://yourdomain.com/webhooks/whatsapp
  5. Включить типы уведомлений: incomingMessageReceived

Переменные окружения:
    GREENAPI_ENABLED=true
    GREENAPI_INSTANCE_ID=<с dashboard.green-api.com>
    GREENAPI_TOKEN=<с dashboard.green-api.com>
    GREENAPI_WEBHOOK_TOKEN=<опционально, для валидации>

Формат chat_id в Green API: 7XXXXXXXXXX@c.us (без +)
"""

import logging
import re
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.green-api.com"


def _api_url(method: str) -> str:
    """Собрать URL для Green API метода."""
    return f"{BASE_URL}/waInstance{settings.GREENAPI_INSTANCE_ID}/{method}/{settings.GREENAPI_TOKEN}"


def normalize_phone(phone: str) -> str:
    """
    Нормализовать номер телефона в формат Green API chat_id.

    +79161234567 → 79161234567@c.us
    89161234567  → 79161234567@c.us
    """
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    return f"{digits}@c.us"


async def send_message(chat_id: str, text: str) -> bool:
    """
    Отправить текстовое сообщение.

    chat_id: 79161234567@c.us или просто +7916...
    Возвращает True если успешно.
    """
    if not settings.GREENAPI_ENABLED:
        logger.debug("WhatsApp disabled, skipping send")
        return False

    if "@" not in chat_id:
        chat_id = normalize_phone(chat_id)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                _api_url("sendMessage"),
                json={"chatId": chat_id, "message": text},
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("idMessage"):
                logger.info("WhatsApp: sent to %s (%d chars)", chat_id, len(text))
                return True
            logger.warning("WhatsApp send: unexpected response %s", data)
            return False
    except Exception as e:
        logger.error("WhatsApp send_message failed: %s", e)
        return False


async def send_file_by_url(chat_id: str, url: str, file_name: str, caption: str = "") -> bool:
    """
    Отправить файл по URL (PDF, изображение).

    Файл должен быть публично доступен по URL.
    """
    if not settings.GREENAPI_ENABLED:
        return False

    if "@" not in chat_id:
        chat_id = normalize_phone(chat_id)

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                _api_url("sendFileByUrl"),
                json={
                    "chatId": chat_id,
                    "urlFile": url,
                    "fileName": file_name,
                    "caption": caption,
                },
            )
            resp.raise_for_status()
            logger.info("WhatsApp: sent file %s to %s", file_name, chat_id)
            return True
    except Exception as e:
        logger.error("WhatsApp send_file_by_url failed: %s", e)
        return False


async def send_location(chat_id: str, lat: float, lon: float, name: str = "") -> bool:
    """Отправить геолокацию."""
    if not settings.GREENAPI_ENABLED:
        return False

    if "@" not in chat_id:
        chat_id = normalize_phone(chat_id)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                _api_url("sendLocation"),
                json={"chatId": chat_id, "latitude": lat, "longitude": lon, "nameLocation": name},
            )
            resp.raise_for_status()
            return True
    except Exception as e:
        logger.error("WhatsApp send_location failed: %s", e)
        return False


def parse_webhook(data: dict) -> Optional[dict]:
    """
    Разобрать входящий webhook от Green API.

    Возвращает нормализованный dict:
    {
        "chat_id": "79161234567@c.us",
        "sender_phone": "79161234567",
        "sender_name": "Имя",
        "text": "текст сообщения",
        "type": "text" | "image" | "document" | ...,
        "raw": {...},  # оригинальный payload
    }
    или None если тип события не поддерживается.
    """
    type_webhook = data.get("typeWebhook")

    if type_webhook != "incomingMessageReceived":
        return None

    message_data = data.get("messageData", {})
    sender_data = data.get("senderData", {})

    msg_type = message_data.get("typeMessage", "")
    text = ""

    if msg_type == "textMessage":
        text = message_data.get("textMessageData", {}).get("textMessage", "")
    elif msg_type in ("imageMessage", "videoMessage", "documentMessage", "audioMessage"):
        text = message_data.get(f"{msg_type}Data", {}).get("caption", "")
        if not text:
            text = f"[{msg_type.replace('Message', '')}]"
    elif msg_type == "extendedTextMessage":
        text = message_data.get("extendedTextMessageData", {}).get("text", "")
    else:
        text = f"[{msg_type}]"

    chat_id = sender_data.get("chatId", "")
    sender_phone = chat_id.replace("@c.us", "").replace("@g.us", "")
    sender_name = sender_data.get("senderName", "")

    if not chat_id or not text:
        return None

    return {
        "chat_id": chat_id,
        "sender_phone": sender_phone,
        "sender_name": sender_name,
        "text": text,
        "type": msg_type,
        "raw": data,
    }


async def get_account_info() -> dict:
    """Получить информацию об аккаунте (для проверки связи)."""
    if not settings.GREENAPI_ENABLED:
        return {"status": "disabled"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(_api_url("getStateInstance"))
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error("WhatsApp getStateInstance failed: %s", e)
        return {"status": "error", "error": str(e)}
