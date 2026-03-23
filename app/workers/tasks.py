"""ARQ worker tasks — async background jobs.

Tasks:
- process_email: Process incoming email (with retry)
- send_delayed_reply: Send a reply after human-like delay
- enrich_lead: Fetch company info for a new lead
- compute_daily_stats: Aggregate daily analytics
- send_daily_summary: Send summary to manager
- process_delayed_queue: Poll Redis for ready-to-send replies
"""

import logging
import random

from arq import cron

logger = logging.getLogger(__name__)


async def process_email(ctx: dict, message_id: str, account_email: str = "") -> None:
    """Process a single email message (retryable via ARQ)."""
    from app.routers.gmail_webhook import _process_message
    try:
        await _process_message(message_id)
        logger.info("Processed email %s", message_id)
    except Exception as e:
        logger.error("Failed to process email %s: %s", message_id, e)
        raise  # ARQ will retry


async def send_delayed_reply(
    ctx: dict,
    to: str,
    subject: str,
    body_html: str,
    thread_id: str,
    message_id: str,
    references: str = "",
    attachment_path: str | None = None,
) -> None:
    """Send an email reply (called after delay)."""
    from app.config import settings
    from app.services import gmail_service
    from app.services.redis_service import check_rate_limit, increment_send_count

    account = settings.GOOGLE_DELEGATED_EMAIL
    if not await check_rate_limit(account, settings.GMAIL_DAILY_SEND_LIMIT):
        logger.warning("Rate limit reached for %s, dropping reply to %s", account, to)
        return

    gmail_service.send_reply(
        to=to,
        subject=subject,
        body_html=body_html,
        thread_id=thread_id,
        message_id=message_id,
        references=references,
        attachment_path=attachment_path,
    )
    await increment_send_count(account)
    logger.info("Sent delayed reply to %s", to)


async def enrich_lead(ctx: dict, lead_id: int) -> None:
    """Enrich a lead with company data from email domain."""
    from app.services.enrichment_service import enrich_lead_data
    try:
        await enrich_lead_data(lead_id)
    except Exception as e:
        logger.error("Enrichment failed for lead %d: %s", lead_id, e)


async def compute_daily_stats(ctx: dict) -> None:
    """Aggregate daily stats for the dashboard."""
    from app.services.analytics_service import compute_stats
    await compute_stats()
    logger.info("Daily stats computed")


async def send_daily_summary(ctx: dict) -> None:
    """Send daily summary to manager via Telegram."""
    from app.services.analytics_service import generate_summary_text
    from app.services import telegram_service
    text = await generate_summary_text()
    await telegram_service.notify_manager_daily_summary(text)
    logger.info("Daily summary sent")


async def process_delayed_queue(ctx: dict) -> None:
    """Poll Redis for replies whose delay has passed and send them."""
    from app.services.redis_service import get_ready_replies
    replies = await get_ready_replies()
    for payload in replies:
        try:
            await send_delayed_reply(ctx, **payload)
        except Exception as e:
            logger.error("Failed to send delayed reply: %s", e)


class WorkerSettings:
    """ARQ worker configuration."""
    functions = [
        process_email,
        send_delayed_reply,
        enrich_lead,
        compute_daily_stats,
        send_daily_summary,
        process_delayed_queue,
    ]
    cron_jobs = [
        cron(process_delayed_queue, second={0, 15, 30, 45}),  # every 15 seconds
        cron(compute_daily_stats, hour={23}, minute={55}),
        cron(send_daily_summary, hour={18}, minute={0}),
    ]
    max_jobs = 10
    job_timeout = 300
    max_tries = 3
    retry_delay = 60  # 1 min between retries

    @staticmethod
    async def on_startup(ctx: dict) -> None:
        from app.config import settings
        import redis.asyncio as aioredis
        ctx["redis"] = aioredis.from_url(settings.REDIS_URL)

    @staticmethod
    async def on_shutdown(ctx: dict) -> None:
        if "redis" in ctx:
            await ctx["redis"].close()

    redis_settings = None  # set dynamically from REDIS_URL
