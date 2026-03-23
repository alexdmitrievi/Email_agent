"""A/B testing for email responses — generate two variants, pick randomly, track results."""

import logging
import random

from sqlalchemy import select

from app.config import settings
from app.config_loader import get_config
from app.db.models import ABTestResult
from app.db.session import async_session
from app.services.ai_agent import _render

logger = logging.getLogger(__name__)


async def generate_ab_variants(
    stage: str,
    lead_info: dict,
    thread_history: str,
    exchange_count: int,
) -> tuple[str, str, str]:
    """Generate two response variants and pick one randomly.

    Returns: (chosen_text, variant_label, other_text)
    """
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    config = get_config()

    system_prompt = _render("system_prompt.j2")
    stage_instructions = config.stage_instructions.get(
        stage, config.stage_instructions.get("IN_DISCUSSION", "")
    )
    if "{telegram_link}" in stage_instructions:
        stage_instructions = stage_instructions.replace(
            "{telegram_link}", settings.TELEGRAM_BOT_LINK
        )

    lead_info_str = ", ".join(f"{k}: {v}" for k, v in lead_info.items() if v)
    user_prompt = _render(
        "generate_response.j2",
        stage=stage,
        lead_info=lead_info_str,
        exchange_count=exchange_count,
        thread_history=thread_history,
        stage_instructions=stage_instructions,
    )

    # Generate two variants in parallel
    responses = []
    for temp in [0.5, 0.9]:  # A = conservative, B = creative
        resp = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temp,
            max_tokens=500,
        )
        responses.append(resp.choices[0].message.content.strip())

    variant_a, variant_b = responses
    chosen = random.choice(["A", "B"])
    chosen_text = variant_a if chosen == "A" else variant_b
    other_text = variant_b if chosen == "A" else variant_a

    logger.info("A/B test for stage %s: chose variant %s", stage, chosen)
    return chosen_text, chosen, other_text


async def record_ab_test(
    lead_id: int,
    stage: str,
    variant_a: str,
    variant_b: str,
    sent_variant: str,
) -> int:
    """Record an A/B test in the database. Returns the test ID."""
    async with async_session() as session:
        test = ABTestResult(
            lead_id=lead_id,
            stage=stage,
            variant_a=variant_a,
            variant_b=variant_b,
            sent_variant=sent_variant,
        )
        session.add(test)
        await session.commit()
        return test.id


async def record_ab_reply(lead_id: int, reply_category: str) -> None:
    """When a lead replies, mark the most recent A/B test as got_reply=True."""
    async with async_session() as session:
        result = await session.execute(
            select(ABTestResult)
            .where(ABTestResult.lead_id == lead_id, ABTestResult.got_reply == False)
            .order_by(ABTestResult.created_at.desc())
            .limit(1)
        )
        test = result.scalar_one_or_none()
        if test:
            test.got_reply = True
            test.reply_category = reply_category
            await session.commit()
            logger.info("A/B test %d: reply recorded (%s)", test.id, reply_category)
