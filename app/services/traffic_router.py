"""
Traffic Router — определяет источник трафика и адаптирует поведение агента.

Разные источники трафика → разные стратегии общения:
  - Холодное email → формально, деловой тон, структурированное КП
  - Входящий Telegram → полуформально, быстро, conversational
  - WhatsApp → максимально conversational, короткие сообщения
  - Avito листинг → практично, конкретные условия работы
  - Реферал → тепло, упомянуть кто порекомендовал

Traffic Source также влияет на:
  - Автовыбор роли (recruiter для Avito, sales_manager для email)
  - Параметры AI (max_tokens, temperature)
  - Стиль приветствия
"""

import logging
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class TrafficSource(str, Enum):
    """Источник трафика / канал привлечения."""
    COLD_EMAIL = "cold_email"          # Исходящий холодный email
    INBOUND_EMAIL = "inbound_email"    # Входящий email (клиент написал сам)
    TELEGRAM_ORGANIC = "telegram_organic"  # Нашёл в Telegram сам
    TELEGRAM_REFERRED = "telegram_referred"  # Пришёл по реферальной ссылке
    TELEGRAM_BOT = "telegram_bot"      # Через бот
    TELEGRAM_MTPROTO = "telegram_mtproto"  # Через личный аккаунт (Telethon)
    WHATSAPP_ORGANIC = "whatsapp_organic"  # Сам написал в WhatsApp
    AVITO_LISTING = "avito_listing"    # Откликнулся на Avito объявление
    AVITO_SEARCH = "avito_search"      # Нашёл через поиск Avito
    REFERRAL = "referral"              # Порекомендовали
    WEB_FORM = "web_form"              # Форма на сайте
    UNKNOWN = "unknown"


# Соответствие источника → лучшая роль
SOURCE_TO_ROLE: dict[TrafficSource, str] = {
    TrafficSource.COLD_EMAIL: "sales_manager",
    TrafficSource.INBOUND_EMAIL: "consultant",
    TrafficSource.TELEGRAM_ORGANIC: "sales_manager",
    TrafficSource.TELEGRAM_REFERRED: "sales_manager",
    TrafficSource.TELEGRAM_BOT: "sales_manager",
    TrafficSource.TELEGRAM_MTPROTO: "sales_manager",
    TrafficSource.WHATSAPP_ORGANIC: "sales_manager",
    TrafficSource.AVITO_LISTING: "recruiter",
    TrafficSource.AVITO_SEARCH: "recruiter",
    TrafficSource.REFERRAL: "consultant",
    TrafficSource.WEB_FORM: "consultant",
    TrafficSource.UNKNOWN: "sales_manager",
}

# Параметры AI по каналу
CHANNEL_AI_PARAMS: dict[str, dict[str, Any]] = {
    "email": {
        "max_tokens": 400,
        "temperature": 0.7,
        "max_sentences": 5,
        "formality": "formal",
    },
    "telegram": {
        "max_tokens": 200,
        "temperature": 0.8,
        "max_sentences": 3,
        "formality": "semiformal",
    },
    "telegram_mtproto": {
        "max_tokens": 200,
        "temperature": 0.8,
        "max_sentences": 3,
        "formality": "semiformal",
    },
    "whatsapp": {
        "max_tokens": 150,
        "temperature": 0.85,
        "max_sentences": 2,
        "formality": "casual",
    },
    "avito": {
        "max_tokens": 180,
        "temperature": 0.75,
        "max_sentences": 3,
        "formality": "casual",
    },
}


