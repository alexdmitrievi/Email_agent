"""
Supabase CRM service — real-time journey tracking & lead scoring.

Пишет события в три таблицы:
  - leads           (основная CRM — upsert)
  - journey_events  (каждый переход стадии, отправка, получение)
  - conversations   (полный лог каждого сообщения)

SQL для создания таблиц — см. README или суть в том что всё хранится в Supabase
и менеджер видит путь каждого лида в реальном времени через Supabase Dashboard.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_client = None


def init(url: str, key: str) -> None:
    """Инициализировать Supabase клиент. Вызывается при старте приложения."""
    global _client
    try:
        from supabase import create_client
        _client = create_client(url, key)
        logger.info("Supabase client initialized: %s", url[:40] + "...")
    except ImportError:
        logger.warning("supabase package not installed — Supabase disabled")
    except Exception as e:
        logger.error("Failed to init Supabase: %s", e)


def _get_client():
    """Вернуть клиент или None если недоступен."""
    return _client


# ---------------------------------------------------------------------------
# Leads
# ---------------------------------------------------------------------------

async def upsert_lead(lead_data: dict) -> dict | None:
    """
    Создать или обновить лид в Supabase.

    lead_data может содержать: email, name, company, phone, telegram_username,
    whatsapp_number, stage, source_channel, traffic_source, assigned_role,
    lead_score, niche, follow_up_count.
    """
    client = _get_client()
    if not client:
        return None

    try:
        payload = {
            **lead_data,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if "created_at" not in payload:
            payload["created_at"] = payload["updated_at"]

        result = await asyncio.to_thread(
            lambda: client.table("leads")
            .upsert(payload, on_conflict="email")
            .execute()
        )
        if result.data:
            return result.data[0]
        return None
    except Exception as e:
        logger.error("Supabase upsert_lead error: %s", e)
        return None


async def get_lead(email: str) -> dict | None:
    """Получить лид по email."""
    client = _get_client()
    if not client:
        return None
    try:
        result = await asyncio.to_thread(
            lambda: client.table("leads").select("*").eq("email", email).limit(1).execute()
        )
        if result.data:
            return result.data[0]
        return None
    except Exception as e:
        logger.error("Supabase get_lead error: %s", e)
        return None


# ---------------------------------------------------------------------------
# Journey Events
# ---------------------------------------------------------------------------

async def log_journey_event(
    lead_email: str,
    event_type: str,
    channel: str,
    from_stage: str = "",
    to_stage: str = "",
    role_used: str = "",
    message_preview: str = "",
    classification: str = "",
    confidence: float = 0.0,
    metadata: dict | None = None,
) -> None:
    """
    Записать событие в путь лида (journey).

    event_type: stage_change | message_sent | message_received | handoff |
                follow_up | whatsapp_received | telethon_sent | ...
    """
    client = _get_client()
    if not client:
        return

    try:
        payload = {
            "lead_email": lead_email,
            "event_type": event_type,
            "channel": channel,
            "from_stage": from_stage,
            "to_stage": to_stage,
            "role_used": role_used,
            "message_preview": (message_preview or "")[:200],
            "classification": classification,
            "confidence": confidence,
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await asyncio.to_thread(
            lambda: client.table("journey_events").insert(payload).execute()
        )
    except Exception as e:
        logger.error("Supabase log_journey_event error: %s", e)


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

async def log_conversation(
    lead_email: str,
    channel: str,
    direction: str,
    message_text: str,
    classification: str = "",
    confidence: float = 0.0,
    role_used: str = "",
    stage_at_time: str = "",
) -> None:
    """
    Записать сообщение в лог разговора.

    direction: inbound | outbound
    channel:   email | telegram | telegram_mtproto | whatsapp | avito
    """
    client = _get_client()
    if not client:
        return

    try:
        payload = {
            "lead_email": lead_email,
            "channel": channel,
            "direction": direction,
            "message_text": (message_text or "")[:5000],
            "classification": classification,
            "confidence": confidence,
            "role_used": role_used,
            "stage_at_time": stage_at_time,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await asyncio.to_thread(
            lambda: client.table("conversations").insert(payload).execute()
        )
    except Exception as e:
        logger.error("Supabase log_conversation error: %s", e)


# ---------------------------------------------------------------------------
# Lead scoring
# ---------------------------------------------------------------------------

def calculate_lead_score(stage: str, channel: str, message_count: int, last_classification: str) -> int:
    """
    Рассчитать score лида (0-100).

    Используется для приоритизации горячих лидов менеджером.
    """
    score = 0

    # Канал (до 10 pts) — WhatsApp самый тёплый, значит сам написал
    channel_scores = {
        "whatsapp": 10,
        "telegram_mtproto": 8,
        "telegram": 7,
        "avito": 6,
        "email": 5,
    }
    score += channel_scores.get(channel, 5)

    # Стадия воронки (до 30 pts)
    stage_scores = {
        "IN_DISCUSSION": 30,
        "KP_SENT": 20,
        "MATERIALS_SENT": 20,
        "CASE_STUDY_SENT": 18,
        "DEMO_SCHEDULED": 25,
        "ESTIMATE_SCHEDULED": 22,
        "INTERESTED": 10,
        "NEW_REPLY": 5,
    }
    score += stage_scores.get(stage, 0)

    # Активность — количество сообщений (до 20 pts)
    score += min(message_count * 4, 20)

    # Последняя классификация (до 40 pts)
    class_scores = {
        "READY_TO_ORDER": 40,
        "INTERESTED": 25,
        "QUESTION": 15,
        "NOT_INTERESTED": -20,
    }
    score += class_scores.get(last_classification, 0)

    return max(0, min(score, 100))


async def update_lead_score(lead_email: str, score: int) -> None:
    """Обновить lead_score в Supabase."""
    client = _get_client()
    if not client:
        return
    try:
        await asyncio.to_thread(
            lambda: client.table("leads")
            .update({"lead_score": score, "updated_at": datetime.now(timezone.utc).isoformat()})
            .eq("email", lead_email)
            .execute()
        )
    except Exception as e:
        logger.error("Supabase update_lead_score error: %s", e)


# ---------------------------------------------------------------------------
# Dashboard helpers
# ---------------------------------------------------------------------------

async def get_funnel_stats() -> dict[str, Any]:
    """Получить распределение лидов по стадиям для дашборда."""
    client = _get_client()
    if not client:
        return {}
    try:
        result = await asyncio.to_thread(
            lambda: client.table("leads").select("stage, source_channel, assigned_role").execute()
        )
        rows = result.data or []
        by_stage: dict[str, int] = {}
        by_channel: dict[str, int] = {}
        by_role: dict[str, int] = {}
        for row in rows:
            stage = row.get("stage", "UNKNOWN")
            channel = row.get("source_channel", "unknown")
            role = row.get("assigned_role", "unknown")
            by_stage[stage] = by_stage.get(stage, 0) + 1
            by_channel[channel] = by_channel.get(channel, 0) + 1
            by_role[role] = by_role.get(role, 0) + 1
        return {"by_stage": by_stage, "by_channel": by_channel, "by_role": by_role, "total": len(rows)}
    except Exception as e:
        logger.error("Supabase get_funnel_stats error: %s", e)
        return {}


async def get_lead_journey(lead_email: str) -> list[dict]:
    """Получить полный путь лида (хронологически)."""
    client = _get_client()
    if not client:
        return []
    try:
        result = await asyncio.to_thread(
            lambda: client.table("journey_events")
            .select("*")
            .eq("lead_email", lead_email)
            .order("created_at")
            .execute()
        )
        return result.data or []
    except Exception as e:
        logger.error("Supabase get_lead_journey error: %s", e)
        return []
