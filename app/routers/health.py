"""Health check with dependency probing."""

import logging

from fastapi import APIRouter

from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
async def health_check():
    """Deep health check — probes Redis, DB, and config status."""
    checks = {
        "status": "ok",
        "config": await _check_config(),
        "database": await _check_database(),
        "redis": await _check_redis(),
        "gmail": _check_gmail_credentials(),
    }

    # Overall status
    all_ok = all(v == "ok" for k, v in checks.items() if k != "status")
    checks["status"] = "ok" if all_ok else "degraded"

    return checks


async def _check_config() -> str:
    try:
        from app.config_loader import get_config
        cfg = get_config()
        return "ok" if cfg.business.name else "error"
    except Exception:
        return "not_loaded"


async def _check_database() -> str:
    try:
        from sqlalchemy import text
        from app.db.session import async_session
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        return "ok"
    except Exception as e:
        logger.debug("DB health check failed: %s", e)
        return "unavailable"


async def _check_redis() -> str:
    try:
        from app.services.redis_service import get_redis
        r = await get_redis()
        await r.ping()
        return "ok"
    except Exception as e:
        logger.debug("Redis health check failed: %s", e)
        return "unavailable"


def _check_gmail_credentials() -> str:
    from pathlib import Path
    if Path(settings.GOOGLE_SERVICE_ACCOUNT_FILE).exists():
        return "ok"
    return "credentials_missing"
