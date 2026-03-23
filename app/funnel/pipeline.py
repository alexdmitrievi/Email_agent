import logging

from app.funnel.stages import ReplyCategory, Stage

logger = logging.getLogger(__name__)

# Transition table: (current_stage, reply_category) → (new_stage, action_name)
TRANSITIONS: dict[tuple[str, str], tuple[str, str]] = {
    # New reply from cold email
    (Stage.NEW_REPLY, ReplyCategory.INTERESTED): (Stage.INTERESTED, "reply_with_interest"),
    (Stage.NEW_REPLY, ReplyCategory.QUESTION): (Stage.INTERESTED, "reply_with_interest"),
    (Stage.NEW_REPLY, ReplyCategory.NOT_INTERESTED): (Stage.NOT_INTERESTED, "reply_not_interested"),
    (Stage.NEW_REPLY, ReplyCategory.SPAM): (Stage.ARCHIVED, "ignore"),
    (Stage.NEW_REPLY, ReplyCategory.OUT_OF_OFFICE): (Stage.NEW_REPLY, "ignore"),
    (Stage.NEW_REPLY, ReplyCategory.READY_TO_ORDER): (Stage.HANDOFF_TO_MANAGER, "handoff_to_manager"),
    # Interested stage
    (Stage.INTERESTED, ReplyCategory.INTERESTED): (Stage.PORTFOLIO_SENT, "send_portfolio"),
    (Stage.INTERESTED, ReplyCategory.QUESTION): (Stage.PORTFOLIO_SENT, "send_portfolio"),
    (Stage.INTERESTED, ReplyCategory.NOT_INTERESTED): (Stage.NOT_INTERESTED, "reply_not_interested"),
    (Stage.INTERESTED, ReplyCategory.READY_TO_ORDER): (Stage.HANDOFF_TO_MANAGER, "handoff_to_manager"),
    # Portfolio sent
    (Stage.PORTFOLIO_SENT, ReplyCategory.INTERESTED): (Stage.IN_DISCUSSION, "continue_discussion"),
    (Stage.PORTFOLIO_SENT, ReplyCategory.QUESTION): (Stage.IN_DISCUSSION, "continue_discussion"),
    (Stage.PORTFOLIO_SENT, ReplyCategory.NOT_INTERESTED): (Stage.NOT_INTERESTED, "reply_not_interested"),
    (Stage.PORTFOLIO_SENT, ReplyCategory.READY_TO_ORDER): (Stage.HANDOFF_TO_MANAGER, "handoff_to_manager"),
    # In discussion
    (Stage.IN_DISCUSSION, ReplyCategory.INTERESTED): (Stage.IN_DISCUSSION, "continue_discussion"),
    (Stage.IN_DISCUSSION, ReplyCategory.QUESTION): (Stage.IN_DISCUSSION, "continue_discussion"),
    (Stage.IN_DISCUSSION, ReplyCategory.NOT_INTERESTED): (Stage.NOT_INTERESTED, "reply_not_interested"),
    (Stage.IN_DISCUSSION, ReplyCategory.READY_TO_ORDER): (Stage.HANDOFF_TO_MANAGER, "handoff_to_manager"),
}


def get_transition(current_stage: str, category: str) -> tuple[str, str]:
    """Get the next stage and action for a given stage+category combo."""
    key = (current_stage, category)
    if key in TRANSITIONS:
        return TRANSITIONS[key]

    # Default: stay in current stage, just continue discussion
    logger.warning("No transition for %s, defaulting to continue_discussion", key)
    return (current_stage, "continue_discussion")
