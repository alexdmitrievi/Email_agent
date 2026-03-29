"""
Telethon incoming message handler.

Обрабатывает входящие сообщения от реального Telegram-аккаунта (MTProto).
Регистрируется как event handler в telethon_service при старте.

Логика аналогична telegram_webhook.py, но:
  - Работает через Telethon events (не Bot API webhooks)
  - Ответы идут тоже через Telethon (от реального аккаунта)
  - channel = "telegram_mtproto" для аналитики
"""

import logging

from app.config import settings
from app.config_loader import get_config
from app.funnel.pipeline import get_transition
from app.funnel.stages import is_terminal
from app.services import ai_agent, sheets_service
from app.services.role_manager import role_manager
from app.services.traffic_router import traffic_router
from app.services import supabase_service

logger = logging.getLogger(__name__)

CHANNEL = "telegram_mtproto"


async def handle_telethon_message(event) -> None:
    """
    Обработчик входящего сообщения через Telethon MTProto.

    event: Telethon NewMessage event
    """
    try:
        text = event.text or ""
        if not text:
            return

        sender = await event.get_sender()
        chat_id = event.chat_id
        username = getattr(sender, "username", None) or ""
        first_name = getattr(sender, "first_name", None) or ""
        phone = getattr(sender, "phone", None) or ""

        sender_id = str(sender.id)

        logger.info(
            "Telethon MTProto message from @%s (id=%s): %s",
            username, sender_id, text[:100],
        )

        # Найти лид по telegram username
        lead = None
        if username:
            lead = _find_lead_by_telegram(username)
        if not lead and phone:
            lead = sheets_service.find_lead_by_email(f"whatsapp_{phone.strip('+')}@wa.local")

        # Создать лид если не найден
        if not lead:
            email_key = f"tg_{sender_id}@mtproto.local"
            lead = sheets_service.find_lead_by_email(email_key)
            if not lead:
                lead = sheets_service.create_lead(
                    email=email_key,
                    name=first_name,
                    thread_id=f"tg_{chat_id}",
                )
                if username:
                    sheets_service.update_lead(lead["row_number"], {"telegram": username})

        current_stage = lead.get("stage", "NEW_REPLY")

        if is_terminal(current_stage):
            logger.info("Telethon lead in terminal stage %s, skipping", current_stage)
            return

        # Определить роль и источник трафика
        traffic_source = traffic_router.detect_source(CHANNEL, {"first_message": text})
        role_id = role_manager.assign_role_for_source(CHANNEL, lead)

        # Сохранить входящее в Supabase
        await supabase_service.log_conversation(
            lead_email=lead.get("email", ""),
            channel=CHANNEL,
            direction="inbound",
            message_text=text,
            role_used=role_id,
            stage_at_time=current_stage,
        )

        # История разговора из Redis
        history = await _get_history(chat_id)
        await _append_history(chat_id, "user", text)

        # Проверить хэндофф
        config = get_config()
        should_handoff = (
            role_manager.is_handoff_trigger(role_id, text)
            or any(kw in text.lower() for kw in config.handoff.telegram_keywords)
        )

        if should_handoff:
            sheets_service.update_lead(lead["row_number"], {"stage": "HANDOFF_TO_MANAGER"})
            from app.services import telegram_service
            await telegram_service.notify_manager_handoff(
                lead={"email": lead.get("email", ""), "name": first_name, "telegram": username},
                message=f"📱 Telegram MTProto (@{username or sender_id})\n\n{text}",
            )
            reply = config.telegram.handoff_confirmation.strip()
        else:
            # Классификация и переход
            classification = await ai_agent.classify_reply(text, channel=CHANNEL)
            category = classification.get("category", "INTERESTED")
            new_stage, _ = get_transition(current_stage, category)
            sheets_service.update_lead(lead["row_number"], {"stage": new_stage})
            lead["stage"] = new_stage

            # Генерация ответа
            history_updated = await _get_history(chat_id)
            reply = await ai_agent.generate_telegram_response(
                lead_info={"name": first_name, "telegram": username},
                conversation_history=history_updated,
                role=role_id,
                channel=CHANNEL,
                traffic_source=str(traffic_source),
            )

            await supabase_service.log_journey_event(
                lead_email=lead.get("email", ""),
                event_type="stage_change" if new_stage != current_stage else "message_sent",
                channel=CHANNEL,
                from_stage=current_stage,
                to_stage=new_stage,
                role_used=role_id,
                message_preview=text[:200],
                classification=category,
            )

        # Отправить ответ через Telethon (с реального аккаунта)
        from app.services.telethon_service import telethon_service
        sent = await telethon_service.send_message(chat_id, reply)
        if sent:
            await _append_history(chat_id, "assistant", reply)

        # Записать ответ в Supabase
        await supabase_service.log_conversation(
            lead_email=lead.get("email", ""),
            channel=CHANNEL,
            direction="outbound",
            message_text=reply,
            role_used=role_id,
            stage_at_time=lead.get("stage", current_stage),
        )

    except Exception as e:
        logger.error("handle_telethon_message error: %s", e, exc_info=True)


def _find_lead_by_telegram(username: str) -> dict | None:
    """Найти лид по Telegram username в Sheets."""
    try:
        rows = sheets_service._get_all_rows()
        for i, row in enumerate(rows):
            if i == 0:
                continue
            lead = sheets_service._row_to_dict(row, i + 1)
            if lead.get("telegram", "").lower().strip("@") == username.lower():
                return lead
    except Exception:
        pass
    return None


async def _get_history(chat_id: int) -> list[dict]:
    try:
        from app.services.redis_service import get_telegram_history
        return await get_telegram_history(chat_id)
    except Exception:
        return []


async def _append_history(chat_id: int, role: str, content: str) -> None:
    try:
        from app.services.redis_service import append_telegram_message
        await append_telegram_message(chat_id, role, content)
    except Exception:
        pass
