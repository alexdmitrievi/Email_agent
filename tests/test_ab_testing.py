"""Tests for A/B testing service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_generate_ab_variants():
    """Test that two different variants are generated."""
    with patch("openai.AsyncOpenAI") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client

        # Two different responses for temp=0.5 and temp=0.9
        resp_a = MagicMock()
        resp_a.choices = [MagicMock(message=MagicMock(content="Вариант А — формальный"))]
        resp_b = MagicMock()
        resp_b.choices = [MagicMock(message=MagicMock(content="Вариант Б — креативный"))]
        mock_client.chat.completions.create = AsyncMock(side_effect=[resp_a, resp_b])

        from app.services.ab_testing_service import generate_ab_variants

        chosen, variant, other = await generate_ab_variants(
            stage="INTERESTED",
            lead_info={"email": "test@example.com"},
            thread_history="test",
            exchange_count=1,
        )

        assert variant in ("A", "B")
        assert chosen  # non-empty
        assert other  # non-empty
        assert chosen != other


@pytest.mark.asyncio
async def test_record_ab_test():
    """Test recording A/B test to database."""
    with patch("app.services.ab_testing_service.async_session") as mock_session_maker:
        mock_session = AsyncMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_session.commit = AsyncMock()

        from app.services.ab_testing_service import record_ab_test

        result = await record_ab_test(
            lead_id=1,
            stage="INTERESTED",
            variant_a="Вариант А",
            variant_b="Вариант Б",
            sent_variant="A",
        )
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
