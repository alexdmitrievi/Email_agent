"""
Business configuration loader.

Loads a YAML config file and validates it into Pydantic models.
Separates business logic (YAML) from infrastructure secrets (.env).
"""

import logging
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic models for YAML config
# ---------------------------------------------------------------------------

class BusinessInfo(BaseModel):
    name: str
    niche: str
    language: str = "ru"
    website: str = ""
    phone: str = ""
    description: str


class ProductDetail(BaseModel):
    name: str
    description: str


class ProductsConfig(BaseModel):
    summary: str
    details: list[ProductDetail] = []
    pricing_policy: str = ""


class StageConfig(BaseModel):
    id: str
    label: str
    description: str = ""
    attachment: Optional[str] = None  # path to file to attach at this stage


class CategoryConfig(BaseModel):
    id: str
    description: str


class TransitionConfig(BaseModel):
    from_stage: str  # aliased from 'from' in YAML
    on: str
    to: str
    action: str


class FunnelConfig(BaseModel):
    stages: list[StageConfig]
    categories: list[CategoryConfig]
    transitions: list[TransitionConfig]
    follow_up_eligible_stages: list[str] = []


class FollowUpsConfig(BaseModel):
    delay_days: int = 3
    max_count: int = 2


class HandoffConfig(BaseModel):
    telegram_keywords: list[str] = []


class ToneConfig(BaseModel):
    formality: str = "semiformal"
    address: str = "Вы"
    max_sentences_email: int = 5
    max_sentences_telegram: int = 3
    sign_off_style: str = "professional"


class TelegramConfig(BaseModel):
    welcome_message: str = "Здравствуйте, {first_name}! Я — виртуальный помощник компании «{company_name}»."
    handoff_confirmation: str = "Сейчас подключу менеджера!"


class WorkingHours(BaseModel):
    start: str = "09:00"
    end: str = "18:00"


class CalendarConfig(BaseModel):
    enabled: bool = False
    calendar_id: str = "primary"
    slot_duration_minutes: int = 30
    working_hours: WorkingHours = WorkingHours()
    timezone: str = "Europe/Moscow"


class BusinessConfig(BaseModel):
    """Root model for the entire business YAML configuration."""
    business: BusinessInfo
    products: ProductsConfig
    funnel: FunnelConfig
    follow_ups: FollowUpsConfig = FollowUpsConfig()
    stage_instructions: dict[str, str] = {}
    handoff: HandoffConfig = HandoffConfig()
    tone: ToneConfig = ToneConfig()
    telegram: TelegramConfig = TelegramConfig()
    calendar: CalendarConfig = CalendarConfig()
    not_interested_reply: str = "Спасибо за ваш ответ! Хорошего дня!"

    @field_validator("funnel")
    @classmethod
    def validate_transitions(cls, funnel: FunnelConfig) -> FunnelConfig:
        """Ensure all transitions reference valid stages and categories."""
        stage_ids = {s.id for s in funnel.stages}
        category_ids = {c.id for c in funnel.categories}
        for t in funnel.transitions:
            if t.from_stage not in stage_ids:
                raise ValueError(f"Transition references unknown stage: '{t.from_stage}'")
            if t.to not in stage_ids:
                raise ValueError(f"Transition references unknown target stage: '{t.to}'")
            if t.on not in category_ids:
                raise ValueError(f"Transition references unknown category: '{t.on}'")
        for stage_id in funnel.follow_up_eligible_stages:
            if stage_id not in stage_ids:
                raise ValueError(f"follow_up_eligible_stages references unknown stage: '{stage_id}'")
        return funnel


# ---------------------------------------------------------------------------
# Global config singleton
# ---------------------------------------------------------------------------

_config: Optional[BusinessConfig] = None


def load_business_config(path: str) -> BusinessConfig:
    """Load and validate a business YAML config file."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Business config not found: {path}")

    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    # YAML uses 'from' as key (Python reserved word) — remap to 'from_stage'
    # YAML also parses 'on' as boolean True — remap to string key 'on'
    if "funnel" in raw and "transitions" in raw["funnel"]:
        for t in raw["funnel"]["transitions"]:
            if "from" in t:
                t["from_stage"] = t.pop("from")
            if True in t:
                t["on"] = t.pop(True)
            if False in t:
                t["on"] = t.pop(False)

    config = BusinessConfig(**raw)
    logger.info("Loaded business config: %s (%s)", config.business.name, config.business.niche)
    return config


def get_config() -> BusinessConfig:
    """Get the current business config (must be loaded first)."""
    if _config is None:
        raise RuntimeError("Business config not loaded. Call load_business_config() first.")
    return _config


def init_config(path: str) -> BusinessConfig:
    """Load config and set as global singleton."""
    global _config
    _config = load_business_config(path)
    return _config
