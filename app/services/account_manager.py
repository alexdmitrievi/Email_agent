"""Multi-account manager — route emails to the correct account context."""

import logging
from pathlib import Path
from typing import Optional

import yaml

from app.config import settings

logger = logging.getLogger(__name__)


class AccountContext:
    """Context for a single email account."""
    def __init__(self, email: str, service_account_file: str, pubsub_topic: str, sheet_id: str):
        self.email = email
        self.service_account_file = service_account_file
        self.pubsub_topic = pubsub_topic
        self.sheet_id = sheet_id


_accounts: dict[str, AccountContext] = {}


def load_accounts() -> dict[str, AccountContext]:
    """Load multi-account config from YAML. Falls back to single account from .env."""
    global _accounts

    if settings.ACCOUNTS_CONFIG_PATH:
        path = Path(settings.ACCOUNTS_CONFIG_PATH)
        if path.exists():
            with open(path, encoding="utf-8") as f:
                raw = yaml.safe_load(f)
            for acc in raw.get("accounts", []):
                ctx = AccountContext(
                    email=acc["email"],
                    service_account_file=acc.get("service_account_file", settings.GOOGLE_SERVICE_ACCOUNT_FILE),
                    pubsub_topic=acc.get("pubsub_topic", settings.GOOGLE_PUBSUB_TOPIC),
                    sheet_id=acc.get("sheet_id", settings.GOOGLE_SHEET_ID),
                )
                _accounts[acc["email"].lower()] = ctx
            logger.info("Loaded %d email accounts", len(_accounts))
            return _accounts

    # Single account fallback
    _accounts[settings.GOOGLE_DELEGATED_EMAIL.lower()] = AccountContext(
        email=settings.GOOGLE_DELEGATED_EMAIL,
        service_account_file=settings.GOOGLE_SERVICE_ACCOUNT_FILE,
        pubsub_topic=settings.GOOGLE_PUBSUB_TOPIC,
        sheet_id=settings.GOOGLE_SHEET_ID,
    )
    logger.info("Single account mode: %s", settings.GOOGLE_DELEGATED_EMAIL)
    return _accounts


def get_account(email: str) -> Optional[AccountContext]:
    """Get account context by email address."""
    return _accounts.get(email.lower())


def get_all_accounts() -> list[AccountContext]:
    """Get all configured accounts."""
    return list(_accounts.values())


def get_default_account() -> AccountContext:
    """Get the default (first) account."""
    if _accounts:
        return next(iter(_accounts.values()))
    return AccountContext(
        email=settings.GOOGLE_DELEGATED_EMAIL,
        service_account_file=settings.GOOGLE_SERVICE_ACCOUNT_FILE,
        pubsub_topic=settings.GOOGLE_PUBSUB_TOPIC,
        sheet_id=settings.GOOGLE_SHEET_ID,
    )
