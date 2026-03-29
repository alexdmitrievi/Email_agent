"""Telegram bot webhook — persistent state in Redis, config-driven messages."""

import logging

from fastapi import APIRouter, Request
from telegram import Update

from app.config import settings
from app.config_loader import get_config
from app.services import ai_agent, sheets_service, telegram_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks")


@router.post("/telegram")
async def telegram_webhook(request: Request):
    """Handle incoming Telegram messages."""
    # Validate secret token if configured
    if settings.TELEGRAM_WEBHOOK_SECRET:
        token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if token != settings.TELEGRAM_WEBHOOK_SECRET:
            logger.warning("Invalid Telegram webhook secret token")
            return {"status": "unauthorized"}

    data = await request.json()
    update = Update.de_json(data, telegram_service.bot)

    if not update.message or not update.message.text:
        return {"status": "ok"}

    chat_id = update.message.chat_id
    username = update.message.from_user.username or ""
    first_name = update.message.from_user.first_name or ""
    text = update.message.text

    logger.info("Telegram message from %s (@%s): %s", first_name, username, text[:100])

    # Handle /start command
    if text.startswith("/start"):
        await _handle_start(chat_id, username, first_name)
        return {"status": "ok"}

    lead = _find_lead_by_telegram(username) if username else None

    # Save user message to Redis (persistent across restarts)
    await _append_history(chat_id, "user", text)

    # Определить роль и источник трафика
    from app.services.role_manager import role_manager
    from app.services.traffic_router import traffic_router
    from app.services import supabase_service
    role_id = role_manager.assign_role_for_source("telegram", lead or {})
    traffic_source = traffic_router.detect_source("telegram", {"first_message": text})

    # Записать входящее в Supabase (non-fatal)
    await supabase_service.log_conversation(
        lead_email=(lead or {}).get("email", f"tg_{chat_id}@bot.local"),
        channel="telegram",
        direction="inbound",
        message_text=text,
        role_used=role_id,
        stage_at_time=(lead or {}).get("stage", "NEW_REPLY"),
    )

    # Check if client wants to order / meet manager
    if _should_handoff(text) or role_manager.is_handoff_trigger(role_id, text):
        config = get_config()
        if lead:
            sheets_service.update_lead(lead["row_number"], {"stage": "HANDOFF_TO_MANAGER"})
            await telegram_service.notify_manager_handoff(
                lead or {"email": "N/A", "name": first_name, "telegram": username},
                text,
            )
        reply = config.telegram.handoff_confirmation.strip()
    else:
        lead_info = lead or {"name": first_name, "telegram": username}
        history = await _get_history(chat_id)
        reply = await ai_agent.generate_telegram_response(
            lead_info=lead_info,
            conversation_history=history,
            role=role_id,
            channel="telegram",
            traffic_source=str(traffic_source),
        )

    await _append_history(chat_id, "assistant", reply)
    await telegram_service.send_message(chat_id, reply)
    return {"status": "ok"}


async def _handle_start(chat_id: int, username: str, first_name: str) -> None:
    config = get_config()
    if username:
        lead = _find_lead_by_telegram(username)
        if lead:
            logger.info("Telegram user @%s linked to lead %s", username, lead["email"])

    welcome = config.telegram.welcome_message.strip().format(
        first_name=first_name,
        company_name=config.business.name,
    )
    await telegram_service.send_message(chat_id, welcome)


def _find_lead_by_telegram(username: str) -> dict | None:
    rows = sheets_service._get_all_rows()
    for i, row in enumerate(rows):
        if i == 0:
            continue
        lead = sheets_service._row_to_dict(row, i + 1)
        if lead.get("telegram", "").lower().strip("@") == username.lower():
            return lead
    return None


def _should_handoff(text: str) -> bool:
    config = get_config()
    text_lower = text.lower()
    return any(kw in text_lower for kw in config.handoff.telegram_keywords)


async def _get_history(chat_id: int) -> list[dict]:
    """Get conversation history — Redis if available, else empty."""
    try:
        from app.services.redis_service import get_telegram_history
        return await get_telegram_history(chat_id)
    except Exception:
        return []


async def _append_history(chat_id: int, role: str, content: str) -> None:
    """Append message to Redis history (non-fatal on failure)."""
    try:
        from app.services.redis_service import append_telegram_message
        await append_telegram_message(chat_id, role, content)
    except Exception:
        pass  # Redis unavailable — non-fatal
