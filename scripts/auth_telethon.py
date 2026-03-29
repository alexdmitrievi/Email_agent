#!/usr/bin/env python3
"""
Первичная авторизация Telethon MTProto клиента.

Запускать ОДИН РАЗ перед первым запуском агента:
    python scripts/auth_telethon.py

Что делает:
  1. Запрашивает номер телефона (если не задан в .env)
  2. Отправляет код подтверждения в Telegram
  3. Запрашивает код из приложения
  4. При необходимости — 2FA пароль
  5. Сохраняет session-файл (credentials/telegram.session)

После успешной авторизации:
  - Файл credentials/telegram.session создан
  - Агент может запускаться без запроса кода

Требует в .env:
    TELETHON_API_ID=<с my.telegram.org>
    TELETHON_API_HASH=<с my.telegram.org>
    TELETHON_PHONE=+7XXXXXXXXXX
    TELETHON_SESSION_PATH=credentials/telegram.session

Как получить API ID и API Hash:
  1. Зайти на https://my.telegram.org
  2. Log in с номером телефона аккаунта
  3. "API development tools" → создать приложение
  4. Скопировать api_id и api_hash
"""

import asyncio
import os
import sys
from pathlib import Path

# Добавить корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent))


async def main():
    print("=" * 60)
    print("Telethon MTProto — первичная авторизация")
    print("=" * 60)

    try:
        from telethon import TelegramClient
    except ImportError:
        print("ОШИБКА: telethon не установлен.")
        print("Установите: pip install telethon")
        sys.exit(1)

    # Загружаем настройки из .env
    try:
        from app.config import settings
        api_id = settings.TELETHON_API_ID
        api_hash = settings.TELETHON_API_HASH
        phone = settings.TELETHON_PHONE
        session_path = settings.TELETHON_SESSION_PATH
    except Exception:
        # Fallback — ввод вручную
        api_id = int(input("API ID (с my.telegram.org): ").strip())
        api_hash = input("API Hash (с my.telegram.org): ").strip()
        phone = input("Номер телефона (+7...): ").strip()
        session_path = "credentials/telegram.session"

    if not api_id or not api_hash:
        print("ОШИБКА: TELETHON_API_ID и TELETHON_API_HASH обязательны в .env")
        sys.exit(1)

    if not phone:
        phone = input("Номер телефона (+7...): ").strip()

    # Создать папку для session если нужно
    session_dir = Path(session_path).parent
    session_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nSession file: {session_path}")
    print(f"Phone: {phone}")
    print("\nПодключаемся к Telegram...")

    client = TelegramClient(session_path, api_id, api_hash)

    try:
        await client.start(phone=phone)

        if await client.is_user_authorized():
            me = await client.get_me()
            print(f"\n✓ Успешная авторизация!")
            print(f"  Аккаунт: {me.first_name} {me.last_name or ''}")
            print(f"  Username: @{me.username or 'нет'}")
            print(f"  ID: {me.id}")
            print(f"\nSession сохранён: {session_path}")
            print("\nТеперь можно запускать агента с TELETHON_ENABLED=true")
        else:
            print("ОШИБКА: Авторизация не удалась")
            sys.exit(1)

    except Exception as e:
        print(f"ОШИБКА: {e}")
        sys.exit(1)
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
