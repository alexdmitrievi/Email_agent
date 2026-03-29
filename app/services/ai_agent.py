"""
AI agent service — role-aware OpenAI GPT integration with Jinja2 prompts.

Поддерживает динамические роли (sales_manager, recruiter, consultant, support_agent),
адаптацию под канал (email, telegram, whatsapp, avito) и источник трафика.
"""

import json
import logging
from pathlib import Path
from typing import Optional

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

# Параметры AI по каналу
_CHANNEL_PARAMS = {
    "email":            {"max_tokens": 400, "temperature": 0.7, "max_sentences": 5},
    "telegram":         {"max_tokens": 200, "temperature": 0.8, "max_sentences": 3},
    "telegram_mtproto": {"max_tokens": 200, "temperature": 0.8, "max_sentences": 3},
    "whatsapp":         {"max_tokens": 150, "temperature": 0.85, "max_sentences": 2},
    "avito":            {"max_tokens": 180, "temperature": 0.75, "max_sentences": 3},
}


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


def _get_role_config(role: str):
    """Вернуть RoleConfig или None если role_manager недоступен."""
    try:
        from app.services.role_manager import role_manager
        return role_manager.get_role(role)
    except Exception:
        return None


def _get_traffic_context(channel: str, traffic_source: str) -> dict:
    """Получить контекст источника трафика для промпта."""
    try:
        from app.services.traffic_router import traffic_router, TrafficSource
        source_enum = TrafficSource(traffic_source) if traffic_source else TrafficSource.UNKNOWN
        return traffic_router.get_context_for_prompt(source_enum, channel, {})
    except Exception:
        params = _CHANNEL_PARAMS.get(channel, _CHANNEL_PARAMS["email"])
        return {
            "source": traffic_source or "unknown",
            "channel": channel,
            "source_instructions": "Отвечай профессионально и по существу.",
            "max_sentences": params["max_sentences"],
            "formality": "semiformal",
            "is_warm_lead": False,
            "is_recruiter_channel": False,
        }


async def classify_reply(
    email_body: str,
    config_override=None,
    channel: str = "email",
) -> dict:
    """Classify an incoming message into a funnel category."""
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

    logger.info("Classified reply (%s): %s", channel, result.get("category"))
    return result


