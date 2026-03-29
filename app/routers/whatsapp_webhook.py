"""
WhatsApp webhook router — обрабатывает входящие сообщения от Green API.

Endpoint: POST /webhooks/whatsapp

Настройка в Green API Dashboard:
  1. Settings → Notifications
  2. Webhook URL: https://yourdomain.com/webhooks/whatsapp
  3. Включить: incomingMessageReceived
"""

import logging

from fastapi import APIRouter, Request, Response

from app.config import settings
from app.config_loader import get_config
from app.funnel.pipeline import get_transition
from app.funnel.stages import is_terminal
from app.services import ai_agent, whatsapp_service
from app.services.role_manager import role_manager
from app.services.traffic_router import traffic_router
from app.services import supabase_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks")

# In-memory история разговоров по WhatsApp (chat_id → list[dict])
# В production следует хранить в Redis
_conversations: dict[str, list[dict]] = {}


@router.post("/whatsapp")
async def whatsapp_webhook(request: Request):
    """
    Обработчик входящих сообщений WhatsApp через Green API webhook.

    Всегда возвращает 200 немедленно — Green API ждёт быстрый ответ.
    """
    # Сразу возвращаем 200 — обработку делаем асинхронно через background task
    try:
        data = await request.json()
    except Exception:
        return Response(status_code=200)

    # Опциональная валидация токена
    if settings.GREENAPI_WEBHOOK_TOKEN:
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if token != settings.GREENAPI_WEBHOOK_TOKEN:
            logger.warning("WhatsApp webhook: invalid token")
            return Response(status_code=200)

    type_webhook = data.get("typeWebhook")
    logger.debug("WhatsApp webhook: typeWebhook=%s", type_webhook)

    # Обрабатываем только входящие сообщения
    if type_webhook == "incomingMessageReceived":
        parsed = whatsapp_service.parse_webhook(data)
        if parsed:
            try:
                await _process_whatsapp_message(parsed)
            except Exception as e:
                logger.error("WhatsApp message processing error: %s", e, exc_info=True)

    return Response(status_code=200)


async def _process_whatsapp_message(msg: dict) -> None:
    """Обработать входящее WhatsApp сообщение через воронку."""
    chat_id = msg["chat_id"]
    sender_phone = msg["sender_phone"]
    sender_name = msg["sender_name"]
    text = msg["text"]

    logger.info("WhatsApp message from %s (%s): %s", sender_name, sender_phone, text[:100])

    # Найти или создать лид через Sheets
    from app.services import sheets_service
    lead = sheets_service.find_lead_by_email(f"whatsapp_{sender_phone}@wa.local")
    if not lead:
        lead = sheets_service.create_lead(
            email=f"whatsapp_{sender_phone}@wa.local",
            name=sender_name or sender_phone,
            thread_id=f"wa_{chat_id}",
        )
        # Обновляем поля специфичные для WhatsApp
        sheets_service.update_lead(lead["row_number"], {
            "notes": f"WhatsApp: +{sender_phone}",
        })

    current_stage = lead.get("stage", "NEW_REPLY")

    if is_terminal(current_stage):
        logger.info("WhatsApp lead %s in terminal stage %s", sender_phone, current_stage)
        return

    # Определить роль и источник трафика
    traffic_source = traffic_router.detect_source("whatsapp", {"phone": sender_phone})
    role_id = role_manager.assign_role_for_source("whatsapp", lead)
    role_config = role_manager.get_role(role_id)

    # Добавить сообщение в историю
    _append_history(chat_id, "user", text)
    history = _get_history(chat_id)

    # Записать в Supabase
    await supabase_service.log_conversation(
        lead_email=lead.get("email", ""),
        channel="whatsapp",
        direction="inbound",
        message_text=text,
        role_used=role_id,
        stage_at_time=current_stage,
    )

    # Классификация
    classification = await ai_agent.classify_reply(text)
    category = classification.get("category", "INTERESTED")
    confidence = classification.get("confidence", 0.0)

    # Проверить хэндофф через конфиг роли или бизнес-конфиг
    config = get_config()
    should_handoff = (
        role_manager.is_handoff_trigger(role_id, text)
        or any(kw in text.lower() for kw in config.handoff.telegram_keywords)
        or category == "READY_TO_ORDER"
    )

    if should_handoff:
        new_stage = "HANDOFF_TO_MANAGER"
        sheets_service.update_lead(lead["row_number"], {"stage": new_stage})
        # Уведомить менеджера
        from app.services import telegram_service
        await telegram_service.notify_manager_handoff(
            lead={"email": lead.get("email", ""), "name": sender_name, "telegram": ""},
            message=f"📱 WhatsApp: +{sender_phone}\n\n{text}",
        )
        reply = config.telegram.handoff_confirmation.strip()
    else:
        # Переход воронки
        new_stage, action_name = get_transition(current_stage, category)
        sheets_service.update_lead(lead["row_number"], {"stage": new_stage})
        lead["stage"] = new_stage

        # Генерировать ответ с ролью
        reply = await ai_agent.generate_response(
            stage=new_stage,
            lead_info={"name": sender_name, "phone": sender_phone},
            thread_history=_format_history(history[:-1]),  # без последнего
            exchange_count=len(history),
            role=role_id,
            channel="whatsapp",
            traffic_source=str(traffic_source),
        )

    # Отправить ответ
    sent = await whatsapp_service.send_message(chat_id, reply)
    if sent:
        _append_history(chat_id, "assistant", reply)

    # Записать ответ в Supabase
    await supabase_service.log_conversation(
        lead_email=lead.get("email", ""),
        channel="whatsapp",
        direction="outbound",
        message_text=reply,
        classification=category,
        confidence=confidence,
        role_used=role_id,
        stage_at_time=new_stage if not should_handoff else "HANDOFF_TO_MANAGER",
    )

    # Journey event
    await supabase_service.log_journey_event(
        lead_email=lead.get("email", ""),
        event_type="stage_change" if new_stage != current_stage else "message_sent",
        channel="whatsapp",
        from_stage=current_stage,
        to_stage=new_stage if not should_handoff else "HANDOFF_TO_MANAGER",
        role_used=role_id,
        message_preview=text[:200],
        classification=category,
        confidence=confidence,
    )

    # Обновить lead score
    score = supabase_service.calculate_lead_score(
        stage=new_stage,
        channel="whatsapp",
        message_count=len(history),
        last_classification=category,
    )
    await supabase_service.upsert_lead({
        "email": lead.get("email", ""),
        "name": sender_name,
        "whatsapp_number": sender_phone,
        "stage": new_stage,
        "source_channel": "whatsapp",
        "traffic_source": str(traffic_source),
        "assigned_role": role_id,
        "lead_score": score,
    })


# ---------------------------------------------------------------------------
# История разговора (in-memory, в production → Redis)
# ---------------------------------------------------------------------------

def _get_history(chat_id: str) -> list[dict]:
    return _conversations.get(chat_id, [])


def _append_history(chat_id: str, role: str, content: str) -> None:
    if chat_id not in _conversations:
        _conversations[chat_id] = []
    _conversations[chat_id].append({"role": role, "content": content})
    # Хранить только последние 20 сообщений
    if len(_conversations[chat_id]) > 20:
        _conversations[chat_id] = _conversations[chat_id][-20:]


def _format_history(history: list[dict]) -> str:
    parts = []
    for msg in history:
        role_label = "Клиент" if msg["role"] == "user" else "Агент"
        parts.append(f"{role_label}: {msg['content']}")
    return "\n\n".join(parts)
