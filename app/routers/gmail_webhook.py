"""Gmail Pub/Sub webhook — full pipeline with rate limiting, delayed sending, A/B, logging."""

import base64
import json
import logging
import random
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response

from app.config import settings
from app.config_loader import get_config
from app.funnel.actions import ACTION_MAP
from app.funnel.pipeline import get_transition
from app.funnel.stages import is_terminal
from app.services import ai_agent, gmail_service, sheets_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks")

_last_history_id: int = 0


@router.post("/gmail")
async def gmail_push(request: Request):
    """Handle Gmail Pub/Sub push notifications."""
    global _last_history_id

    body = await request.json()

    if settings.GOOGLE_PUBSUB_VERIFICATION_TOKEN:
        token = body.get("message", {}).get("attributes", {}).get("token", "")
        if token and token != settings.GOOGLE_PUBSUB_VERIFICATION_TOKEN:
            logger.warning("Invalid verification token")
            return Response(status_code=200)

    data_b64 = body.get("message", {}).get("data", "")
    if not data_b64:
        return {"status": "no_data"}

    data = json.loads(base64.urlsafe_b64decode(data_b64))
    history_id = int(data.get("historyId", 0))

    if history_id <= _last_history_id:
        return {"status": "duplicate"}

    logger.info("Processing Gmail push, historyId=%d", history_id)

    if _last_history_id > 0:
        messages = gmail_service.get_history(str(_last_history_id))
    else:
        messages = gmail_service.get_history(str(history_id - 1))

    _last_history_id = history_id

    for msg_stub in messages:
        try:
            await _process_message(msg_stub["id"])
        except Exception as e:
            logger.error("Error processing message %s: %s", msg_stub.get("id"), e, exc_info=True)
            # Enqueue for retry via ARQ if available
            await _enqueue_retry(msg_stub["id"])

    return {"status": "ok", "processed": len(messages)}


@router.post("/gmail/renew-watch")
async def renew_gmail_watch():
    result = gmail_service.register_watch()
    return {"status": "ok", "watch": result}


@router.post("/follow-ups")
async def trigger_follow_ups():
    from app.funnel.actions import send_follow_up

    config = get_config()
    stale_leads = sheets_service.get_stale_leads(config.follow_ups.delay_days)
    sent = 0
    for lead in stale_leads:
        try:
            await send_follow_up(lead)
            sent += 1
        except Exception as e:
            logger.error("Failed to send follow-up to %s: %s", lead["email"], e)

    return {"status": "ok", "follow_ups_sent": sent}


@router.post("/daily-summary")
async def daily_summary():
    """Endpoint for n8n to trigger daily summary."""
    from app.services.analytics_service import generate_summary_text
    from app.services import telegram_service

    text = await generate_summary_text()
    await telegram_service.notify_manager_daily_summary(text)
    return {"status": "ok"}


