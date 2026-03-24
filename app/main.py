"""FastAPI application — full-featured Email Agent."""

import logging

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.config_loader import init_config
from app.funnel.pipeline import load_transitions
from app.middleware import APIRateLimitMiddleware, RequestIdMiddleware
from app.routers import admin, analytics, avito_webhook, gmail_webhook, health, telegram_webhook

# ---- Structured logging ----
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer() if settings.DEBUG else structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        logging.DEBUG if settings.DEBUG else logging.INFO
    ),
)

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Email Agent", version="2.0.0")

# ---- CORS ----
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Middleware ----
app.add_middleware(RequestIdMiddleware)
app.add_middleware(APIRateLimitMiddleware)

# ---- Sentry ----
if settings.SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    sentry_sdk.init(dsn=settings.SENTRY_DSN, integrations=[FastApiIntegration()])
    logger.info("Sentry initialized")

# ---- Prometheus ----
if settings.PROMETHEUS_ENABLED:
    from prometheus_fastapi_instrumentator import Instrumentator
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# ---- Routers ----
app.include_router(health.router, tags=["health"])
app.include_router(gmail_webhook.router, tags=["gmail"])
app.include_router(telegram_webhook.router, tags=["telegram"])
app.include_router(admin.router)
app.include_router(analytics.router)
if settings.AVITO_ENABLED:
    app.include_router(avito_webhook.router)


@app.on_event("startup")
async def on_startup():
    logger.info("Email Agent starting up...")

    # 1. Load business config
    try:
        config = init_config(settings.BUSINESS_CONFIG_PATH)
        load_transitions()
        logger.info("Business config: %s (%s)", config.business.name, config.business.niche)
    except Exception as e:
        logger.error("Failed to load business config: %s", e)
        raise

    # 2. Init database
    try:
        from app.db.session import init_db
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.warning("Database init failed (non-fatal): %s", e)

    # 3. Init Redis
    try:
        from app.services.redis_service import get_redis
        await get_redis()
        logger.info("Redis connected")
    except Exception as e:
        logger.warning("Redis unavailable (non-fatal): %s", e)

    # 4. Load multi-account config
    from app.services.account_manager import load_accounts
    load_accounts()

    # 4b. Load Avito config (if enabled)
    if settings.AVITO_ENABLED:
        from app.funnel.avito_pipeline import load_avito_config
        load_avito_config()
        logger.info("Avito integration enabled")

    # 5. Register Gmail push notifications
    try:
        from app.services import gmail_service
        gmail_service.register_watch()
        logger.info("Gmail watch registered")
    except Exception as e:
        logger.error("Failed to register Gmail watch: %s", e)

    # 6. Set Telegram webhook with secret token
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
    try:
        from app.services.redis_service import close_redis
        await close_redis()
    except Exception:
        pass
