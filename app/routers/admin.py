"""Admin API — dashboard, config management, analytics.

Protected by ADMIN_SECRET bearer token.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])
security = HTTPBearer(auto_error=False)


def _verify_admin(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify admin bearer token."""
    if not settings.ADMIN_SECRET:
        raise HTTPException(403, "Admin secret not configured")
    if not credentials or credentials.credentials != settings.ADMIN_SECRET:
        raise HTTPException(401, "Invalid admin token")


@router.get("/stats", dependencies=[Depends(_verify_admin)])
async def get_stats():
    """Get dashboard stats: funnel metrics, recent stats, A/B results."""
    from app.services.analytics_service import (
        get_ab_test_stats,
        get_funnel_metrics,
        get_recent_stats,
    )

    funnel = await get_funnel_metrics()
    recent = await get_recent_stats(7)
    ab = await get_ab_test_stats()

    return {
        "funnel": funnel,
        "recent_days": recent,
        "ab_testing": ab,
    }


@router.get("/leads", dependencies=[Depends(_verify_admin)])
async def get_leads(stage: str = "", limit: int = 50, offset: int = 0):
    """List leads with optional stage filter."""
    from sqlalchemy import select

    from app.db.models import Lead
    from app.db.session import async_session

    async with async_session() as session:
        query = select(Lead).order_by(Lead.updated_at.desc()).offset(offset).limit(limit)
        if stage:
            query = query.where(Lead.stage == stage)
        result = await session.execute(query)
        leads = result.scalars().all()

        return [
            {
                "id": lead.id,
                "email": lead.email,
                "name": lead.name,
                "company": lead.company,
                "stage": lead.stage,
                "follow_up_count": lead.follow_up_count,
                "last_contact": lead.last_contact_at.isoformat() if lead.last_contact_at else None,
                "created_at": lead.created_at.isoformat() if lead.created_at else None,
            }
            for lead in leads
        ]


@router.get("/lead/{lead_id}/messages", dependencies=[Depends(_verify_admin)])
async def get_lead_messages(lead_id: int):
    """Get message history for a lead."""
    from sqlalchemy import select

    from app.db.models import Message
    from app.db.session import async_session

    async with async_session() as session:
        result = await session.execute(
            select(Message)
            .where(Message.lead_id == lead_id)
            .order_by(Message.created_at.asc())
        )
        messages = result.scalars().all()
        return [
            {
                "id": msg.id,
                "direction": msg.direction,
                "channel": msg.channel,
                "body": msg.body[:500],
                "stage_at_time": msg.stage_at_time,
                "classification": msg.classification,
                "ab_variant": msg.ab_variant,
                "has_attachment": msg.has_attachment,
                "attachment_summary": msg.attachment_summary,
                "created_at": msg.created_at.isoformat(),
            }
            for msg in messages
        ]


@router.get("/config", dependencies=[Depends(_verify_admin)])
async def get_current_config():
    """Get the current business config (read-only view)."""
    from app.config_loader import get_config

    config = get_config()
    return {
        "business": {
            "name": config.business.name,
            "niche": config.business.niche,
            "language": config.business.language,
        },
        "funnel_stages": [s.id for s in config.funnel.stages],
        "categories": [c.id for c in config.funnel.categories],
        "follow_ups": {
            "delay_days": config.follow_ups.delay_days,
            "max_count": config.follow_ups.max_count,
        },
        "calendar_enabled": config.calendar.enabled,
    }


@router.post("/config/reload", dependencies=[Depends(_verify_admin)])
async def reload_config():
    """Hot-reload business config from YAML (no restart needed)."""
    from app.config_loader import init_config
    from app.funnel.pipeline import load_transitions

    try:
        config = init_config(settings.BUSINESS_CONFIG_PATH)
        load_transitions()
        return {"status": "ok", "business": config.business.name}
    except Exception as e:
        raise HTTPException(400, f"Config reload failed: {e}")


@router.get("/rate-limits", dependencies=[Depends(_verify_admin)])
async def get_rate_limits():
    """Get current send counts for all accounts."""
    from app.services.redis_service import get_redis

    try:
        r = await get_redis()
        keys = []
        async for key in r.scan_iter("ratelimit:gmail:*"):
            count = await r.get(key)
            keys.append({"key": key, "count": int(count or 0)})
        return {"limits": keys, "daily_max": settings.GMAIL_DAILY_SEND_LIMIT}
    except Exception:
        return {"limits": [], "daily_max": settings.GMAIL_DAILY_SEND_LIMIT, "redis": "unavailable"}
