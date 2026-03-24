"""Redis client — shared connection for all services."""

import logging
from typing import Optional

import redis.asyncio as redis

from app.config import settings

logger = logging.getLogger(__name__)

_pool: Optional[redis.Redis] = None


async def get_redis() -> redis.Redis:
    """Get or create the Redis connection pool."""
    global _pool
    if _pool is None:
        _pool = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=20,
        )
        logger.info("Redis connected: %s", settings.REDIS_URL)
    return _pool


async def close_redis() -> None:
    """Close the Redis connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("Redis disconnected")


# ---- Telegram conversation persistence ----

TELEGRAM_HISTORY_PREFIX = "tg:chat:"
TELEGRAM_HISTORY_MAX = 20


async def get_telegram_history(chat_id: int) -> list[dict]:
    """Get conversation history for a Telegram chat from Redis."""
    import json
    r = await get_redis()
    raw = await r.lrange(f"{TELEGRAM_HISTORY_PREFIX}{chat_id}", 0, -1)
    return [json.loads(item) for item in raw]


async def append_telegram_message(chat_id: int, role: str, content: str) -> None:
    """Append a message to Telegram conversation history in Redis."""
    import json
    r = await get_redis()
    key = f"{TELEGRAM_HISTORY_PREFIX}{chat_id}"
    await r.rpush(key, json.dumps({"role": role, "content": content}))
    await r.ltrim(key, -TELEGRAM_HISTORY_MAX, -1)
    await r.expire(key, 86400 * 7)  # TTL 7 days


# ---- Rate limiting ----

RATE_LIMIT_PREFIX = "ratelimit:gmail:"


async def check_rate_limit(account_email: str, daily_limit: int) -> bool:
    """Check if we can send another email. Returns True if OK."""
    from datetime import datetime, timezone
    r = await get_redis()
    date_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"{RATE_LIMIT_PREFIX}{account_email}:{date_key}"
    count = await r.get(key)
    return int(count or 0) < daily_limit


async def increment_send_count(account_email: str) -> int:
    """Increment daily send count, return new count."""
    from datetime import datetime, timezone
    r = await get_redis()
    date_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"{RATE_LIMIT_PREFIX}{account_email}:{date_key}"
    count = await r.incr(key)
    await r.expire(key, 86400 + 3600)  # TTL 25 hours
    return count


# ---- Delayed sending queue ----

DELAYED_QUEUE_KEY = "queue:delayed_replies"


async def enqueue_delayed_reply(payload: dict, delay_seconds: int) -> None:
    """Schedule a reply to be sent after a delay."""
    import json
    import time
    r = await get_redis()
    execute_at = time.time() + delay_seconds
    await r.zadd(DELAYED_QUEUE_KEY, {json.dumps(payload): execute_at})


async def get_ready_replies() -> list[dict]:
    """Get replies whose delay has passed."""
    import json
    import time
    r = await get_redis()
    now = time.time()
    items = await r.zrangebyscore(DELAYED_QUEUE_KEY, "-inf", now)
    if items:
        await r.zremrangebyscore(DELAYED_QUEUE_KEY, "-inf", now)
    return [json.loads(item) for item in items]


# ---- Avito lead state persistence ----

AVITO_LEAD_PREFIX = "avito:lead:"
AVITO_COOLDOWN_PREFIX = "avito:cooldown:"
AVITO_LEAD_TTL = 86400 * 30  # 30 days


async def get_avito_lead_state(chat_id: str) -> dict | None:
    """Get Avito lead state from Redis."""
    import json
    r = await get_redis()
    raw = await r.get(f"{AVITO_LEAD_PREFIX}{chat_id}")
    return json.loads(raw) if raw else None


async def set_avito_lead_state(chat_id: str, state: dict) -> None:
    """Save Avito lead state to Redis."""
    import json
    r = await get_redis()
    await r.set(f"{AVITO_LEAD_PREFIX}{chat_id}", json.dumps(state), ex=AVITO_LEAD_TTL)


async def check_avito_cooldown(chat_id: str) -> bool:
    """Return True if we can reply (no cooldown active)."""
    r = await get_redis()
    return not await r.exists(f"{AVITO_COOLDOWN_PREFIX}{chat_id}")


async def set_avito_cooldown(chat_id: str, seconds: int = 300) -> None:
    """Set a cooldown to prevent rapid-fire replies."""
    r = await get_redis()
    await r.set(f"{AVITO_COOLDOWN_PREFIX}{chat_id}", "1", ex=seconds)
