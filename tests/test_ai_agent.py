"""Tests for AI agent module (with mocked OpenAI)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_openai():
    """Mock OpenAI client."""
    with patch("app.services.ai_agent._client") as mock_client:
        yield mock_client


@pytest.mark.asyncio
async def test_classify_reply_interested(mock_openai):
    from app.services.ai_agent import classify_reply

    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content=json.dumps(
                    {"category": "INTERESTED", "confidence": 0.95, "reasoning": "test"}
                )
            )
        )
    ]
    mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

    result = await classify_reply("Да, расскажите подробнее о вашей мебели")
    assert result["category"] == "INTERESTED"
    assert result["confidence"] == 0.95


@pytest.mark.asyncio
async def test_classify_reply_not_interested(mock_openai):
    from app.services.ai_agent import classify_reply

    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content=json.dumps(
                    {"category": "NOT_INTERESTED", "confidence": 0.9, "reasoning": "test"}
                )
            )
        )
    ]
    mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

    result = await classify_reply("Нет, спасибо, не интересует")
    assert result["category"] == "NOT_INTERESTED"


@pytest.mark.asyncio
async def test_classify_reply_parse_error(mock_openai):
    from app.services.ai_agent import classify_reply

    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content="not valid json"))
    ]
    mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

    result = await classify_reply("some text")
    assert result["category"] == "INTERESTED"  # fallback
    assert result["reasoning"] == "parse_error"


@pytest.mark.asyncio
async def test_generate_response(mock_openai):
    from app.services.ai_agent import generate_response

    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(content="Спасибо за интерес! Какой тип мебели вас интересует?")
        )
    ]
    mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

    result = await generate_response(
        stage="INTERESTED",
        lead_info={"email": "test@example.com", "name": "Иван"},
        thread_history="Тестовая история",
        exchange_count=1,
    )
    assert "мебели" in result.lower() or len(result) > 0


@pytest.mark.asyncio
async def test_generate_telegram_response(mock_openai):
    from app.services.ai_agent import generate_telegram_response

    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content="Добрый день! Чем могу помочь?"))
    ]
    mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

    result = await generate_telegram_response(
        lead_info={"name": "Иван"},
        conversation_history=[{"role": "user", "content": "Привет"}],
    )
    assert len(result) > 0
