"""Avito worker recruitment pipeline — separate from email pipeline."""

import logging
from typing import Optional

from app.config import settings
from app.config_loader import BusinessConfig, load_business_config

logger = logging.getLogger(__name__)

_avito_config: Optional[BusinessConfig] = None
_avito_transitions: dict[tuple[str, str], tuple[str, str]] = {}

TERMINAL_STAGES = {"REGISTERED", "NOT_INTERESTED", "ARCHIVED"}


def load_avito_config() -> None:
    """Load the Avito worker funnel config. Called at startup if AVITO_ENABLED."""
    global _avito_config, _avito_transitions

    if not settings.AVITO_ENABLED:
        logger.info("Avito disabled, skipping config load")
        return

    _avito_config = load_business_config(settings.AVITO_FUNNEL_CONFIG_PATH)
    _avito_transitions = {}
    for t in _avito_config.funnel.transitions:
        key = (t.from_stage, t.on)
        _avito_transitions[key] = (t.to, t.action)

    logger.info(
        "Loaded Avito funnel: %s (%d transitions)",
        _avito_config.business.name,
        len(_avito_transitions),
    )


def get_avito_config() -> BusinessConfig:
    """Get the Avito config for use as config_override in AI functions."""
    if _avito_config is None:
        raise RuntimeError("Avito config not loaded — is AVITO_ENABLED=true?")
    return _avito_config


def get_avito_transition(current_stage: str, category: str) -> tuple[str, str]:
    """Get the next stage and action for the Avito funnel."""
    key = (current_stage, category)
    if key in _avito_transitions:
        return _avito_transitions[key]
    logger.warning("No Avito transition for %s, defaulting to continue_discussion", key)
    return (current_stage, "continue_discussion")


def is_terminal(stage: str) -> bool:
    """Check if a stage is terminal (no auto-reply)."""
    return stage in TERMINAL_STAGES
