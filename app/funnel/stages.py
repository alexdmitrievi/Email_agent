"""
Dynamic funnel stages and categories — loaded from business config.

No more hardcoded Enums. Stages and categories are strings
defined in configs/business.yaml.
"""

from app.config_loader import get_config

# Terminal stages where AI does NOT auto-reply
TERMINAL_STAGES = {"HANDOFF_TO_MANAGER", "ORDER", "NOT_INTERESTED", "ARCHIVED"}


def get_stage_ids() -> set[str]:
    """Return all stage IDs from the loaded config."""
    config = get_config()
    return {s.id for s in config.funnel.stages}


def get_category_ids() -> set[str]:
    """Return all category IDs from the loaded config."""
    config = get_config()
    return {c.id for c in config.funnel.categories}


def is_terminal(stage: str) -> bool:
    """Check if a stage is terminal (no auto-reply)."""
    return stage in TERMINAL_STAGES


def get_stage_attachment(stage: str) -> str | None:
    """Get the attachment path for a stage, if any."""
    config = get_config()
    for s in config.funnel.stages:
        if s.id == stage:
            return s.attachment
    return None


def get_follow_up_eligible_stages() -> list[str]:
    """Return stage IDs eligible for follow-up emails."""
    config = get_config()
    return config.funnel.follow_up_eligible_stages