async def _process_message(message_id: str) -> None:
    """Process a single incoming email — classify, transition, act."""
    message = gmail_service.get_message(message_id)
    parsed = gmail_service.parse_message(message)

    our_email = settings.GOOGLE_DELEGATED_EMAIL.lower()
    if our_email in parsed["from"].lower():
        return

    sender_email = _extract_email(parsed["from"])
    if not sender_email:
        return

    logger.info("Processing email from %s, thread=%s", sender_email, parsed["threadId"])

    # Find or create lead
    lead = sheets_service.find_lead_by_thread_id(parsed["threadId"])
    if not lead:
        lead = sheets_service.find_lead_by_email(sender_email)
    if not lead:
        lead = sheets_service.create_lead(
            email=sender_email,
            name=_extract_name(parsed["from"]),
            thread_id=parsed["threadId"],
        )
        # Enqueue lead enrichment (non-blocking)
        await _enqueue_enrichment(lead)

    current_stage = lead.get("stage", "NEW_REPLY")

    if is_terminal(current_stage):
        logger.info("Lead %s in terminal stage %s, skipping", sender_email, current_stage)
        return

    # Log inbound message to DB (non-fatal)
    await _log_message(lead, parsed, "inbound")

    # Classify
    classification = await ai_agent.classify_reply(parsed["body"])
    category = classification.get("category", "INTERESTED")

    # Record A/B test reply (feedback loop)
    await _record_ab_reply(lead, category)

    # Transition
    new_stage, action_name = get_transition(current_stage, category)
    logger.info("Transition: %s + %s -> %s (%s)", current_stage, category, new_stage, action_name)

    # Update lead
    sheets_service.update_lead(lead["row_number"], {
        "stage": new_stage,
        "last_contact": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "notes": f"AI: {category} ({classification.get('confidence', 0):.0%})",
    })
    lead["stage"] = new_stage

    # Thread history
    thread = gmail_service.get_thread(parsed["threadId"])
    thread_messages = thread.get("messages", [])
    thread_history = _build_thread_history(thread_messages)
    exchange_count = len(thread_messages)

    # Check rate limit before sending
    if not await _check_rate_limit():
        logger.warning("Rate limit reached, skipping reply to %s", sender_email)
        return

    # Execute action
    action_fn = ACTION_MAP.get(action_name)
    if action_fn:
        await action_fn(lead, parsed, thread_history, exchange_count)
    else:
        logger.error("Unknown action: %s", action_name)


# ---- Helpers ----

def _extract_email(from_header: str) -> str:
    match = re.search(r"<(.+?)>", from_header)
    if match:
        return match.group(1).lower()
    if "@" in from_header:
        return from_header.strip().lower()
    return ""


def _extract_name(from_header: str) -> str:
    match = re.match(r"(.+?)\s*<", from_header)
    if match:
        return match.group(1).strip().strip('"')
    return ""


def _build_thread_history(messages: list[dict]) -> str:
    parts = []
    for msg in messages:
        parsed = gmail_service.parse_message(msg)
        parts.append(f"От: {parsed['from']}\nДата: {parsed['date']}\n\n{parsed['body']}")
    return "\n\n---\n\n".join(parts)


async def _check_rate_limit() -> bool:
    """Check Gmail daily rate limit (non-fatal on Redis failure)."""
    try:
        from app.services.redis_service import check_rate_limit
        return await check_rate_limit(settings.GOOGLE_DELEGATED_EMAIL, settings.GMAIL_DAILY_SEND_LIMIT)
    except Exception:
        return True  # if Redis is down, allow sending


async def _enqueue_retry(message_id: str) -> None:
    """Enqueue failed message for retry via ARQ (non-fatal)."""
    try:
        from arq import create_pool
        from arq.connections import RedisSettings
        pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
        await pool.enqueue_job("process_email", message_id)
        await pool.close()
    except Exception:
        pass


async def _enqueue_enrichment(lead: dict) -> None:
    """Enqueue lead enrichment (non-fatal)."""
    if not settings.ENRICHMENT_ENABLED:
        return
    try:
        from arq import create_pool
        from arq.connections import RedisSettings
        pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
        await pool.enqueue_job("enrich_lead", lead.get("row_number", 0))
        await pool.close()
    except Exception:
        pass


async def _log_message(lead: dict, parsed: dict, direction: str) -> None:
    """Log message to DB for analytics (non-fatal)."""
    try:
        from app.db.models import Message
        from app.db.session import async_session

        async with async_session() as session:
            msg = Message(
                lead_id=lead.get("row_number", 0),
                direction=direction,
                channel="email",
                gmail_message_id=parsed.get("id", ""),
                subject=parsed.get("subject", ""),
                body=parsed.get("body", "")[:2000],
                stage_at_time=lead.get("stage", ""),
            )
            session.add(msg)
            await session.commit()
    except Exception:
        pass


async def _record_ab_reply(lead: dict, category: str) -> None:
    """Record that a lead replied (feedback loop for A/B testing)."""
    try:
        from app.services.ab_testing_service import record_ab_reply
        await record_ab_reply(lead.get("row_number", 0), category)
    except Exception:
        pass
