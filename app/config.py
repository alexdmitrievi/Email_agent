from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # OpenAI
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4o"

    # Gmail / Google
    GOOGLE_SERVICE_ACCOUNT_FILE: str = "credentials/service_account.json"
    GOOGLE_DELEGATED_EMAIL: str  # email of the Workspace user to impersonate
    GOOGLE_PUBSUB_TOPIC: str  # e.g. projects/my-project/topics/gmail-push
    GOOGLE_PUBSUB_VERIFICATION_TOKEN: str = ""

    # Google Sheets
    GOOGLE_SHEET_ID: str

    # Telegram
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_MANAGER_CHAT_ID: str  # chat_id of the manager for handoff notifications
    TELEGRAM_BOT_LINK: str = ""  # e.g. https://t.me/your_bot

    # n8n
    N8N_API_URL: str = "http://localhost:5678/api/v1"
    N8N_API_KEY: str = ""

    # Company info (used in prompts and signature)
    COMPANY_NAME: str = "Мебельная компания"
    COMPANY_PHONE: str = ""
    COMPANY_WEBSITE: str = ""

    # Funnel settings
    FOLLOW_UP_DAYS: int = 3
    MAX_FOLLOW_UPS: int = 2

    # App
    APP_BASE_URL: str = "http://localhost:8000"
    DEBUG: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
