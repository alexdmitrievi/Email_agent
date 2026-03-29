from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # OpenAI
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4o"

    # Gmail / Google
    GOOGLE_SERVICE_ACCOUNT_FILE: str = "credentials/service_account.json"
    GOOGLE_DELEGATED_EMAIL: str
    GOOGLE_PUBSUB_TOPIC: str
    GOOGLE_PUBSUB_VERIFICATION_TOKEN: str = ""

    # Google Sheets
    GOOGLE_SHEET_ID: str

    # Telegram
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_MANAGER_CHAT_ID: str
    TELEGRAM_BOT_LINK: str = ""

    # n8n
    N8N_API_URL: str = "http://localhost:5678/api/v1"
    N8N_API_KEY: str = ""

    # Company info (legacy fallback, overridden by business config)
    COMPANY_NAME: str = "Мебельная компания"
    COMPANY_PHONE: str = ""
    COMPANY_WEBSITE: str = ""

    # Funnel settings (legacy fallback)
    FOLLOW_UP_DAYS: int = 3
    MAX_FOLLOW_UPS: int = 2

    # Business config
    BUSINESS_CONFIG_PATH: str = "configs/business.yaml"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/agent.db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Rate limiting
    GMAIL_DAILY_SEND_LIMIT: int = 230  # safety margin below 250

    # Response delay (seconds) — makes replies look human
    REPLY_DELAY_MIN: int = 120   # 2 min
    REPLY_DELAY_MAX: int = 900   # 15 min

    # Lead enrichment
    ENRICHMENT_ENABLED: bool = False

    # Observability
    SENTRY_DSN: str = ""
    PROMETHEUS_ENABLED: bool = True

    # Multi-account (path to accounts YAML, empty = single account)
    ACCOUNTS_CONFIG_PATH: str = ""

    # Telegram webhook secret (X-Telegram-Bot-Api-Secret-Token)
    TELEGRAM_WEBHOOK_SECRET: str = ""

    # Avito
    AVITO_ENABLED: bool = False
    AVITO_CLIENT_ID: str = ""
    AVITO_CLIENT_SECRET: str = ""
    AVITO_USER_ID: str = ""
    AVITO_POLL_INTERVAL: int = 60
    AVITO_FUNNEL_CONFIG_PATH: str = "configs/avito_worker_funnel.yaml"

    # Telethon (MTProto — реальный аккаунт Telegram, не бот)
    TELETHON_ENABLED: bool = False
    TELETHON_API_ID: int = 0
    TELETHON_API_HASH: str = ""
    TELETHON_PHONE: str = ""
    TELETHON_SESSION_PATH: str = "credentials/telegram.session"

    # Green API (WhatsApp через реальный номер)
    GREENAPI_ENABLED: bool = False
    GREENAPI_INSTANCE_ID: str = ""
    GREENAPI_TOKEN: str = ""
    GREENAPI_WEBHOOK_TOKEN: str = ""  # для валидации входящих webhook

    # Supabase (real-time CRM + journey tracking)
    SUPABASE_ENABLED: bool = False
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""

    # Roles
    ROLES_CONFIG_PATH: str = "configs/roles"
    DEFAULT_ROLE: str = "sales_manager"

    # Admin
    ADMIN_SECRET: str = ""  # Bearer token for admin endpoints

    # App
    APP_BASE_URL: str = "http://localhost:8000"
    DEBUG: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
