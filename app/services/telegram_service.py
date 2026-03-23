import logging

from telegram import Bot

from app.config import settings

logger = logging.getLogger(__name__)

bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)


async def send_message(chat_id: str | int, text: str) -> None:
    """Send a text message to a Telegram user."""
    await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
    logger.info("Sent Telegram message to %s", chat_id)


async def notify_manager_handoff(lead: dict, last_message: str) -> None:
    """Notify the manager that a lead is ready for handoff."""
    text = (
        f"<b>Новый лид готов к передаче!</b>\n\n"
        f"Email: {lead.get('email', 'N/A')}\n"
        f"Имя: {lead.get('name', 'N/A')}\n"
        f"Компания: {lead.get('company', 'N/A')}\n"
        f"Стадия: {lead.get('stage', 'N/A')}\n"
    )
    if lead.get("telegram"):
        text += f"Telegram: @{lead['telegram']}\n"
    text += f"\n<b>Последнее сообщение клиента:</b>\n<i>{_truncate(last_message, 500)}</i>"

    await send_message(settings.TELEGRAM_MANAGER_CHAT_ID, text)
    logger.info("Manager notified about handoff for %s", lead.get("email"))


async def notify_manager_daily_summary(summary: str) -> None:
    """Send daily summary to the manager."""
    await send_message(settings.TELEGRAM_MANAGER_CHAT_ID, summary)


async def set_webhook(url: str) -> None:
    """Set the Telegram bot webhook URL with optional secret token."""
    kwargs = {"url": url}
    if settings.TELEGRAM_WEBHOOK_SECRET:
        kwargs["secret_token"] = settings.TELEGRAM_WEBHOOK_SECRET
    result = await bot.set_webhook(**kwargs)
    logger.info("Telegram webhook set: %s (result: %s)", url, result)


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."
