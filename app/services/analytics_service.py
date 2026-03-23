"""Analytics service — daily stats, funnel metrics, summary generation."""

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.config_loader import get_config
from app.db.models import ABTestResult, DailyStats, Lead, Message
from app.db.session import async_session

logger = logging.getLogger(__name__)


async def compute_stats() -> None:
    """Compute daily aggregated stats and store in DailyStats table."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    async with async_session() as session:
        # Check if already computed
        existing = await session.execute(
            select(DailyStats).where(DailyStats.date == today)
        )
        stats = existing.scalar_one_or_none()
        if not stats:
            stats = DailyStats(date=today)
            session.add(stats)

        # Count messages today
        inbound = await session.execute(
            select(func.count(Message.id)).where(
                Message.direction == "inbound",
                func.date(Message.created_at) == today,
            )
        )
        stats.emails_received = inbound.scalar() or 0

        outbound = await session.execute(
            select(func.count(Message.id)).where(
                Message.direction == "outbound",
                func.date(Message.created_at) == today,
            )
        )
        stats.emails_sent = outbound.scalar() or 0

        # Count leads by stage
        new = await session.execute(
            select(func.count(Lead.id)).where(
                func.date(Lead.created_at) == today
            )
        )
        stats.new_leads = new.scalar() or 0

        for stage, attr in [
            ("INTERESTED", "leads_interested"),
            ("MATERIALS_SENT", "leads_materials_sent"),
            ("HANDOFF_TO_MANAGER", "leads_handoff"),
            ("NOT_INTERESTED", "leads_not_interested"),
        ]:
            count = await session.execute(
                select(func.count(Lead.id)).where(Lead.stage == stage)
            )
            setattr(stats, attr, count.scalar() or 0)

        # A/B test results
        ab_total = await session.execute(
            select(func.count(ABTestResult.id)).where(
                func.date(ABTestResult.created_at) == today
            )
        )
        stats.ab_tests_run = ab_total.scalar() or 0

        await session.commit()
        logger.info("Stats computed for %s", today)


async def get_funnel_metrics() -> dict:
    """Get current funnel stage distribution."""
    async with async_session() as session:
        result = await session.execute(
            select(Lead.stage, func.count(Lead.id)).group_by(Lead.stage)
        )
        return {stage: count for stage, count in result.all()}


async def get_recent_stats(days: int = 7) -> list[dict]:
    """Get stats for the last N days."""
    async with async_session() as session:
        result = await session.execute(
            select(DailyStats)
            .order_by(DailyStats.date.desc())
            .limit(days)
        )
        return [
            {
                "date": s.date,
                "emails_received": s.emails_received,
                "emails_sent": s.emails_sent,
                "new_leads": s.new_leads,
                "handoffs": s.leads_handoff,
            }
            for s in result.scalars()
        ]


async def get_ab_test_stats() -> dict:
    """Get A/B test win rates."""
    async with async_session() as session:
        total = await session.execute(
            select(func.count(ABTestResult.id)).where(ABTestResult.got_reply == True)
        )
        a_wins = await session.execute(
            select(func.count(ABTestResult.id)).where(
                ABTestResult.got_reply == True,
                ABTestResult.sent_variant == "A",
            )
        )
        b_wins = await session.execute(
            select(func.count(ABTestResult.id)).where(
                ABTestResult.got_reply == True,
                ABTestResult.sent_variant == "B",
            )
        )
        return {
            "total_replies": total.scalar() or 0,
            "variant_a_replies": a_wins.scalar() or 0,
            "variant_b_replies": b_wins.scalar() or 0,
        }


async def generate_summary_text() -> str:
    """Generate daily summary text for Telegram notification."""
    config = get_config()
    funnel = await get_funnel_metrics()
    stats = await get_recent_stats(1)

    today_stats = stats[0] if stats else {}

    lines = [
        f"<b>Дневная сводка — {config.business.name}</b>\n",
        f"Получено писем: {today_stats.get('emails_received', 0)}",
        f"Отправлено писем: {today_stats.get('emails_sent', 0)}",
        f"Новых лидов: {today_stats.get('new_leads', 0)}",
        f"Передано менеджеру: {today_stats.get('handoffs', 0)}",
        "\n<b>Воронка:</b>",
    ]
    for stage, count in sorted(funnel.items()):
        lines.append(f"  {stage}: {count}")

    return "\n".join(lines)