async def generate_response(
    stage: str,
    lead_info: dict,
    thread_history: str,
    exchange_count: int,
    config_override=None,
    role: str = "sales_manager",
    channel: str = "email",
    traffic_source: str = "unknown",
    lead_score: int = 0,
) -> str:
    """
    Generate a reply based on funnel stage, role and channel.

    Новые параметры (все опциональные, обратно совместимо):
      role:           ID роли (sales_manager, recruiter, consultant, support_agent)
      channel:        Канал (email, telegram, telegram_mtproto, whatsapp, avito)
      traffic_source: Источник трафика (cold_email, inbound_email, avito_listing, ...)
      lead_score:     Числовой скор лида 0-100 (влияет на агрессивность закрытия)
    """
    config = config_override or get_config()
    params = _CHANNEL_PARAMS.get(channel, _CHANNEL_PARAMS["email"])

    # 1. Загрузить конфиг роли
    role_config = _get_role_config(role)

    # 2. Получить контекст источника трафика
    traffic_ctx = _get_traffic_context(channel, traffic_source)

    # 3. Инструкции для текущей стадии
    stage_instruction = config.stage_instructions.get(
        stage, config.stage_instructions.get("IN_DISCUSSION", "Продолжай разговор.")
    )
    if "{telegram_link}" in stage_instruction:
        stage_instruction = stage_instruction.replace("{telegram_link}", settings.TELEGRAM_BOT_LINK)

    # 4. Системный промпт — если есть role_config используем role_system.j2
    if role_config:
        try:
            system_prompt = _render(
                "role_system.j2",
                config_override=config,
                role=role_config,
                channel=channel,
                formality=traffic_ctx.get("formality", "semiformal"),
                max_sentences=params["max_sentences"],
                source_instructions=traffic_ctx.get("source_instructions", ""),
                is_warm_lead=traffic_ctx.get("is_warm_lead", False),
                is_recruiter_channel=traffic_ctx.get("is_recruiter_channel", False),
            )
        except Exception as e:
            logger.warning("role_system.j2 render failed, using system_prompt.j2: %s", e)
            system_prompt = _render("system_prompt.j2", config_override=config)
    else:
        system_prompt = _render("system_prompt.j2", config_override=config)

    # 5. Пользовательский промпт — если есть role_response.j2 используем его
    try:
        # Обнаружить тип возражения из текста если есть
        last_msg = thread_history.split("---")[-1] if "---" in thread_history else thread_history
        objection_hint = ""
        objection_response = ""
        if role_config:
            for obj_type, obj_response in role_config.objection_responses.items():
                obj_keywords = {
                    "price_too_high": ["дорого", "цена", "стоимость", "бюджет"],
                    "need_to_think": ["подумаю", "посоветуюсь", "не знаю"],
                    "not_right_time": ["не сейчас", "потом", "позже"],
                    "already_have_supplier": ["есть поставщик", "работаем с"],
                }.get(obj_type, [])
                if any(kw in last_msg.lower() for kw in obj_keywords):
                    objection_hint = obj_type
                    objection_response = obj_response
                    break

        user_prompt = _render(
            "role_response.j2",
            config_override=config,
            stage=stage,
            lead_info=lead_info,
            thread_history=thread_history,
            exchange_count=exchange_count,
            stage_instruction=stage_instruction,
            role_name=role_config.name if role_config else role,
            channel=channel,
            max_sentences=params["max_sentences"],
            lead_score=lead_score,
            objection_hint=objection_hint,
            objection_response=objection_response,
        )
    except Exception as e:
        logger.warning("role_response.j2 render failed, using generate_response.j2: %s", e)
        lead_info_str = ", ".join(f"{k}: {v}" for k, v in lead_info.items() if v)
        user_prompt = _render(
            "generate_response.j2",
            config_override=config,
            stage=stage,
            lead_info=lead_info_str,
            exchange_count=exchange_count,
            thread_history=thread_history,
            stage_instructions=stage_instruction,
        )

    # 6. Вызов API
    response = await _client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=params["temperature"],
        max_tokens=params["max_tokens"],
    )

    reply = response.choices[0].message.content.strip()
    logger.info(
        "Generated response: stage=%s role=%s channel=%s (%d chars)",
        stage, role, channel, len(reply),
    )
    return reply


async def generate_telegram_response(
    lead_info: dict,
    conversation_history: list[dict],
    role: str = "sales_manager",
    channel: str = "telegram",
    traffic_source: str = "unknown",
) -> str:
    """
    Generate a Telegram message reply (Bot API or MTProto).

    Используется для Telegram Bot и Telethon каналов.
    """
    config = get_config()
    role_config = _get_role_config(role)
    traffic_ctx = _get_traffic_context(channel, traffic_source)
    params = _CHANNEL_PARAMS.get(channel, _CHANNEL_PARAMS["telegram"])

    # Системный промпт
    if role_config:
        try:
            system_prompt = _render(
                "role_system.j2",
                role=role_config,
                channel=channel,
                formality=traffic_ctx.get("formality", "semiformal"),
                max_sentences=params["max_sentences"],
                source_instructions=traffic_ctx.get("source_instructions", ""),
                is_warm_lead=traffic_ctx.get("is_warm_lead", False),
                is_recruiter_channel=traffic_ctx.get("is_recruiter_channel", False),
            )
        except Exception:
            system_prompt = _render("system_prompt.j2")
    else:
        system_prompt = _render("system_prompt.j2")
        system_prompt += (
            f"\n\nСейчас ты общаешься в Telegram. "
            f"Будь кратким — максимум {config.tone.max_sentences_telegram} предложения."
        )

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(conversation_history)

    response = await _client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=messages,
        temperature=params["temperature"],
        max_tokens=params["max_tokens"],
    )

    return response.choices[0].message.content.strip()
