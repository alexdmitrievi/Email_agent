import logging

from fastapi import FastAPI

from app.config import settings
from app.routers import gmail_webhook, health, telegram_webhook

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Email Agent", version="1.0.0")

app.include_router(health.router, tags=["health"])
app.include_router(gmail_webhook.router, tags=["gmail"])
app.include_router(telegram_webhook.router, tags=["telegram"])


@app.on_event("startup")
async def on_startup():
    logger.info("Email Agent starting up...")

    # Register Gmail push notifications
    try:
        from app.services import gmail_service

        gmail_service.register_watch()
        logger.info("Gmail watch registered")
    except Exception as e:
        logger.error("Failed to register Gmail watch: %s", e)

    # Set Telegram webhook
    try:
        from app.services import telegram_service

        webhook_url = f"{settings.APP_BASE_URL}/webhooks/telegram"
        await telegram_service.set_webhook(webhook_url)
        logger.info("Telegram webhook set to %s", webhook_url)
    except Exception as e:
        logger.error("Failed to set Telegram webhook: %s", e)


@app.on_event("shutdown")
async def on_shutdown():
    logger.info("Email Agent shutting down...")
