import base64
import json
import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response

from app.config import settings
from app.funnel.actions import ACTION_MAP
from app.funnel.pipeline import get_transition
from app.services import ai_agent, gmail_service, sheets_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks")

# Track last processed historyId to deduplicate
_last_history_id: int = 0


@router.post("/gmail")
async def gmail_push(request: Request):
    """Handle Gmail Pub/Sub push notifications."""
    global _last_history_id

    body = await request.json()

    # Verify token if configured
    if settings.GOOGLE_PUBSUB_VERIFICATION_TOKEN:
        token = body.get("message", {}).get("attributes", {}).get("token", "")
        if token and token != settings.GOOGLE_PUBSUB_VERIFICATION_TOKEN:
            logger.warning("Invalid verification token")
            return Response(status_code=200)  # Return 200 to avoid retries

    # Decode the Pub/Sub message
    data_b64 = body.get("message", {}).get("data", "")
    if not data_b64:
        return {"status": "no_data"}

    data = json.loads(base64.urlsafe_b64decode(data_b64))
    history_id = int(data.get("historyId", 0))

    # Deduplicate
    if history_id <= _last_history_id:
        logger.debug("Skipping duplicate historyId %d", history_id)
        return {"status": "duplicate"}

    logger.info("Processing Gmail push, historyId=%d", history_id)

    # Get new messages since last known historyId
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

    return {"status": "ok", "processed": len(messages)}


@router.post("/gmail/renew-watch")
async def renew_gmail_watch():
    """Endpoint for n8n to trigger Gmail watch renewal."""
    result = gmail_service.register_watch()
    return {"status": "ok", "watch": result}


@router.post("/follow-ups")
async def trigger_follow_ups():
    """Endpoint for n8n to trigger daily follow-up checks."""
    from app.funnel.actions import send_follow_up

    stale_leads = sheets_service.get_stale_leads(settings.FOLLOW_UP_DAYS)
    sent = 0
    for lead in stale_leads:
        try:
            await send_follow_up(lead)
            sent += 1
        except Exception as e:
            logger.error("Failed to send follow-up to %s: %s", lead["email"], e)

    return {"status": "ok", "follow_ups_sent": sent}


async def _process_message(message_id: str) -> None:
    """Process a single incoming email message."""
    message = gmail_service.get_message(message_id)
    parsed = gmail_service.parse_message(message)

    # Skip messages sent by us
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

    current_stage = lead.get("stage", "NEW_REPLY")

    # Skip if already handed off or archived
    if current_stage in ("HANDOFF_TO_MANAGER", "ORDER", "ARCHIVED"):
        logger.info("Lead %s is in stage %s, skipping auto-reply", sender_email, current_stage)
        return

    # Classify the reply
    classification = await ai_agent.classify_reply(parsed["body"])
    category = classification.get("category", "INTERESTED")

    # Get transition
    new_stage, action_name = get_transition(current_stage, category)

    logger.info(
        "Transition: %s + %s → %s (action: %s)",
        current_stage, category, new_stage, action_name,
    )

    # Update lead stage
    sheets_service.update_lead(lead["row_number"], {
        "stage": new_stage,
        "last_contact": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "notes": f"AI: {category} ({classification.get('confidence', 0):.0%})",
    })
    lead["stage"] = new_stage

    # Build thread history for context
    thread = gmail_service.get_thread(parsed["threadId"])
    thread_messages = thread.get("messages", [])
    thread_history = _build_thread_history(thread_messages)
    exchange_count = len(thread_messages)

    # Execute action
    action_fn = ACTION_MAP.get(action_name)
    if action_fn:
        await action_fn(lead, parsed, thread_history, exchange_count)
    else:
        logger.error("Unknown action: %s", action_name)


def _extract_email(from_header: str) -> str:
    """Extract email address from 'Name <email>' format."""
    match = re.search(r"<(.+?)>", from_header)
    if match:
        return match.group(1).lower()
    if "@" in from_header:
        return from_header.strip().lower()
    return ""


def _extract_name(from_header: str) -> str:
    """Extract name from 'Name <email>' format."""
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
