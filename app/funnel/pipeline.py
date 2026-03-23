"""
Config-driven state machine for the sales funnel.

Transitions are loaded from business config YAML.
"""

import logging

from app.config_loader import get_config

logger = logging.getLogger(__name__)

# Built at startup from config
_transitions: dict[tuple[str, str], tuple[str, str]] = {}


def load_transitions() -> None:
    """Build the transition lookup dict from the loaded config."""
    global _transitions
    config = get_config()
    _transitions = {}
    for t in config.funnel.transitions:
        key = (t.from_stage, t.on)
        _transitions[key] = (t.to, t.action)
    logger.info("Loaded %d funnel transitions", len(_transitions))


def get_transition(current_stage: str, category: str) -> tuple[str, str]:
    """Get the next stage and action for a given stage+category combo."""
    key = (current_stage, category)
    if key in _transitions:
        return _transitions[key]

    # Default: stay in current stage, just continue discussion
    logger.warning("No transition for %s, defaulting to continue_discussion", key)
    return (current_stage, "continue_discussion")
