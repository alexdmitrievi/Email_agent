import logging

from fastapi import APIRouter, Request
from telegram import Bot, Update

from app.config import settings
from app.services import ai_agent, sheets_service, telegram_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks")

# In-memory conversation history per chat_id (limited)
_conversations: dict[int, list[dict]] = {}
MAX_HISTORY = 20


@router.post("/telegram")
async def telegram_webhook(request: Request):
    """Handle incoming Telegram messages."""
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

    # Try to find lead by Telegram username
    lead = _find_lead_by_telegram(username) if username else None

    # Build conversation history
    if chat_id not in _conversations:
        _conversations[chat_id] = []

    _conversations[chat_id].append({"role": "user", "content": text})

    # Trim history
    if len(_conversations[chat_id]) > MAX_HISTORY:
        _conversations[chat_id] = _conversations[chat_id][-MAX_HISTORY:]

    # Check if client wants to order / meet manager
    if _should_handoff(text):
        if lead:
            sheets_service.update_lead(lead["row_number"], {"stage": "HANDOFF_TO_MANAGER"})
            await telegram_service.notify_manager_handoff(
                lead or {"email": "N/A", "name": first_name, "telegram": username},
                text,
            )
        reply = (
            "Отлично! Я передам ваш запрос нашему менеджеру, и он свяжется с вами "
            "в ближайшее время. Спасибо за интерес к нашей продукции!"
        )
    else:
        # Generate AI response
        lead_info = lead or {"name": first_name, "telegram": username}
        reply = await ai_agent.generate_telegram_response(
            lead_info=lead_info,
            conversation_history=_conversations[chat_id],
        )

    # Save assistant reply to history
    _conversations[chat_id].append({"role": "assistant", "content": reply})

    await telegram_service.send_message(chat_id, reply)
    return {"status": "ok"}


async def _handle_start(chat_id: int, username: str, first_name: str) -> None:
    """Handle the /start command."""
    # Try to link Telegram to existing lead
    if username:
        lead = _find_lead_by_telegram(username)
        if lead:
            logger.info("Telegram user @%s linked to lead %s", username, lead["email"])

    welcome = (
        f"Здравствуйте, {first_name}! Я — виртуальный помощник компании "
        f"«{settings.COMPANY_NAME}».\n\n"
        "Могу рассказать о нашей мебели, показать примеры работ "
        "или помочь связаться с менеджером.\n\n"
        "Чем могу быть полезен?"
    )
    await telegram_service.send_message(chat_id, welcome)


def _find_lead_by_telegram(username: str) -> dict | None:
    """Search for a lead by Telegram username in Google Sheets."""
    rows = sheets_service._get_all_rows()
    for i, row in enumerate(rows):
        if i == 0:
            continue
        lead = sheets_service._row_to_dict(row, i + 1)
        if lead.get("telegram", "").lower().strip("@") == username.lower():
            return lead
    return None


def _should_handoff(text: str) -> bool:
    """Simple keyword check to detect if client wants manager/order."""
    keywords = [
        "заказ", "заказать", "купить", "оформить",
        "менеджер", "встреча", "встретиться", "позвонить",
        "звонок", "договориться", "оплата", "оплатить",
    ]
    text_lower = text.lower()
    return any(kw in text_lower for kw in keywords)
