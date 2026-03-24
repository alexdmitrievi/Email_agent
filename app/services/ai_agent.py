"""
AI agent service — OpenAI GPT integration with config-driven Jinja2 prompts.
"""

import json
import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from openai import AsyncOpenAI

from app.config import settings
from app.config_loader import get_config

logger = logging.getLogger(__name__)

_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
_jinja_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent.parent / "prompts"),
    keep_trailing_newline=True,
)


def _render(template_name: str, config_override=None, **runtime_vars) -> str:
    """Render a Jinja2 prompt template with config + runtime vars."""
    config = config_override or get_config()
    template = _jinja_env.get_template(template_name)
    return template.render(
        business=config.business,
        products=config.products,
        tone=config.tone,
        categories=config.funnel.categories,
        **runtime_vars,
    )


async def classify_reply(email_body: str, config_override=None) -> dict:
    """Classify an incoming email reply into a category."""
    prompt = _render("classify_reply.j2", config_override=config_override, email_body=email_body)

    response = await _client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    text = response.choices[0].message.content
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        logger.error("Failed to parse classification JSON: %s", text)
        result = {"category": "INTERESTED", "confidence": 0.5, "reasoning": "parse_error"}

    logger.info("Classified reply: %s", result)
    return result


async def generate_response(
    stage: str,
    lead_info: dict,
    thread_history: str,
    exchange_count: int,
    config_override=None,
) -> str:
    """Generate an email reply based on the current funnel stage."""
    config = config_override or get_config()

    system_prompt = _render("system_prompt.j2", config_override=config)

    # Stage instructions from config
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
        config_override=config,
        stage=stage,
        lead_info=lead_info_str,
        exchange_count=exchange_count,
        thread_history=thread_history,
        stage_instructions=stage_instructions,
    )

    response = await _client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        max_tokens=500,
    )

    reply = response.choices[0].message.content.strip()
    logger.info("Generated response for stage %s (%d chars)", stage, len(reply))
    return reply


async def generate_telegram_response(
    lead_info: dict,
    conversation_history: list[dict],
) -> str:
    """Generate a Telegram message reply."""
    config = get_config()
    system_prompt = _render("system_prompt.j2")
    system_prompt += (
        f"\n\nСейчас ты общаешься в Telegram. Будь ещё более кратким — "
        f"1-{config.tone.max_sentences_telegram} предложения. "
        f"Используй неформальный, но уважительный тон."
    )

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(conversation_history)

    response = await _client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=messages,
        temperature=0.7,
        max_tokens=300,
    )

    return response.choices[0].message.content.strip()