class TrafficRouterService:
    """Определяет источник трафика и возвращает контекст для агента."""

    def detect_source(self, channel: str, metadata: dict | None = None) -> TrafficSource:
        """
        Определить источник трафика.

        channel: email | telegram | telegram_mtproto | whatsapp | avito
        metadata: дополнительные данные (subject, first_message, utm_source, ...)
        """
        metadata = metadata or {}

        if channel == "avito":
            return TrafficSource.AVITO_LISTING

        if channel in ("telegram_mtproto",):
            return TrafficSource.TELEGRAM_MTPROTO

        if channel == "telegram":
            # Проверить есть ли referral-маркер в первом сообщении
            first_msg = metadata.get("first_message", "").lower()
            if any(kw in first_msg for kw in ["порекомендовали", "посоветовали", "от ", "рефер"]):
                return TrafficSource.TELEGRAM_REFERRED
            return TrafficSource.TELEGRAM_BOT

        if channel == "whatsapp":
            return TrafficSource.WHATSAPP_ORGANIC

        if channel == "email":
            # Определить холодный vs входящий по subject / from_address
            subject = metadata.get("subject", "").lower()
            # Признаки входящего: клиент пишет первым (нет нашей подписи в теле)
            is_first_contact = metadata.get("is_first_contact", False)
            if is_first_contact:
                return TrafficSource.INBOUND_EMAIL
            return TrafficSource.COLD_EMAIL

        return TrafficSource.UNKNOWN

    def get_role_for_source(self, source: TrafficSource) -> str:
        """Получить рекомендованную роль для данного источника трафика."""
        return SOURCE_TO_ROLE.get(source, "sales_manager")

    def get_ai_params(self, channel: str) -> dict[str, Any]:
        """Получить параметры AI (max_tokens, temperature, ...) для канала."""
        return CHANNEL_AI_PARAMS.get(channel, CHANNEL_AI_PARAMS["email"])

    def get_context_for_prompt(self, source: TrafficSource, channel: str, lead: dict) -> dict:
        """
        Собрать контекст для промпта с учётом источника трафика.

        Возвращает dict который вставляется в Jinja2-шаблон промпта.
        """
        ai_params = self.get_ai_params(channel)

        # Специфичные инструкции по источнику
        source_instructions = {
            TrafficSource.COLD_EMAIL: (
                "Это холодный email — клиент ранее не обращался. "
                "Будь структурированным и деловым. "
                "Не пиши длинно — максимум 4-5 предложений."
            ),
            TrafficSource.INBOUND_EMAIL: (
                "Клиент написал сам — это тёплый лид! "
                "Отвечай быстро и конкретно на его вопрос. "
                "Не нужно долго представляться."
            ),
            TrafficSource.WHATSAPP_ORGANIC: (
                "WhatsApp — максимально conversational. "
                "Короткие сообщения (2-3 предл.), как в живом чате. "
                "Можно использовать разговорный стиль."
            ),
            TrafficSource.AVITO_LISTING: (
                "Avito — человек ищет работу/подработку. "
                "Говори конкретно: условия, оплата, что нужно делать. "
                "Минимум воды — только факты."
            ),
            TrafficSource.TELEGRAM_REFERRED: (
                "Клиент пришёл по рекомендации — это тёплый лид. "
                "Упомяни что рады принять по рекомендации. "
                "Можно быть немного теплее и неформальнее."
            ),
            TrafficSource.TELEGRAM_MTPROTO: (
                "Общение в Telegram через личный аккаунт. "
                "Будь естественным и живым в общении. "
                "Не используй официальный 'бот-стиль'."
            ),
        }.get(source, "Отвечай профессионально и по существу.")

        return {
            "source": source.value,
            "channel": channel,
            "source_instructions": source_instructions,
            "max_sentences": ai_params["max_sentences"],
            "formality": ai_params["formality"],
            "is_warm_lead": source in (
                TrafficSource.INBOUND_EMAIL,
                TrafficSource.REFERRAL,
                TrafficSource.TELEGRAM_REFERRED,
                TrafficSource.WHATSAPP_ORGANIC,
            ),
            "is_recruiter_channel": source in (
                TrafficSource.AVITO_LISTING,
                TrafficSource.AVITO_SEARCH,
            ),
        }


# Глобальный синглтон
traffic_router = TrafficRouterService()
