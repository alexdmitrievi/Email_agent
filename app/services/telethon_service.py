"""
Telethon MTProto service — агент пишет с реального Telegram-аккаунта.

В отличие от Bot API, здесь используется MTProto-протокол:
- Сообщения приходят от обычного пользователя, не от бота
- Можно писать первым в любой диалог (не требует /start)
- Поддерживает все типы чатов

Первичная авторизация (один раз):
    python scripts/auth_telethon.py

После авторизации session-файл сохраняется в credentials/telegram.session
и используется при каждом запуске без запроса кода.

Переменные окружения:
    TELETHON_ENABLED=true
    TELETHON_API_ID=<число с my.telegram.org>
    TELETHON_API_HASH=<хэш с my.telegram.org>
    TELETHON_PHONE=+7XXXXXXXXXX
    TELETHON_SESSION_PATH=credentials/telegram.session
"""

import asyncio
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Lazy imports — telethon опциональная зависимость
_TelegramClient = None
_events = None

try:
    from telethon import TelegramClient, events
    _TelegramClient = TelegramClient
    _events = events
except ImportError:
    logger.info("telethon not installed — Telethon channel disabled")


class TelethonService:
    """
    Обёртка над Telethon TelegramClient.

    Запускается при старте FastAPI (если TELETHON_ENABLED=true).
    Слушает входящие сообщения и отправляет ответы.
    """

    def __init__(self):
        self._client: Optional[object] = None
        self._message_handler: Optional[Callable] = None
        self._running = False

    def register_message_handler(self, handler: Callable) -> None:
        """
        Зарегистрировать функцию обработки входящих сообщений.

        handler(event) вызывается для каждого нового личного сообщения.
        event.sender_id, event.text, event.chat_id доступны в handler.
        """
        self._message_handler = handler

    async def start_client(
        self,
        api_id: int,
        api_hash: str,
        session_path: str,
        phone: str = "",
    ) -> bool:
        """
        Запустить Telethon клиент.

        Требует уже существующий session-файл (см. scripts/auth_telethon.py).
        Возвращает True если успешно, False если telethon недоступен/ошибка.
        """
        if _TelegramClient is None:
            logger.warning("Telethon not installed, skipping MTProto client")
            return False

        if not api_id or not api_hash:
            logger.warning("TELETHON_API_ID/HASH not configured, skipping")
            return False

        try:
            self._client = _TelegramClient(session_path, api_id, api_hash)

            if self._message_handler:
                @self._client.on(_events.NewMessage(incoming=True))
                async def _on_new_message(event):
                    # Только личные сообщения (не группы, не каналы)
                    if not event.is_private:
                        return
                    try:
                        await self._message_handler(event)
                    except Exception as e:
                        logger.error("Error in Telethon message handler: %s", e, exc_info=True)

            await self._client.start(phone=phone if phone else None)
            me = await self._client.get_me()
            logger.info(
                "Telethon started as @%s (id=%s)",
                me.username or "unknown",
                me.id,
            )
            self._running = True
            return True
        except Exception as e:
            logger.error("Failed to start Telethon client: %s", e)
            return False

    async def stop_client(self) -> None:
        """Остановить клиент при shutdown приложения."""
        if self._client and self._running:
            try:
                await self._client.disconnect()
                self._running = False
                logger.info("Telethon client disconnected")
            except Exception as e:
                logger.error("Error disconnecting Telethon: %s", e)

    async def send_message(self, peer: str | int, text: str) -> bool:
        """
        Отправить сообщение.

        peer: username (@username), номер телефона (+7...) или chat_id (int)
        Возвращает True если успешно.
        """
        if not self._client or not self._running:
            logger.warning("Telethon client not running, cannot send message")
            return False

        try:
            await self._client.send_message(peer, text, parse_mode="md")
            logger.info("Telethon: sent message to %s (%d chars)", peer, len(text))
            return True
        except Exception as e:
            logger.error("Telethon send_message failed to %s: %s", peer, e)
            return False

    async def send_file(self, peer: str | int, file_path: str, caption: str = "") -> bool:
        """Отправить файл (PDF, изображение) с подписью."""
        if not self._client or not self._running:
            return False
        try:
            await self._client.send_file(peer, file_path, caption=caption)
            logger.info("Telethon: sent file %s to %s", file_path, peer)
            return True
        except Exception as e:
            logger.error("Telethon send_file failed: %s", e)
            return False

    async def get_entity(self, peer: str | int) -> dict | None:
        """Получить информацию о пользователе/чате."""
        if not self._client or not self._running:
            return None
        try:
            entity = await self._client.get_entity(peer)
            return {
                "id": entity.id,
                "username": getattr(entity, "username", None),
                "first_name": getattr(entity, "first_name", None),
                "last_name": getattr(entity, "last_name", None),
                "phone": getattr(entity, "phone", None),
            }
        except Exception as e:
            logger.error("Telethon get_entity failed: %s", e)
            return None

    @property
    def is_running(self) -> bool:
        return self._running


# Глобальный синглтон
telethon_service = TelethonService()
