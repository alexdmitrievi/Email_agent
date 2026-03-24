"""Avito messenger polling — process inbound messages from workers."""

import logging

from fastapi import APIRouter, Depends

from app.config import settings
from app.funnel.avito_actions import AVITO_ACTION_MAP
from app.funnel.avito_pipeline import get_avito_config, get_avito_transition, is_terminal
from app.services import ai_agent, avito_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/avito", tags=["avito"])

# In-memory cooldown fallback (Redis preferred)
_cooldowns: dict[str, float] = {}
COOLDOWN_SECONDS = 300  # 5 min per chat


def _check_cooldown(chat_id: str) -> bool:
    """Return True if we can reply (cooldown expired)."""
    import time
    last = _cooldowns.get(chat_id, 0)
    return time.time() - last > COOLDOWN_SECONDS


def _set_cooldown(chat_id: str) -> None:
    import time
    _cooldowns[chat_id] = time.time()


async def _get_lead_state(chat_id: str) -> dict | None:
    """Get lead state from Redis."""
    try:
        from app.services.redis_service import get_avito_lead_state
        return await get_avito_lead_state(chat_id)
    except Exception:
        return None


async def _save_lead_state(chat_id: str, state: dict) -> None:
    """Save lead state to Redis."""
    try:
        from app.services.redis_service import set_avito_lead_state
        await set_avito_lead_state(chat_id, state)
    except Exception:
        pass


@router.post("/poll")
async def poll_avito():
    """Poll Avito for new messages and process them. Called by ARQ or manually."""
    if not settings.AVITO_ENABLED:
        return {"status": "disabled"}

    processed = 0
    try:
        chats = await avito_service.get_chats(unread_only=True)
    except Exception as e:
        logger.error("Failed to fetch Avito chats: %s", e)
        return {"status": "error", "detail": str(e)}

    for chat in chats:
        chat_id = str(chat.get("id", ""))
        if not chat_id:
            continue

        # Cooldown check
        if not _check_cooldown(chat_id):
            continue

        try:
            count = await _process_chat(chat_id)
            if count > 0:
                processed += count
                _set_cooldown(chat_id)
        except Exception as e:
            logger.error("Error processing Avito chat %s: %s", chat_id, e)

    logger.info("Avito poll: processed %d chats", processed)
    return {"status": "ok", "processed": processed}


async def _process_chat(chat_id: str) -> int:
    """Process a single Avito chat. Returns 1 if replied, 0 if skipped."""
    user_id = settings.AVITO_USER_ID

    # Get messages
    messages = await avito_service.get_messages(chat_id, limit=10)
    if not messages:
        return 0

    # Find latest message from the worker (not from us)
    worker_messages = [
        m for m in messages
        if str(m.get("author_id", "")) != user_id
    ]
    if not worker_messages:
        return 0  # Only our messages — don't reply

    latest = worker_messages[0]  # API returns newest first
    worker_text = latest.get("content", {}).get("text", "").strip()
    if not worker_text:
        return 0

    # Get or create lead state
    state = await _get_lead_state(chat_id)
    if state is None:
        state = {
            "chat_id": chat_id,
            "stage": "NEW_MESSAGE",
            "name": latest.get("author", {}).get("name", ""),
            "exchange_count": 0,
        }

    # Skip terminal stages
    if is_terminal(state["stage"]):
        return 0

    # Build thread history
    history_lines = []
    for m in reversed(messages[-10:]):
        role = "Исполнитель" if str(m.get("author_id", "")) != user_id else "Мы"
        text = m.get("content", {}).get("text", "")
        if text:
            history_lines.append(f"{role}: {text}")
    history = "\n".join(history_lines)

    # Classify
    config = get_avito_config()
    classification = await ai_agent.classify_reply(worker_text, config_override=config)
    category = classification.get("category", "INTERESTED")

    # Transition
    new_stage, action_name = get_avito_transition(state["stage"], category)
    logger.info(
        "Avito chat %s: %s + %s → %s (%s)",
        chat_id, state["stage"], category, new_stage, action_name,
    )

    # Execute action
    action_fn = AVITO_ACTION_MAP.get(action_name)
    if action_fn:
        lead_info = {
            "chat_id": chat_id,
            "name": state.get("name", ""),
            "stage": state["stage"],
        }
        await action_fn(lead_info, worker_text, history, state.get("exchange_count", 0))

    # Update state
    state["stage"] = new_stage
    state["exchange_count"] = state.get("exchange_count", 0) + 1
    await _save_lead_state(chat_id, state)

    # Mark as read
    await avito_service.mark_chat_read(chat_id)

    return 1
