"""Tests for Redis service — Telegram history, rate limiting, delayed queue."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_redis():
    """Mock the Redis connection."""
    mock = AsyncMock()
    mock.lrange = AsyncMock(return_value=[])
    mock.rpush = AsyncMock()
    mock.ltrim = AsyncMock()
    mock.expire = AsyncMock()
    mock.get = AsyncMock(return_value=None)
    mock.incr = AsyncMock(return_value=1)
    mock.zadd = AsyncMock()
    mock.zrangebyscore = AsyncMock(return_value=[])
    mock.zremrangebyscore = AsyncMock()
    return mock


@pytest.mark.asyncio
async def test_get_telegram_history_empty(mock_redis):
    with patch("app.services.redis_service.get_redis", return_value=mock_redis):
        from app.services.redis_service import get_telegram_history
        result = await get_telegram_history(12345)
        assert result == []


@pytest.mark.asyncio
async def test_get_telegram_history_with_messages(mock_redis):
    msgs = [
        json.dumps({"role": "user", "content": "hello"}),
        json.dumps({"role": "assistant", "content": "hi"}),
    ]
    mock_redis.lrange = AsyncMock(return_value=msgs)
    with patch("app.services.redis_service.get_redis", return_value=mock_redis):
        from app.services.redis_service import get_telegram_history
        result = await get_telegram_history(12345)
        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[1]["content"] == "hi"


@pytest.mark.asyncio
async def test_append_telegram_message(mock_redis):
    with patch("app.services.redis_service.get_redis", return_value=mock_redis):
        from app.services.redis_service import append_telegram_message
        await append_telegram_message(12345, "user", "test message")
        mock_redis.rpush.assert_called_once()
        mock_redis.ltrim.assert_called_once()
        mock_redis.expire.assert_called_once()


@pytest.mark.asyncio
async def test_check_rate_limit_under(mock_redis):
    mock_redis.get = AsyncMock(return_value="100")
    with patch("app.services.redis_service.get_redis", return_value=mock_redis):
        from app.services.redis_service import check_rate_limit
        result = await check_rate_limit("test@example.com", 230)
        assert result is True


@pytest.mark.asyncio
async def test_check_rate_limit_exceeded(mock_redis):
    mock_redis.get = AsyncMock(return_value="230")
    with patch("app.services.redis_service.get_redis", return_value=mock_redis):
        from app.services.redis_service import check_rate_limit
        result = await check_rate_limit("test@example.com", 230)
        assert result is False


@pytest.mark.asyncio
async def test_increment_send_count(mock_redis):
    mock_redis.incr = AsyncMock(return_value=5)
    with patch("app.services.redis_service.get_redis", return_value=mock_redis):
        from app.services.redis_service import increment_send_count
        count = await increment_send_count("test@example.com")
        assert count == 5
        mock_redis.expire.assert_called_once()


@pytest.mark.asyncio
async def test_enqueue_delayed_reply(mock_redis):
    with patch("app.services.redis_service.get_redis", return_value=mock_redis):
        from app.services.redis_service import enqueue_delayed_reply
        await enqueue_delayed_reply({"to": "test@example.com"}, delay_seconds=60)
        mock_redis.zadd.assert_called_once()


@pytest.mark.asyncio
async def test_get_ready_replies_empty(mock_redis):
    with patch("app.services.redis_service.get_redis", return_value=mock_redis):
        from app.services.redis_service import get_ready_replies
        result = await get_ready_replies()
        assert result == []
