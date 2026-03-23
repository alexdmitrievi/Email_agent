"""Pytest configuration — set env vars before any imports."""

import os

# Set required env vars for tests (before app.config imports)
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("GOOGLE_DELEGATED_EMAIL", "test@example.com")
os.environ.setdefault("GOOGLE_PUBSUB_TOPIC", "projects/test/topics/test")
os.environ.setdefault("GOOGLE_SHEET_ID", "test-sheet-id")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:ABC-DEF")
os.environ.setdefault("TELEGRAM_MANAGER_CHAT_ID", "123456789")
os.environ.setdefault("BUSINESS_CONFIG_PATH", "tests/fixtures/test_business.yaml")

import pytest

from app.config_loader import init_config, load_business_config


@pytest.fixture(autouse=True)
def _load_test_config():
    """Ensure all tests use the test business config."""
    import app.config_loader as cl

    cl._config = load_business_config("tests/fixtures/test_business.yaml")

    from app.funnel.pipeline import load_transitions

    load_transitions()
    yield
    cl._config = None
