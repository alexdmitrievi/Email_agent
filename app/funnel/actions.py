import logging
from datetime import datetime, timezone

from app.config import settings
from app.services import ai_agent, gmail_service, sheets_service

logger = logging.getLogger(__name__)

PORTFOLIO_PATH = "assets/portfolio.pdf"


async def reply_with_interest(lead: dict, parsed_msg: dict, thread_history: str, exchange_count: int) -> None:
    """Reply to an interested client with a personalized response."""
    body = await ai_agent.generate_response(
        stage="INTERESTED",
        lead_info=lead,
        thread_history=thread_history,
        exchange_count=exchange_count,
    )
    gmail_service.send_reply(
        to=parsed_msg["from"],
        subject=parsed_msg["subject"],
        body_html=f"<p>{_text_to_html(body)}</p>",
        thread_id=parsed_msg["threadId"],
        message_id=parsed_msg["message_id"],
        references=parsed_msg["references"],
    )
    _update_lead_contact(lead)


async def send_portfolio(lead: dict, parsed_msg: dict, thread_history: str, exchange_count: int) -> None:
    """Send portfolio PDF with a personalized cover message."""
    body = await ai_agent.generate_response(
        stage="PORTFOLIO_SENT",
        lead_info=lead,
        thread_history=thread_history,
        exchange_count=exchange_count,
    )
    gmail_service.send_reply(
        to=parsed_msg["from"],
        subject=parsed_msg["subject"],
        body_html=f"<p>{_text_to_html(body)}</p>",
        thread_id=parsed_msg["threadId"],
        message_id=parsed_msg["message_id"],
        references=parsed_msg["references"],
        attachment_path=PORTFOLIO_PATH,
    )
    _update_lead_contact(lead)


async def continue_discussion(lead: dict, parsed_msg: dict, thread_history: str, exchange_count: int) -> None:
    """Continue the discussion, potentially suggest Telegram."""
    body = await ai_agent.generate_response(
        stage="IN_DISCUSSION",
        lead_info=lead,
        thread_history=thread_history,
        exchange_count=exchange_count,
    )
    gmail_service.send_reply(
        to=parsed_msg["from"],
        subject=parsed_msg["subject"],
        body_html=f"<p>{_text_to_html(body)}</p>",
        thread_id=parsed_msg["threadId"],
        message_id=parsed_msg["message_id"],
        references=parsed_msg["references"],
    )
    _update_lead_contact(lead)


async def handoff_to_manager(lead: dict, parsed_msg: dict, thread_history: str, exchange_count: int) -> None:
    """Notify the manager and send a confirmation to the client."""
    # Notify manager via Telegram
    from app.services import telegram_service

    await telegram_service.notify_manager_handoff(lead, parsed_msg["body"])

    # Reply to client
    body = await ai_agent.generate_response(
        stage="HANDOFF_TO_MANAGER",
        lead_info=lead,
        thread_history=thread_history,
        exchange_count=exchange_count,
    )
    gmail_service.send_reply(
        to=parsed_msg["from"],
        subject=parsed_msg["subject"],
        body_html=f"<p>{_text_to_html(body)}</p>",
        thread_id=parsed_msg["threadId"],
        message_id=parsed_msg["message_id"],
        references=parsed_msg["references"],
    )
    _update_lead_contact(lead)


async def reply_not_interested(lead: dict, parsed_msg: dict, thread_history: str, exchange_count: int) -> None:
    """Send a polite goodbye and archive the lead."""
    body = (
        "Спасибо за ваш ответ! Если в будущем у вас возникнет потребность в мебели, "
        "мы всегда будем рады помочь. Хорошего дня!"
    )
    gmail_service.send_reply(
        to=parsed_msg["from"],
        subject=parsed_msg["subject"],
        body_html=f"<p>{body}</p>",
        thread_id=parsed_msg["threadId"],
        message_id=parsed_msg["message_id"],
        references=parsed_msg["references"],
    )
    _update_lead_contact(lead)


async def ignore(lead: dict, parsed_msg: dict, thread_history: str, exchange_count: int) -> None:
    """Do nothing for spam/out-of-office."""
    logger.info("Ignoring message from %s (spam/ooo)", parsed_msg["from"])


async def send_follow_up(lead: dict) -> None:
    """Send a follow-up email to a stale lead."""
    if not lead.get("thread_id"):
        logger.warning("No thread_id for lead %s, skipping follow-up", lead["email"])
        return

    thread = gmail_service.get_thread(lead["thread_id"])
    messages = thread.get("messages", [])
    if not messages:
        return

    last_msg = gmail_service.parse_message(messages[-1])
    thread_history = _build_thread_history(messages)
    exchange_count = len(messages)

    body = await ai_agent.generate_response(
        stage=lead["stage"],
        lead_info=lead,
        thread_history=thread_history,
        exchange_count=exchange_count,
    )

    gmail_service.send_reply(
        to=lead["email"],
        subject=last_msg["subject"],
        body_html=f"<p>{_text_to_html(body)}</p>",
        thread_id=lead["thread_id"],
        message_id=last_msg["message_id"],
        references=last_msg["references"],
    )

    follow_up_count = int(lead.get("follow_up_count") or "0") + 1
    sheets_service.update_lead(lead["row_number"], {
        "last_contact": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "follow_up_count": str(follow_up_count),
    })
    logger.info("Sent follow-up #%d to %s", follow_up_count, lead["email"])


def _update_lead_contact(lead: dict) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    sheets_service.update_lead(lead["row_number"], {"last_contact": now})


def _text_to_html(text: str) -> str:
    return text.replace("\n", "<br>")


def _build_thread_history(messages: list[dict]) -> str:
    parts = []
    for msg in messages:
        parsed = gmail_service.parse_message(msg)
        parts.append(f"От: {parsed['from']}\nДата: {parsed['date']}\n\n{parsed['body']}")
    return "\n\n---\n\n".join(parts)


# Action registry
ACTION_MAP = {
    "reply_with_interest": reply_with_interest,
    "send_portfolio": send_portfolio,
    "continue_discussion": continue_discussion,
    "handoff_to_manager": handoff_to_manager,
    "reply_not_interested": reply_not_interested,
    "ignore": ignore,
}
