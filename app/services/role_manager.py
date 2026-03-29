"""
Role Manager — динамическое управление ролями/персонами AI-агента.

Загружает YAML-конфиги ролей из configs/roles/ при старте.
Позволяет менять роль агента на лету без перезапуска.

Роли определяют:
  - Личность и тон общения
  - Тактики разговора (mirror, rapport, urgency...)
  - Обработку возражений
  - Признаки закрытия сделки
  - Триггеры передачи менеджеру
"""

import logging
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic models для конфига роли
# ---------------------------------------------------------------------------

class Persona(BaseModel):
    tone: str = "professional_friendly"
    expertise: str = ""
    focus: str = ""
    language_style: str = ""


class ConversationTactic(BaseModel):
    name: str
    description: str = ""


class RoleConfig(BaseModel):
    id: str
    name: str
    description: str = ""
    persona: Persona = Persona()
    system_context: str = ""
    conversation_tactics: list[ConversationTactic] = []
    objection_responses: dict[str, str] = {}
    closing_indicators: list[str] = []
    handoff_triggers: list[str] = []
    primary_channels: list[str] = []


# ---------------------------------------------------------------------------
# Role Manager singleton
# ---------------------------------------------------------------------------

class RoleManager:
    """Менеджер ролей — загружает, хранит, выдаёт по запросу."""

    def __init__(self):
        self._roles: dict[str, RoleConfig] = {}

    def load_all_roles(self, roles_dir: str) -> int:
        """
        Загрузить все YAML-файлы из директории ролей.
        Возвращает количество загруженных ролей.
        """
        path = Path(roles_dir)
        if not path.exists():
            logger.warning("Roles directory not found: %s", roles_dir)
            return 0

        loaded = 0
        for yaml_file in path.glob("*.yaml"):
            try:
                with open(yaml_file, encoding="utf-8") as f:
                    raw = yaml.safe_load(f)
                role = RoleConfig(**raw)
                self._roles[role.id] = role
                logger.info("Loaded role: %s (%s)", role.id, role.name)
                loaded += 1
            except Exception as e:
                logger.error("Failed to load role from %s: %s", yaml_file.name, e)

        if not self._roles:
            logger.warning("No roles loaded — using built-in default")
            self._roles["sales_manager"] = _default_sales_manager_role()

        return loaded

    def get_role(self, role_id: str) -> RoleConfig:
        """
        Получить конфиг роли по ID.
        Если роль не найдена — возвращает sales_manager или базовый дефолт.
        """
        if role_id in self._roles:
            return self._roles[role_id]
        logger.warning("Role '%s' not found, falling back to sales_manager", role_id)
        return self._roles.get("sales_manager", _default_sales_manager_role())

    def list_roles(self) -> list[dict]:
        """Список доступных ролей (id + name + description)."""
        return [
            {"id": r.id, "name": r.name, "description": r.description[:80]}
            for r in self._roles.values()
        ]

    def assign_role_for_source(self, channel: str, lead_data: dict | None = None) -> str:
        """
        Автоматически выбрать роль исходя из канала и данных лида.

        Логика:
        - avito → recruiter (привлечение исполнителей)
        - email cold outreach → sales_manager
        - telegram/whatsapp с жалобой → support_agent
        - email inbound запрос с детальными вопросами → consultant
        """
        lead_data = lead_data or {}
        stage = lead_data.get("stage", "")

        # Avito — всегда рекрутёр (там живут исполнители)
        if channel == "avito":
            return "recruiter"

        # Если лид в поздней стадии (уже продажа идёт) → support если проблема
        if stage in ("HANDOFF_TO_MANAGER", "ORDER") and lead_data.get("is_complaint"):
            return "support_agent"

        # Email / Telegram / WhatsApp → продажи
        if channel in ("email", "telegram", "telegram_mtproto", "whatsapp"):
            return "sales_manager"

        return "sales_manager"

    def get_objection_response(self, role_id: str, objection_type: str) -> Optional[str]:
        """Получить заготовленный ответ на возражение для роли."""
        role = self.get_role(role_id)
        return role.objection_responses.get(objection_type)

    def is_closing_signal(self, role_id: str, text: str) -> bool:
        """Проверить есть ли в тексте признаки готовности к закрытию."""
        role = self.get_role(role_id)
        text_lower = text.lower()
        return any(indicator in text_lower for indicator in role.closing_indicators)

    def is_handoff_trigger(self, role_id: str, text: str) -> bool:
        """Проверить есть ли в тексте триггер передачи менеджеру."""
        role = self.get_role(role_id)
        text_lower = text.lower()
        return any(trigger in text_lower for trigger in role.handoff_triggers)


# ---------------------------------------------------------------------------
# Fallback дефолтная роль (если файлы не загружены)
# ---------------------------------------------------------------------------

def _default_sales_manager_role() -> RoleConfig:
    return RoleConfig(
        id="sales_manager",
        name="Менеджер по продажам",
        description="Профессиональный B2B менеджер по продажам",
        persona=Persona(
            tone="professional_friendly",
            expertise="sales_negotiation",
            focus="closing_deals",
            language_style="Уверенно и доброжелательно, с акцентом на выгоду клиента.",
        ),
        system_context=(
            "Ты — опытный менеджер по продажам компании {business_name}. "
            "Выявляй потребности, работай с возражениями, предлагай следующий шаг."
        ),
        closing_indicators=["интересно", "сколько стоит", "как заказать", "пришлите"],
        handoff_triggers=["договор", "оплатить", "встреча", "звонок"],
        primary_channels=["email", "telegram", "whatsapp"],
    )


# ---------------------------------------------------------------------------
# Глобальный синглтон
# ---------------------------------------------------------------------------

role_manager = RoleManager()
