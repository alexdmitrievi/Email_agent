"""Avito funnel actions — respond to workers via Avito messenger."""

import logging

from app.funnel.avito_pipeline import get_avito_config
from app.services import ai_agent, avito_service, telegram_service

logger = logging.getLogger(__name__)

REGISTRATION_URL = "https://podryadpro.ru/auth/register"


async def reply_with_interest(lead: dict, message: str, history: str, exchange_count: int) -> str:
    """Respond to an interested worker, qualify them."""
    config = get_avito_config()
    reply = await ai_agent.generate_response(
        stage=lead.get("stage", "NEW_MESSAGE"),
        lead_info=lead,
        thread_history=history,
        exchange_count=exchange_count,
        config_override=config,
    )
    await avito_service.send_message(lead["chat_id"], reply)
    return reply


async def send_materials(lead: dict, message: str, history: str, exchange_count: int) -> str:
    """Send registration link to the worker."""
    config = get_avito_config()
    reply = await ai_agent.generate_response(
        stage=lead.get("stage", "QUALIFIED"),
        lead_info=lead,
        thread_history=history,
        exchange_count=exchange_count,
        config_override=config,
    )
    # Ensure the registration link is in the message
    if REGISTRATION_URL not in reply:
        reply += f"\n\nРегистрируйся здесь: {REGISTRATION_URL}"
    await avito_service.send_message(lead["chat_id"], reply)
    return reply


async def continue_discussion(lead: dict, message: str, history: str, exchange_count: int) -> str:
    """Continue the conversation with the worker."""
    config = get_avito_config()
    reply = await ai_agent.generate_response(
        stage=lead.get("stage", "LINK_SENT"),
        lead_info=lead,
        thread_history=history,
        exchange_count=exchange_count,
        config_override=config,
    )
    await avito_service.send_message(lead["chat_id"], reply)
    return reply


async def handoff_to_manager(lead: dict, message: str, history: str, exchange_count: int) -> str:
    """Notify manager about a registered or problem worker."""
    await telegram_service.notify_manager_handoff(
        lead={"email": "avito", "name": lead.get("name", ""), "telegram": "", "stage": lead.get("stage", "")},
        last_message=message,
    )
    config = get_avito_config()
    reply = config.telegram.handoff_confirmation.strip()
    await avito_service.send_message(lead["chat_id"], reply)
    return reply


async def reply_not_interested(lead: dict, message: str, history: str, exchange_count: int) -> str:
    """Polite goodbye."""
    config = get_avito_config()
    reply = config.not_interested_reply.strip()
    await avito_service.send_message(lead["chat_id"], reply)
    return reply


async def ignore(lead: dict, message: str, history: str, exchange_count: int) -> str:
    """Do nothing for spam/auto-replies."""
    return ""


AVITO_ACTION_MAP = {
    "reply_with_interest": reply_with_interest,
    "send_materials": send_materials,
    "continue_discussion": continue_discussion,
    "handoff_to_manager": handoff_to_manager,
    "reply_not_interested": reply_not_interested,
    "ignore": ignore,
}
