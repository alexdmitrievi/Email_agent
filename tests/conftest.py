"""Pytest configuration — set env vars before any imports."""

import os

# Set required env vars for tests (before app.config imports)
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("GOOGLE_DELEGATED_EMAIL", "test@example.com")
os.environ.setdefault("GOOGLE_PUBSUB_TOPIC", "projects/test/topics/test")
os.environ.setdefault("GOOGLE_SHEET_ID", "test-sheet-id")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:ABC-DEF")
os.environ.setdefault("TELEGRAM_MANAGER_CHAT_ID", "123456789")
